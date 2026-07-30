#!/usr/bin/env python3
"""Adversarial battery for lint_brief.py. Run: python3 tests/battery.py

Each case declares which rule ids MUST fire as errors, which MUST fire as warnings, and
which must not fire at all. Prints a pass/fail table and exits 1 if any case fails.

This file is about the linter's judgement on a YAML string. Whether the skill actually
works — measured baselines, a guard that catches an out-of-scope edit — is tests/e2e.py.
"""
import json
import pathlib
import subprocess
import sys
import tempfile

LINT = pathlib.Path(__file__).resolve().parent.parent / "lint_brief.py"
TMP = pathlib.Path(tempfile.mkdtemp(prefix="prompire-cases-"))

# (name, yaml, must_fire_as_error, must_fire_as_warning, must_not_fire_at_all)
CASES = [
    ("clean-nontest-checks", """
goal: Add a --json flag to the report CLI.
scope: [src/cli/report.py]
forbidden: [tests/**]
acceptance:
  - cmd: ruff check src/cli/report.py
    expect: exit 0
  - cmd: python -m src.cli.report --json
    expect: valid JSON on stdout
autonomy: ask
""", [], [], ["B7", "B10", "B14", "B3"]),

    ("dependency-bump-modernize", """
goal: Bump the modernize-py dependency from 1.2 to 2.0 in requirements.txt.
scope: [requirements.txt]
forbidden: [tests/**]
acceptance:
  - cmd: pip install -r requirements.txt
    expect: exit 0
autonomy: ask
""", [], [], ["B3", "B10", "B14"]),

    ("export-support-not-a-port", """
goal: Add CSV export support to the reporting endpoint.
scope: [src/api/reports.py]
forbidden: [tests/**]
acceptance:
  - cmd: curl -s localhost:8000/reports.csv
    expect: exit 0
autonomy: ask
""", [], [], ["B10", "B14", "B3"]),

    ("tests-pinned-by-constraint", """
goal: Fix the off-by-one in the pagination cursor.
scope: [src/api/paging.py]
constraints:
  - do not modify tests
acceptance:
  - cmd: pytest -q tests/test_paging.py
    expect: exit 0
autonomy: ask
""", [], [], ["B7"]),

    ("tests-unpinned-npm", """
goal: Fix the flaky retry in the upload client.
scope: [src/upload.ts]
forbidden: [src/legacy/**]
acceptance:
  - cmd: npm test
    expect: exit 0
autonomy: ask
""", ["B7"], [], []),

    ("czech-brief-clean", """
goal: Přidej validaci IČO do registračního formuláře.
scope: [src/forms/register.py]
forbidden: [tests/**]
acceptance:
  - cmd: pytest -q tests/test_register.py
    expect: exit 0
autonomy: ask
""", [], [], ["B3", "B7", "B10"]),

    ("czech-brief-vague", """
goal: Uprav registrační formulář pořádně, ať to funguje správně.
scope: [src/forms/register.py]
acceptance: []
autonomy: ask
""", ["B3", "B4"], [], []),

    ("autonomy-capitalised", """
goal: Regenerate the API client from the OpenAPI schema.
scope: [src/client/]
forbidden: [tests/**]
acceptance:
  - cmd: mypy src/client
    expect: exit 0
autonomy: ASK
""", [], [], ["B8"]),

    ("auto-with-rollback-ok", """
goal: Delete the dead jinja rendering path from the invoice module.
scope: [src/render/invoice.py]
forbidden: [tests/**]
acceptance:
  - cmd: pytest -q tests/test_invoices.py
    expect: exit 0
  - cmd: rg -n jinja src/render/
    expect: no matches
autonomy: auto
rollback: branch chore/drop-jinja
""", [], [], ["B8", "B9"]),

    ("scope-glob-ok", """
goal: Replace print calls with structured logging in the ingest package.
scope: [src/ingest/**]
forbidden: [tests/**]
acceptance:
  - cmd: rg -n "print\\(" src/ingest/
    expect: no matches
autonomy: ask
""", [], [], ["B6"]),

    ("acceptance-mapping-not-list", """
goal: Add a healthcheck endpoint.
scope: [src/api/health.py]
acceptance:
  first:
    cmd: curl -s localhost:8000/health
    expect: exit 0
autonomy: ask
""", ["B5"], [], []),

    ("empty-brief", """
notes: just do the thing
""", ["B1", "B4", "B6", "B8"], [], []),

    # B15 — the verbal-beat-gate failure: a criterion that was red before the work started
    ("baseline-green-clean", """
goal: Add a --json flag to the report CLI.
scope: [src/cli/report.py]
forbidden: [tests/**]
acceptance:
  - cmd: ruff check src/cli/report.py
    expect: exit 0
baseline:
  - cmd: ruff check src/cli/report.py
    status: pass
    evidence: exit 0, 1 line(s) stdout, 0.2s
autonomy: ask
""", [], [], ["B15"]),

    ("baseline-red-undeclared", """
goal: Gate the assemble pipeline on the three verbal beats.
scope: [youtube/scripts/yt_assemble.py]
forbidden: [tests/**]
acceptance:
  - cmd: python3 -m pytest tests/python -q
    expect: exit 0
baseline:
  - cmd: python3 -m pytest tests/python -q
    status: fail
    evidence: exit 1, 6 failed
autonomy: ask
""", ["B15"], [], []),

    ("baseline-red-transition-flip-ok", """
goal: Fix the off-by-one in the pagination cursor.
scope: [src/api/paging.py]
forbidden: [tests/**]
acceptance:
  - cmd: pytest -q tests/test_paging.py
    expect: exit 0
    transition: flip
baseline:
  - cmd: pytest -q tests/test_paging.py
    status: fail
    evidence: exit 1, 1 failed
autonomy: ask
""", [], [], ["B15"]),

    # the pre-2026-07-27 spelling still parses, still declares the flip, and says so
    ("baseline-legacy-must-flip", """
goal: Fix the off-by-one in the pagination cursor.
scope: [src/api/paging.py]
forbidden: [tests/**]
acceptance:
  - cmd: pytest -q tests/test_paging.py
    expect: exit 0
baseline:
  - cmd: pytest -q tests/test_paging.py
    status: fail
    evidence: exit 1, 1 failed
    must_flip: true
autonomy: ask
""", [], ["B15"], []),

    ("baseline-cmd-drift", """
goal: Add a healthcheck endpoint to the API.
scope: [src/api/health.py]
forbidden: [tests/**]
acceptance:
  - cmd: curl -sf localhost:8000/health
    expect: exit 0
baseline:
  - cmd: curl -s localhost:8000/health
    status: fail
    must_flip: true
autonomy: ask
""", ["B15"], [], []),

    ("baseline-status-guessed-blank", """
goal: Add a --json flag to the report CLI.
scope: [src/cli/report.py]
forbidden: [tests/**]
acceptance:
  - cmd: ruff check src/cli/report.py
    expect: exit 0
baseline:
  - cmd: ruff check src/cli/report.py
    status: probably fine
autonomy: ask
""", ["B15"], [], []),

    # --- schema edges the old battery could not express -----------------------------

    ("baseline-cwd-is-part-of-the-key", """
goal: Add a version field to the api status payload.
scope: [services/api/handler.py]
forbidden: [tests/**]
acceptance:
  - cmd: pytest -q
    cwd: services/api
    expect: exit 0
baseline:
  - cmd: pytest -q
    status: pass
    evidence: exit 0
autonomy: ask
""", ["B15"], [], []),

    ("duplicate-acceptance-command", """
goal: Add a --json flag to the report CLI.
scope: [src/cli/report.py]
forbidden: [tests/**]
acceptance:
  - cmd: ruff check src/cli/report.py
    expect: exit 0
  - cmd: ruff check   src/cli/report.py
    expect: exit 0
autonomy: ask
""", ["B5"], [], []),

    ("not-runnable-needs-a-reason", """
goal: Add a health endpoint to the billing service.
scope: [src/billing/health.py]
forbidden: [tests/**]
acceptance:
  - cmd: curl -sf localhost:9000/health
    expect: exit 0
    transition: flip
baseline:
  - cmd: curl -sf localhost:9000/health
    status: not_runnable
autonomy: ask
""", ["B15"], [], []),

    ("not-runnable-with-reason-and-flip-ok", """
goal: Add a health endpoint to the billing service.
scope: [src/billing/health.py]
forbidden: [tests/**]
acceptance:
  - cmd: curl -sf localhost:9000/health
    expect: exit 0
    transition: flip
    requires: [services]
baseline:
  - cmd: curl -sf localhost:9000/health
    status: not_runnable
    reason: the endpoint does not exist on HEAD
autonomy: ask
""", [], [], ["B15", "B5"]),

    ("not-runnable-left-as-green-is-unverifiable", """
goal: Add a health endpoint to the billing service.
scope: [src/billing/health.py]
forbidden: [tests/**]
acceptance:
  - cmd: curl -sf localhost:9000/health
    expect: exit 0
baseline:
  - cmd: curl -sf localhost:9000/health
    status: not_runnable
    reason: needs the staging cluster
autonomy: ask
""", [], ["B15"], []),

    ("hold-needs-evidence", """
goal: Add a --json flag to the report CLI.
scope: [src/cli/report.py]
forbidden: [tests/**]
acceptance:
  - cmd: pytest -q tests/test_legacy.py
    expect: exit 1
    transition: hold
baseline:
  - cmd: pytest -q tests/test_legacy.py
    status: pass
autonomy: ask
""", ["B15"], [], []),

    ("hold-must-describe-today", """
goal: Add a --json flag to the report CLI.
scope: [src/cli/report.py]
forbidden: [tests/**]
acceptance:
  - cmd: pytest -q tests/test_legacy.py
    expect: exit 0
    transition: hold
baseline:
  - cmd: pytest -q tests/test_legacy.py
    status: fail
    evidence: exit 1, 3 failed
autonomy: ask
""", ["B15"], [], []),

    ("hold-with-no-baseline-at-all", """
goal: Add a --json flag to the report CLI.
scope: [src/cli/report.py]
forbidden: [tests/**]
acceptance:
  - cmd: pytest -q tests/test_legacy.py
    expect: exit 1
    transition: hold
autonomy: ask
""", ["B15"], [], []),

    ("bad-transition-word", """
goal: Add a --json flag to the report CLI.
scope: [src/cli/report.py]
forbidden: [tests/**]
acceptance:
  - cmd: ruff check src/cli/report.py
    expect: exit 0
    transition: mustpass
autonomy: ask
""", ["B5"], [], []),

    ("scope-must-be-repo-relative", """
goal: Add a --json flag to the report CLI.
scope: [/Users/me/proj/src/cli/report.py, ../other-repo/src]
forbidden: [tests/**]
acceptance:
  - cmd: ruff check src/cli/report.py
    expect: exit 0
autonomy: ask
""", ["B6"], [], []),

    ("forbidden-shadows-the-scope", """
goal: Add a --json flag to the report CLI.
scope: [src/cli/report.py]
forbidden: [src/**]
acceptance:
  - cmd: ruff check src/cli/report.py
    expect: exit 0
autonomy: ask
""", ["B11"], [], []),

    ("explicit-empty-forbidden-is-not-a-warning", """
goal: Add a --json flag to the report CLI.
scope: [src/cli/report.py]
forbidden: []
acceptance:
  - cmd: ruff check src/cli/report.py
    expect: exit 0
baseline:
  - cmd: ruff check src/cli/report.py
    status: pass
    evidence: exit 0
autonomy: ask
""", [], [], ["B13"]),

    ("timeout-must-be-seconds", """
goal: Add a --json flag to the report CLI.
scope: [src/cli/report.py]
forbidden: [tests/**]
acceptance:
  - cmd: ruff check src/cli/report.py
    expect: exit 0
    timeout: five minutes
autonomy: ask
""", ["B5"], [], []),

    ("unknown-requires-token", """
goal: Add a --json flag to the report CLI.
scope: [src/cli/report.py]
forbidden: [tests/**]
acceptance:
  - cmd: ruff check src/cli/report.py
    expect: exit 0
    requires: [quantum-annealer]
autonomy: ask
""", [], ["B5"], []),

    # --- B7, the three arrangements --------------------------------------------------

    ("tests-policy-immutable-satisfies-b7", """
goal: Fix the flaky retry in the upload client.
scope: [src/upload.ts]
forbidden: []
tests_policy: immutable
acceptance:
  - cmd: npm test
    expect: exit 0
autonomy: ask
""", [], [], ["B7"]),

    ("tests-policy-named-needs-the-names", """
goal: Update the upload suite for the new retry counter.
scope: [src/upload.ts]
tests_policy: named
acceptance:
  - cmd: npm test
    expect: exit 0
autonomy: ask
""", ["B7"], [], []),

    ("tests-policy-authoring-needs-an-oracle", """
goal: Replace the upload suite with tests that assert the current behaviour.
scope: [src/__tests__/upload.test.ts]
tests_policy: authoring
tests_editable: [src/__tests__/upload.test.ts]
acceptance:
  - cmd: npm test
    expect: exit 0
autonomy: ask
""", ["B7"], [], []),

    ("tests-policy-authoring-with-oracle-warns-for-a-human", """
goal: Replace the upload suite with tests that assert the current behaviour.
scope: [src/__tests__/upload.test.ts]
tests_policy: authoring
tests_editable: [src/__tests__/upload.test.ts]
oracle: npx stryker run — mutation score must not drop
acceptance:
  - cmd: npm test
    expect: exit 0
manual_checks:
  - read the whole test diff before merging
autonomy: ask
""", [], ["B7"], []),

    ("tests-policy-typo-is-not-a-policy", """
goal: Fix the flaky retry in the upload client.
scope: [src/upload.ts]
forbidden: [tests/**]
tests_policy: frozen
acceptance:
  - cmd: npm test
    expect: exit 0
autonomy: ask
""", ["B7"], [], []),

    ("unknown-top-level-key", """
goal: Add a --json flag to the report CLI.
scope: [src/cli/report.py]
forbidden: [tests/**]
priority: high
acceptance:
  - cmd: ruff check src/cli/report.py
    expect: exit 0
autonomy: ask
""", [], ["B12"], []),

    # Task 15: a brief with no base_rev is defeated by the agent committing its own
    # work — check_scope.py's diff then defaults to HEAD and comes back empty.
    ("no-base-rev-is-a-hole", """
goal: Add a --json flag to the report CLI.
scope: [src/cli/report.py]
forbidden: [tests/**]
acceptance:
  - cmd: ruff check src/cli/report.py
    expect: exit 0
autonomy: ask
""", ["B16"], [], []),

    ("base-rev-present-quiets-the-hole", """
goal: Add a --json flag to the report CLI.
scope: [src/cli/report.py]
forbidden: [tests/**]
acceptance:
  - cmd: ruff check src/cli/report.py
    expect: exit 0
autonomy: ask
base_rev: 1a2b3c4
""", [], [], ["B16", "B6"]),

    ("base-rev-garbage-string-is-still-an-error", """
goal: Add a --json flag to the report CLI.
scope: [src/cli/report.py]
forbidden: [tests/**]
acceptance:
  - cmd: ruff check src/cli/report.py
    expect: exit 0
autonomy: ask
base_rev: "not a revision!!"
""", ["B16"], [], []),

    # Fix round 1 found that the original regex (`[0-9a-fA-F]{7,40}|[\\w./-]+`) waved
    # every one of these through as "present and shaped like something git resolves" —
    # each is a ref that moves, which reproduces the exact hole B16 exists to close.
    ("base-rev-HEAD-is-a-moving-target", """
goal: Add a --json flag to the report CLI.
scope: [src/cli/report.py]
forbidden: [tests/**]
acceptance:
  - cmd: ruff check src/cli/report.py
    expect: exit 0
autonomy: ask
base_rev: HEAD
""", ["B16"], [], []),

    ("base-rev-branch-name-is-a-moving-target", """
goal: Add a --json flag to the report CLI.
scope: [src/cli/report.py]
forbidden: [tests/**]
acceptance:
  - cmd: ruff check src/cli/report.py
    expect: exit 0
autonomy: ask
base_rev: main
""", ["B16"], [], []),

    ("base-rev-at-sign-is-a-moving-target", """
goal: Add a --json flag to the report CLI.
scope: [src/cli/report.py]
forbidden: [tests/**]
acceptance:
  - cmd: ruff check src/cli/report.py
    expect: exit 0
autonomy: ask
base_rev: "@"
""", ["B16"], [], []),

    ("base-rev-relative-ref-is-a-moving-target", """
goal: Add a --json flag to the report CLI.
scope: [src/cli/report.py]
forbidden: [tests/**]
acceptance:
  - cmd: ruff check src/cli/report.py
    expect: exit 0
autonomy: ask
base_rev: "HEAD~1"
""", ["B16"], [], []),
]


