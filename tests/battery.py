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

    # E1, T07 GOLD: `requires: [tests/test_orderedset.py]` — a path, not a vocabulary
    # word — armed, and both baseline and verify then refused to run the criterion,
    # so the contract's only executable check was one nothing ever executed. A
    # declared requires disables execution by design; an unrecognized value doing
    # that silently is an error, not a style note.
    ("unknown-requires-token", """
goal: Add a --json flag to the report CLI.
scope: [src/cli/report.py]
forbidden: [tests/**]
acceptance:
  - cmd: ruff check src/cli/report.py
    expect: exit 0
    requires: [quantum-annealer]
autonomy: ask
""", ["B5"], [], []),

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

    # B17 — a measured brief whose every criterion already passes on untouched HEAD
    # cannot tell done from not started. Only judged once a baseline exists: before
    # measurement, transitions are claims B15 has not tested yet.
    ("vacuous-measured-green", """
goal: Add a retry to the upload client.
scope: [src/upload.py]
forbidden: [tests/**]
acceptance:
  - cmd: pytest -q tests/test_upload.py
    expect: exit 0
baseline:
  - cmd: pytest -q tests/test_upload.py
    status: pass
    evidence: exit 0, 1 passed
autonomy: ask
""", ["B17"], [], []),

    ("flip-criterion-discriminates", """
goal: Add a retry to the upload client.
scope: [src/upload.py]
forbidden: [tests/**]
acceptance:
  - cmd: pytest -q tests/test_upload.py
    expect: exit 0
  - cmd: python -c "from src.upload import retry"
    expect: exit 0
    transition: flip
baseline:
  - cmd: pytest -q tests/test_upload.py
    status: pass
    evidence: exit 0, 1 passed
  - cmd: python -c "from src.upload import retry"
    status: fail
    evidence: exit 1, ImportError
autonomy: ask
""", [], [], ["B17"]),

    # a declared flip the baseline already meets is not a discriminator — B15 warns
    # pointless-flip, and B17 must not count it as telling done apart from untouched
    ("pointless-flip-does-not-discriminate", """
goal: Add a retry to the upload client.
scope: [src/upload.py]
forbidden: [tests/**]
acceptance:
  - cmd: pytest -q tests/test_upload.py
    expect: exit 0
    transition: flip
baseline:
  - cmd: pytest -q tests/test_upload.py
    status: pass
    evidence: exit 0, 1 passed
autonomy: ask
""", ["B17"], ["B15"], []),

    ("hold-is-a-declared-preservation-shape", """
goal: Add a count helper to the cart module.
scope: [src/cart.py]
forbidden: [tests/**]
acceptance:
  - cmd: pytest -q tests/test_legacy.py
    expect: exit 1
    transition: hold
baseline:
  - cmd: pytest -q tests/test_legacy.py
    status: pass
    evidence: "exit 1, 1 failed"
autonomy: ask
""", [], [], ["B17"]),

    # E1's T05 and T08 armed with every criterion green on untouched HEAD because a
    # non-empty manual_checks suppressed B17. A manual check *existing* proves
    # nothing; only the human's own `done:` spelling declares that this judgment is
    # the completion condition — and a compiler proposal cannot carry that spelling.
    ("manual-check-strings-do-not-carry-doneness", """
goal: Add a retry to the upload client.
scope: [src/upload.py]
forbidden: [tests/**]
acceptance:
  - cmd: pytest -q tests/test_upload.py
    expect: exit 0
baseline:
  - cmd: pytest -q tests/test_upload.py
    status: pass
    evidence: exit 0, 1 passed
manual_checks:
  - the diff adds a retry loop to upload()
autonomy: ask
""", ["B17"], [], []),

    ("manual-done-declaration-carries-doneness", """
goal: Add a retry to the upload client.
scope: [src/upload.py]
forbidden: [tests/**]
acceptance:
  - cmd: pytest -q tests/test_upload.py
    expect: exit 0
baseline:
  - cmd: pytest -q tests/test_upload.py
    status: pass
    evidence: exit 0, 1 passed
manual_checks:
  - done: the diff adds a retry loop to upload() and a test exercises it
  - the changelog entry matches neighboring style
autonomy: ask
""", [], [], ["B17"]),

    # the T05/T08 shape verbatim: authoring policy, a free-text oracle, review-style
    # manual checks, acceptance green on HEAD. The oracle is the compiler's own
    # prose, so it cannot stand in for a completion condition either.
    ("authoring-oracle-manual-strings-still-vacuous", """
goal: Preserve custom prompt validation errors when input is hidden.
scope: [src/termui.py]
forbidden: [src/core.py]
tests_policy: authoring
tests_editable: [tests/test_termui.py]
oracle: author a test asserting the message appears in output
acceptance:
  - cmd: pytest -q tests/test_termui.py
    expect: exit 0
baseline:
  - cmd: pytest -q tests/test_termui.py
    status: pass
    evidence: exit 0, 4 passed
manual_checks:
  - confirm the changelog gets a terse entry
  - confirm no regression in hidden-input echo
autonomy: ask
""", ["B17"], [], []),

    # a mapping that is not exactly `done: <text>` is neither a note nor a
    # declaration — refuse it rather than guess which it meant to be
    ("manual-check-shape-must-be-string-or-done", """
goal: Add a retry to the upload client.
scope: [src/upload.py]
forbidden: [tests/**]
acceptance:
  - cmd: pytest -q tests/test_upload.py
    expect: exit 0
baseline:
  - cmd: pytest -q tests/test_upload.py
    status: pass
    evidence: exit 0, 1 passed
manual_checks:
  - carries_done: the diff adds a retry loop
autonomy: ask
""", ["B17"], [], []),

    ("preserve-goal-green-is-legitimate", """
goal: Refactor the report module into renderer and writer halves.
scope: [src/report.py, src/render.py]
forbidden: [tests/**]
plan_first: true
acceptance:
  - cmd: python -m src.report
    expect: exit 0, output identical to the baseline digest
    before_after: true
baseline:
  - cmd: python -m src.report
    status: pass
    evidence: "exit 0, 2 line(s) stdout, 0.3s, sha256:2c913d0e74e2"
autonomy: ask
""", [], [], ["B17"]),

    # autonomy: manual already decouples planning from execution — the run never
    # writes — so B10 must not demand a mid-run approval stop on top of it
    ("wide-manual-run-needs-no-plan-gate", """
goal: Refactor the report module into renderer and writer halves.
scope: [src/report.py, src/render.py]
forbidden: [tests/**]
acceptance:
  - cmd: python -m src.report
    expect: exit 0
autonomy: manual
""", [], [], ["B10"]),

    # a `hold` over "exit 0, nothing printed" freezes the state of every trivial
    # command — `python3 -c "pass"` reproduces it on an untouched tree, on the work
    # and on any wrong work alike, exactly like the empty before/after digest
    ("hold-over-silent-success-carries-nothing", """
goal: Rename the greet helper parameter without changing output.
scope: [src/greet.py]
forbidden: [tests/**]
tests_policy: immutable
acceptance:
  - cmd: python3 -m unittest -q tests.test_greet
    expect: exit 0
  - cmd: python3 -c "pass"
    expect: exit 0
    transition: hold
baseline:
  - cmd: python3 -m unittest -q tests.test_greet
    status: pass
    evidence: "exit 0, 0 line(s) stdout, 0.1s"
  - cmd: python3 -c "pass"
    status: pass
    evidence: "exit 0, 0 line(s) stdout, 0.1s"
autonomy: ask
""", ["B17"], [], []),

    # a hold on a genuinely known-red suite freezes a specific failure, which is
    # information — this must keep working
    ("hold-over-known-red-still-carries", """
goal: Add a count() helper without disturbing the legacy suite.
scope: [src/cart.py]
forbidden: [tests/**]
tests_policy: immutable
acceptance:
  - cmd: python3 -m unittest -q tests.test_legacy
    expect: exit 1 — the one known failure, unchanged
    transition: hold
baseline:
  - cmd: python3 -m unittest -q tests.test_legacy
    status: pass
    evidence: "exit 1, 0 line(s) stdout, 0.1s"
autonomy: ask
""", [], [], ["B17"]),

    # a criterion that claims `flip` but was never measured is a claim, not a red
    # baseline: `verify` passes it on an untouched tree
    ("flip-without-a-baseline-entry-is-not-a-discriminator", """
goal: Fix the off-by-one in total() so carts add up.
scope: [src/cart.py]
forbidden: [tests/**]
tests_policy: immutable
acceptance:
  - cmd: python3 -m unittest -q tests.test_cart
    expect: exit 0
  - cmd: python3 -c "import sys; sys.exit(0)"
    expect: exit 0
    transition: flip
baseline:
  - cmd: python3 -m unittest -q tests.test_cart
    status: pass
    evidence: "exit 0, 0 line(s) stdout, 0.1s"
autonomy: ask
""", ["B15", "B17"], [], []),

    # a truthy string is not a plan gate: YAML `plan_first: "false"` is truthy, and
    # rendering it as a hard approval stop would gate execution on a typo
    ("plan-first-string-is-an-error", """
goal: Add a retry to the upload client.
scope: [src/upload.py]
forbidden: [tests/**]
tests_policy: immutable
plan_first: "false"
acceptance:
  - cmd: pytest -q tests/test_upload.py
    expect: exit 0
autonomy: ask
""", ["B8"], [], []),

    # before the baseline is measured, B17 stays silent — B15 owns that gap
    ("unmeasured-green-not-yet-vacuous", """
goal: Add a retry to the upload client.
scope: [src/upload.py]
forbidden: [tests/**]
acceptance:
  - cmd: pytest -q tests/test_upload.py
    expect: exit 0
autonomy: ask
""", [], [], ["B17"]),

    # a digest over no output reproduces whatever the agent does, so it carries
    # nothing — the criterion is marked before_after but compares an empty string
    ("before-after-over-empty-output", """
goal: Fix the off-by-one in total() so carts add up.
scope: [src/cart.py]
forbidden: [tests/**]
tests_policy: immutable
acceptance:
  - cmd: python3 -m unittest -q tests.test_cart
    expect: exit 0
    before_after: true
baseline:
  - cmd: python3 -m unittest -q tests.test_cart
    status: pass
    evidence: "exit 0, 0 line(s) stdout, 0.4s, sha256:e3b0c44298fc"
autonomy: ask
""", ["B17"], ["B17"], []),

    # a preserve word in the goal is not evidence: goal is the one field a compiler
    # writes freely and no marker covers
    ("preserve-word-in-goal-is-not-evidence", """
goal: Fix the off-by-one in total() and rename the helper.
scope: [src/cart.py]
forbidden: [tests/**]
tests_policy: immutable
acceptance:
  - cmd: python3 -m unittest -q tests.test_cart
    expect: exit 0
baseline:
  - cmd: python3 -m unittest -q tests.test_cart
    status: pass
    evidence: "exit 0, 0 line(s) stdout, 0.4s"
autonomy: ask
""", ["B17"], [], []),

    # B18 — a draft marker means the file is a proposal, not a brief
    ("unconfirmed-marker-is-not-shippable", """
goal: Add a retry to the upload client.
scope: [src/upload.py]  # prompire:unconfirmed — list the exact files the agent may edit
forbidden: [tests/**]
acceptance:
  - cmd: pytest -q tests/test_upload.py
    expect: exit 0
autonomy: ask
""", ["B18"], [], []),

    # the same refusal after a round-trip has dropped every comment marker
    ("unconfirmed-ledger-survives-a-round-trip", """
unconfirmed:
  - scope[0]
  - acceptance[0]
goal: Add a retry to the upload client.
scope: [src/upload.py]
forbidden: [tests/**]
acceptance:
  - cmd: pytest -q tests/test_upload.py
    expect: exit 0
autonomy: ask
""", ["B18"], [], []),
]


