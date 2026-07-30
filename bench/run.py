#!/usr/bin/env python3
"""Behavioural benchmark: task briefs × prompt variants × agents, measured from outside.

Usage: python3 bench/run.py [--tasks bench/tasks|one.yaml] [--variants current]
                            [--agents scripted:good] [--out bench/results/run.jsonl]
                            [--keep]
Exit 0 = every cell ran and was measured, 1 = at least one cell errored, 2 = bad usage.

A cell is one task brief run through one prompt variant by one agent, in a fresh
fixture repo (tests/fixtures.py). The brief lives at .prompire/brief.yaml so the
brief itself never trips the scope check. After the agent stops, the measurement
is the same one a human would run: verify_acceptance + check_scope + the git
diff — nothing the agent reported is trusted. Live agents cost minutes and
money; tests/bench.py only ever runs scripted:* agents.
"""
import pathlib
import shutil
import subprocess
import sys

SKILL = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL))
sys.path.insert(0, str(SKILL / "tests"))
sys.path.insert(0, str(SKILL / "bench"))

import fixtures

BRIEF_REL = ".prompire/brief.yaml"


def tool(repo, name, *args):
    return subprocess.run([sys.executable, str(SKILL / name), *args],
                          cwd=str(repo), capture_output=True, text=True,
                          encoding="utf-8")


def prepare(task_path, workdir):
    """Fresh fixture repo with the task brief measured, armed and lintable."""
    repo = fixtures.build(pathlib.Path(workdir) / "repo")
    brief = repo / BRIEF_REL
    brief.parent.mkdir(exist_ok=True)
    shutil.copy(task_path, brief)
    for args in (("baseline.py", BRIEF_REL, "--write"),
                 ("check_scope.py", BRIEF_REL, "--activate")):
        r = tool(repo, *args)
        if r.returncode != 0:
            raise RuntimeError(f"{args[0]} failed for {task_path.name}: "
                               f"{r.stdout}{r.stderr}")
    return repo, brief
