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
from behaviors import BEHAVIORS
from brief_common import load_brief
from variants import VARIANTS

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


def check_behavior_coverage():
    missing = sorted(t.stem for t in TASKS.glob("*.yaml")
                     if "good" not in BEHAVIORS.get(t.stem, {}))
    check("every task has a scripted good behavior", not missing, str(missing))


def check_variants():
    brief = load_brief(str(TASKS / "T01-flip-fix.yaml"))
    cur = VARIANTS["current"](brief, bench_run.BRIEF_REL)
    per = VARIANTS["persona"](brief, bench_run.BRIEF_REL)
    check("current names the external check", "check_scope.py" in cur)
    check("current carries no persona", "senior engineer" not in cur.lower())
    check("persona is current plus its one header",
          per != cur and per.endswith(cur))


def main():
    with tempfile.TemporaryDirectory(prefix="prompire-bench-test-") as tmp:
        check_seed_briefs(tmp)
    check_behavior_coverage()
    check_variants()
    print(f"{TOTAL - FAILS}/{TOTAL} bench harness checks pass")
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