def read_verdict(r):
    """(findings, None) from a finished lint run, or (None, why) if none can be read.

    Split out of `run()` so the `stdout is None` branch can be asserted directly, because
    no test on this platform can reach it. A child whose output does not decode fails in
    two different places depending on the OS, from one root cause:

    - **POSIX**: the decode happens in the parent's `_communicate`, so `subprocess.run`
      raises `UnicodeDecodeError` and `run()` catches it below.
    - **Windows**: the decode happens in a reader thread, where the exception is
      swallowed, and `stdout` arrives as **None**. That is the `TypeError` in the CI log —
      `json.loads(None)` — and `cli-windows` runs this suite as its first step.

    So the None branch is Windows-only in effect and is pinned by `self_checks()` instead.
    `r.stdout or ""` on the exit-2 path is the same hazard: a refusal whose stdout did not
    decode would otherwise raise `AttributeError` here, on Windows only.
    """
    if r.returncode == 2:
        return None, ((r.stdout or "").strip() or (r.stderr or "").strip()
                      or "the linter refused (exit 2) and printed nothing readable")
    if r.stdout is None:
        return None, "the linter's stdout could not be read at all (not decodable?)"
    try:
        return json.loads(r.stdout), None
    except ValueError as e:
        return None, (f"exit {r.returncode} but stdout is not json ({e}): "
                      f"{(r.stderr or '').strip()}")


