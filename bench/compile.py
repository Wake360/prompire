#!/usr/bin/env python3
"""Compiler-stage harness: short intent → compiled contract, scored against hidden gold.

Usage: python3 bench/compile.py [--tasks bench/compile_tasks.yaml] [--only NAME]
                                [--backend deterministic|gold|cmd:<shell>]
                                [--out bench/results/compile.jsonl] [--keep]
Exit 0 = every task compiled and was scored, 1 = at least one task errored, 2 = bad usage.

This is the compile half of E1, runnable without a paid execution arm. For each task:
build a fresh fixture repo, run a compiler backend on the request alone, mechanically
blind-confirm the draft (strip every `# prompire:unconfirmed` marker, logging how many
human decisions that stood in for), measure and lint it with the real tools, and check
the discrimination triple — the compiled acceptance run on untouched HEAD, on the gold
write-set, and on the wrong write-set. A behavioral contract should read fail / pass /
fail; one that reads pass everywhere cannot tell done from untouched.

The gold contract and both write-sets stay in this repository, outside the fixture repo
the backend inspects: nothing the harness hands a backend names them, and no route it
provides reaches them. That is isolation of the *fixture tree*, not a sandbox — a
`cmd:` backend with filesystem access to this checkout can read `bench/tasks/` for
itself, and a hostile one is trusted code by construction. Run untrusted backends with
this checkout out of reach. Backends:
`deterministic` is `prompire draft` with no model; `gold` compiles the gold brief's own
fields through `--proposal` (a ceiling: what a perfect proposer would score, still
subject to the same gate); `cmd:<shell>` hands the request to any drafting command via
`--agent-cmd` — a scripted stand-in offline, a live host model for a real E1 arm.

Scope coverage is a pattern-vs-pattern comparison and deliberately rough: an entry
counts as covering a gold entry when either glob matches the other spelled as a path.
"""
import argparse
import json
import pathlib
import re
import subprocess
import sys
import tempfile
import time

import yaml

SKILL = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL / "prompire"))
sys.path.insert(0, str(SKILL / "tests"))
sys.path.insert(0, str(SKILL / "bench"))

import fixtures
import verify_acceptance
from behaviors import BEHAVIORS
from brief_common import (DRAFT_LEDGER, DRAFT_MARKER, acceptance_entries, as_list,
                          effective_transition, glob_re, load_brief,
                          manual_check_entries, norm_cmd, norm_path, utf8_stdio)
from cli import DRAFT_KEYS, detect_acceptance

BRIEF_REL = ".prompire/task.yaml"
MARKER_LINE = re.compile(rf"[ \t]*# {re.escape(DRAFT_MARKER)}[^\n]*")


def tool(repo, name, *args):
    return subprocess.run([sys.executable, str(SKILL / "prompire" / name), *args],
                          cwd=str(repo), capture_output=True, text=True,
                          encoding="utf-8", errors="replace")


def covers(pattern, other):
    """Does one scope spelling cover the other? Pattern-vs-pattern, both directions."""
    a, b = str(pattern), str(other)
    if norm_path(a) == norm_path(b):
        return True
    try:
        return bool(glob_re(a).match(norm_path(b)) or glob_re(b).match(norm_path(a)))
    except re.error:
        return False


