"""Recipe format and validation.

    name: won_deal_invoice
    trigger:
      app: crm
      event: deal.stage_changed
      filter: "trigger.deal.stage == 'won'"      # optional; events that fail it are ignored
    steps:
      - id: contact
        action: crm.get_contact
        inputs: {id: "{{trigger.deal.contact_id}}"}
      - id: new_customer
        if: "steps.customer is null"             # optional; a skipped step's output is null
        action: billing.create_customer
        inputs: {name: "{{steps.contact.name}}", email: "{{steps.contact.email}}"}
      - id: notify_each
        for_each: "trigger.deal.tags"            # runs its steps once per item, as `item`
        steps:
          - id: post
            action: chat.post_message
            inputs: {channel: sales, text: "tag {{item}}"}

Expression context: `trigger` (the event's data), `event` (id, type, at), `steps.<id>` (outputs
of earlier steps) and, inside for_each, `item` and `index`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from flow_forge.apps import App, TYPES
from flow_forge.expr import ExprError, check, expressions

ID = re.compile(r"^[a-z_][a-z0-9_]*$")
STEP_REF = re.compile(r"\bsteps\.([A-Za-z_]\w*)")


class RecipeError(ValueError):
    pass


@dataclass
class Step:
    id: str
    action: str | None = None
    inputs: dict[str, Any] = field(default_factory=dict)
    if_: str | None = None
    for_each: str | None = None
    steps: list["Step"] = field(default_factory=list)


@dataclass
class Recipe:
    name: str
    trigger_app: str
    trigger_event: str
    filter: str | None
    steps: list[Step]


def _step(raw: Any, where: str) -> Step:
    if not isinstance(raw, dict):
        raise RecipeError(f"{where}: a step must be a mapping")
    known = {"id", "action", "inputs", "if", "for_each", "steps"}
    unknown = set(raw) - known
    if unknown:
        raise RecipeError(f"{where}: unknown keys {sorted(unknown)} (allowed: {sorted(known)})")
    if "id" not in raw:
        raise RecipeError(f"{where}: step needs an id")
    if ("action" in raw) == ("for_each" in raw):
        raise RecipeError(f"{where} ({raw['id']}): a step needs exactly one of 'action' or 'for_each'")
    if "for_each" in raw and not isinstance(raw.get("steps"), list):
        raise RecipeError(f"{where} ({raw['id']}): for_each needs a 'steps' list")
    if "action" in raw and "steps" in raw:
        raise RecipeError(f"{where} ({raw['id']}): only for_each steps can have 'steps'")
    inputs = raw.get("inputs") or {}
    if not isinstance(inputs, dict):
        raise RecipeError(f"{where} ({raw['id']}): inputs must be a mapping")
    return Step(
        id=str(raw["id"]),
        action=raw.get("action"),
        inputs=inputs,
        if_=raw.get("if"),
        for_each=raw.get("for_each"),
        steps=[_step(s, f"{where}.steps[{i}]") for i, s in enumerate(raw.get("steps") or [])],
    )


def parse(data: Any) -> Recipe:
    if not isinstance(data, dict):
        raise RecipeError("recipe must be a mapping")
    for key in ("name", "trigger", "steps"):
        if key not in data:
            raise RecipeError(f"missing required key: {key}")
    unknown = set(data) - {"name", "trigger", "steps", "description"}
    if unknown:
        raise RecipeError(f"unknown keys: {sorted(unknown)}")
    trig = data["trigger"]
    if not isinstance(trig, dict) or "app" not in trig or "event" not in trig:
        raise RecipeError("trigger needs 'app' and 'event'")
    if set(trig) - {"app", "event", "filter"}:
        raise RecipeError(f"trigger: unknown keys {sorted(set(trig) - {'app', 'event', 'filter'})}")
    if not isinstance(data["steps"], list) or not data["steps"]:
        raise RecipeError("steps must be a non-empty list")
    return Recipe(
        name=str(data["name"]),
        trigger_app=str(trig["app"]),
        trigger_event=str(trig["event"]),
        filter=trig.get("filter"),
        steps=[_step(s, f"steps[{i}]") for i, s in enumerate(data["steps"])],
    )


def loads(text: str) -> Recipe:
    import yaml

    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as e:
        raise RecipeError(f"invalid YAML: {e}") from None
    return parse(data)


def _strip(src: str) -> str:
    m = re.match(r"^\s*\{\{(.*)\}\}\s*$", src, re.DOTALL)
    return m.group(1) if m else src


def validate(recipe: Recipe, apps: dict[str, App]) -> list[str]:
    """Static checks against the app definitions. Returns readable errors (empty = valid)."""
    errors: list[str] = []
    app = apps.get(recipe.trigger_app)
    if app is None:
        errors.append(f"trigger: unknown app {recipe.trigger_app!r}; apps: {sorted(apps)}")
    elif recipe.trigger_event not in app.triggers:
        errors.append(f"trigger: {recipe.trigger_app} has no event {recipe.trigger_event!r}; "
                      f"events: {sorted(app.triggers)}")
    if recipe.filter is not None:
        errors += _check_expr("trigger.filter", _strip(str(recipe.filter)), set(), False)
    seen: set[str] = set()
    _validate_steps(recipe.steps, apps, seen, errors, in_loop=False)
    return errors


def _check_expr(where: str, src: str, defined: set[str], in_loop: bool) -> list[str]:
    errs = []
    try:
        check(src)
    except ExprError as e:
        return [f"{where}: {e}"]
    for ref in STEP_REF.findall(src):
        if ref not in defined:
            errs.append(f"{where}: refers to step {ref!r}, which is not defined before this point")
    if not in_loop and re.search(r"\b(item|index)\b(?!\s*:)", re.sub(r"'[^']*'|\"[^\"]*\"", "", src)):
        errs.append(f"{where}: 'item'/'index' can only be used inside for_each")
    return errs


def _validate_steps(steps: list[Step], apps, defined: set[str], errors: list[str], in_loop: bool) -> None:
    for st in steps:
        where = f"step {st.id}"
        if not ID.match(st.id):
            errors.append(f"{where}: id must be lowercase letters, digits and _")
        if st.id in defined:
            errors.append(f"{where}: duplicate step id")
        if st.if_ is not None:
            errors += _check_expr(f"{where}.if", _strip(str(st.if_)), defined, in_loop)
        if st.for_each is not None:
            errors += _check_expr(f"{where}.for_each", _strip(str(st.for_each)), defined, in_loop)
            _validate_steps(st.steps, apps, defined, errors, in_loop=True)
            defined.add(st.id)
            continue
        app_name, _, action = str(st.action).partition(".")
        app = apps.get(app_name)
        if app is None or not action:
            errors.append(f"{where}: action must be '<app>.<action>' with app in {sorted(apps)}, got {st.action!r}")
        elif action not in app.actions:
            errors.append(f"{where}: {app_name} has no action {action!r}; actions: {sorted(app.actions)}")
        else:
            spec = app.actions[action]
            for name in st.inputs:
                if name not in spec.inputs:
                    errors.append(f"{where}: {st.action} has no input {name!r}; inputs: {sorted(spec.inputs)}")
            for name, p in spec.inputs.items():
                if p.required and name not in st.inputs:
                    errors.append(f"{where}: {st.action} needs input {name!r} ({p.type})")
                v = st.inputs.get(name)
                if name in st.inputs and not expressions(v):
                    ok = v is None or (isinstance(v, TYPES[p.type]) and not (p.type != "boolean" and isinstance(v, bool)))
                    if not ok:
                        errors.append(f"{where}: input {name!r} must be {p.type}, got {v!r}")
                    elif p.enum and v not in p.enum:
                        errors.append(f"{where}: input {name!r} must be one of {list(p.enum)}, got {v!r}")
        for src in expressions(st.inputs):
            errors += _check_expr(f"{where}.inputs", src, defined, in_loop)
        defined.add(st.id)
