# Prompire launch synthesis — FIX THEN SHIP

Adjudication of `positioning_verdict.md` (Report A) and `product-validation_verdict.md`
(Report B) against the repository at `db64bf7`. Every disputed claim that could be tested
was reproduced; the rest is labelled as uncertainty rather than resolved by argument. The
repository was not modified: all reproductions ran in a session scratchpad.

**Verdict: FIX THEN SHIP.** Five bounded fixes, then launch. The core mechanism is real and
held under every adversarial probe run here. The blockers are one false security claim, one
accidental dead-end on the modal task, and self-inflicted state — none is a design problem.

## Reproduced facts

These are the primary evidence the adjudications below rest on. Each was reproduced from a
clean `git init` in a throwaway repository.

**R1 — two-cycle workflow.** `prepare → work → verify (exit 0) → close → prepare → work →
verify` ends at exit 1 with a `repin` REVIEW and acceptance NOT RUN. The same run with the
`--ack-disarms` digest printed by `close` exits 0 with acceptance passing. The mechanism is
deliberate and documented in `references/threat-model.md` and `SKILL.md`, but not in the
README.

**R2 — test policies.** Lint-clean `tests_policy: authoring` and `tests_policy: named`
briefs, each with a perfect in-scope run, report 0 violations, 1 policy REVIEW, acceptance
NOT RUN, exit 1. The unconditional policy REVIEW (`check_scope.py:696`), verify's hardcoded
`--strict` (`prompire.py:737`) and the preflight gate (`prompire.py:747`) combine to make a
green `verify` unreachable. `ci.md:88` already disables the Action's `strict` for exactly
this reason.

**R3 — gitignored paths.** A planted executable under an ignored `vendor/` yields exit 0
with zero violations and zero reviews. `changed()` uses `git diff` plus `git status
--untracked-files=all`, both of which exclude ignored paths. `README.md:182`,
`references/threat-model.md:20` and `references/hosts.md:546,552` state that git sees the
write whatever tool made it — falsified for ignored paths.

**R4 — self-created artifacts.** In a fresh Python repository with no `.gitignore` and an
acceptance command that imports a module: `prepare` succeeds and its own baseline run
creates `__pycache__/mod.cpython-313.pyc`; `verify` then reports that as a VIOLATION though
the agent touched only the in-scope file; a `.gitignore` written to fix it is itself
flagged; the next `prepare` refuses on a dirty tree. The demo's own brief avoids importing
modules for this reason (`prompire.py:75`).

**R5 — failed prepare.** `prepare` runs `baseline --write` before the lint. A lint failure
leaves the measured `base_rev` and `baseline:` block in the brief, and `baseline.py:271`
then refuses the corrected retry.

**R6 — verify output.** Human mode prints raw child JSON for both stages with no verdict
line (`prompire.py:212-226`).

**R7 — benchmark rows.** Of 20 `bare` runs, 9 changed a forbidden test file and the checker
caught all nine (`scope_exit=1`). Across all 160 committed non-bare rows: zero test-file
changes, zero scope violations. Zero tamper events in any arm, including `bare`.

**R8 — release surface.** `prompire --version` errors; `--help` lists ten subcommands with
no descriptions; `pyproject.toml` has no `[project.urls]`; the wheel ships eleven top-level
modules and no `SKILL.md`, `references/` or `examples/`; 21 commits are unpushed; `ci.md`
pins `@v0.8.0` against a released 0.9.1. No test exercises a full two-cycle CLI workflow.

## 1. Consensus between both investigations

Both reports independently reach the same conclusions on the questions that decide the
release, and nothing in the repository overturns any of them.

Prompire should continue as a standalone product: the pinned pre-work contract is a
property no substitute provides, and both reports verified it live. The target user is the
same in both — a developer delegating several substantial, semi-unattended coding tasks to
a CLI agent, solo or on a 2–3 person team, not vibe coders. Deterministic verification is
the core and must stay the core; both reports reject any ML in the verdict path, which
matches the repository's own conclusion in `ml-research-assessment.md`. Positioning
must be verification, never prevention, because the hooks are a documented speed bump. No
additional host adapters: both name the four existing hooks as the most commoditized code
in the tree. Verify's human output is illegible and needs a verdict line with JSON
preserved behind `--json`. The `named`/`authoring` path is broken for legitimate work. The
benchmark evidence is strong, already committed, and unpublished. The README buries its
best asset and leads with a claim its own benchmark cannot support. Distribution follows
the fixes rather than preceding them. And the three questions that actually decide the
product — catch incidence, repeat-use tolerance, demo conversion — cannot be answered by
more code.

