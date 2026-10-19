"""Agent tools for one task, behind a guard.

Agents work on a *practice world*: the task's world built from a different seed, so they never
see the test events. `dry_run` shows what a recipe would do there (effects and errors), never
the expected effects: like a real workflow builder, the agent must check the result against the
description itself. The final score always comes from the test world (harness.evaluate).

Tools: read_task, read_catalog, sample_events, call_readonly, write_recipe, dry_run, submit.
The guard enforces per-tool limits, allows only read-only actions in call_readonly, and logs
every call.
"""

from __future__ import annotations

import dataclasses
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from flow_forge.apps import ActionError
from flow_forge.catalog import render as render_catalog
from flow_forge.recipe import RecipeError, loads, validate
from flow_forge.task import Task, build_world

DEFAULT_LIMITS = {"read_task": 3, "read_catalog": 3, "sample_events": 6, "call_readonly": 10,
                  "write_recipe": 8, "dry_run": 6, "submit": 1}
PRACTICE_SEED_OFFSET = 1000
MAX_RESULT = 1500


@dataclass
class ToolCall:
    tool: str
    args: dict[str, Any]
    ok: bool
    blocked: bool
    seconds: float
    result: str


class GuardError(Exception):
    pass


@dataclass
class ToolBox:
    task: Task
    run_dir: Path
    limits: dict[str, int] = field(default_factory=lambda: dict(DEFAULT_LIMITS))
    allow_probe: bool = True  # sample_events and call_readonly
    log: list[ToolCall] = field(default_factory=list)
    versions: int = 0
    submitted: bool = False

    def __post_init__(self):
        self.run_dir = Path(self.run_dir)
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.practice = dataclasses.replace(self.task, seed=self.task.seed + PRACTICE_SEED_OFFSET)
        self._world = build_world(self.practice)

    @property
    def recipe_path(self) -> Path:
        return self.run_dir / "recipe.yaml"

    @property
    def blocked(self) -> int:
        return sum(c.blocked for c in self.log)

    def count(self, tool: str) -> int:
        return sum(1 for c in self.log if c.tool == tool and not c.blocked)

    def call(self, tool: str, args: dict[str, Any] | None = None) -> str:
        args = dict(args or {})
        started = time.monotonic()
        handler = getattr(self, f"_tool_{tool}", None)
        blocked, ok = False, False
        if handler is None or (tool in ("sample_events", "call_readonly") and not self.allow_probe):
            blocked, result = True, f"error: unknown or disabled tool {tool!r}"
        elif self.submitted:
            blocked, result = True, "error: already submitted"
        elif self.count(tool) >= self.limits.get(tool, 0):
            blocked, result = True, f"error: call limit for {tool} reached ({self.limits.get(tool, 0)})"
        else:
            try:
                result, ok = handler(**args), True
            except GuardError as e:
                blocked, result = True, f"error: blocked: {e}"
            except TypeError as e:
                result = f"error: bad arguments: {e}"
        short = {k: (v[:80] + "..." if isinstance(v, str) and len(v) > 80 else v) for k, v in args.items()}
        self.log.append(ToolCall(tool, short, ok, blocked, round(time.monotonic() - started, 3), result[:300]))
        return result

    # tools
    def _tool_read_task(self) -> str:
        return f"Task: {self.task.description}\nApps available: {', '.join(self.task.apps)}"

    def _tool_read_catalog(self) -> str:
        return render_catalog(self.task.apps)

    def _tool_sample_events(self, app: str, n: int = 3) -> str:
        if app not in self._world:
            raise GuardError(f"app must be one of {sorted(self._world)}")
        evs = self._world[app].events[: max(1, min(int(n), 5))]
        return _clip(json.dumps(evs, indent=1)) if evs else f"{app} has no events in the practice world"

    def _tool_call_readonly(self, action: str, inputs: dict[str, Any] | None = None) -> str:
        app_name, _, name = str(action).partition(".")
        app = self._world.get(app_name)
        if app is None or name not in app.actions:
            return f"error: unknown action {action!r}"
        if app.actions[name].writes:
            raise GuardError(f"{action} changes data; only read-only actions can be called")
        try:
            return _clip(json.dumps(app.call(name, inputs or {}), indent=1))
        except ActionError as e:
            return f"error {e.status}: {e.message}"

    def _tool_write_recipe(self, recipe: str) -> str:
        if not isinstance(recipe, str) or not recipe.strip():
            return "error: empty recipe"
        self.versions += 1
        (self.run_dir / f"recipe_v{self.versions}.yaml").write_text(recipe, encoding="utf-8")
        self.recipe_path.write_text(recipe, encoding="utf-8")
        try:
            errors = validate(loads(recipe), build_world(self.practice))
        except RecipeError as e:
            errors = [str(e)]
        if errors:
            return f"saved version {self.versions}, but it is invalid:\n" + "\n".join(f"- {e}" for e in errors[:8])
        return f"saved version {self.versions}; valid"

    def _tool_dry_run(self) -> str:
        from flow_forge.harness import run_recipe

        if not self.recipe_path.exists():
            return "error: no recipe saved yet; call write_recipe first"
        text = self.recipe_path.read_text(encoding="utf-8")
        try:
            errors = validate(loads(text), build_world(self.practice))
        except RecipeError as e:
            errors = [str(e)]
        if errors:
            return "the recipe is invalid:\n" + "\n".join(f"- {e}" for e in errors[:8])
        _, _, log, effects, replayed, _ = run_recipe(self.practice, text, replay=True)
        lines = [
            f"practice run: {len(log.events)} trigger events: {log.count('ok')} ran, {log.count('filtered')} filtered "
            f"out, {log.count('failed')} failed",
        ]
        lines += [f"failed event {e.event_id}: {e.error[:200]}" for e in log.events if e.error][:3]
        effs = list(effects.elements())
        lines.append(f"effects ({len(effs)}):" if effs else "effects: none")
        lines += [f"- {' | '.join(str(x) for x in e)[:160]}" for e in effs[:10]]
        if len(effs) > 10:
            lines.append(f"... {len(effs) - 10} more")
        dups = sum((replayed - effects).values())
        if dups:
            lines.append(f"replaying the same events created {dups} duplicate effects")
        lines.append("Check these effects against the task description.")
        return "\n".join(lines)

    def _tool_submit(self) -> str:
        self.submitted = True
        return "submitted"


def _clip(s: str) -> str:
    return s if len(s) <= MAX_RESULT else s[:MAX_RESULT] + f"... [{len(s) - MAX_RESULT} more characters]"
