"""Agent variants that turn a task description into a recipe.

- prompt: one LLM call from the task and the app catalog.
- probe:  may look at sample events and call read-only actions first (SAMPLE / CALL lines).

All actions go through a ToolBox, so the guard sees and logs them. The final recipe is scored on
the test world by harness.evaluate; agents never see that score.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from flow_forge.llm import LLM, extract_recipe
from flow_forge.task import Task
from flow_forge.tools import ToolBox

ROOT = Path(__file__).resolve().parents[2]

CONTRACT = """You build integration workflows as YAML recipes for a workflow engine.
Reply with exactly one recipe in a ```yaml block. Use only the apps, events, actions and inputs in
the catalog. Follow the task description exactly, including the exact text of any messages,
titles, notes or memos. Do nothing the task does not ask for."""

PROBE_HELP = """Before writing the recipe you may inspect the apps. Reply with only lines like
SAMPLE <app>                      (shows a few example events of that app)
CALL <app>.<action> {"input": "value"}   (read-only actions only)
at most {n} lines per reply. When ready, reply with the recipe in a ```yaml block instead."""

SAMPLE_LINE = re.compile(r"^\s*SAMPLE\s+([a-z_]+)\s*$", re.MULTILINE)
CALL_LINE = re.compile(r"^\s*CALL\s+([a-z_]+\.[a-z_]+)\s*(\{.*\})?\s*$", re.MULTILINE)


@dataclass
class AgentResult:
    variant: str
    task: str
    model: str
    report: dict[str, Any] | None
    llm_calls: int
    prompt_tokens: int
    output_tokens: int
    llm_seconds: float
    seconds: float
    rounds: int
    tool_calls: int
    blocked: int
    questions: int = 0
    error: str | None = None
    tool_log: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def reference_text(task: Task, set_name: str, root: Path = ROOT) -> str:
    base = root / "recipes" / "reference"
    return ((base / "heldout") if set_name == "heldout" else base).joinpath(f"{task.name}.yaml").read_text(encoding="utf-8")


def _messages(system: str, user: str) -> list[dict[str, str]]:
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def _context(tb: ToolBox) -> str:
    return f"{tb.call('read_catalog')}\n\n{tb.call('read_task')}"


def _write(tb: ToolBox, reply: str) -> str:
    recipe = extract_recipe(reply)
    if recipe is None:
        return "error: no ```yaml recipe found in the reply"
    return tb.call("write_recipe", {"recipe": recipe})


def _finish(variant, task, llm, tb: ToolBox, started, rounds, reference, error=None, questions=0) -> AgentResult:
    from flow_forge.harness import evaluate

    if not tb.submitted:
        tb.call("submit")
    report = None
    if tb.recipe_path.exists():
        report = evaluate(task, tb.recipe_path.read_text(encoding="utf-8"), reference).to_dict()
    return AgentResult(
        variant=variant, task=task.name, model=getattr(llm, "model", type(llm).__name__), report=report,
        llm_calls=llm.usage.calls, prompt_tokens=llm.usage.prompt_tokens, output_tokens=llm.usage.output_tokens,
        llm_seconds=round(llm.usage.seconds, 2), seconds=round(time.monotonic() - started, 2), rounds=rounds,
        tool_calls=len(tb.log), blocked=tb.blocked, questions=questions, error=error,
        tool_log=[asdict(c) for c in tb.log],
    )


def run_prompt(task: Task, llm: LLM, run_dir: Path, reference: str) -> AgentResult:
    started = time.monotonic()
    tb = ToolBox(task, run_dir, allow_probe=False)
    reply = llm.chat(_messages(CONTRACT, _context(tb) + "\n\nWrite the recipe."))
    out = _write(tb, reply)
    return _finish("prompt", task, llm, tb, started, 1, reference, error=out if out.startswith("error") else None)


def _probe_results(tb: ToolBox, reply: str, n: int) -> list[str]:
    results = []
    for app in SAMPLE_LINE.findall(reply)[:n]:
        results.append(f"SAMPLE {app}\n{tb.call('sample_events', {'app': app})}")
    for action, raw in CALL_LINE.findall(reply)[:n]:
        try:
            inputs = json.loads(raw) if raw else {}
        except ValueError:
            results.append(f"CALL {action}\nerror: inputs must be a JSON object")
            continue
        results.append(f"CALL {action} {raw}\n{tb.call('call_readonly', {'action': action, 'inputs': inputs})}")
    return results


def probe_turns(tb: ToolBox, llm: LLM, messages: list[dict[str, str]], max_turns: int, n: int) -> str:
    """Let the model inspect the apps for up to `max_turns` replies; return the first reply with a recipe."""
    reply = llm.chat(messages)
    for _ in range(max_turns):
        if extract_recipe(reply) is not None:
            return reply
        results = _probe_results(tb, reply, n)
        if not results:
            break
        messages += [{"role": "assistant", "content": reply},
                     {"role": "user", "content": "\n\n".join(results) + "\n\nInspect more, or write the recipe."}]
        reply = llm.chat(messages)
    if extract_recipe(reply) is None:
        messages += [{"role": "assistant", "content": reply},
                     {"role": "user", "content": "Write the complete recipe now, in a ```yaml block."}]
        reply = llm.chat(messages)
    return reply


def run_probe(task: Task, llm: LLM, run_dir: Path, reference: str, max_turns: int = 3, n: int = 4) -> AgentResult:
    started = time.monotonic()
    tb = ToolBox(task, run_dir)
    messages = _messages(CONTRACT + "\n\n" + PROBE_HELP.replace("{n}", str(n)), _context(tb) + "\n\nInspect if useful, "
                         "then write the recipe.")
    reply = probe_turns(tb, llm, messages, max_turns, n)
    out = _write(tb, reply)
    return _finish("probe", task, llm, tb, started, 1, reference, error=out if out.startswith("error") else None)


AGENTS = {"prompt": run_prompt, "probe": run_probe}