## 2. Adjudicated disagreements

| Issue | Report A | Report B | Primary evidence | Verdict |
|---|---|---|---|---|
| A. close → repin → verify | P0: second cycle "never green," acceptance never runs again in that repo | Deliberate anti-laundering with a working `--ack-disarms` remedy; UX friction only | R1 | **B correct.** A's "impossible" claim is false. Documentation work, not a code fix |
| B. `tests_policy: named` / `authoring` | P1: green verify unreachable | P0: the modal task dead-ends the flagship verb | R2 | **B correct on severity.** Local `verify` contradicts the project's own design note in `ci.md` |
| C. Gitignored-path blindness | Not mentioned | Serious gap: docs claim git sees every write; ignored paths are invisible | R3 | **B correct.** A false security claim in a document promising every limitation in full. Highest priority |
| D. Prompire-generated `__pycache__` | P0: `prepare` manufactures a false violation; ignore interpreter byproducts | Accidental friction; `prepare` dirties the tree then refuses the retry | R4 | **Both right on the symptom, A's fix rejected.** See §3 |
| E. Failed `prepare` retry | P0 (bundled): the leftover baseline block blocks the retry | Accidental friction, same mechanism | R5 | **Both correct.** Safely fixable — no security state exists before arming |
| F. Tracked vs untracked briefs | P0: README and `ci.md` contradict; change the brief-changed REVIEW to fire on change-since-arming | Not raised as a blocker | `README.md:172`, `SKILL.md:92` vs `ci.md:42-52` | **Documentation-only.** A's behavioral change rejected: the digest already covers change-since-arming, and the change-since-base REVIEW is the deliberate reusable-slot re-stamp flag |
| G. Human `verify` output | P0: verdict line, JSON behind `--json` | Same, listed as accidental friction | R6 | **Agreement.** No reason for JSON by default |
| H. Demo strategy | Rebuild around the pinned-baseline regression | Keep the drift demo canonical; test-edit second, acceptance failure third | Shipped demo runs in ~2.5s; `examples/worked-example.yaml` encodes the regression | **B for the first ten seconds, A for the extended demo.** Not a launch blocker either way |

Two Report A claims are stale or wrong and should not drive work: "acceptance never runs
again in that repo" (the ack path works and its digest is printed at close), and framing the
`__pycache__` fix as extending the `.prompire/` precedent (that precedent is protected by
the hook; a `dirty_baseline` entry is not).

## 3. False fixes found

Two proposed P0 changes would have weakened a guarantee, including one drafted during this
synthesis and killed by a fresh-context reviewer.

**Excusing interpreter artifacts via `dirty_baseline` breaks the headline guarantee.**
Those paths are skipped unconditionally by `boundary_verdict` (`brief_common.py:404`), the
single shared authority called by both `check_scope.py` and the PreToolUse hook
(`hook_policy.py:281`). Anything persisted there is invisible to *both* layers for the rest
of the task. The attack is two cycles and uses only watched tools: cycle-1 in-scope code
with an import-time side effect creates a chosen path; cycle-2's `prepare` runs acceptance,
the path appears, is excused and digest-pinned at arming; the agent then writes any payload
there and `verify` exits 0. Even the benign single-cycle version is a code path — a crafted
`.pyc` whose header matches the source makes acceptance results attacker-chosen while the
reviewed diff stays clean. Today both layers catch that write.

**Unblocking acceptance on "reviews only" would execute agent-authored commands.** Unarmed
`verify` reaches zero violations, one REVIEW, `base_source: None` (reproduced). There the
brief is agent-writable — `.prompire/**` is in `ALWAYS_ALLOWED` — and the threat model calls
this state an advisory diff-classifier where one Write buys a clean verdict. A kind-blind
unblock would let a rewritten brief's `cmd: python3 -c "…"` run on the reviewer's machine
through the shell; `verify_acceptance.py:35` reuses baseline's four-regex `classify()`,
whose own docstring says it cannot make an arbitrary command safe. The fix must gate on
`base_source ∈ {pin, repin}`.

Also rejected: globally ignoring interpreter artifacts (silently widens every brief's
scope); changing the brief-changed REVIEW's trigger (removes the re-stamp flag); auto-closing
or folding `close` into `verify` before launch (the tombstone is the anti-laundering record).