def run(name, body):
    """The linter's JSON, or (None, why) if this suite could not read a verdict at all.

    The decode is strict on purpose — the linter's stdout is a wire format and UTF-8 is
    the contract `tests/encoding.py` pins — but a child that broke it must surface as a
    named case failure, not as a `UnicodeDecodeError` out of `subprocess.run` that stops
    the suite on its first case and says nothing about the other forty-four.
    """
    p = TMP / f"{name}.yaml"
    p.write_text(body.lstrip(), encoding="utf-8")
    try:
        r = subprocess.run([sys.executable, str(LINT), str(p), "--json"],
                           capture_output=True, text=True, encoding="utf-8")
    except UnicodeDecodeError as e:
        return None, f"the linter's stdout is not utf-8: {e}"
    return read_verdict(r)


class _Finished:
    """The three fields `read_verdict` reads off a `CompletedProcess`."""

    def __init__(self, returncode, stdout, stderr=""):
        self.returncode, self.stdout, self.stderr = returncode, stdout, stderr


def self_checks():
    """`read_verdict`'s unreachable-on-POSIX branches, asserted directly.

    Every one of these is a real Windows shape (see `read_verdict`). The contract is
    identical in all of them: return a reason, never raise, and never hand a None to
    `json.loads`.
    """
    cases = (
        ("exit 0 with stdout None", _Finished(0, None)),
        ("exit 1 with stdout None", _Finished(1, None)),
        ("exit 2 with stdout None", _Finished(2, None, None)),
        ("exit 1 with non-json stdout", _Finished(1, "not json at all")),
    )
    fails = 0
    for label, r in cases:
        try:
            data, why = read_verdict(r)
            ok = data is None and bool(why)
            detail = "" if ok else f"returned {data!r}, {why!r}"
        except Exception as e:
            ok, detail = False, f"raised {type(e).__name__}: {e}"
        fails += 0 if ok else 1
        print(f"{'pass' if ok else 'FAIL'}  {label:44s} {detail}")
    return fails


def main():
    # Counted apart from CASES so the tally below stays a count of linter cases.
    probe_fails = self_checks()
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
    return 1 if fails or probe_fails else 0


if __name__ == "__main__":
    sys.exit(main())
