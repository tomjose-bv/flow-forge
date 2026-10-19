"""Run a recipe against the apps over HTTP.

The engine polls the trigger app's events feed from a cursor, applies the filter, and runs the
steps for each matching event. Write actions get an Idempotency-Key of
`<recipe>:<event id>:<step path>`, so replaying events never duplicates side effects.
429 and 5xx responses are retried with backoff; other errors fail that event and the engine
moves on to the next one.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, field
from typing import Any, Callable

from flow_forge.expr import ExprError, condition, evaluate, render
from flow_forge.recipe import Recipe, Step


class CallError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(f"{status}: {message}")
        self.status = status
        self.message = message


@dataclass
class Client:
    base_url: str
    keys: dict[str, str]
    max_retries: int = 3
    backoff: float = 0.1
    sleep: Callable[[float], None] = time.sleep
    calls: int = 0

    def _request(self, method: str, path: str, app: str, body: Any = None, idem: str | None = None) -> Any:
        headers = {"Content-Type": "application/json", "X-Api-Key": self.keys.get(app, "")}
        if idem:
            headers["Idempotency-Key"] = idem
        data = json.dumps(body).encode() if body is not None else None
        for attempt in range(self.max_retries + 1):
            self.calls += 1
            req = urllib.request.Request(self.base_url + path, data=data, headers=headers, method=method)
            try:
                with urllib.request.urlopen(req, timeout=10) as r:
                    return json.loads(r.read())
            except urllib.error.HTTPError as e:
                try:
                    msg = json.loads(e.read()).get("error", "")
                except ValueError:
                    msg = ""
                retryable = e.code == 429 or e.code >= 500
                if not retryable or attempt == self.max_retries:
                    raise CallError(e.code, msg) from None
                wait = float(e.headers.get("Retry-After") or self.backoff * 2 ** attempt)
                self.sleep(wait)
            except (urllib.error.URLError, TimeoutError) as e:
                if attempt == self.max_retries:
                    raise CallError(0, f"connection failed: {e}") from None
                self.sleep(self.backoff * 2 ** attempt)
        raise AssertionError("unreachable")  # pragma: no cover

    def call(self, app: str, action: str, inputs: dict[str, Any], idem: str | None = None) -> Any:
        return self._request("POST", f"/{app}/actions/{action}", app, {"inputs": inputs}, idem)["result"]

    def events(self, app: str, after: int) -> list[dict[str, Any]]:
        return self._request("GET", f"/{app}/events?after={after}", app)["events"]


@dataclass
class StepCall:
    step: str
    action: str
    status: str  # ok | skipped | failed
    error: str | None = None


@dataclass
class EventResult:
    event_id: int
    status: str  # ok | filtered | failed
    calls: list[StepCall] = field(default_factory=list)
    error: str | None = None


@dataclass
class RunLog:
    recipe: str
    cursor: int
    events: list[EventResult] = field(default_factory=list)

    def count(self, status: str) -> int:
        return sum(1 for e in self.events if e.status == status)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class _EventFailed(Exception):
    pass


def run(recipe: Recipe, client: Client, cursor: int = 0, max_events: int = 10_000) -> RunLog:
    log = RunLog(recipe.name, cursor)
    while len(log.events) < max_events:
        try:
            batch = client.events(recipe.trigger_app, log.cursor)
        except CallError as e:
            raise RuntimeError(f"cannot read {recipe.trigger_app} events: {e}") from None
        if not batch:
            break
        for ev in batch:
            log.cursor = ev["id"]
            if ev["type"] != recipe.trigger_event:
                continue
            log.events.append(_run_event(recipe, client, ev))
    return log


def _run_event(recipe: Recipe, client: Client, ev: dict[str, Any]) -> EventResult:
    res = EventResult(ev["id"], "ok")
    ctx = {"trigger": ev["data"], "event": {k: ev[k] for k in ("id", "type", "at")}, "steps": {}}
    try:
        if recipe.filter is not None and not condition(recipe.filter, ctx):
            res.status = "filtered"
            return res
    except ExprError as e:
        res.status, res.error = "failed", f"filter: {e}"
        return res
    try:
        _run_steps(recipe, client, recipe.steps, ctx, f"{recipe.name}:{ev['id']}", "", res)
    except _EventFailed as e:
        res.status, res.error = "failed", str(e)
    return res


def _run_steps(recipe, client, steps: list[Step], ctx, key_base: str, prefix: str, res: EventResult) -> None:
    for st in steps:
        path = f"{prefix}{st.id}"
        try:
            if st.if_ is not None and not condition(st.if_, ctx):
                ctx["steps"][st.id] = None
                res.calls.append(StepCall(path, st.action or "for_each", "skipped"))
                continue
            if st.for_each is not None:
                items = evaluate(st.for_each.strip().removeprefix("{{").removesuffix("}}"), ctx)
                if not isinstance(items, list):
                    raise _EventFailed(f"step {path}: for_each needs a list, got {type(items).__name__}")
                outputs = []
                for i, item in enumerate(items):
                    inner = {**ctx, "item": item, "index": i, "steps": dict(ctx["steps"])}
                    _run_steps(recipe, client, st.steps, inner, key_base, f"{path}[{i}].", res)
                    outputs.append({s.id: inner["steps"].get(s.id) for s in st.steps})
                ctx["steps"][st.id] = outputs
                continue
            inputs = render(st.inputs, ctx)
        except ExprError as e:
            res.calls.append(StepCall(path, st.action or "for_each", "failed", str(e)))
            raise _EventFailed(f"step {path}: {e}") from None
        app, _, action = st.action.partition(".")
        try:
            ctx["steps"][st.id] = client.call(app, action, inputs, f"{key_base}:{path}")
        except CallError as e:
            res.calls.append(StepCall(path, st.action, "failed", str(e)))
            raise _EventFailed(f"step {path}: {st.action} failed with {e}") from None
        res.calls.append(StepCall(path, st.action, "ok"))