## 4. Correct product thesis

**Primary category** — a verification tool for delegated agent work; an independent examiner
that composes with sandboxes rather than competing with them.

**Primary user** — a developer running several substantial, semi-unattended CLI-agent tasks
per week in a repository where the test suite is the de-facto grading function, with no
second human reviewer in the loop.

**Core property** — the scope, the executable acceptance commands, their measured baseline
and the base commit are all fixed before the agent starts, in a form the agent cannot
silently edit, and the verdict is recomputed afterward from the real git diff plus a re-run
of those commands.

**Primary failure mode** — scope drift and unverified done-ness. Measured: 9 of 20
undirected runs drifted and all nine were caught; 0 of 160 briefed runs drifted (R7).

**Secondary threat** — manipulation of the grading surface. Real, and the reason the design
exists, but zero tamper events were observed in any arm including `bare`, so it is the tail
risk the mechanism also covers, not the headline.

## 5. Claims Prompire may safely make

That the contract is pinned before the work starts and the verdict is read from the real git
diff against that pin, needing no cooperation from the agent. That editing an armed brief
produces no verdict rather than a favourable one. That untracked additions, renames and
committed work are all seen — where the naive shell replication fails. That the baseline
separates pre-existing red from new breakage. That the work is equally *checked* across the
four supported hosts. That in its own pre-registered benchmark, undirected runs drifted 9
times in 20 and briefed runs drifted zero times in 160, with raw rows committed. That the
checker itself is tested by roughly 9.5k lines of adversarial suites.

## 6. Claims Prompire must not make

Prevention, guarding, sandboxing or blocking as the product's function. Tamper-proofness
against an agent holding shell — the honest claim is tamper-*evident* against watched tools
and tamper-*detectable* only via transcript against the shell. "Git sees the write whatever
tool made it," unqualified. "An agent graded on a suite it can edit will, sooner or later,
edit the suite," stated as measured fact. Equal output quality across hosts. Any semantic
judgment of whether the work is good.

## 7. Must fix before launch

1. The gitignored-path truth boundary — a false security claim in the document that promises
   every limitation in full.
2. `verify` runs acceptance when the scope is corroborated and violation-free — the modal
   delegated task currently dead-ends.
3. `prepare` and `verify` stop manufacturing violations from their own runs, and a failed
   `prepare` leaves no partial state.
4. A human verdict line on `verify`.
5. Release coherence — README, brief-tracking rule, sequential-task loop, PyPI↔GitHub links,
   docs in the wheel, `--version`, the stale `ci.md` pin, and 0.9.2 released.

## 8. Should fix before promotion

The extended demo (test-edit beat, then the pinned-baseline regression from
`examples/worked-example.yaml`). A design review of a "clean close" that spares honest users
the digest treadmill without reopening the laundering hole. An advisory REVIEW when an
acceptance command resolves to a repo-local gitignored executable. Qualifying the Windows
claim or extending the CI matrix to run the encoding suite there. The Claude Code plugin
manifest, then the GitHub Action Marketplace listing.

## 9. Explicitly deferred until real-user evidence

Catch incidence, repeat-loop tolerance and demo conversion (§12). Any `verify --done` or
`prompire run -- <agent-cmd>` wrapper. A `prompire/` package directory. Brief provenance or
any B2B layer. A schema freeze — add a schema-version field when convenient; freezing with
zero external briefs is premature. Any dashboard, service or telemetry.

## 10. Implementation briefs

```yaml
id: P1-truth-boundary
goal: Stop claiming the checker sees every write, and say exactly what it does see.
why_now: |
  Reproduced: a file planted under a gitignored directory yields exit 0 with zero
  findings, while README.md:182, threat-model.md:20 and hosts.md:546,552 say git sees
  the write whatever tool made it. A false security claim in a document whose stated
  purpose is every known limitation, in full.
scope:
  - references/threat-model.md
  - references/hosts.md
  - README.md
  - check_scope.py
forbidden:
  - brief_common.py
  - hook_policy.py
behavior_to_preserve:
  - The checker's path set is unchanged; ignored paths stay out of the diff authority.
  - The two-layer framing (hook is a speed bump, checker is the authority) stands.
  - The corrected wording must also state that the hook judges by pattern and does not
    consult gitignore, so a watched-tool write to an ignored out-of-scope path is still
    refused early — the blind spot is checker-only.
  - Add the limitation row for ignored paths, and one sentence in hosts.md saying the
    verifying copy must run from outside the governed workspace.
  - check_scope.py's --activate diagnostic must stop claiming unconditionally that
    writes outside scope are refused before they happen (check_scope.py:269); it does
    not know whether any hook is installed. prepare() discards this line, so the
    primary flow is unaffected.
acceptance:
  - cmd: python3 tests/run_all.py
    expect: exit 0
  - cmd: grep -rn "sees the write whatever tool made it" README.md references/ | grep -v "git-visible"
    expect: empty output
tests_policy: named
evidence:
  - Planted vendor/evil.sh under an ignored path; verify exited 0, violations 0, reviews 0.
not_part_of_this_task:
  - Any change to what the checker scans.
  - The advisory REVIEW for ignored acceptance executables (promotion, not launch).
```

