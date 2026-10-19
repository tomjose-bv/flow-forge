"""Evaluation harness: run a candidate recipe and a reference recipe on identical worlds and
compare their side effects.

Effects are objects created or changed in the apps, in a canonical form with generated ids
replaced by natural keys (a customer by email, an invoice by its customer's email and fields,
a message by channel and text), so the order in which objects were created does not matter.
Text compares case-insensitively with whitespace collapsed; amounts compare to the cent.
"""

from __future__ import annotations

import copy
import re
from collections import Counter
from dataclasses import asdict, dataclass, field
from typing import Any

from flow_forge.apps import App
from flow_forge.engine import Client, RunLog, run
from flow_forge.recipe import RecipeError, loads, validate
from flow_forge.server import AppServer
from flow_forge.task import Task, build_world

Effect = tuple


def _t(v: Any) -> Any:
    if isinstance(v, str):
        return re.sub(r"\s+", " ", v).strip().casefold()
    if isinstance(v, bool) or v is None:
        return v
    if isinstance(v, (int, float)):
        return round(float(v), 2)
    return repr(v)


def _snapshot(apps: dict[str, App]) -> dict[str, dict[str, dict[str, dict]]]:
    return {n: copy.deepcopy(a.collections) for n, a in apps.items()}


def effects(apps: dict[str, App], initial: dict[str, dict[str, dict[str, dict]]]) -> Counter:
    """Canonical created/changed objects relative to the `initial` snapshot."""
    out: Counter = Counter()
    billing = apps.get("billing")

    def cust_email(cid):
        c = billing.get("customers", cid) if billing else None
        return _t(c["email"]) if c else f"<unknown customer {cid}>"

    for app_name, app in apps.items():
        for coll, objs in app.collections.items():
            before = initial.get(app_name, {}).get(coll, {})
            for oid, obj in objs.items():
                if before.get(oid) == obj:
                    continue
                out[_canon(app_name, coll, obj, oid in before, cust_email)] += 1
    return out


def _canon(app: str, coll: str, o: dict, changed: bool, cust_email) -> Effect:
    if (app, coll) == ("billing", "customers"):
        return ("billing.customer", _t(o["email"]), _t(o["name"]))
    if (app, coll) == ("billing", "invoices"):
        return ("billing.invoice", cust_email(o["customer_id"]), _t(o["amount"]), o["currency"], _t(o.get("memo")),
                _t(o.get("external_ref")))
    if (app, coll) == ("chat", "messages"):
        return ("chat.message", o["channel"], _t(o["text"]))
    if (app, coll) == ("tickets", "tickets"):
        return ("tickets.ticket", _t(o["title"]), o["priority"], _t(o["requester_email"]), _t(o.get("description")))
    if (app, coll) == ("crm", "deals") and changed:
        return ("crm.deal_update", o["id"], o["stage"], _t(o.get("note")))
    items = tuple(sorted((k, _t(v)) for k, v in o.items() if k not in ("id", "updated_at")))
    return (f"{app}.{coll}", "changed" if changed else "created", items)


@dataclass
class Report:
    task: str
    valid: bool
    validation_errors: list[str]
    success: bool
    precision: float
    recall: float
    expected: int
    produced: int
    matched: int
    duplicates_on_replay: int
    events_ok: int
    events_filtered: int
    events_failed: int
    missing: list[str] = field(default_factory=list)  # up to 3 examples
    unexpected: list[str] = field(default_factory=list)  # up to 3 examples
    errors: list[str] = field(default_factory=list)  # up to 3 event errors
    api_calls: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def keys_for(apps: dict[str, App]) -> dict[str, str]:
    return {n: a.api_key for n, a in apps.items()}


def run_recipe(task: Task, recipe_text: str, replay: bool = False):
    """Build the task's world, run the recipe once (and optionally replay all events).

    Returns (apps, initial snapshot, RunLog, effects after first run, effects after replay, api calls).
    """
    recipe = loads(recipe_text)
    apps = build_world(task)
    initial = _snapshot(apps)
    with AppServer(apps) as srv:
        client = Client(srv.url, keys_for(apps), sleep=lambda s: None)
        log = run(recipe, client)
        first = effects(apps, initial)
        second = first
        if replay:
            run(recipe, client, cursor=0)
            second = effects(apps, initial)
    return apps, initial, log, first, second, client.calls


def _fmt(e: Effect) -> str:
    return " | ".join(str(x) for x in e)[:200]


def evaluate(task: Task, recipe_text: str, reference_text: str) -> Report:
    _, _, _, expected, _, _ = run_recipe(task, reference_text)
    try:
        recipe = loads(recipe_text)
        errors = validate(recipe, build_world(task))
    except RecipeError as e:
        errors = [str(e)]
    if errors:
        return Report(task.name, False, errors[:10], False, 0.0, 0.0, sum(expected.values()), 0, 0, 0, 0, 0, 0)
    _, _, log, got, replayed, calls = run_recipe(task, recipe_text, replay=True)
    matched = sum((got & expected).values())
    produced, exp_n = sum(got.values()), sum(expected.values())
    return Report(
        task=task.name,
        valid=True,
        validation_errors=[],
        success=got == expected and log.count("failed") == 0,
        precision=matched / produced if produced else (1.0 if exp_n == 0 else 0.0),
        recall=matched / exp_n if exp_n else 1.0,
        expected=exp_n,
        produced=produced,
        matched=matched,
        duplicates_on_replay=sum((replayed - got).values()),
        events_ok=log.count("ok"),
        events_filtered=log.count("filtered"),
        events_failed=log.count("failed"),
        missing=[_fmt(e) for e in list((expected - got).elements())[:3]],
        unexpected=[_fmt(e) for e in list((got - expected).elements())[:3]],
        errors=[f"event {e.event_id}: {e.error}" for e in log.events if e.error][:3],
        api_calls=calls,
    )
