#!/usr/bin/env python3
"""Semantic-recovery grading for tc_eval runs.

Usage: python3 bench/tc_grade.py [--corpus bench/tc_corpus]
                                 [--artifacts bench/results/tc_artifacts]
                                 [--model MODEL] [--out bench/results/tc_grades.jsonl]

For each corpus task with compiled artifacts, a fresh model session receives
only the frozen rubric, the task's hidden facts, and the compiled contract
(requirements + constraints from the ledger and brief, plus the probe source).
It never sees the gold patch, the wrong patches, or the compiler transcript.
Task-level recovery (preregistered): every omitted fact at least partial, at
least one omitted fact recovered, no omitted fact missed.
"""
import argparse
import json
import pathlib
import re
import subprocess
import sys

import yaml

SKILL = pathlib.Path(__file__).resolve().parent.parent

RUBRIC = """\
You are grading a task-compiler run. Judge only what is written below; do not
guess intent. For each hidden fact, decide whether the compiled contract
captures it:
- recovered: the fact is stated or executably checked, in its full generality
- partial: a narrower version is captured (one case, one sign, one path)
- missed: not captured at all
Reply with ONE yaml document only — a list, one item per fact, in order:
- {grade: recovered|partial|missed, where: <one line pointing at the evidence>}

Hidden facts:
{facts}

Compiled contract (goal, scope, constraints, acceptance):
{brief}

Compiler decision ledger (requirement claims):
{claims}

Probe source (the executable acceptance):
{probe}
"""


def fill(template, **values):
    for key, value in values.items():
        template = template.replace("{" + key + "}", str(value))
    return template


def strip_fences(text):
    lines = str(text or "").strip().splitlines()
    if lines and lines[0].startswith("```"):
        lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
    return "\n".join(lines)


def grade_task(task, artifacts, model, timeout=600):
    brief_path = artifacts / "task.yaml"
    ledger_path = artifacts / "task.ledger.yaml"
    probe_path = artifacts / "probes" / "task.py"
    if not brief_path.is_file():
        return {"task": task["id"], "error": "no compiled brief"}
    facts = [f for f in task.get("hidden_facts", []) if f.get("omitted")]
    if not facts:
        return {"task": task["id"], "error": "no omitted facts recorded"}
    ledger = {}
    if ledger_path.is_file():
        ledger = yaml.safe_load(ledger_path.read_text(encoding="utf-8")) or {}
    claims = [f"- {d.get('id')}: {d.get('claim')}"
              for d in (ledger.get("decisions") or [])
              if d.get("claim")]
    prompt = fill(
        RUBRIC,
        facts="\n".join(f"{i + 1}. {f['fact']}" for i, f in enumerate(facts)),
        brief=brief_path.read_text(encoding="utf-8"),
        claims="\n".join(claims) or "(none)",
        probe=(probe_path.read_text(encoding="utf-8")
               if probe_path.is_file() else "(no probe file)"))
    argv = ["claude", "-p", "--setting-sources", "project",
            "--output-format", "json"]
    if model:
        argv += ["--model", model]
    done = subprocess.run(argv, input=prompt, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=timeout)
    if done.returncode:
        return {"task": task["id"],
                "error": f"grader exited {done.returncode}"}
    try:
        wrapper = json.loads(done.stdout)
        reply = wrapper.get("result") if isinstance(wrapper, dict) else done.stdout
    except (json.JSONDecodeError, ValueError):
        reply = done.stdout
    try:
        graded = yaml.safe_load(strip_fences(reply))
    except yaml.YAMLError:
        graded = None
    if not isinstance(graded, list) or len(graded) != len(facts):
        return {"task": task["id"], "error": "grader reply unusable",
                "raw": str(reply)[:400]}
    rows = []
    for fact, item in zip(facts, graded):
        grade = str((item or {}).get("grade") or "").strip().lower()
        if grade not in ("recovered", "partial", "missed"):
            grade = "missed"
        rows.append({"fact": fact["fact"], "grade": grade,
                     "where": str((item or {}).get("where") or "")[:200]})
    grades = [r["grade"] for r in rows]
    recovery = ("missed" not in grades) and ("recovered" in grades)
    return {"task": task["id"], "facts": rows, "recovery_pass": recovery}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--corpus", default=str(SKILL / "bench" / "tc_corpus"))
    parser.add_argument("--artifacts",
                        default=str(SKILL / "bench" / "results"
                                    / "tc_artifacts"))
    parser.add_argument("--model", default=None)
    parser.add_argument("--only", default=None)
    parser.add_argument("--out", default=str(SKILL / "bench" / "results"
                                             / "tc_grades.jsonl"))
    args = parser.parse_args(argv)
    corpus = pathlib.Path(args.corpus)
    artifacts_root = pathlib.Path(args.artifacts)
    out_path = pathlib.Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    errored = 0
    with open(out_path, "a", encoding="utf-8") as sink:
        for path in sorted((corpus / "tasks").glob("*.yaml")):
            task = yaml.safe_load(path.read_text(encoding="utf-8"))
            if args.only and task.get("id") != args.only:
                continue
            row = grade_task(task, artifacts_root / task["id"], args.model)
            sink.write(json.dumps(row, ensure_ascii=False) + "\n")
            sink.flush()
            if row.get("error"):
                errored += 1
                print(f"ERR   {row['task']}: {row['error']}")
            else:
                print(f"{row['task']}  recovery_pass={row['recovery_pass']}  "
                      + " ".join(r["grade"][0].upper() for r in row["facts"]))
    print(f"rows appended to {out_path}")
    return 1 if errored else 0


if __name__ == "__main__":
    sys.exit(main())