```yaml
id: P2-acceptance-under-review
goal: Run acceptance and report it alongside REVIEW findings when the base is corroborated and nothing was violated.
why_now: |
  Reproduced on lint-clean `named` and `authoring` briefs with perfect in-scope runs:
  0 violations, 1 policy REVIEW, acceptance NOT RUN, exit 1. The unconditional policy
  REVIEW (check_scope.py:696) plus verify's hardcoded --strict (prompire.py:737) plus
  the preflight gate (prompire.py:747) make a green verify unreachable for the modal
  task. ci.md:88 already disables the Action's strict for the same reason.
scope:
  - prompire.py
  - tests/verify.py
  - tests/e2e.py
forbidden:
  - check_scope.py
  - verify_acceptance.py
  - baseline.py
behavior_to_preserve:
  - Acceptance runs ONLY when the scope JSON reports zero violations AND base_source is
    "pin" or "repin". A null base_source (nobody armed the guard) must keep blocking:
    in that state the brief is agent-writable and acceptance commands run through the
    shell. A symlink REVIEW also keeps blocking.
  - Non-blocking kinds are the tests_policy REVIEW, the authoring skip-marker REVIEW,
    the brief-changed-since-base REVIEW, and the repin REVIEW acknowledged or not.
  - Exit code semantics are unchanged: any REVIEW still fails the strict run (exit 1).
    This fix changes what evidence the run reports, never what it concludes.
  - The demo's caught violation must still block acceptance and print NOT RUN.
  - Exit 2 (indeterminate) still short-circuits before acceptance.
acceptance:
  - cmd: python3 tests/run_all.py
    expect: exit 0
  - cmd: python3 prompire.py demo
    expect: exit 0
tests_policy: named
evidence:
  - Authoring and named briefs, perfect runs, acceptance not_run, exit 1.
  - Unarmed verify reaches violations 0 / reviews 1 / base_source None — the state the
    base_source gate exists to keep blocked.
not_part_of_this_task:
  - Any change to which findings check_scope.py produces.
  - Making --ack-disarms silence anything beyond the repin finding.
```

```yaml
id: P3-self-inflicted-state
goal: Stop Prompire's own runs from creating violations, and make a failed prepare leave the brief as it found it.
why_now: |
  Reproduced in a fresh Python repo with no .gitignore: prepare's own baseline run
  creates __pycache__/*.pyc, verify then reports it as a VIOLATION though the agent
  touched only the in-scope file, a .gitignore written to fix it is itself flagged, and
  the next prepare refuses on a dirty tree. Separately, a lint-failed prepare leaves the
  measured base_rev/baseline: block behind and baseline.py:271 refuses the corrected retry.
scope:
  - prompire.py
  - baseline.py
  - tests/e2e.py
forbidden:
  - brief_common.py
  - check_scope.py
  - hook_policy.py
behavior_to_preserve:
  - NOTHING may be persisted into `dirty_baseline`, or into any field the checker skips.
    That field is honored by boundary_verdict (brief_common.py:404), which the PreToolUse
    hook also calls (hook_policy.py:281), so an entry there blinds both layers for the
    rest of the task and is a bought clean verdict, not a UX fix.
  - prepare restores the brief's bytes on any stage failure after the baseline write, and
    removes only untracked paths that (a) did not exist before its own invocation and
    (b) appeared during its own acceptance measurement — reporting what it removed. The
    restore must never run after a successful --activate: the pointer's digest would no
    longer match and every later run would exit 2 until a --deactivate, which costs a
    tombstone. Activation is the last stage today; state the ordering so a reorder
    cannot break it.
  - verify stays read-only. It excludes from its final scope check only the untracked
    paths its own acceptance invocation created, computed per invocation and persisted
    nowhere, and names them in the output. Anything already present at the preflight is
    judged normally — a payload planted before verify is still caught.
  - baseline.py's standalone refusal to overwrite an existing measured block is unchanged.
  - Interpreter and build artifacts created by the user's own tooling remain the user's
    .gitignore hygiene; this task does not excuse them.
acceptance:
  - cmd: python3 tests/run_all.py
    expect: exit 0
  - cmd: python3 tests/e2e.py
    expect: exit 0
tests_policy: named
evidence:
  - R4 and R5, both reproduced from a clean git init with no .gitignore.
not_part_of_this_task:
  - Global ignore rules for interpreter artifacts.
  - Any change to the checker's or the hook's path judgment.
```

