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


def test_graph_fixes_invalid_then_stops_on_done(tmp_path):
    from flow_forge.agents import run_graph

    bad = FENCED.replace("crm.get_contact", "crm.get_person")
    llm = FakeLLM([bad, FENCED, "DONE"])
    r = run_graph(TASK, llm, tmp_path, REF)
    assert r.report["success"] and r.rounds == 2 and r.llm_calls == 3
    assert "get_person" in llm.seen[1][1]["content"] and "invalid" in llm.seen[1][1]["content"]
    assert "Compare them with the task description" in llm.seen[2][1]["content"]
    assert "practice run" in llm.seen[2][1]["content"]


def test_graph_keeps_best_recipe(tmp_path):
    from flow_forge.agents import run_graph

    worse = FENCED.replace('    if: "steps.customer is null"\n', "")  # fails or duplicates
    llm = FakeLLM(["SAMPLE crm", FENCED, worse, "no recipe here", worse])
    r = run_graph(TASK, llm, tmp_path, REF, rounds=4)
    assert r.report["success"]
    assert (tmp_path / "recipe.yaml").read_text() == REF


def test_graph_without_any_recipe(tmp_path):
    from flow_forge.agents import run_graph

    r = run_graph(TASK, FakeLLM(["hmm"] * 10), tmp_path, REF, rounds=2)
    assert r.report is None and r.error == "no recipe was written"


AMBIG = load(ROOT / "tasks/dev/big_wins_shoutout.yaml")
AMBIG_REF = reference_text(AMBIG, "dev")


def test_scripted_user():
    from flow_forge.agents import COMPLETE, JUDGMENT, ScriptedUser

    u = ScriptedUser(AMBIG)
    assert "8000" in u.answer("How big is a big deal, what amount?")
    assert "#wins" in u.answer("Which channel should I post in?")
    assert u.answer("What is your favourite colour?") == JUDGMENT
    assert ScriptedUser(TASK).answer("Which channel?") == COMPLETE


def test_graph_clarify_uses_answers(tmp_path):
    from flow_forge.agents import run_graph_clarify

    questions = "QUESTION: What amount counts as big?\nQUESTION: Which channel?\nQUESTION: What text exactly?"
    llm = FakeLLM([questions, f"```yaml\n{AMBIG_REF}```", "DONE"])
    r = run_graph_clarify(AMBIG, llm, tmp_path, AMBIG_REF)
    assert r.variant == "graph+clarify" and r.questions == 3 and r.report["success"]
    ctx = llm.seen[1][1]["content"]
    assert "Clarifications from the user" in ctx and "8000" in ctx and "We won <deal name>!" in ctx


def test_graph_clarify_ready_asks_nothing(tmp_path):
    from flow_forge.agents import run_graph_clarify

    r = run_graph_clarify(TASK, FakeLLM(["READY", FENCED, "DONE"]), tmp_path, REF)
    assert r.questions == 0 and r.report["success"]


def test_question_limit(tmp_path):
    from flow_forge.agents import run_graph_clarify

    many = "\n".join(f"QUESTION: q{i} amount?" for i in range(6))
    r = run_graph_clarify(AMBIG, FakeLLM([many, f"```yaml\n{AMBIG_REF}```", "DONE"]), tmp_path, AMBIG_REF)
    assert r.questions == 3
