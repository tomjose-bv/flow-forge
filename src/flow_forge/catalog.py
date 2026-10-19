"""Markdown catalog of the apps a task uses: the only app information agents get.

Generated from the same ActionSpec/TriggerSpec definitions the apps enforce, plus the object
shapes, the recipe format and an expression cheat sheet.
"""

from __future__ import annotations

from flow_forge.apps import APP_CLASSES

OBJECTS = {
    "deal": {"id": "string", "name": "string", "amount": "number", "currency": "string (USD, EUR, GBP, INR)",
             "stage": "string (lead, qualified, proposal, won, lost)", "owner_email": "string",
             "contact_id": "string (id of a crm contact)", "tags": "list of strings", "note": "string or absent",
             "updated_at": "string (ISO time)"},
    "contact": {"id": "string", "name": "string", "email": "string", "company": "string", "phone": "string"},
    "customer": {"id": "string", "name": "string", "email": "string"},
    "invoice": {"id": "string", "customer_id": "string (id of a billing customer)", "amount": "number",
                "currency": "string", "memo": "string or null", "external_ref": "string or null",
                "status": "string (draft, paid)"},
    "ticket": {"id": "string", "title": "string", "priority": "string (low, normal, high)",
               "requester_email": "string", "description": "string or null", "status": "string (open)"},
    "message": {"id": "string", "channel": "string", "text": "string"},
}
OUTPUT_OBJECT = {"deal": "deal", "contact": "contact", "customer": "customer", "invoice": "invoice",
                 "ticket": "ticket", "message": "message"}

RECIPE_HELP = """## Recipe format (YAML)

```yaml
name: <short_name>
trigger:
  app: <app>
  event: <event>
  filter: "<expression>"          # optional: events where it is false are ignored
steps:
  - id: <step_id>                 # lowercase letters, digits, _
    action: <app>.<action>
    inputs: {<input>: <value or template>, ...}
    if: "<expression>"            # optional: when false the step is skipped and its output is null
  - id: <loop_id>
    for_each: "<expression giving a list>"
    steps: [ ... ]                # inside: `item` is the current element, `index` its position
```

Expressions and templates:
- `trigger` is the event's data, `steps.<id>` the output of an earlier step.
- In inputs, `"{{trigger.deal.amount}}"` alone keeps the value's type; text with templates
  such as `"Deal {{trigger.deal.name}} won"` becomes a string.
- Operators: `== != > >= < <=`, `and`, `or`, `not`, `in` (list or substring), `is null`, `is not null`.
- Literals: `'text'`, numbers, `true`, `false`, `null`, lists `['a', 'b']`.
- Filters: `| lower`, `| upper`, `| trim`, `| default: <value or path>`, `| round: 2`, `| number`,
  `| integer`, `| string`, `| length`.
- Using a field that does not exist is an error, except with `is null` or `| default:`.
- Write actions are retried and de-duplicated by the engine; do not add your own retries.
"""


def render(app_names) -> str:
    apps = [APP_CLASSES[n]() for n in app_names]
    parts = ["# App catalog", ""]
    used_objects = set()
    for app in apps:
        parts += [f"## {app.name}", "", app.description, ""]
        if app.triggers:
            parts += ["Triggers (events):", ""]
            for t in app.triggers.values():
                parts.append(f"- `{t.event}`: {t.description} `trigger` = {t.data}.")
                used_objects |= {o for o in OBJECTS if o in t.data}
            parts.append("")
        parts += ["Actions:", ""]
        for a in app.actions.values():
            ins = []
            for name, p in a.inputs.items():
                extra = f" one of {list(p.enum)}" if p.enum else ""
                desc = f" ({p.description})" if p.description else ""
                ins.append(f"`{name}`: {p.type}{'' if p.required else ', optional'}{extra}{desc}")
            parts.append(f"- `{app.name}.{a.name}`: {a.description} Inputs: {'; '.join(ins)}. Returns {a.output}.")
            used_objects |= {o for o in OBJECTS if o in a.output}
        parts.append("")
    parts += ["## Objects", ""]
    for o in sorted(used_objects):
        fields = ", ".join(f"`{k}` ({v})" for k, v in OBJECTS[o].items())
        parts.append(f"- **{o}**: {fields}")
    parts += ["", RECIPE_HELP]
    return "\n".join(parts)
