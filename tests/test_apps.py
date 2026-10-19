import json
import urllib.error
import urllib.request

import pytest

from flow_forge.apps import ActionError, make_apps
from flow_forge.server import AppServer


@pytest.fixture
def apps():
    a = make_apps()
    a["billing"].insert("customers", {"id": "cus_0001", "name": "Ada Abel", "email": "ada@example.com"})
    a["chat"].insert("channels", {"id": "sales", "name": "sales"})
    return a


def test_validation(apps):
    b = apps["billing"]
    with pytest.raises(ActionError, match="missing required input 'currency'"):
        b.call("create_invoice", {"customer_id": "cus_0001", "amount": 10})
    with pytest.raises(ActionError, match="must be number"):
        b.call("create_invoice", {"customer_id": "cus_0001", "amount": "10", "currency": "USD"})
    with pytest.raises(ActionError, match="one of"):
        b.call("create_invoice", {"customer_id": "cus_0001", "amount": 10, "currency": "XYZ"})
    with pytest.raises(ActionError, match="unknown inputs"):
        b.call("create_invoice", {"customer_id": "cus_0001", "amount": 10, "currency": "USD", "x": 1})
    with pytest.raises(ActionError) as e:
        b.call("create_invoice", {"customer_id": "nope", "amount": 10, "currency": "USD"})
    assert e.value.status == 404


def test_idempotency(apps):
    b = apps["billing"]
    args = {"customer_id": "cus_0001", "amount": 5, "currency": "EUR"}
    first = b.call("create_invoice", args, idempotency_key="k1")
    assert b.call("create_invoice", args, idempotency_key="k1") == first
    assert len(b.all("invoices")) == 1
    b.call("create_invoice", args)
    assert len(b.all("invoices")) == 2


def test_events_and_find(apps):
    crm = apps["crm"]
    crm.insert("contacts", {"id": "con_1", "name": "Ben", "email": "Ben@Example.com", "company": "x"})
    crm.emit("contact.created", crm.get("contacts", "con_1"))
    assert crm.call("find_contact", {"email": "ben@example.com"})["id"] == "con_1"
    assert crm.call("find_contact", {"email": "none@example.com"}) is None
    assert [e["id"] for e in crm.events_after(0)] == [1]
    with pytest.raises(ValueError):
        crm.emit("deal.deleted", {})


def http(url, data=None, key=None, idem=None):
    headers = {"Content-Type": "application/json"}
    if key:
        headers["X-Api-Key"] = key
    if idem:
        headers["Idempotency-Key"] = idem
    req = urllib.request.Request(url, data=json.dumps(data).encode() if data is not None else None, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def test_http(apps):
    with AppServer(apps) as srv:
        u = srv.url
        assert http(f"{u}/chat/actions/post_message", {"inputs": {"channel": "sales", "text": "hi"}})[0] == 401
        s, body = http(f"{u}/chat/actions/post_message", {"inputs": {"channel": "#sales", "text": "hi"}}, "chat-key")
        assert s == 200 and body["result"]["channel"] == "sales"
        s, body = http(f"{u}/chat/actions/post_message", {"inputs": {"channel": "nope", "text": "hi"}}, "chat-key")
        assert s == 404 and "no channel" in body["error"]
        apps["crm"].insert("contacts", {"id": "con_1", "name": "Ben", "email": "b@x.io", "company": "x"})
        apps["crm"].emit("contact.created", apps["crm"].get("contacts", "con_1"))
        s, body = http(f"{u}/crm/events?after=0", key="crm-key")
        assert s == 200 and body["last_id"] == 1 and body["events"][0]["type"] == "contact.created"
        assert http(f"{u}/crm/events?after=1", key="crm-key")[1] == {"events": [], "last_id": 1}
        args = {"inputs": {"customer_id": "cus_0001", "amount": 3, "currency": "USD"}}
        a = http(f"{u}/billing/actions/create_invoice", args, "billing-key", "e1:s1")[1]
        b = http(f"{u}/billing/actions/create_invoice", args, "billing-key", "e1:s1")[1]
        assert a == b and len(apps["billing"].all("invoices")) == 1
        assert http(f"{u}/nope/events", key="x")[0] == 404
        assert len(srv.log) == 8


def test_new_ids_skip_hand_inserted(apps):
    c = apps["billing"].call("create_customer", {"name": "Ben", "email": "ben@example.com"})
    assert c["id"] == "cus_0002" and len(apps["billing"].all("customers")) == 2
