"""Task format: a plain-English workflow, the apps it touches, and a seeded world + event stream.

    name: won_deal_invoice
    description: |
      When a deal is marked won in the CRM, create a USD invoice in billing for the deal amount ...
    seed: 1
    apps: [crm, billing]
    world:
      contacts: 12
      billing_customers: 5        # this many contacts already exist in billing
      channels: [sales]
      open_tickets: 0
    events:
      - {type: deal.stage_changed, count: 15, stages: {won: 6, lost: 4, proposal: 5}}
    ambiguous: false              # the description leaves something open (milestone 4)
    clarifications: {}            # scripted answers for the clarify agent (milestone 4)

The same seed always builds the same world and the same events.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from flow_forge.apps import APP_CLASSES, App, make_apps

FIRST = ["Ada", "Ben", "Cleo", "Dev", "Eli", "Fay", "Gus", "Hana", "Ivo", "Jun", "Kai", "Lea", "Mo", "Nia"]
LAST = ["Abel", "Brook", "Cruz", "Dahl", "Ekko", "Frost", "Gale", "Holm", "Iyer", "Juno"]
COMPANIES = ["Northwind", "Bluebird", "Copperleaf", "Driftwood", "Evergreen", "Foxglove", "Granite", "Harbor"]
WORDS = ["alpha", "beta", "gamma", "delta", "omega", "lumen", "nova", "pixel", "quartz", "zephyr"]
CURRENCIES = ["USD", "EUR", "GBP", "INR"]
BASE = datetime(2026, 3, 1, 9, 0, tzinfo=timezone.utc)
EVENT_TYPES = {"deal.stage_changed", "deal.created", "contact.created", "ticket.created", "invoice.paid"}


class TaskError(ValueError):
    pass


@dataclass(frozen=True)
class Task:
    name: str
    description: str
    seed: int
    apps: tuple[str, ...]
    world: dict[str, Any] = field(default_factory=dict)
    events: tuple[dict[str, Any], ...] = ()
    ambiguous: bool = False
    clarifications: dict[str, str] = field(default_factory=dict)


def parse(data: Any) -> Task:
    if not isinstance(data, dict):
        raise TaskError("task must be a mapping")
    for key in ("name", "description", "seed", "apps", "events"):
        if key not in data:
            raise TaskError(f"missing required key: {key}")
    unknown = set(data) - {"name", "description", "seed", "apps", "world", "events", "ambiguous", "clarifications"}
    if unknown:
        raise TaskError(f"unknown keys: {sorted(unknown)}")
    apps = tuple(data["apps"])
    for a in apps:
        if a not in APP_CLASSES:
            raise TaskError(f"unknown app {a!r}")
    for i, ev in enumerate(data["events"]):
        if not isinstance(ev, dict) or ev.get("type") not in EVENT_TYPES:
            raise TaskError(f"events[{i}]: type must be one of {sorted(EVENT_TYPES)}")
        needs = {"ticket": "tickets", "invoice": "billing"}.get(ev["type"].split(".")[0])
        if needs and needs not in apps:
            raise TaskError(f"events[{i}]: {ev['type']} needs the {needs} app")
    return Task(
        name=str(data["name"]),
        description=str(data["description"]).strip(),
        seed=int(data["seed"]),
        apps=apps,
        world=dict(data.get("world") or {}),
        events=tuple(data["events"]),
        ambiguous=bool(data.get("ambiguous", False)),
        clarifications=dict(data.get("clarifications") or {}),
    )


def load(path: str | Path) -> Task:
    import yaml

    with open(path, encoding="utf-8") as f:
        return parse(yaml.safe_load(f))


class _Clock:
    def __init__(self):
        self.t = BASE

    def tick(self, rng: random.Random) -> str:
        self.t += timedelta(minutes=rng.randint(1, 90))
        return self.t.strftime("%Y-%m-%dT%H:%M:%SZ")


def _mix(spec: dict[str, int] | None, default: list[str], count: int, rng: random.Random) -> list[str]:
    if spec:
        out = [k for k, n in spec.items() for _ in range(int(n))]
        if len(out) != count:
            raise TaskError(f"mix {spec} adds up to {len(out)}, expected count {count}")
        rng.shuffle(out)
        return out
    return [rng.choice(default) for _ in range(count)]


def build_world(task: Task) -> dict[str, App]:
    """Apps populated deterministically from the task's seed, with the event stream emitted."""
    rng = random.Random(task.seed)
    clock = _Clock()
    apps = make_apps(sorted(set(task.apps) | {"crm"}))
    for app in apps.values():
        app.clock = lambda: clock.t.strftime("%Y-%m-%dT%H:%M:%SZ")
    crm = apps["crm"]
    w = task.world

    def new_contact():
        first, last = rng.choice(FIRST), rng.choice(LAST)
        cid = crm.new_id("con")
        return crm.insert("contacts", {
            "id": cid, "name": f"{first} {last}", "email": f"{first.lower()}.{last.lower()}{len(crm.all('contacts'))}@example.com",
            "company": rng.choice(COMPANIES), "phone": f"+1-555-{rng.randint(1000, 9999)}",
        })

    contacts = [new_contact() for _ in range(int(w.get("contacts", 10)))]
    if "billing" in apps:
        billing = apps["billing"]
        for c in rng.sample(contacts, min(int(w.get("billing_customers", 0)), len(contacts))):
            email = c["email"].upper() if rng.random() < 0.3 else c["email"]  # case differs sometimes
            billing.insert("customers", {"id": billing.new_id("cus"), "name": c["name"], "email": email})
    if "chat" in apps:
        for ch in w.get("channels", ["general"]):
            apps["chat"].insert("channels", {"id": ch, "name": ch})
    if "tickets" in apps:
        for _ in range(int(w.get("open_tickets", 0))):
            c = rng.choice(contacts)
            t = apps["tickets"]
            t.insert("tickets", {"id": t.new_id("tkt"), "title": f"{rng.choice(WORDS)} issue", "priority": "normal",
                                 "requester_email": c["email"], "description": None, "status": "open"})

    for spec in task.events:
        n = int(spec.get("count", 1))
        kind = spec["type"]
        if kind in ("deal.stage_changed", "deal.created"):
            stages = _mix(spec.get("stages"), ["won", "lost", "proposal", "qualified"], n, rng)
            currencies = _mix(spec.get("currencies"), spec.get("currency_pool", ["USD"]), n, rng)
            for stage, cur in zip(stages, currencies):
                clock.tick(rng)
                c = rng.choice(contacts)
                deal = crm.insert("deals", {
                    "id": crm.new_id("deal"), "name": f"{c['company']} {rng.choice(WORDS)}",
                    "amount": rng.choice([rng.randint(5, 200) * 100, rng.randint(500, 9999)]),
                    "currency": cur, "stage": stage if kind == "deal.stage_changed" else "lead",
                    "owner_email": f"{rng.choice(FIRST).lower()}@sales.example.com", "contact_id": c["id"],
                    "tags": rng.sample(["enterprise", "smb", "renewal", "upsell", "partner"], rng.randint(0, 2)),
                    "updated_at": clock.t.strftime("%Y-%m-%dT%H:%M:%SZ"),
                })
                if kind == "deal.created":
                    crm.emit("deal.created", deal)
                else:
                    prev = rng.choice([s for s in ("qualified", "proposal") if s != stage] or ["proposal"])
                    crm.emit("deal.stage_changed", {"deal": deal, "previous_stage": prev})
        elif kind == "contact.created":
            for _ in range(n):
                clock.tick(rng)
                c = new_contact()
                contacts.append(c)
                crm.emit("contact.created", c)
        elif kind == "ticket.created":
            t = apps["tickets"]
            prios = _mix(spec.get("priorities"), ["low", "normal", "high"], n, rng)
            for prio in prios:
                clock.tick(rng)
                c = rng.choice(contacts)
                tk = t.insert("tickets", {"id": t.new_id("tkt"), "title": f"{rng.choice(WORDS)} {rng.choice(['outage', 'question', 'bug', 'refund'])}",
                                          "priority": prio, "requester_email": c["email"],
                                          "description": f"Reported by {c['name']}", "status": "open"})
                t.emit("ticket.created", tk)
        elif kind == "invoice.paid":
            b = apps["billing"]
            for _ in range(n):
                clock.tick(rng)
                c = rng.choice(contacts)
                cust = b.do_find_customer(c["email"]) or b.insert(
                    "customers", {"id": b.new_id("cus"), "name": c["name"], "email": c["email"]})
                inv = b.insert("invoices", {"id": b.new_id("inv"), "customer_id": cust["id"],
                                            "amount": rng.randint(5, 300) * 10, "currency": rng.choice(CURRENCIES),
                                            "memo": None, "external_ref": None, "status": "paid"})
                b.emit("invoice.paid", inv)
    for app in apps.values():
        app.action_log.clear()
    return {k: v for k, v in apps.items() if k in task.apps}