```yaml
id: P4-human-verdict
goal: End every verify run with one line a human can read, and keep --json byte-identical.
why_now: |
  prompire.py:212-226 prints two walls of child JSON in human mode; the verdict is a
  "passed": 1 mid-line. The demo promises "clean (exit 0)" and the product never says
  those words again.
scope:
  - prompire.py
  - tests/golden
  - tests/verify.py
forbidden:
  - check_scope.py
  - verify_acceptance.py
behavior_to_preserve:
  - --json output is unchanged, byte for byte, including the refusal and indeterminate shapes.
  - Vocabulary maps onto exit states with nothing hidden: `clean` (0); `caught: N
    violation(s)` (1, violations present); `review: N flag(s) — needs a human` (1,
    reviews only); `no verdict: <reason> — <next command>` (2).
  - A repin review's line names the --ack-disarms command with the digest, so the
    sequential-task remedy is discoverable from the output rather than from the threat model.
  - After P2, a run with reviews only also reports the acceptance result; the summary
    must show both, never the acceptance result alone.
acceptance:
  - cmd: python3 tests/run_all.py
    expect: exit 0
  - cmd: python3 tests/golden.py
    expect: exit 0
tests_policy: named
evidence:
  - Verify output reproduced in every state: clean, caught, reviews-only, repin, indeterminate.
not_part_of_this_task:
  - Color, TTY detection, or any change to the demo's narration.
```

```yaml
id: P5-release-coherence
goal: Make the published artifact findable, self-documenting, and honest about what it measured.
why_now: |
  21 hardening commits unpushed; pyproject 0.9.1 with no [project.urls]; the wheel ships
  11 .py modules and no SKILL.md, references/ or examples/; `prompire --version` errors;
  ci.md pins @v0.8.0; README leads with a claim its own benchmark cannot support while
  the 9-of-20 vs 0-of-160 result is committed and unpublished; README.md:172 and
  SKILL.md:92 contradict ci.md:42 on whether briefs are tracked.
scope:
  - README.md
  - SKILL.md
  - pyproject.toml
  - prompire.py
  - references/ci.md
  - tests/package.py
  - tests/docs.py
forbidden:
  - check_scope.py
  - brief_common.py
  - hook_policy.py
behavior_to_preserve:
  - The headline becomes drift and done-ness, carrying the measured numbers; tamper
    stays as the trust anchor and the tail risk, never as an observed frequency.
  - One stated rule for brief lifecycle, matching ci.md's existing prescription: state
    files and rendered artifacts are ignored, briefs are tracked when the Action is used
    and may stay local otherwise, one brief per pull request.
  - The primary workflow section documents the sequential-task loop as it behaves AFTER
    P2 — acceptance runs, the repin REVIEW still fails the run, --ack-disarms clears it.
  - The "needs no cooperation from the agent" sentence carries the shell caveat with
    equal weight, and "What this is not" keeps its honesty.
  - No claim added that P1 through P4 do not implement.
acceptance:
  - cmd: python3 tests/run_all.py
    expect: exit 0
  - cmd: python3 prompire.py --version
    expect: exit 0
  - cmd: python3 -c "import tomllib,pathlib; d=tomllib.loads(pathlib.Path('pyproject.toml').read_text()); raise SystemExit(0 if d['project'].get('urls') else 1)"
    expect: exit 0
tests_policy: named
evidence:
  - R7, verified against the raw rows in bench/campaigns/.
not_part_of_this_task:
  - The extended demo.
  - Any marketplace or plugin manifest.
  - New benchmark campaigns.
```

