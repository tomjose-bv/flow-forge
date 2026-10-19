"""Command-line entry point."""

from __future__ import annotations

import argparse
import json
import platform
from datetime import datetime, timezone
from pathlib import Path

from flow_forge import __version__


def meta(**extra) -> dict:
    return {
        "date": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "machine": f"{platform.system()} {platform.release()} {platform.machine()}",
        "processor": platform.processor(),
        "python": platform.python_version(),
        "version": __version__,
        **extra,
    }


def _reference_dir(root: Path, set_name: str) -> Path:
    base = root / "recipes" / "reference"
    return base / "heldout" if set_name == "heldout" else base


def cmd_eval(args) -> int:
    from flow_forge.harness import evaluate
    from flow_forge.task import load

    root = Path(args.root)
    files = sorted((root / "tasks" / args.set).glob("*.yaml"))
    if args.task:
        files = [f for f in files if f.stem in args.task]
    if not files:
        print("no tasks found")
        return 1
    ref_dir = _reference_dir(root, args.set)
    rec_dir = Path(args.recipe_dir) if args.recipe_dir else ref_dir
    print(f"{'task':<32} {'valid':>5} {'ok':>3} {'prec':>5} {'recall':>6} {'dup':>4} {'failed':>6}")
    reports = []
    for f in files:
        rec = rec_dir / f"{f.stem}.yaml"
        text = rec.read_text(encoding="utf-8") if rec.exists() else ""
        r = evaluate(load(f), text, (ref_dir / f"{f.stem}.yaml").read_text(encoding="utf-8"))
        reports.append(r.to_dict())
        print(f"{r.task:<32} {str(r.valid):>5} {'yes' if r.success else 'no':>3} {r.precision:>5.2f} {r.recall:>6.2f} "
              f"{r.duplicates_on_replay:>4} {r.events_failed:>6}")
        for e in (r.validation_errors or r.errors)[:2]:
            print(f"    {e[:150]}")
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(json.dumps({"meta": meta(set=args.set), "reports": reports}, indent=2),
                                  encoding="utf-8")
    return 0 if all(r["success"] for r in reports) else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="flow-forge")
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="command")
    ev = sub.add_parser("eval", help="score recipes against the reference recipes")
    ev.add_argument("--set", choices=("dev", "heldout"), default="dev")
    ev.add_argument("--task", action="append", help="limit to this task (repeatable)")
    ev.add_argument("--recipe-dir", help="directory with <task>.yaml recipes (default: the references)")
    ev.add_argument("--out", help="write a JSON report here")
    ev.add_argument("--root", default=".")
    cat = sub.add_parser("catalog", help="print the app catalog for a task")
    cat.add_argument("task", help="path to a task YAML")
    args = parser.parse_args(argv)
    if args.command == "eval":
        return cmd_eval(args)
    if args.command == "catalog":
        from flow_forge.catalog import render
        from flow_forge.task import load

        print(render(load(args.task).apps))
        return 0
    parser.print_help()
    return 0
