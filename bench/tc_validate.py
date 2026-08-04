#!/usr/bin/env python3
"""Mechanical validation of tc_corpus deliverables before freezing.

Usage: python3 bench/tc_validate.py [--corpus bench/tc_corpus] [--only C01]

Per task, in fresh clones: the hidden check must exit non-zero at PIN, zero at
PIN+gold, and non-zero under every wrong patch; every patch must apply
cleanly; the request must be ≤ 15 words and must not name the fix commit.
Exit 0 = every task validated.
"""
import argparse
import json
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile

import yaml

SKILL = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL / "bench"))

from tc_eval import apply_patch, clone_at  # noqa: E402


def check_arm(tree, check_path):
    shutil.copy(check_path, tree / "_hidden_check.py")
    done = subprocess.run([sys.executable, "_hidden_check.py"], cwd=str(tree),
                          capture_output=True, text=True, timeout=300)
    (tree / "_hidden_check.py").unlink()
    return done.returncode, (done.stdout + done.stderr).strip()[-200:]


def validate(task, corpus, base):
    problems = []
    words = len(str(task.get("request") or "").split())
    if not 0 < words <= 15:
        problems.append(f"request is {words} words")
    facts = task.get("hidden_facts") or []
    if not any(f.get("omitted") for f in facts):
        problems.append("no omitted hidden fact")
    check = corpus / task["hidden_check"]
    gold = corpus / task["gold"]
    wrongs = [(w.get("class"), corpus / w["patch"])
              for w in (task.get("wrong") or [])]
    if len(wrongs) < 2:
        problems.append("fewer than two wrong patches")
    for label, path in [("hidden_check", check), ("gold", gold)] + [
            (f"wrong:{c}", p) for c, p in wrongs]:
        if not path.is_file():
            problems.append(f"{label} file missing: {path.name}")
    if problems:
        return problems, {}
    arms = {}
    tree = base / task["id"]
    for arm, patch in [("pin", None), ("gold", gold)] + [
            (f"wrong-{c}", p) for c, p in wrongs]:
        if tree.exists():
            shutil.rmtree(tree)
        clone_at(task["repo"], task["rev"], base / "repo-cache", tree)
        if patch is not None:
            ok, why = apply_patch(tree, patch)
            if not ok:
                problems.append(f"{arm} patch does not apply: {why}")
                continue
        code, tail = check_arm(tree, check)
        arms[arm] = code
        want_zero = arm == "gold"
        if (code == 0) != want_zero:
            problems.append(f"{arm}: hidden check exit {code} "
                            f"(want {'0' if want_zero else 'non-zero'}) — {tail}")
    shutil.rmtree(tree, ignore_errors=True)
    return problems, arms


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--corpus", default=str(SKILL / "bench" / "tc_corpus"))
    parser.add_argument("--only", default=None)
    parser.add_argument("--workdir", default=None)
    args = parser.parse_args(argv)
    corpus = pathlib.Path(args.corpus)
    base = pathlib.Path(args.workdir) if args.workdir else pathlib.Path(
        tempfile.mkdtemp(prefix="tc-validate-"))
    bad = 0
    for path in sorted((corpus / "tasks").glob("*.yaml")):
        task = yaml.safe_load(path.read_text(encoding="utf-8"))
        if args.only and task.get("id") != args.only:
            continue
        try:
            problems, arms = validate(task, corpus, base)
        except Exception as exc:
            problems, arms = [f"{type(exc).__name__}: {exc}"], {}
        if problems:
            bad += 1
            print(f"FAIL  {task.get('id')}")
            for problem in problems:
                print(f"      {problem}")
        else:
            print(f"PASS  {task['id']}  arms={json.dumps(arms)}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
