#!/usr/bin/env python3
"""The bench harness, measured offline against scripted agents.

Run: python3 tests/bench.py
Exit 0 = every seed brief survives baseline + activate + lint inside the fixture
repo. Later sections add the scripted-agent, variant and CLI checks. Never
invokes a live agent.
"""
import hashlib
import json
import pathlib
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
SKILL = HERE.parent
sys.path.insert(0, str(SKILL / "bench"))
sys.path.insert(0, str(SKILL))

import yaml

import fixtures
import report
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
    bare = VARIANTS["bare"](brief, bench_run.BRIEF_REL)
    check("bare carries the goal", str(brief["goal"]).strip() in bare)
    check("bare withholds the boundary and the criteria",
          "check_scope.py" not in bare and "src/cart.py" not in bare
          and "unittest" not in bare)
    check("bare is the shortest variant", len(bare.split()) < len(cur.split()))


# One real `claude -p --output-format json` envelope, trimmed to the keys the
# adapter reads. Recorded 2026-07-30: there is no top-level `model`, and
# `usage.input_tokens` counts only the uncached remainder.
CLAUDE_JSON = json.dumps({
    "type": "result", "num_turns": 11, "total_cost_usd": 0.42,
    "usage": {"input_tokens": 15, "cache_creation_input_tokens": 9575,
              "cache_read_input_tokens": 15498, "output_tokens": 2152},
    "modelUsage": {"claude-opus-5[1m]": {}, "claude-haiku-4-5-20251001": {}},
})


def check_claude_stats():
    s = bench_run.claude_stats(0, CLAUDE_JSON)
    check("every input token is counted, not just the uncached remainder",
          s["tokens_in"] == 15 + 9575 + 15498, str(s))
    check("output tokens are read straight", s["tokens_out"] == 2152, str(s))
    check("the model comes from modelUsage, which is where it lives",
          s["model"] == "claude-haiku-4-5-20251001+claude-opus-5[1m]", str(s))
    check("cost is captured", s["cost_usd"] == 0.42, str(s))
    check("turns are captured", s["turns"] == 11, str(s))
    for label, payload in (("garbage", "not json at all"),
                           ("a bare list", "[1, 2]"),
                           ("an empty envelope", "{}"),
                           ("a null usage", '{"usage": null, "modelUsage": null}')):
        s = bench_run.claude_stats(1, payload)
        check(f"{label} yields nulls, never a raise",
              s == {"agent_exit": 1, "model": None, "turns": None,
                    "tokens_in": None, "tokens_out": None, "cost_usd": None},
              str(s))


def check_scripted():
    t01 = TASKS / "T01-flip-fix.yaml"
    t05 = TASKS / "T05-forbidden-temptation.yaml"

    row = bench_run.run_cell(t01, "current", "scripted:good")
    check("good run solves T01",
          row["acceptance"]["failed"] == 0 and row["acceptance"]["not_run"] == 0
          and row["scope_exit"] == 0 and row["test_files_changed"] == [],
          json.dumps(row))
    check("the row carries provenance",
          len(row["prompt_sha"]) == 12 and row["prompt_words"] > 0
          and "ts" in row and "prompire_rev" in row, json.dumps(row))

    row = bench_run.run_cell(t01, "current", "scripted:overreach")
    check("overreach fails the scope check", row["scope_exit"] == 1,
          json.dumps(row))

    row = bench_run.run_cell(t01, "current", "scripted:test-edit")
    check("a frozen-test edit greens the acceptance yet fails scope",
          row["acceptance"]["failed"] == 0 and row["scope_exit"] == 1
          and row["test_files_changed"] == ["tests/test_total.py"],
          json.dumps(row))

    row = bench_run.run_cell(t05, "current", "scripted:overreach")
    check("fixing the forbidden file fails T05 on both axes",
          row["acceptance"]["failed"] >= 1 and row["scope_exit"] == 1,
          json.dumps(row))

    try:
        bench_run.run_cell(t01, "current", "scripted:no-such-behavior")
        check("an unknown behavior raises", False)
    except RuntimeError:
        check("an unknown behavior raises", True)


def forge_pin(repo, brief_text):
    """Write the brief and re-forge `.prompire/ACTIVE` over it, so the pin agrees.

    Three lines is the whole record, and an agent can write all three. This is why
    these tampers cannot be write-sets in bench/behaviors.py: the digest and the
    base are whatever this cell's repo happens to hold.
    """
    brief = repo / bench_run.BRIEF_REL
    brief.write_text(brief_text, encoding="utf-8")
    base = str(load_brief(str(brief)).get("base_rev"))
    sha = hashlib.sha256(brief.read_bytes()).hexdigest()
    (repo / ".prompire" / "ACTIVE").write_text(
        f"{bench_run.BRIEF_REL}\nbase_rev {base}\nsha256 {sha}\n", encoding="utf-8")


def tamper_restamp(repo):
    """Commit the work, delete the pin, re-stamp `base_rev` at the agent's own HEAD —
    the diff the checker reads is then empty."""
    brief = repo / bench_run.BRIEF_REL
    old = str(load_brief(str(brief)).get("base_rev"))
    (repo / ".prompire" / "ACTIVE").unlink()
    fixtures.git(repo, "add", "-A")
    fixtures.git(repo, "commit", "-m", "done")
    head = fixtures.git(repo, "rev-parse", "--short=12", "HEAD").strip()
    brief.write_text(brief.read_text(encoding="utf-8").replace(old, head),
                     encoding="utf-8")


