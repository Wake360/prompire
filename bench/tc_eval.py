#!/usr/bin/env python3
"""Offline task-compiler evaluation against the frozen tc_corpus.

Usage: python3 bench/tc_eval.py [--corpus bench/tc_corpus] [--only C01]
                                [--model MODEL] [--role-cmd CMD]
                                [--out bench/results/tc_eval.jsonl]
                                [--workdir DIR] [--keep]

Per task: clone the pinned revision, run `prompire compile` on the request
alone, then grade mechanically:
  HEAD arm   — compiled acceptance on the untouched pin        (must FAIL)
  GOLD arm   — pin + upstream fix patch                        (must PASS)
  WRONG arms — pin + each plausible wrong patch                (must FAIL)
The hidden facts, gold patch and wrong patches stay in this checkout; the
compiler roles run inside a snapshot of the task workspace and are never told
they exist. Semantic recovery against the hidden facts is graded separately
(`--grade`), by a fresh model session that sees only the frozen rubric, the
hidden facts and the compiled artifacts.

A NEEDS_DECISION contract is blind-confirmed before grading: marker lines and
undecided DECIDE placeholders are stripped, nothing is added — the human
stand-in supplies zero semantics, so whatever quality survives is the
compiler's own.
"""
import argparse
import json
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
import time

import yaml

SKILL = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL))

from brief_common import DRAFT_LEDGER, DRAFT_MARKER  # noqa: E402

MARKER_LINE = re.compile(rf"[ \t]*# {re.escape(DRAFT_MARKER)}[^\n]*")
COMPILE_TIMEOUT = 3600

def run(argv, cwd=None, env=None, timeout=600, input_text=None):
    done = subprocess.run(argv, cwd=cwd, env=env, capture_output=True,
                          text=True, encoding="utf-8", errors="replace",
                          timeout=timeout, input=input_text)
    return done


def clone_at(repo_url, rev, cache_dir, dest):
    cache = cache_dir / re.sub(r"[^A-Za-z0-9]+", "-", repo_url)
    if not cache.is_dir():
        r = run(["git", "clone", "--quiet", repo_url, str(cache)], timeout=600)
        if r.returncode:
            raise RuntimeError(f"clone failed: {r.stderr.strip()[:300]}")
    have = run(["git", "-C", str(cache), "cat-file", "-t", rev])
    if have.returncode:
        run(["git", "-C", str(cache), "fetch", "--quiet", "origin"], timeout=600)
    shutil.copytree(cache, dest, symlinks=True)
    r = run(["git", "-C", str(dest), "checkout", "--quiet", rev])
    if r.returncode:
        raise RuntimeError(f"checkout {rev} failed: {r.stderr.strip()[:300]}")
    run(["git", "-C", str(dest), "clean", "-fdq"])
    return dest


def apply_patch(tree, patch_path):
    r = run(["git", "-C", str(tree), "apply", "--whitespace=nowarn",
             str(patch_path)])
    return r.returncode == 0, r.stderr.strip()[:300]


def blind_confirm(brief_path):
    """Strip markers and undecided DECIDE placeholders; add nothing."""
    text = brief_path.read_text(encoding="utf-8")
    stripped, _ = MARKER_LINE.subn("", text)
    data = yaml.safe_load(stripped) or {}
    data.pop(DRAFT_LEDGER, None)
    constraints = [c for c in (data.get("constraints") or [])
                   if not str(c).startswith("DECIDE ")]
    if constraints:
        data["constraints"] = constraints
    else:
        data.pop("constraints", None)
    brief_path.write_text(
        yaml.safe_dump(data, allow_unicode=True, sort_keys=False),
        encoding="utf-8")


def acceptance_arm(tree, brief_rel):
    """pass/fail/error for the compiled acceptance run in this tree."""
    r = run([sys.executable, str(SKILL / "verify_acceptance.py"),
             brief_rel, "--json"], cwd=str(tree), timeout=900)
    try:
        data = json.loads(r.stdout)
    except (json.JSONDecodeError, ValueError):
        return "error", (r.stdout + r.stderr).strip()[:300]
    results = data.get("results") or []
    ok = bool(results) and all(row.get("ok") for row in results)
    return ("pass" if ok else "fail"), None


