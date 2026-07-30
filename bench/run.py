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
import argparse
import hashlib
import json
import pathlib
import shutil
import subprocess
import sys
import tempfile
import time

SKILL = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL))
sys.path.insert(0, str(SKILL / "tests"))
sys.path.insert(0, str(SKILL / "bench"))

import fixtures
import verify_acceptance
from behaviors import BEHAVIORS
from brief_common import is_test_path, load_brief, norm_path, utf8_stdio
from variants import VARIANTS

BRIEF_REL = ".prompire/brief.yaml"
# Restored before every measurement — see run_cell.
GUARDED = (BRIEF_REL, ".prompire/ACTIVE")


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


def run_agent(spec, prompt, repo, task):
    if spec.startswith("scripted:"):
        behavior = spec.split(":", 1)[1]
        writes = BEHAVIORS.get(task, {}).get(behavior)
        if writes is None:
            raise RuntimeError(f"no scripted behavior {behavior!r} for {task}")
        for rel, body in writes.items():
            fixtures.write(repo, rel, body)
        return {"agent_exit": 0, "model": None, "turns": None,
                "tokens_in": None, "tokens_out": None}
    if spec == "claude":
        # --setting-sources project: the user's global CLAUDE.md, behaviour
        # profile and skills must not leak into a measured cell — the benchmark
        # compares prompts, not one machine's personal instructions.
        r = subprocess.run(["claude", "-p", "--output-format", "json",
                            "--permission-mode", "acceptEdits",
                            "--setting-sources", "project"],
                           cwd=str(repo), input=prompt, capture_output=True,
                           text=True, encoding="utf-8", timeout=900)
        usage, turns, model = {}, None, None
        try:
            data = json.loads(r.stdout)
            data = data if isinstance(data, dict) else {}
            usage = data.get("usage") or {}
            turns = data.get("num_turns")
            model = data.get("model")
        except ValueError:
            pass
        return {"agent_exit": r.returncode, "model": model, "turns": turns,
                "tokens_in": usage.get("input_tokens"),
                "tokens_out": usage.get("output_tokens")}
    raise RuntimeError(f"unknown agent {spec!r} — scripted:<behavior> or claude")


def measure(repo, base):
    """`base` is captured before the agent runs: the brief lives in .prompire/, which
    the scope check does not police, so an agent can re-stamp `base_rev` and delete the
    pin. Re-reading the base here would let it choose its own diff."""
    # baseline.py already compiled the untouched tree. CPython invalidates a .pyc on
    # (source mtime second, source size), so an edit of the same size inside that
    # second is invisible and the acceptance would score HEAD's bytecode instead of
    # the agent's file. __pycache__ is gitignored, so this changes no diff.
    for cache in repo.rglob("__pycache__"):
        shutil.rmtree(cache, ignore_errors=True)
    verdict = verify_acceptance.verify(str(repo / BRIEF_REL))
    scope = tool(repo, "check_scope.py", BRIEF_REL, "--json", "--base", base, "--strict")
    try:
        scope_report = json.loads(scope.stdout)
    except ValueError:
        # stderr too: a check_scope that crashed and a check_scope that found
        # something both leave a row without findings, and only the traceback
        # tells them apart.
        scope_report = {"raw": scope.stdout, "stderr": scope.stderr}
    changed = subprocess.run(["git", "-C", str(repo), "diff", "--name-only", base],
                             capture_output=True, text=True, encoding="utf-8")
    untracked = subprocess.run(["git", "-C", str(repo), "ls-files", "--others",
                                "--exclude-standard"],
                               capture_output=True, text=True, encoding="utf-8")
    if changed.returncode != 0 or untracked.returncode != 0:
        raise RuntimeError(f"git could not diff against {base}: "
                           f"{changed.stderr}{untracked.stderr}")
    paths = set(changed.stdout.split()) | set(untracked.stdout.split())
    return {"acceptance": {k: verdict[k] for k in ("passed", "failed", "not_run")},
            "scope_exit": scope.returncode,
            "scope_report": scope_report,
            "test_files_changed": sorted(p for p in paths
                                         if is_test_path(norm_path(p)))}


