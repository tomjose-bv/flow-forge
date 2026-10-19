import json
from pathlib import Path

from flow_forge.apps import APP_CLASSES
from flow_forge.catalog import render
from flow_forge.cli import main

ROOT = Path(__file__).resolve().parent.parent


def test_catalog_lists_everything():
    doc = render(["crm", "billing", "chat", "tickets"])
    for name, cls in APP_CLASSES.items():
        app = cls()
        for a, spec in app.actions.items():
            assert f"`{name}.{a}`" in doc
            for inp in spec.inputs:
                assert f"`{inp}`" in doc
        for ev in app.triggers:
            assert f"`{ev}`" in doc
    assert "for_each" in doc and "| default:" in doc and "**deal**" in doc


def test_catalog_only_task_apps():
    doc = render(["tickets", "chat"])
    assert "## tickets" in doc and "## crm" not in doc and "**deal**" not in doc


def test_catalog_never_contains_reference_recipes():
    doc = render(["crm", "billing", "chat", "tickets"])
    for ref in (ROOT / "recipes" / "reference").rglob("*.yaml"):
        assert ref.read_text(encoding="utf-8").split("\n", 1)[1] not in doc


def test_cli_eval_references(tmp_path, capsys):
    out = tmp_path / "r.json"
    assert main(["eval", "--root", str(ROOT), "--task", "won_deal_chat", "--out", str(out)]) == 0
    data = json.loads(out.read_text())
    assert data["reports"][0]["success"] and data["meta"]["machine"]
    assert "won_deal_chat" in capsys.readouterr().out


def test_cli_eval_missing_recipe(tmp_path):
    assert main(["eval", "--root", str(ROOT), "--task", "won_deal_chat", "--recipe-dir", str(tmp_path)]) == 1


def test_cli_agent_with_fake_llm(tmp_path):
    import argparse

    from flow_forge.cli import cmd_agent
    from flow_forge.llm import FakeLLM

    ref = (ROOT / "recipes/reference/lost_deal_note.yaml").read_text()  # tasks run in name order
    args = argparse.Namespace(root=str(ROOT), set="dev", task=["won_deal_chat", "lost_deal_note"], variant="prompt",
                              model="fake", seed=1, temperature=0.0, out=str(tmp_path / "run"))
    assert cmd_agent(args, llm=FakeLLM([f"```yaml\n{ref}```"])) == 0  # second task: model runs out -> crash
    results = json.loads((tmp_path / "run/summary.json").read_text())["results"]
    by_task = {r["task"]: r for r in results}
    assert by_task["lost_deal_note"]["report"]["success"]
    assert "agent crashed" in by_task["won_deal_chat"]["error"]
