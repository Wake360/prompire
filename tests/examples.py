#!/usr/bin/env python3
"""Generate and verify `examples/` — the canonical shapes, with measured baselines.

Run: python3 tests/examples.py [--regenerate]
Exit 0 = every example lints clean and still reproduces the baseline it records.

No example baseline is written by hand. Each one is produced by running baseline.py
against the fixture repo, so the four shapes the schema has to express — an ordinary
green criterion, one that must flip, one that must hold, one that cannot run yet — are
demonstrated with numbers a reader can reproduce in one command.
"""
import json
import pathlib
import shutil
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
SKILL = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(SKILL))

import fixtures  # noqa: E402

import baseline as bl  # noqa: E402
from brief_common import baseline_map, entry_key, load_brief  # noqa: E402

EXAMPLES = SKILL / "examples"

HEADER = """# {name} — {blurb}
#
# The `baseline:` block below was measured, not written: it is what baseline.py
# recorded against the fixture repo in tests/fixtures.py. Reproduce with
#   python3 tests/examples.py --regenerate
"""

SPECS = [
    ("01-green-baseline", "an ordinary criterion that is green today and must stay green", """
goal: Add a count() helper to src/cart.py.
scope:
  - src/cart.py
forbidden:
  - tests/**
tests_policy: immutable
acceptance:
  - cmd: python3 -m unittest -q tests.test_cart
    expect: exit 0
manual_checks:
  - done: the diff adds count() to src/cart.py
autonomy: ask
"""),

    ("02-must-flip", "a criterion that is red today, and turning it green is the goal", """
goal: Fix the off-by-one in src/cart.total().
scope:
  - src/cart.py
forbidden:
  - tests/**
tests_policy: immutable
acceptance:
  - cmd: python3 -m unittest -q tests.test_total
    expect: exit 0
    transition: flip
  - cmd: python3 -m unittest -q tests.test_cart
    expect: exit 0
manual_checks:
  - read the diff of src/cart.py and confirm only the arithmetic moved
autonomy: ask
"""),

    ("03-known-red-hold", "a suite that fails today and must keep failing the same way", """
goal: Add a count() helper to src/cart.py without disturbing the legacy suite.
scope:
  - src/cart.py
forbidden:
  - tests/**
tests_policy: immutable
acceptance:
  - cmd: python3 -m unittest -q tests.test_cart
    expect: exit 0
  - cmd: python3 -m unittest -q tests.test_legacy
    expect: exit 1 — the one known failure, unchanged
    transition: hold
autonomy: ask
"""),

    ("04-not-yet-runnable", "a criterion that cannot run until the code exists", """
goal: Add src/render/text.py with a render() that takes report rows.
scope:
  - src/render/
forbidden:
  - tests/**
tests_policy: immutable
acceptance:
  - cmd: python3 -m unittest -q tests.test_cart
    expect: exit 0
  - cmd: python3 -c "import text; print(text.render([]))"
    cwd: src/render
    expect: exit 0
    transition: flip
autonomy: ask
"""),

    ("05-multiline-acceptance", "a multi-line command, measured and rendered verbatim", """
goal: Add a count() helper to src/cart.py.
scope:
  - src/cart.py
forbidden:
  - tests/**
tests_policy: immutable
acceptance:
  - cmd: |
      STATUS="cart  ok"
      test "$STATUS" = "cart  ok"
    expect: exit 0
  - cmd: python3 -m unittest -q tests.test_cart
    expect: exit 0
manual_checks:
  - done: the diff adds count() to src/cart.py
autonomy: ask
"""),

    ("worked-example", "the shape to copy: green, held and before/after in one brief", """
goal: Extract report rendering from src/report.py into src/render/text.py.
scope:
  - src/report.py
  - src/render/
forbidden:
  - tests/**
  - golden/**
constraints:
  - the report output stays byte-identical
  - no new third-party packages
tests_policy: immutable
plan_first: true
acceptance:
  - cmd: python3 -m src.report
    expect: exit 0, output identical to the baseline digest
    before_after: true
  - cmd: python3 -m unittest -q tests.test_cart
    expect: exit 0
  - cmd: python3 -m unittest -q tests.test_legacy
    expect: exit 1 — the one known failure, unchanged
    transition: hold
manual_checks:
  - open src/render/text.py and confirm it does not import src.report
autonomy: ask
context: |
  golden/report.txt holds the current output of `python3 -m src.report`.
"""),
]


def measure(repo, name, body):
    p = pathlib.Path(repo) / ".prompire" / f"{name}.yaml"
    p.parent.mkdir(exist_ok=True)
    p.write_text(body.lstrip(), encoding="utf-8")
    r = subprocess.run([sys.executable, str(SKILL / "baseline.py"), str(p), "--json"],
                       capture_output=True, text=True, encoding="utf-8")
    if r.returncode == 2:
        raise AssertionError(f"{name}: baseline refused: {r.stdout}{r.stderr}")
    return json.loads(r.stdout)


def compose(name, blurb, body, data):
    return (HEADER.format(name=name, blurb=blurb) + body.lstrip()
            + bl.render_block(data["results"], data["base_rev"]) + "\n")


def statuses(brief):
    out = {}
    for a in brief.get("acceptance") or []:
        e = baseline_map(brief).get(entry_key(a))
        if e:
            out[entry_key(a)] = (str(e.get("status")), "sha256:" in str(e.get("evidence") or ""))
    return out


def main():
    regen = "--regenerate" in sys.argv
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="prompire-examples-"))
    fails = 0
    EXAMPLES.mkdir(exist_ok=True)
    for name, blurb, body in SPECS:
        repo = fixtures.build(tmp / name)
        data = measure(repo, name, body)
        text = compose(name, blurb, body, data)
        target = EXAMPLES / f"{name}.yaml"
        if regen:
            target.write_text(text, encoding="utf-8")
            print(f"wrote {target.relative_to(SKILL)}")
            continue
        problems = []
        if not target.exists():
            problems.append("missing — run with --regenerate")
        else:
            committed = load_brief(str(target))
            fresh = load_brief(str(tmp / name / ".prompire" / f"{name}.yaml"))
            fresh["baseline"] = [
                {"cmd": r["cmd"], "cwd": r["cwd"], "status": r["status"],
                 "evidence": r.get("evidence", "")}
                for r in data["results"] if r["status"]]
            if statuses(committed) != statuses(fresh):
                problems.append(f"recorded {statuses(committed)} but a fresh measurement "
                                f"gives {statuses(fresh)}")
            r = subprocess.run([sys.executable, str(SKILL / "lint_brief.py"), str(target),
                                "--json"], capture_output=True, text=True, encoding="utf-8")
            lr = json.loads(r.stdout)
            if lr["errors"] or lr["warnings"]:
                problems.append(f"lints {lr['errors']}E/{lr['warnings']}W: "
                                + str([f["rule"] for f in lr["findings"]]))
        fails += 1 if problems else 0
        print(f"{'FAIL' if problems else 'pass'}  {name}")
        for p in problems:
            print(f"        {p}")
    shutil.rmtree(tmp, ignore_errors=True)
    if regen:
        return 0
    print(f"\n{len(SPECS) - fails}/{len(SPECS)} examples verified")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
