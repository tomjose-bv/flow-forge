"""Synthetic apps: in-memory state, an events feed for triggers, and typed actions.

Actions and triggers are declared as data (`ActionSpec`, `TriggerSpec`) so that the app
catalog the agent reads (catalog.py) is generated from the same definitions the apps enforce.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any, Callable

TYPES = {"string": str, "number": (int, float), "integer": int, "boolean": bool, "object": dict}


class ActionError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


@dataclass(frozen=True)
class Param:
    type: str
    required: bool = True
    description: str = ""
    enum: tuple[str, ...] = ()


@dataclass(frozen=True)
class ActionSpec:
    name: str
    description: str
    inputs: dict[str, Param]
    output: str
    writes: bool  # creates or changes data (subject to idempotency keys)


@dataclass(frozen=True)
class TriggerSpec:
    event: str
    description: str
    data: str  # what `data` holds


@dataclass
class App:
    name: str
    api_key: str
    description: str = ""
    collections: dict[str, dict[str, dict[str, Any]]] = field(default_factory=dict)
    events: list[dict[str, Any]] = field(default_factory=list)
    action_log: list[dict[str, Any]] = field(default_factory=list)
    _idempotent: dict[tuple[str, str], Any] = field(default_factory=dict)
    _counters: dict[str, int] = field(default_factory=dict)
    clock: Callable[[], str] = lambda: "2026-03-01T00:00:00Z"

    actions: dict[str, ActionSpec] = field(default_factory=dict)
    triggers: dict[str, TriggerSpec] = field(default_factory=dict)

    # data helpers
    def new_id(self, prefix: str) -> str:
        n = self._counters.get(prefix, 0) + 1
        self._counters[prefix] = n
        return f"{prefix}_{n:04d}"

    def insert(self, collection: str, obj: dict[str, Any]) -> dict[str, Any]:
        self.collections.setdefault(collection, {})[obj["id"]] = obj
        return obj

    def get(self, collection: str, obj_id: str) -> dict[str, Any] | None:
        return self.collections.get(collection, {}).get(obj_id)

    def all(self, collection: str) -> list[dict[str, Any]]:
        return list(self.collections.get(collection, {}).values())

    def emit(self, event: str, data: dict[str, Any]) -> dict[str, Any]:
        if event not in self.triggers:
            raise ValueError(f"{self.name}: unknown event {event}")
        ev = {"id": len(self.events) + 1, "type": event, "at": self.clock(), "data": copy.deepcopy(data)}
        self.events.append(ev)
        return ev

    def events_after(self, after: int, limit: int = 50) -> list[dict[str, Any]]:
        return [copy.deepcopy(e) for e in self.events if e["id"] > after][:limit]

    # actions
    def call(self, action: str, inputs: dict[str, Any], idempotency_key: str | None = None) -> Any:
        spec = self.actions.get(action)
        if spec is None:
            raise ActionError(404, f"{self.name} has no action {action!r}")
        inputs = self._validate(spec, inputs)
        if spec.writes and idempotency_key:
            cached = self._idempotent.get((action, idempotency_key))
            if cached is not None:
                return copy.deepcopy(cached)
        result = getattr(self, f"do_{action}")(**inputs)
        self.action_log.append({"action": action, "inputs": copy.deepcopy(inputs), "key": idempotency_key})
        if spec.writes and idempotency_key:
            self._idempotent[(action, idempotency_key)] = copy.deepcopy(result)
        return copy.deepcopy(result)

    def _validate(self, spec: ActionSpec, inputs: Any) -> dict[str, Any]:
        if not isinstance(inputs, dict):
            raise ActionError(400, "inputs must be an object")
        unknown = set(inputs) - set(spec.inputs)
        if unknown:
            raise ActionError(400, f"{spec.name}: unknown inputs {sorted(unknown)}")
        out = {}
        for name, p in spec.inputs.items():
            if name not in inputs or inputs[name] is None:
                if p.required:
                    raise ActionError(400, f"{spec.name}: missing required input {name!r}")
                continue
            v = inputs[name]
            ok = isinstance(v, TYPES[p.type]) and not (p.type in ("number", "integer") and isinstance(v, bool))
            if not ok:
                raise ActionError(400, f"{spec.name}: input {name!r} must be {p.type}, got {type(v).__name__}")
            if p.enum and v not in p.enum:
                raise ActionError(400, f"{spec.name}: input {name!r} must be one of {list(p.enum)}")
            out[name] = v
        return out


def _p(type_: str, description: str = "", required: bool = True, enum: tuple[str, ...] = ()) -> Param:
    return Param(type_, required, description, enum)


class CRM(App):
    def __init__(self, api_key: str = "crm-key", **kw):
        super().__init__("crm", api_key, "Customer relationship management: deals and contacts.", **kw)
        self.triggers = {
            "deal.created": TriggerSpec("deal.created", "A deal was created.", "the deal"),
            "deal.stage_changed": TriggerSpec(
                "deal.stage_changed", "A deal moved to another stage.",
                "{deal: the deal after the change, previous_stage: string}"),
            "contact.created": TriggerSpec("contact.created", "A contact was created.", "the contact"),
        }
        self.actions = {
            "get_deal": ActionSpec("get_deal", "Get a deal by id.", {"id": _p("string")}, "the deal", False),
            "get_contact": ActionSpec("get_contact", "Get a contact by id.", {"id": _p("string")}, "the contact", False),
            "find_contact": ActionSpec("find_contact", "Find a contact by email.", {"email": _p("string")},
                                       "the contact, or null if none", False),
            "update_deal": ActionSpec("update_deal", "Change a deal's stage or note.",
                                      {"id": _p("string"), "stage": _p("string", required=False, enum=STAGES),
                                       "note": _p("string", required=False)}, "the updated deal", True),
        }

    def do_get_deal(self, id):
        d = self.get("deals", id)
        if d is None:
            raise ActionError(404, f"no deal {id}")
        return d

    def do_get_contact(self, id):
        c = self.get("contacts", id)
        if c is None:
            raise ActionError(404, f"no contact {id}")
        return c

    def do_find_contact(self, email):
        return next((c for c in self.all("contacts") if c["email"].lower() == email.lower()), None)

    def do_update_deal(self, id, stage=None, note=None):
        d = self.do_get_deal(id)
        if stage is not None:
            d["stage"] = stage
        if note is not None:
            d["note"] = note
        d["updated_at"] = self.clock()
        return d


STAGES = ("lead", "qualified", "proposal", "won", "lost")


class Billing(App):
    def __init__(self, api_key: str = "billing-key", **kw):
        super().__init__("billing", api_key, "Billing: customers and invoices.", **kw)
        self.triggers = {
            "invoice.paid": TriggerSpec("invoice.paid", "An invoice was paid.", "the invoice"),
        }
        self.actions = {
            "find_customer": ActionSpec("find_customer", "Find a billing customer by email.",
                                        {"email": _p("string")}, "the customer, or null if none", False),
            "create_customer": ActionSpec("create_customer", "Create a billing customer.",
                                          {"name": _p("string"), "email": _p("string")}, "the new customer", True),
            "create_invoice": ActionSpec(
                "create_invoice", "Create a draft invoice for a customer.",
                {"customer_id": _p("string"), "amount": _p("number", "positive amount"),
                 "currency": _p("string", enum=("USD", "EUR", "GBP", "INR")),
                 "memo": _p("string", required=False), "external_ref": _p("string", "id in the source app", False)},
                "the new invoice", True),
        }

    def do_find_customer(self, email):
        return next((c for c in self.all("customers") if c["email"].lower() == email.lower()), None)

    def do_create_customer(self, name, email):
        if self.do_find_customer(email):
            raise ActionError(409, f"customer with email {email} exists")
        return self.insert("customers", {"id": self.new_id("cus"), "name": name, "email": email})

    def do_create_invoice(self, customer_id, amount, currency, memo=None, external_ref=None):
        if self.get("customers", customer_id) is None:
            raise ActionError(404, f"no customer {customer_id}")
        if amount <= 0:
            raise ActionError(400, "create_invoice: amount must be positive")
        return self.insert("invoices", {"id": self.new_id("inv"), "customer_id": customer_id, "amount": amount,
                                        "currency": currency, "memo": memo, "external_ref": external_ref,
                                        "status": "draft"})


class Chat(App):
    def __init__(self, api_key: str = "chat-key", **kw):
        super().__init__("chat", api_key, "Team chat: channels and messages.", **kw)
        self.triggers = {}
        self.actions = {
            "post_message": ActionSpec("post_message", "Post a message to a channel.",
                                       {"channel": _p("string", "channel name without #"), "text": _p("string")},
                                       "the message", True),
        }

    def do_post_message(self, channel, text):
        if channel.lstrip("#") not in self.collections.get("channels", {}):
            raise ActionError(404, f"no channel {channel}")
        return self.insert("messages", {"id": self.new_id("msg"), "channel": channel.lstrip("#"), "text": text})


class Tickets(App):
    def __init__(self, api_key: str = "tickets-key", **kw):
        super().__init__("tickets", api_key, "Support tickets.", **kw)
        self.triggers = {
            "ticket.created": TriggerSpec("ticket.created", "A ticket was opened.", "the ticket"),
        }
        self.actions = {
            "create_ticket": ActionSpec(
                "create_ticket", "Open a support ticket.",
                {"title": _p("string"), "priority": _p("string", enum=("low", "normal", "high")),
                 "requester_email": _p("string"), "description": _p("string", required=False)},
                "the new ticket", True),
            "find_tickets": ActionSpec("find_tickets", "Open tickets for a requester.",
                                       {"requester_email": _p("string")}, "list of tickets", False),
        }

    def do_create_ticket(self, title, priority, requester_email, description=None):
        return self.insert("tickets", {"id": self.new_id("tkt"), "title": title, "priority": priority,
                                       "requester_email": requester_email, "description": description,
                                       "status": "open"})

    def do_find_tickets(self, requester_email):
        return [t for t in self.all("tickets") if t["requester_email"].lower() == requester_email.lower()
                and t["status"] == "open"]


APP_CLASSES = {"crm": CRM, "billing": Billing, "chat": Chat, "tickets": Tickets}


def make_apps(names=None) -> dict[str, App]:
    return {n: APP_CLASSES[n]() for n in (names or APP_CLASSES)}