def run(name, body):
    p = TMP / f"{name}.yaml"
    p.write_text(body.lstrip(), encoding="utf-8")
    r = subprocess.run([sys.executable, str(LINT), str(p), "--json"],
                       capture_output=True, text=True, encoding="utf-8")
    if r.returncode == 2:
        return None, r.stdout.strip() or r.stderr.strip()
    return json.loads(r.stdout), None


def main():
    fails = 0
    for name, body, must_err, must_warn, must_not in CASES:
        data, error = run(name, body)
        if data is None:
            print(f"FAIL  {name:44s} linter could not read fixture: {error}")
            fails += 1
            continue
        fired = {f["rule"].split()[0] for f in data["findings"]}
        errs = {f["rule"].split()[0] for f in data["findings"] if f["severity"] == "error"}
        warns = {f["rule"].split()[0] for f in data["findings"] if f["severity"] == "warn"}
        missing = [r for r in must_err if r not in errs]
        missing_w = [r for r in must_warn if r not in warns]
        spurious = [r for r in must_not if r in fired]
        ok = not missing and not missing_w and not spurious
        fails += 0 if ok else 1
        print(f"{'pass' if ok else 'FAIL'}  {name:44s} "
              f"errors={data['errors']} warns={data['warnings']} fired={sorted(fired)}")
        if missing:
            print(f"        missing expected error(s): {missing}")
        if missing_w:
            print(f"        missing expected warning(s): {missing_w}")
        if spurious:
            print(f"        false positive(s): {spurious}")

    print(f"\n{len(CASES) - fails}/{len(CASES)} cases pass")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