def run_backend(backend, request, repo):
    """Invoke the compiler frontend; returns (draft_json, error)."""
    argv = [sys.executable, str(SKILL / "prompire" / "cli.py"), "draft", request, "--json"]
    proposal_file = None
    if backend == "gold":
        # The gold brief's proposable fields, through the same gate as any model
        # reply. Written outside the repo: the fixture tree never holds gold data.
        gold = load_brief(str(run_backend.gold_path))
        proposal = {k: gold[k] for k in DRAFT_KEYS if k in gold}
        proposal_file = pathlib.Path(tempfile.mkstemp(prefix="prompire-gold-",
                                                      suffix=".yaml")[1])
        proposal_file.write_text(yaml.safe_dump(proposal, allow_unicode=True,
                                                sort_keys=False), encoding="utf-8")
        argv += ["--proposal", str(proposal_file)]
    elif backend.startswith("cmd:"):
        argv += ["--agent-cmd", backend[4:]]
    elif backend != "deterministic":
        return None, f"unknown backend `{backend}`"
    try:
        r = subprocess.run(argv, cwd=str(repo), capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
    finally:
        if proposal_file is not None:
            proposal_file.unlink(missing_ok=True)
    if r.returncode != 0:
        return None, f"draft exited {r.returncode}: {r.stdout.strip()[:300]}"
    try:
        return json.loads(r.stdout), None
    except json.JSONDecodeError:
        return None, f"draft --json did not emit JSON: {r.stdout[:200]!r}"


def score_compiled(repo, compiled, gold):
    """Compiler quality vs the hidden gold contract."""
    gold_scope = [str(s) for s in as_list(gold.get("scope"))]
    gold_allowed = gold_scope + [str(t) for t in as_list(gold.get("tests_editable"))]
    scope = [str(s) for s in as_list(compiled.get("scope"))]
    missing = [g for g in gold_scope if not any(covers(c, g) for c in scope)]
    extra = [c for c in scope if not any(covers(c, g) for g in gold_allowed)]
    evidenced = {norm_cmd(cmd) for cmd, _ in detect_acceptance(repo)}
    gold_cmds = {norm_cmd(a.get("cmd")) for a in acceptance_entries(gold)}
    invented = sorted(norm_cmd(a.get("cmd")) for a in acceptance_entries(compiled)
                      if norm_cmd(a.get("cmd")) not in evidenced
                      and norm_cmd(a.get("cmd")) not in gold_cmds)
    return {
        "scope_missing": missing,
        "scope_extra": extra,
        "invented_cmds": invented,
        "tests_policy": {"gold": gold.get("tests_policy"),
                         "compiled": compiled.get("tests_policy")},
    }


def blind_confirm(brief_path):
    """Stand in for the human confirmer: accept every marked line, on the record.

    E1's blind confirmer is a person; offline, the harness confirms everything and
    reports how many decisions that swallowed — a backend that hides decisions from
    the marker gate shows up here as a suspiciously low count, not as a clean run.
    Both records are cleared: the comment markers a reader sees and the
    `unconfirmed:` ledger that survives a round-trip. The count comes from the
    ledger, which is the one a serialization step cannot quietly shorten.
    """
    text = brief_path.read_text(encoding="utf-8")
    data = yaml.safe_load(text) or {}
    decisions = len(as_list(data.get(DRAFT_LEDGER))) if DRAFT_LEDGER in data else 0
    stripped, marked = MARKER_LINE.subn("", text)
    body = yaml.safe_load(stripped) or {}
    body.pop(DRAFT_LEDGER, None)
    brief_path.write_text(yaml.safe_dump(body, allow_unicode=True, sort_keys=False),
                          encoding="utf-8")
    return max(decisions, marked)


def acceptance_arm(brief_path):
    """One arm of the triple: pass / fail / error from the compiled acceptance."""
    try:
        result = verify_acceptance.verify(str(brief_path))
    except Exception as exc:  # a broken compiled contract is a result, not a crash
        return "error", str(exc)[:200]
    ok = bool(result["results"]) and result["passed"] == len(result["results"])
    return ("pass" if ok else "fail"), None


def triple(workdir, brief_path, gold_writes, wrong_writes):
    """Untouched HEAD, gold write-set, wrong write-set — three fresh repos, one brief.

    The fixture pins its commit metadata, so every build shares the same commit hash
    and the measured base_rev in the brief holds in all three."""
    out = {}
    for arm, writes in (("head", {}), ("gold", gold_writes), ("wrong", wrong_writes)):
        repo = fixtures.build(pathlib.Path(workdir) / f"triple-{arm}")
        target = repo / BRIEF_REL
        target.parent.mkdir(exist_ok=True)
        target.write_text(brief_path.read_text(encoding="utf-8"), encoding="utf-8")
        for rel, body in writes.items():
            fixtures.write(repo, rel, body)
        out[arm], trouble = acceptance_arm(target)
        if trouble:
            out[arm + "_error"] = trouble
    return out


def classify(compiled, lint_data):
    if lint_data.get("errors"):
        return "rejected"
    flips = any(effective_transition(a) == "flip"
                for a in acceptance_entries(compiled))
    if flips:
        return "discriminating"
    # Only the human-written `done:` spelling makes a manual check the completion
    # condition (B17); a note that merely exists no longer classifies the contract.
    if any(carries for _, carries, _ in manual_check_entries(compiled)):
        return "manual-semantic"
    return "preservation-only"


def run_task(name, spec, backend, workdir):
    started = time.monotonic()
    gold_path = SKILL / "bench" / "tasks" / f"{name}.yaml"
    gold = load_brief(str(gold_path))
    run_backend.gold_path = gold_path
    repo = fixtures.build(pathlib.Path(workdir) / "repo")

    drafted, error = run_backend(backend, spec["request"], repo)
    if error:
        return {"task": name, "backend": backend, "request": spec["request"],
                "error": error}
    brief = repo / BRIEF_REL
    compiled = load_brief(str(brief))
    row = {
        "task": name, "backend": backend, "request": spec["request"],
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "unconfirmed": drafted.get("unconfirmed"),
        "corroborated": drafted.get("corroborated"),
        "compile_seconds": drafted.get("seconds"),
        **score_compiled(repo, compiled, gold),
    }
    row["blind_confirmed"] = blind_confirm(brief)

    measured = tool(repo, "baseline.py", BRIEF_REL, "--write")
    if measured.returncode:
        row.update({"lint": None, "triple": None, "classification": "rejected",
                    "baseline_error": (measured.stdout + measured.stderr)[-300:]})
        row["seconds"] = round(time.monotonic() - started, 2)
        return row
    linted = tool(repo, "lint_brief.py", BRIEF_REL, "--json")
    lint_data = json.loads(linted.stdout)
    row["lint"] = {"errors": lint_data["errors"], "warnings": lint_data["warnings"],
                   "rules": sorted({f["rule"] for f in lint_data["findings"]})}
    compiled = load_brief(str(brief))  # now carries the measured baseline
    row["classification"] = classify(compiled, lint_data)
    if row["classification"] == "rejected":
        row["triple"] = None
    else:
        wrong_task, wrong_set = spec["wrong"]
        row["triple"] = triple(workdir, brief,
                               BEHAVIORS[name]["good"],
                               BEHAVIORS[wrong_task][wrong_set])
    row["seconds"] = round(time.monotonic() - started, 2)
    return row


def main(argv=None):
    utf8_stdio()
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--tasks", default=str(SKILL / "bench" / "compile_tasks.yaml"))
    parser.add_argument("--only", default=None)
    parser.add_argument("--backend", default="deterministic")
    parser.add_argument("--out", default=str(SKILL / "bench" / "results"
                                             / "compile.jsonl"))
    parser.add_argument("--keep", action="store_true")
    args = parser.parse_args(argv)

    try:
        specs = yaml.safe_load(pathlib.Path(args.tasks).read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        print(f"cannot read {args.tasks}: {exc}")
        return 2
    if args.only:
        if args.only not in specs:
            print(f"unknown task `{args.only}`; known: {', '.join(sorted(specs))}")
            return 2
        specs = {args.only: specs[args.only]}

    out_path = pathlib.Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    errored = 0
    with open(out_path, "a", encoding="utf-8") as sink:
        for name, spec in specs.items():
            workdir = pathlib.Path(tempfile.mkdtemp(prefix=f"prompire-compile-{name}-"))
            try:
                row = run_task(name, spec, args.backend, workdir)
            except Exception as exc:
                row = {"task": name, "backend": args.backend,
                       "error": f"{type(exc).__name__}: {exc}"}
            finally:
                if args.keep:
                    print(f"kept: {workdir}")
                else:
                    import shutil
                    shutil.rmtree(workdir, ignore_errors=True)
            sink.write(json.dumps(row, ensure_ascii=False) + "\n")
            if row.get("error"):
                errored += 1
                print(f"ERR   {name}: {row['error']}")
            else:
                t = row.get("triple") or {}
                print(f"{row['classification']:17s} {name}  "
                      f"markers={row['blind_confirmed']} "
                      f"lint={row['lint']['errors']}E/{row['lint']['warnings']}W "
                      f"triple={t.get('head', '-')}/{t.get('gold', '-')}"
                      f"/{t.get('wrong', '-')} "
                      f"missing={len(row['scope_missing'])} "
                      f"extra={len(row['scope_extra'])} "
                      f"invented={len(row['invented_cmds'])}")
    print(f"rows appended to {out_path}")
    return 1 if errored else 0


if __name__ == "__main__":
    sys.exit(main())