def grade_arms(workdir, task, spec_dir, compiled_dir):
    """Fresh tree per arm; the compiled .prompire artifacts copied in."""
    out = {}
    arms = [("head", None)]
    arms.append(("gold", spec_dir / task["gold"]))
    for i, wrong in enumerate(task.get("wrong") or []):
        arms.append((f"wrong{i}", spec_dir / wrong["patch"]))
    for arm, patch in arms:
        tree = workdir / f"arm-{arm}"
        clone_at(task["repo"], task["rev"], workdir.parent / "repo-cache", tree)
        if patch is not None:
            ok, why = apply_patch(tree, patch)
            if not ok:
                out[arm] = "patch-error"
                out[arm + "_error"] = why
                continue
        target = tree / ".prompire"
        shutil.copytree(compiled_dir, target)
        result, trouble = acceptance_arm(tree, ".prompire/task.yaml")
        out[arm] = result
        if trouble:
            out[arm + "_error"] = trouble
        shutil.rmtree(tree, ignore_errors=True)
    return out


def compile_one(task, workdir, role_args):
    workspace = workdir / "workspace"
    clone_at(task["repo"], task["rev"], workdir.parent / "repo-cache", workspace)
    started = time.monotonic()
    r = run([sys.executable, str(SKILL / "prompire.py"), "compile",
             task["request"], "--slug", "task", "--json"] + role_args,
            cwd=str(workspace), timeout=COMPILE_TIMEOUT)
    seconds = round(time.monotonic() - started, 1)
    try:
        data = json.loads(r.stdout.strip().splitlines()[-1])
    except (json.JSONDecodeError, ValueError, IndexError):
        return None, workspace, {
            "error": f"compile exit {r.returncode}: "
                     + (r.stdout + r.stderr).strip()[-400:],
            "seconds": seconds}
    data["seconds"] = seconds
    data["exit"] = r.returncode
    return data, workspace, None


def measure_baseline(tree, brief_rel):
    r = run([sys.executable, str(SKILL / "baseline.py"), brief_rel, "--write"],
            cwd=str(tree), timeout=900)
    if r.returncode:
        return f"baseline exit {r.returncode}: " + (r.stdout + r.stderr)[-300:]
    r = run([sys.executable, str(SKILL / "lint_brief.py"), brief_rel, "--json"],
            cwd=str(tree), timeout=300)
    try:
        lint = json.loads(r.stdout)
    except (json.JSONDecodeError, ValueError):
        return "lint produced no JSON"
    if lint.get("errors"):
        rules = sorted({f["rule"] for f in lint.get("findings", [])})
        return f"lint errors: {lint['errors']} ({', '.join(rules)})"
    return None


def quality_row(task, compiled, workspace, workdir, spec_dir):
    """The frozen quality gate, scored mechanically."""
    row = {"quality": False}
    state = compiled.get("status")
    if state not in ("ready", "needs_decision"):
        row["quality_reason"] = f"state {state}"
        return row
    brief = workspace / ".prompire" / "task.yaml"
    if state == "needs_decision":
        blind_confirm(brief)
    failure = measure_baseline(workspace, ".prompire/task.yaml")
    if failure:
        row["quality_reason"] = failure
        return row
    words = run([sys.executable, str(SKILL / "render_brief.py"),
                 ".prompire/task.yaml", "--target", "generic", "--words"],
                cwd=str(workspace))
    row["render_exit"] = words.returncode
    if words.returncode:
        row["quality_reason"] = "render over budget or failed"
        return row
    compiled_dir = workdir / "compiled-prompire"
    if compiled_dir.exists():
        shutil.rmtree(compiled_dir)
    shutil.copytree(workspace / ".prompire", compiled_dir)
    arms = grade_arms(workdir, task, spec_dir, compiled_dir)
    row["arms"] = arms
    wrong_arms = [k for k in arms if k.startswith("wrong") and
                  not k.endswith("_error")]
    row["quality"] = (arms.get("head") == "fail"
                      and arms.get("gold") == "pass"
                      and all(arms[k] == "fail" for k in wrong_arms))
    if not row["quality"]:
        row["quality_reason"] = "triple: " + json.dumps(
            {k: v for k, v in arms.items() if not k.endswith("_error")})
    row["trust_failure"] = (state == "ready" and arms.get("head") == "pass")
    return row


