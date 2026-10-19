import pytest

from flow_forge.apps import make_apps
from flow_forge.engine import Client, run
from flow_forge.recipe import loads
from flow_forge.server import AppServer
from test_recipe import GOOD

KEYS = {"crm": "crm-key", "billing": "billing-key", "chat": "chat-key", "tickets": "tickets-key"}


@pytest.fixture
def apps():
    a = make_apps()
    crm = a["crm"]
    crm.insert("contacts", {"id": "con_1", "name": "Ada", "email": "ada@example.com", "company": "A"})
    crm.insert("contacts", {"id": "con_2", "name": "Ben", "email": "ben@example.com", "company": "B"})
    a["billing"].insert("customers", {"id": "cus_0001", "name": "Ada", "email": "ADA@example.com"})
    a["chat"].insert("channels", {"id": "sales", "name": "sales"})
    deals = [
        {"id": "d1", "name": "One", "amount": 100, "stage": "won", "contact_id": "con_1", "tags": ["x"]},
        {"id": "d2", "name": "Two", "amount": 200, "stage": "lost", "contact_id": "con_2", "tags": []},
        {"id": "d3", "name": "Three", "amount": 300, "stage": "won", "contact_id": "con_2", "tags": ["y", "z"]},
    ]
    for d in deals:
        crm.insert("deals", d)
        crm.emit("deal.stage_changed", {"deal": d, "previous_stage": "proposal"})
    crm.emit("contact.created", crm.get("contacts", "con_1"))  # other event types are ignored
    return a


def client(srv, **kw):
    return Client(srv.url, KEYS, sleep=lambda s: None, **kw)


def test_run_recipe(apps):
    with AppServer(apps) as srv:
        log = run(loads(GOOD), client(srv))
    assert log.cursor == 4 and [e.status for e in log.events] == ["ok", "filtered", "ok"]
    customers = {c["email"].lower(): c["id"] for c in apps["billing"].all("customers")}
    assert customers == {"ada@example.com": "cus_0001", "ben@example.com": "cus_0002"}
    inv = apps["billing"].all("invoices")
    assert [(i["customer_id"], i["amount"]) for i in inv] == [("cus_0001", 100), ("cus_0002", 300)]
    assert [m["text"] for m in apps["chat"].all("messages")] == ["0: x", "0: y", "1: z"]
    skipped = [c.step for c in log.events[0].calls if c.status == "skipped"]
    assert skipped == ["new_customer"]  # Ada already exists in billing


def test_replay_is_idempotent(apps):
    with AppServer(apps) as srv:
        run(loads(GOOD), client(srv))
        before = {k: len(v) for k, v in apps["billing"].collections.items()}
        log = run(loads(GOOD), client(srv), cursor=0)  # replay everything
    assert [e.status for e in log.events] == ["ok", "filtered", "ok"]
    assert {k: len(v) for k, v in apps["billing"].collections.items()} == before == {"customers": 2, "invoices": 2}
    assert len(apps["chat"].all("messages")) == 3


def test_cursor_resumes(apps):
    with AppServer(apps) as srv:
        first = run(loads(GOOD), client(srv))
        assert run(loads(GOOD), client(srv), cursor=first.cursor).events == []


def test_failed_step_is_recorded_and_run_continues(apps):
    bad = GOOD.replace("channel: sales", "channel: nowhere")
    with AppServer(apps) as srv:
        log = run(loads(bad), client(srv))
    assert [e.status for e in log.events] == ["failed", "filtered", "failed"]
    assert "chat.post_message failed with 404: no channel nowhere" in log.events[0].error
    assert len(apps["billing"].all("invoices")) == 2  # steps before the failure ran


def test_expression_error_fails_event(apps):
    bad = GOOD.replace("{{trigger.deal.amount}}", "{{trigger.deal.total}}")
    with AppServer(apps) as srv:
        log = run(loads(bad), client(srv))
    assert "unknown path 'trigger.deal.total'" in log.events[0].error


def test_retries_server_errors(apps):
    calls = {"n": 0}
    real = apps["billing"].do_create_invoice

    def flaky(**kw):
        calls["n"] += 1
        if calls["n"] == 1:
            from flow_forge.apps import ActionError
            raise ActionError(503, "try again")
        return real(**kw)

    apps["billing"].do_create_invoice = flaky
    with AppServer(apps) as srv:
        log = run(loads(GOOD), client(srv))
    assert [e.status for e in log.events] == ["ok", "filtered", "ok"]
    assert len(apps["billing"].all("invoices")) == 2