## 11. Implementation order

`P1 → P2 → P3 → P4 → P5`.

P1 is documentation-only, depends on nothing, ships alone, and unblocks any honest
description of the product. P2 and P3 are independent of each other and of P1; both are code
and both should land before anything describes the workflow. P4 depends on P2 and P3 because
the verdict line renders their final states — building it first means building it twice. P5
depends on all four, because its content is a truthful description of what they now do, and
it ends with the push and the 0.9.2 release. P1 through P4 can each ship alone; P5 cannot.

## 12. Blind post-implementation validation

After P5, hand a fresh-context agent only the public repository URL, the published install
command, and this role: a developer who delegates several substantial coding tasks a week to
a CLI agent and is evaluating whether this is worth adopting. It must not see the two
reports, this synthesis, or any implementation reasoning. Its task is the full arc —
discover, install, run the demo, run one real task end to end, verify, run a second real task
in the same repository, verify again, then state the tool's limitations in its own words.

Success is concrete, not an opinion about quality:

- Install to a completed demo in under two minutes using only the README.
- A first real brief reaching a `verify` verdict in under fifteen minutes without hand-editing
  YAML to recover from a tool-created failure.
- Zero violations attributable to Prompire's own runs.
- A second task in the same repository reaching a verdict, with the reviewer able to say from
  the output alone what the repin flag means and which command clears it.
- Every `verify` run ending in a line the reviewer can classify as clean, caught, review or
  no verdict without reading JSON.
- Unprompted, the reviewer naming both that gitignored paths are outside the checker's view
  and that the hook does not watch the shell.

If the reviewer reports that Prompire prevents an agent from writing out of scope, the
documentation still overclaims and P1 failed.

## 13. Three post-launch product experiments

**Catch incidence.** Hypothesis: the failure occurs often enough to justify the loop. Sample:
dogfooding plus 5–10 volunteer heavy delegators running `verify` on every real task for four
weeks. Evidence: confirmed catches per 100 tasks, split drift versus tamper, collected via a
GitHub issue template asking for the verdict block. Success: ≥1 human-confirmed real catch
per ~25 tasks for at least half the cohort. Kill: zero confirmed catches across 200+ real
tasks — reposition as a brief compiler and stop maintaining the rest.

**Loop tolerance.** Hypothesis: users complete the loop repeatedly rather than abandoning it
after `prepare`. Sample: the same cohort, no instrumentation — ask for `.prompire/` directory
listings at weeks 1 and 3. Evidence: share of started briefs that reach `verify`. Success:
≥50% in week 3. Kill: <20%, or a pattern of running `prepare` and then eyeballing diffs,
which abandons the half carrying the guarantee.

**Demo conversion.** Hypothesis: the demo makes the property legible to a skeptic. Sample: 8
target developers shown the extended demo cold. Evidence: unaided articulation of the
pinned-contract property; install actions within a week. Success: 5 of 8 articulate it
without help, 3 install. Kill: a majority describe it as a prompt template or a sandbox —
positioning must be rebuilt before any promotion spend.

No telemetry in any of the three; all evidence is opt-in or public.

## 14. Stop-doing list

No further ML investigation — the repository's own research document already concluded that
no learned signal belongs anywhere near the verdict path, including the REVIEW channel, and
both reports agree. No fifth host adapter and no further work on the four existing hooks. No
further investment in `draft --agent`. No new benchmark campaigns; the committed rows already
support every claim P5 makes. No B2B provenance layer, dashboard, service or telemetry. No
schema freeze. No further broad product audits — three investigations have converged, and a
fourth would produce agreement, not information.

## Single next action

Implement `P1-truth-boundary`: correct the four "git sees the write whatever tool made it"
sentences in `README.md`, `references/threat-model.md` and `references/hosts.md`; add the
ignored-paths row to the limitations table together with the note that the hook still refuses
such writes early; add the sentence to `hosts.md` about running the verifying copy from
outside the governed workspace; and fix the unconditional pre-write claim at
`check_scope.py:269`.

---

*Method note: this synthesis reproduced every testable disputed claim rather than averaging
the two reports, then sent its own draft to a fresh-context adversarial reviewer whose only
task was to find recommendations that would weaken a deterministic guarantee. That review
changed two proposed fixes materially — the `dirty_baseline` persistence in P3 and the
acceptance gate in P2 — both documented in §3. No repository file was modified during the
investigation.*