def load_tasks(corpus, only):
    tasks = []
    for path in sorted((corpus / "tasks").glob("*.yaml")):
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        if only and data.get("id") != only:
            continue
        tasks.append(data)
    return tasks


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--corpus", default=str(SKILL / "bench" / "tc_corpus"))
    parser.add_argument("--only", default=None)
    parser.add_argument("--model", default=None,
                        help="pin the role model (claude --model value)")
    parser.add_argument("--role-cmd", default=None)
    parser.add_argument("--out", default=str(SKILL / "bench" / "results"
                                             / "tc_eval.jsonl"))
    parser.add_argument("--workdir", default=None)
    parser.add_argument("--keep", action="store_true")
    args = parser.parse_args(argv)

    corpus = pathlib.Path(args.corpus)
    tasks = load_tasks(corpus, args.only)
    if not tasks:
        print("no tasks matched")
        return 2
    role_args = []
    if args.role_cmd:
        role_args = ["--role-cmd", args.role_cmd]
    elif args.model:
        role_args = ["--role-cmd",
                     "claude -p --setting-sources project --output-format json "
                     "--allowedTools Bash,Read,Glob,Grep --max-turns 80 "
                     f"--model {args.model}"]
    out_path = pathlib.Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    base = pathlib.Path(args.workdir) if args.workdir else pathlib.Path(
        tempfile.mkdtemp(prefix="tc-eval-"))
    base.mkdir(parents=True, exist_ok=True)
    errored = 0
    with open(out_path, "a", encoding="utf-8") as sink:
        for task in tasks:
            workdir = base / task["id"]
            workdir.mkdir(parents=True, exist_ok=True)
            row = {"task": task["id"], "repo": task["repo"],
                   "rev": task["rev"], "request": task["request"],
                   "ts": time.strftime("%Y-%m-%dT%H:%M:%S")}
            try:
                compiled, workspace, error = compile_one(task, workdir,
                                                         role_args)
                if error:
                    row.update(error)
                else:
                    row["state"] = compiled.get("status")
                    row["questions"] = len(compiled.get("questions") or [])
                    row["question_texts"] = [q.get("text") for q in
                                             (compiled.get("questions") or [])]
                    row["reason"] = compiled.get("reason")
                    row["rounds"] = compiled.get("rounds")
                    cost = compiled.get("cost") or {}
                    row["cost"] = {k: cost.get(k) for k in
                                   ("model_calls", "tokens_in", "tokens_out",
                                    "cost_usd", "probe_runs", "wall_seconds")}
                    row["seconds"] = compiled.get("seconds")
                    row.update(quality_row(task, compiled, workspace, workdir,
                                           corpus))
                    kept = out_path.parent / "tc_artifacts" / task["id"]
                    if (workspace / ".prompire").is_dir():
                        if kept.exists():
                            shutil.rmtree(kept)
                        shutil.copytree(workspace / ".prompire", kept)
            except Exception as exc:
                row["error"] = f"{type(exc).__name__}: {exc}"
            sink.write(json.dumps(row, ensure_ascii=False) + "\n")
            sink.flush()
            if row.get("error"):
                errored += 1
                print(f"ERR   {row['task']}: {row['error'][:200]}")
            else:
                print(f"{row['task']}  state={row.get('state')} "
                      f"quality={row.get('quality')} "
                      f"questions={row.get('questions')} "
                      f"trust_failure={row.get('trust_failure')} "
                      f"arms={json.dumps(row.get('arms') or {})}")
            if not args.keep:
                shutil.rmtree(workdir, ignore_errors=True)
    print(f"rows appended to {out_path}")
    return 1 if errored else 0


if __name__ == "__main__":
    sys.exit(main())
