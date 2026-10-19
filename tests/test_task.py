import pytest

from flow_forge.task import TaskError, build_world, parse


def task(**over):
    d = {
        "name": "t",
        "description": "When a deal is won, invoice it.",
        "seed": 3,
        "apps": ["crm", "billing", "chat", "tickets"],
        "world": {"contacts": 10, "billing_customers": 4, "channels": ["sales", "support"], "open_tickets": 2},
        "events": [
            {"type": "deal.stage_changed", "count": 8, "stages": {"won": 3, "lost": 2, "proposal": 3},
             "currency_pool": ["USD", "EUR"]},
            {"type": "contact.created", "count": 2},
            {"type": "ticket.created", "count": 4, "priorities": {"high": 1, "normal": 3}},
        ],
    }
    d.update(over)
    return parse(d)


def snapshot(apps):
    return {n: (a.collections, a.events) for n, a in apps.items()}


def test_deterministic():
    assert snapshot(build_world(task())) == snapshot(build_world(task()))
    assert snapshot(build_world(task())) != snapshot(build_world(task(seed=4)))


def test_counts_and_mix():
    apps = build_world(task())
    crm = apps["crm"]
    assert len(crm.all("contacts")) == 12 and len(crm.all("deals")) == 8
    stages = [e["data"]["deal"]["stage"] for e in crm.events if e["type"] == "deal.stage_changed"]
    assert sorted(stages) == ["lost"] * 2 + ["proposal"] * 3 + ["won"] * 3
    assert len(apps["billing"].all("customers")) == 4
    assert sorted(apps["chat"].collections["channels"]) == ["sales", "support"]
    tk = apps["tickets"]
    assert len(tk.all("tickets")) == 6 and sum(e["type"] == "ticket.created" for e in tk.events) == 4
    assert all(a.action_log == [] for a in apps.values())
    times = [e["at"] for e in crm.events]
    assert times == sorted(times)


def test_only_task_apps_returned():
    apps = build_world(task(apps=["crm", "chat"], events=[{"type": "deal.created", "count": 2}]))
    assert sorted(apps) == ["chat", "crm"]


@pytest.mark.parametrize(
    "over, msg",
    [
        ({"apps": ["erp"]}, "unknown app"),
        ({"events": [{"type": "deal.deleted"}]}, "type must be one of"),
        ({"bogus": 1}, "unknown keys"),
        ({"apps": ["crm"], "events": [{"type": "ticket.created"}]}, "needs the tickets app"),
    ],
)
def test_parse_errors(over, msg):
    with pytest.raises(TaskError, match=msg):
        task(**over)


def test_mix_must_match_count():
    with pytest.raises(TaskError, match="adds up"):
        build_world(task(events=[{"type": "deal.stage_changed", "count": 3, "stages": {"won": 1}}]))