def prompire_rev():
    """Which Prompire produced this row — an installed skill copy without .git
    records None rather than a guess."""
    r = subprocess.run(["git", "-C", str(SKILL), "rev-parse", "--short", "HEAD"],
                       capture_output=True, text=True, encoding="utf-8")
    return r.stdout.strip() or None


def run_cell(task_path, variant, agent, keep=False):
    tmp = tempfile.mkdtemp(prefix="prompire-bench-")
    try:
        repo, brief = prepare(task_path, tmp)
        brief_data = load_brief(str(brief))
        base = str(brief_data.get("base_rev"))
        prompt = VARIANTS[variant](brief_data, BRIEF_REL)
        # `.prompire/` is gitignored, check_scope never judges paths inside it, and no
        # PreToolUse hook runs in a cell — a fixture repo has no project settings and
        # the live adapter passes `--setting-sources project`. So the brief and the pin
        # are agent-writable state: the criteria, the boundary and the record of both
        # are exactly what a gaming agent would rewrite. Measuring against the file as
        # the agent left it is measuring what the agent chose to be measured on, so
        # snapshot the pristine bytes here and put them back before measuring.
        pristine = {p: (repo / p).read_bytes() for p in GUARDED}
        t0 = time.monotonic()
        stats = run_agent(agent, prompt, repo, task_path.stem)
        tampered = sorted(p for p in GUARDED
                          if not (repo / p).is_file()
                          or (repo / p).read_bytes() != pristine[p])
        for p in tampered:
            (repo / p).parent.mkdir(parents=True, exist_ok=True)
            (repo / p).write_bytes(pristine[p])
        row = {"task": task_path.stem, "variant": variant, "agent": agent,
               "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
               "prompire_rev": prompire_rev(),
               "prompt_sha": hashlib.sha256(prompt.encode("utf-8")).hexdigest()[:12],
               "prompt_words": len(prompt.split()),
               "seconds": round(time.monotonic() - t0, 2),
               "tampered": tampered,
               **stats, **measure(repo, base)}
        if keep:
            row["repo"] = str(repo)
        return row
    finally:
        if not keep:
            shutil.rmtree(tmp, ignore_errors=True)


def main(argv=None):
    utf8_stdio()
    ap = argparse.ArgumentParser(
        description="task × variant × agent benchmark over the fixture repo")
    ap.add_argument("--tasks", default=str(SKILL / "bench" / "tasks"),
                    help="a task brief or a directory of them")
    ap.add_argument("--variants", default="current")
    ap.add_argument("--agents", default="scripted:good")
    ap.add_argument("--repeats", type=int, default=1,
                    help="runs per cell — live agents are stochastic; one run is noise")
    ap.add_argument("--out", default=str(SKILL / "bench" / "results" / "run.jsonl"))
    ap.add_argument("--keep", action="store_true",
                    help="keep each cell's repo for a post-mortem")
    ns = ap.parse_args(argv)
    tasks_path = pathlib.Path(ns.tasks)
    if not tasks_path.exists():
        print(f"no such path: {tasks_path}")
        return 2
    tasks = sorted(tasks_path.glob("*.yaml")) if tasks_path.is_dir() else [tasks_path]
    if not tasks:
        print(f"no task briefs under {tasks_path}")
        return 2
    out = pathlib.Path(ns.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    errs = 0
    with open(out, "a", encoding="utf-8") as fh:
        for task in tasks:
            for variant in (v for v in ns.variants.split(",") if v):
                for agent in (a for a in ns.agents.split(",") if a):
                    for rep in range(ns.repeats):
                        try:
                            row = run_cell(task, variant, agent, keep=ns.keep)
                        except Exception as e:
                            row, errs = {"task": task.stem, "variant": variant,
                                         "agent": agent, "error": str(e)}, errs + 1
                        row["rep"] = rep
                        fh.write(json.dumps(row, ensure_ascii=False) + "\n")
                        print(f"{'ERR' if row.get('error') else 'ok '}  "
                              f"{task.stem} × {variant} × {agent} #{rep}")
    print(f"rows appended to {out}")
    return 1 if errs else 0


if __name__ == "__main__":
    sys.exit(main())