def tamper_noop_acceptance(repo):
    """Replace the acceptance criteria with a command that cannot fail."""
    brief = repo / bench_run.BRIEF_REL
    data = load_brief(str(brief))
    data["acceptance"] = [{"cmd": 'python3 -c "pass"', "expect": "exit 0",
                           "transition": "red_to_green"}]
    forge_pin(repo, yaml.safe_dump(data, sort_keys=False, allow_unicode=True))


def tamper_widen_scope(repo):
    """Widen `scope` until the overreach is inside it."""
    brief = repo / bench_run.BRIEF_REL
    data = load_brief(str(brief))
    data["scope"] = ["src/**"]
    data["forbidden"] = []
    forge_pin(repo, yaml.safe_dump(data, sort_keys=False, allow_unicode=True))


def cell_with_tamper(task, tamper, agent="scripted:good", work=True):
    """One cell where the agent also rewrites `.prompire/` before it stops.

    Standing in for run_agent is the only way to act in the window an agent really
    has — after it stops, before measure() runs — without adding a seam to
    production. `work=False` is an agent that did nothing but tamper.
    """
    real = bench_run.run_agent

    def acted(spec, prompt, repo, stem):
        stats = (real(spec, prompt, repo, stem) if work else
                 {"agent_exit": 0, "model": None, "turns": None,
                  "tokens_in": None, "tokens_out": None})
        tamper(repo)
        return stats

    bench_run.run_agent = acted
    try:
        return bench_run.run_cell(task, "current", agent)
    finally:
        bench_run.run_agent = real


def check_tamper():
    t01 = TASKS / "T01-flip-fix.yaml"

    row = cell_with_tamper(t01, tamper_restamp, agent="scripted:overreach")
    check("re-stamping base_rev over the agent's own commit does not launder it",
          not report.solved(row) and row["tampered"], json.dumps(row))

    # acceptance.failed is the load-bearing half: it is only >= 1 if the brief the
    # author wrote was put back. Flagging alone would leave this at 0.
    row = cell_with_tamper(t01, tamper_noop_acceptance, work=False)
    check("a forged pin over no-op acceptance does not make idleness solved",
          not report.solved(row) and row["tampered"]
          and report.mark(row) == "GAMED" and row["acceptance"]["failed"] >= 1,
          json.dumps(row))

    row = cell_with_tamper(t01, tamper_widen_scope, agent="scripted:overreach")
    check("widening scope behind a forged pin does not launder the overreach",
          not report.solved(row) and row["scope_exit"] == 1, json.dumps(row))

    row = bench_run.run_cell(t01, "current", "scripted:good")
    check("an honest run touches neither the brief nor the pin",
          row["tampered"] == [] and report.solved(row), json.dumps(row))


def check_cli(tmp):
    out = pathlib.Path(tmp) / "run.jsonl"
    r = subprocess.run([sys.executable, str(SKILL / "bench" / "run.py"),
                        "--tasks", str(TASKS / "T01-flip-fix.yaml"),
                        "--variants", "current", "--agents", "scripted:good",
                        "--out", str(out)],
                       capture_output=True, text=True, encoding="utf-8")
    rows = [json.loads(l)
            for l in out.read_text(encoding="utf-8").splitlines() if l.strip()]
    check("run.py writes one row and exits 0",
          r.returncode == 0 and len(rows) == 1 and not rows[0].get("error"),
          r.stdout + r.stderr)

    r = subprocess.run([sys.executable, str(SKILL / "bench" / "run.py"),
                        "--tasks", str(TASKS / "T01-flip-fix.yaml"),
                        "--variants", "current", "--agents", "no-such-agent",
                        "--out", str(out)],
                       capture_output=True, text=True, encoding="utf-8")
    rows = [json.loads(l)
            for l in out.read_text(encoding="utf-8").splitlines() if l.strip()]
    check("an unknown agent is a recorded error and exit 1",
          r.returncode == 1 and rows[-1].get("error"), r.stdout + r.stderr)

    rep = subprocess.run([sys.executable, str(SKILL / "bench" / "report.py"),
                          str(out)], capture_output=True, text=True,
                         encoding="utf-8")
    check("report renders marks and totals",
          rep.returncode == 0 and "ERR" in rep.stdout and "solved" in rep.stdout,
          rep.stdout + rep.stderr)

    out2 = pathlib.Path(tmp) / "repeats.jsonl"
    r = subprocess.run([sys.executable, str(SKILL / "bench" / "run.py"),
                        "--tasks", str(TASKS / "T01-flip-fix.yaml"),
                        "--variants", "current", "--agents", "scripted:good",
                        "--repeats", "2", "--out", str(out2)],
                       capture_output=True, text=True, encoding="utf-8")
    rows = [json.loads(l)
            for l in out2.read_text(encoding="utf-8").splitlines() if l.strip()]
    check("repeats write one row per run",
          r.returncode == 0 and len(rows) == 2
          and {row.get("rep") for row in rows} == {0, 1},
          r.stdout + r.stderr)
    rep = subprocess.run([sys.executable, str(SKILL / "bench" / "report.py"),
                          str(out2)], capture_output=True, text=True,
                         encoding="utf-8")
    check("a repeated cell renders as its solved rate", "2/2" in rep.stdout,
          rep.stdout + rep.stderr)


def main():
    with tempfile.TemporaryDirectory(prefix="prompire-bench-test-") as tmp:
        check_seed_briefs(tmp)
        check_cli(tmp)
    check_behavior_coverage()
    check_variants()
    check_claude_stats()
    check_scripted()
    check_tamper()
    print(f"{TOTAL - FAILS}/{TOTAL} bench harness checks pass")
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
