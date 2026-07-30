#!/usr/bin/env python3
"""The bench harness, measured offline against scripted agents.

Run: python3 tests/bench.py
Exit 0 = every seed brief survives baseline + activate + lint inside the fixture
repo. Later sections add the scripted-agent, variant and CLI checks. Never
invokes a live agent.
"""
import json
import pathlib
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
SKILL = HERE.parent
sys.path.insert(0, str(SKILL / "bench"))
sys.path.insert(0, str(SKILL))

import run as bench_run

TASKS = SKILL / "bench" / "tasks"
FAILS = 0
TOTAL = 0


def check(name, cond, detail=""):
    global FAILS, TOTAL
    TOTAL += 1
    if not cond:
        FAILS += 1
        print(f"FAIL  {name}")
        if detail:
            print(f"        {detail}")


def check_seed_briefs(tmp):
    for task in sorted(TASKS.glob("*.yaml")):
        repo, _ = bench_run.prepare(task, pathlib.Path(tmp) / task.stem)
        lint = subprocess.run([sys.executable, str(SKILL / "lint_brief.py"),
                               bench_run.BRIEF_REL], cwd=str(repo),
                              capture_output=True, text=True, encoding="utf-8")
        check(f"{task.stem} lints clean after baseline", lint.returncode == 0,
              lint.stdout.strip())


def main():
    with tempfile.TemporaryDirectory(prefix="prompire-bench-test-") as tmp:
        check_seed_briefs(tmp)
    print(f"{TOTAL - FAILS}/{TOTAL} bench harness checks pass")
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
