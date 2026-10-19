from pathlib import Path

from flow_forge.agents import reference_text, run_probe, run_prompt
from flow_forge.llm import FakeLLM
from flow_forge.task import load

ROOT = Path(__file__).resolve().parent.parent
TASK = load(ROOT / "tasks/dev/won_deal_invoice.yaml")
REF = reference_text(TASK, "dev")
FENCED = f"Recipe:\n```yaml\n{REF}```\n"


def test_prompt_agent_with_reference_reply(tmp_path):
    llm = FakeLLM([FENCED])
    r = run_prompt(TASK, llm, tmp_path, REF)
    assert r.error is None and r.llm_calls == 1 and r.report["success"]
    sent = llm.seen[0][1]["content"]
    assert "billing.create_invoice" in sent and "Deal <deal name>" in sent
    assert REF.split("\n", 1)[1] not in sent  # the reference is never in the prompt
    assert [c["tool"] for c in r.tool_log] == ["read_catalog", "read_task", "write_recipe", "submit"]


def test_prompt_agent_without_recipe(tmp_path):
    r = run_prompt(TASK, FakeLLM(["Sorry."]), tmp_path, REF)
    assert r.report is None and "no ```yaml" in r.error


def test_prompt_agent_invalid_recipe_scores_zero(tmp_path):
    r = run_prompt(TASK, FakeLLM([FENCED.replace("crm.get_contact", "crm.get_person")]), tmp_path, REF)
    assert r.report["valid"] is False and r.report["success"] is False


def test_probe_agent_inspects_then_writes(tmp_path):
    llm = FakeLLM(['SAMPLE crm\nCALL billing.find_customer {"email": "x@example.com"}', FENCED])
    r = run_probe(TASK, llm, tmp_path, REF)
    assert r.report["success"] and r.llm_calls == 2
    tools = [c["tool"] for c in r.tool_log]
    assert "sample_events" in tools and "call_readonly" in tools
    assert "deal.stage_changed" in llm.seen[1][-1]["content"]


def test_probe_agent_cannot_write_through_call(tmp_path):
    llm = FakeLLM(['CALL billing.create_customer {"name": "a", "email": "b"}', FENCED])
    r = run_probe(TASK, llm, tmp_path, REF)
    assert r.blocked == 1 and "only read-only" in llm.seen[1][-1]["content"]


def test_probe_agent_turn_limit(tmp_path):
    llm = FakeLLM(["SAMPLE crm"] * 3 + ["thinking", FENCED])
    r = run_probe(TASK, llm, tmp_path, REF, max_turns=3)
    assert r.llm_calls == 5 and r.report["success"]
