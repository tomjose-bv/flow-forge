from pathlib import Path

from flow_forge.llm import FakeLLM, extract_recipe
from flow_forge.task import build_world, load
from flow_forge.tools import ToolBox

ROOT = Path(__file__).resolve().parent.parent
TASK = load(ROOT / "tasks/dev/won_deal_invoice.yaml")
REF = (ROOT / "recipes/reference/won_deal_invoice.yaml").read_text()


def box(tmp_path, **kw):
    return ToolBox(TASK, tmp_path / "run", **kw)


def test_read_task_and_catalog(tmp_path):
    tb = box(tmp_path)
    assert "won" in tb.call("read_task") and "crm, billing" in tb.call("read_task")
    cat = tb.call("read_catalog")
    assert "billing.create_invoice" in cat and "chat.post_message" not in cat


def test_practice_world_differs_from_test_world(tmp_path):
    tb = box(tmp_path)
    test_events = build_world(TASK)["crm"].events
    assert tb._world["crm"].events != test_events
    out = tb.call("sample_events", {"app": "crm", "n": 2})
    assert "deal.stage_changed" in out and out.count('"type"') == 2


def test_call_readonly_and_guard(tmp_path):
    tb = box(tmp_path)
    cid = tb._world["crm"].all("contacts")[0]["id"]
    assert '"email"' in tb.call("call_readonly", {"action": "crm.get_contact", "inputs": {"id": cid}})
    assert "error 404" in tb.call("call_readonly", {"action": "crm.get_contact", "inputs": {"id": "nope"}})
    out = tb.call("call_readonly", {"action": "billing.create_customer", "inputs": {"name": "x", "email": "y"}})
    assert "blocked" in out and tb.blocked == 1
    assert "unknown" in tb.call("delete_everything")


def test_probe_disabled(tmp_path):
    tb = box(tmp_path, allow_probe=False)
    assert "disabled" in tb.call("sample_events", {"app": "crm"})


def test_write_and_dry_run(tmp_path):
    tb = box(tmp_path)
    assert "no recipe" in tb.call("dry_run")
    bad = tb.call("write_recipe", {"recipe": REF.replace("billing.create_invoice", "billing.make_invoice")})
    assert "invalid" in bad and "make_invoice" in bad
    assert tb.call("write_recipe", {"recipe": REF}) == "saved version 2; valid"
    out = tb.call("dry_run")
    assert "filtered out" in out and "billing.invoice" in out and "0 failed" in out
    assert "expected" not in out.lower()  # never reveals the answer key
    assert (tmp_path / "run/recipe_v1.yaml").exists()


def test_dry_run_reports_failures_and_duplicates(tmp_path):
    tb = box(tmp_path)
    tb.call("write_recipe", {"recipe": REF.replace('    if: "steps.customer is null"\n', "")})
    out = tb.call("dry_run")
    assert "failed event" in out or "duplicate" in out


def test_limits_and_submit(tmp_path):
    tb = box(tmp_path, limits={"read_task": 1, "submit": 1})
    tb.call("read_task")
    assert "call limit" in tb.call("read_task")
    assert tb.call("submit") == "submitted" and "already submitted" in tb.call("read_task")


def test_extract_recipe():
    assert extract_recipe("Here:\n```yaml\nname: a\n```") == "name: a\n"
    assert extract_recipe("name: a\ntrigger: {}\nsteps: []") is not None
    assert extract_recipe("nothing") is None
    assert FakeLLM(["x"]).chat([]) == "x"
