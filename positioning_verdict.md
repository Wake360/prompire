# Prompire positioning verdict

**The 2–4 things Prompire should focus on next:** (1) Make the tool survive its own
README — today, running the documented prepare → verify → close cycle twice in the
same repo leaves `verify` permanently red, and the first `prepare` in a typical Python
repo manufactures a false violation from its own `__pycache__` byproducts. (2) Make
`prompire verify` speak the demo's language — a human verdict line (`clean` / `caught`
/ `no verdict`) by default, JSON behind the existing `--json` flag. (3) Fix the shop
window: link PyPI and GitHub to each other, ship the docs in the wheel, push the 21
unpushed hardening commits, release 0.9.2, and put the benchmark's strongest number in
the README. (4) Rebuild the demo around the capability no alternative has — catching a
regression against pre-measured state that no diff contains — and only then invest in
distribution (Claude Code plugin first, GitHub Action Marketplace after its coherence
bug is fixed).

## 1. Product verdict

Prompire could succeed because the mechanism is real and honest. Under adversarial
testing this session, the core guarantee held: widening `scope` after prepare produced
*no verdict* (exit 2) rather than a favorable one; an out-of-scope file was caught from
the real diff; committing a file did not exempt it (Observed, first-time-user test of
the published 0.9.1 wheel). The evidence culture — pre-registered benchmark campaigns
with raw rows committed, a threat model that publishes its own false-positive incident
and tracebacks — is rarer than the mechanism itself and is the project's most
defensible asset. The footprint (Python + PyYAML, no service, no key) removes the usual
adoption tax.

It could fail because the product contradicts its own pitch within ten minutes of real
use. The demo takes 9 seconds and lands perfectly; the first real task took five
consecutive failed `prepare` runs, and the *second* task in the same repo can never go
green again after a documented `close` (Observed, reproduced independently by two
auditors). A verification tool whose second use is permanently red trains users to
paste an acknowledgement flag reflexively — the exact reflex it exists to defeat.

Strongest advantage: the pinned baseline. What the repo looked like *before* the
work — a stdout hash, a known-red suite's exact failure — is information no diff
contains and no reviewer can recover by reading harder. Nothing else in the
alternatives landscape has this.

Largest adoption risk: churn between demo and first real value, compounded by zero
discoverability (0 stars, no topics, no PyPI↔GitHub links, no marketplace presence on
any channel).

## 2. Ideal target user

A developer who delegates several substantial coding tasks per week to a CLI agent —
Claude Code or Codex — often semi-unattended or in parallel worktrees. Their workflow
is already brief-shaped: they write the task, walk away, and review a diff later. Their
fear is specific and evidenced in Prompire's own benchmark: on tasks with a tempting
forbidden file and no brief, 9 of 20 live agent runs edited a test file the task
forbade (Observed, `bench/campaigns/` raw rows). The adoption trigger is the first time
an agent games a check or touches something it shouldn't — the recovery moment named in
SKILL.md's own description. Recurring use is one `prepare`/`verify` pair per delegated
task. Vibe coders are not the launch audience; they cannot review a proposed scope, and
the internal verdict doc already reached the same conclusion.

## 3. Recommended positioning

One sentence: **"Prompire pins your repo's state before a coding agent starts and
checks the real git diff after it stops — so the agent can't edit the evidence it's
graded on."**

The one-line peer recommendation: *"It catches what your agent changed that you never
allowed — from the git diff, not from the agent's report."*

Two framings worth adopting. First, the sandbox contrast already in the README is
correct and should stay: a sandbox bounds where an agent can reach; Prompire bounds
what one task allowed it to change. Second, a new one from the competitive analysis:
SWE-bench had to invent FAIL_TO_PASS / PASS_TO_PASS grading because models graded on
suites they can touch will touch them — Prompire is that grading contract applied to
your own delegated work. This converts "another agent wrapper" into "the thing evals
already had to build."

Prompire should NOT claim: prevention (the hooks are speed bumps with a documented
shell hole), semantic quality judgment, equal output quality across hosts (the
benchmark supports "equally checked everywhere," not "equally good"), or
tamper-proofness against an agent holding shell — the threat model already refuses
these claims; marketing must too.

## 4. First 60 seconds

Current experience (Observed): venv + `pip install prompire` in ~6 seconds, `prompire
demo` in 2.4 seconds, and the demo genuinely delivers — the clean run vs. the caught
`secrets.cfg` write, closed by exactly the right sentence about the diff being read
against the pinned base. Install-to-demo is already excellent. This is not where the
problem is.

The problem is minutes 2–10. On a real two-file Python repo: `prompire --help` lists
ten subcommands with zero descriptions; `prompire --version` errors; the first
`prepare` fails on `__pycache__` the tool itself just created; the fix (a `.gitignore`)
is itself flagged as dirt; a lint-failed `prepare` leaves behind a `baseline:` block
that blocks the retry; and when `verify` finally runs, it prints two walls of
single-line JSON in which the verdict is `"passed": 1` buried mid-line. The user who
was promised `clean (exit 0)` never sees those words again. (All Observed, published
wheel.)

The ideal: demo unchanged in speed, extended by one beat (see §6); then in the user's
own repo, `prepare` handles its own byproducts, and `verify` ends with one unmissable
line — `clean` / `caught: 1 violation` / `no verdict: <reason, next command>` —
matching the demo's vocabulary. Everything needed for this exists; it is output
plumbing, not design work.

## 5. Adoption blockers

| Priority | Blocker | Evidence | Impact | Recommended fix |
|---|---|---|---|---|
| P0 | Second cycle never green: `close` tombstones the repo, every later arm is `repin`, and `verify` hardcodes `--strict`, so acceptance never runs again in that repo | Reproduced twice independently; `prompire.py:735` hardcodes strict, no flag to relax | Documented workflow poisons the tool on use #2; trains reflexive `--ack-disarms` pasting | Make a reviewed, clean `close` not degrade the next cycle (or make post-clean-close `repin` benign under `verify`); add a two-cycle e2e test — prepare/verify/close twice, assert exit 0 both times |
| P0 | `verify` prints raw JSON, no verdict line, no color | Green vs. failed runs differ by `"passed": 1` vs `0` mid-line | The product's central command is illegible at its only moment of truth | Human summary by default (demo's vocabulary), JSON behind the existing `--json` |
| P0 | `prepare` manufactures a false violation from its own `__pycache__` byproducts; `.gitignore` written to fix it is itself flagged | First-run failure on essentially every Python repo; five failed prepares before first success | Wrong verdict attributed to the agent on run one | Ignore or auto-handle interpreter byproducts at baseline time (`.prompire/` is already special-cased — extend the precedent) |
| P0 | README says gitignore `.prompire/`; `ci.md` requires the brief tracked; a tracked brief then trips the brief-changed REVIEW locally | `README.md:172` vs `references/ci.md:44`; reproduced by reviewer | Adopting the Action as documented breaks local verify; Action silently `skipped` if you follow the README | Pick one rule (briefs tracked), fix the REVIEW to fire on change-since-arming, update both docs |
| P0 | PyPI and GitHub don't link to each other in either direction; wheel ships no SKILL.md/references/examples; error messages cite files the user cannot have | No `[project.urls]` in pyproject; zero `github.com` hits in docs; wheel RECORD = 11 .py files | User of the published package has no path to any documentation | `[project.urls]` + classifiers; ship docs as package data; make remedy strings name `prompire` subcommands, not internal scripts |
| P1 | `tests_policy: named`/`authoring` make green `verify` unreachable (REVIEW blocks the strict preflight) | Reproduced; `--ack-disarms` doesn't clear it (correctly) | Any task that legitimately edits tests ends red with acceptance NOT RUN | Run acceptance despite test-policy REVIEWs; exit non-zero with the REVIEW listed, so the human sees both |
| P1 | Remedies and help text teach the wrong interface (`baseline.py`, `check_scope.py the brief`, old usage strings) | Rendered agent prompt itself contains the broken invocation | Undermines precision-tool credibility | Sweep remedy strings and subcommand `--help` for the CLI-era interface |
| P1 | 21 hardening commits unpushed; documented Action pin two releases stale; no `--version` | `git rev-list origin/master..HEAD` = 21 at audit time; `ci.md:24` says `@v0.8.0` | Public repo shows pre-hardening code; copy-paste gets an old action | Push, release 0.9.2, fix the pin, add `--version` |

## 6. Proof strategy

The strongest evidence already exists and is unpublished. Across the committed
benchmark campaigns: with no brief, 9 of 20 live runs edited a forbidden test file and
`check_scope` caught all nine; with the brief, 0 of 110 did (Observed, raw rows in
`bench/campaigns/`). That is the whole product in one sentence — the brief prevents,
the checker catches — and it appears nowhere in the README or on PyPI. Publishing that
paragraph costs an hour and is the one claim a skeptic cannot wave away, because the
rows and the pre-registrations are already committed.

Second, rebuild the demo as two beats. Keep the `secrets.cfg` catch as beat one — it
teaches the mechanism in three seconds — but it must not be the closer, because a
skeptic correctly says "git status does that." Beat two is the wedge: the agent
completes a refactor, regenerates a golden file to absorb a one-character output drift,
and "fixes" a known-red legacy test. CI is green; the diff looks plausible; a reviewer
cannot know the output used to hash differently. Prompire catches it three ways from
state measured before the agent started (`before_after` digest, `hold` criterion,
`tests_policy`). This scenario is already encoded in `examples/worked-example.yaml` —
the demo just needs to walk it. No new benchmark task is needed; cite the nine existing
catches instead.

Third, the two-cycle test from §5 becomes executable proof that the tool survives its
own README — the current 13/13 suite never exercises a second cycle, which is exactly
why the trap shipped.

## 7. README strategy

The README is documentation-first; it should be conversion-first. Current first
screen: abstract contract description, then install, then workflow; the demo
transcript — the best asset — arrives at line 104. Restructure to: one-liner + the
"agent edits the suite it's graded on" problem statement (already good at lines 13–16),
then the demo transcript (eventually the two-beat version), then the benchmark
paragraph with the bare-vs-brief numbers, then the 60-second quickstart, then
guarantees and non-guarantees (the "What this is not" section is already excellent —
move it up; honesty is the differentiator here). Fix within the text: the
gitignore-vs-tracked contradiction, the `python3 baseline.py` script invocations a pip
user can't run, the `python3 prompire.py demo` label, and add the GitHub URL — the docs
never name their own repository. The "Measured, not asserted" section should carry the
actual numbers, not just the method.

## 8. Integration strategy

| Rank | Integration | Adoption leverage | Maintenance cost | Recommendation |
|---|---|---|---|---|
| 1 | Claude Code skill → plugin | High — the target user concentrated in one channel with a real discovery surface | Low-moderate | First-class. Prerequisite: ship SKILL.md + references in the distribution; add `.claude-plugin/` manifest so `/plugin marketplace add Wake360/prompire` works; SKILL.md must say "install the CLI first" (its own first command currently fails for a skill-only user) |
| 2 | GitHub Action | Highest ceiling — agent-neutral, verdict runs unasked on every PR; already complete and dogfooded | Lowest | Second, after fixing the tracked-brief incoherence and the stale pin. Marketplace listing only after — listing now broadcasts the contradiction |
| 3 | Generic CLI | Broad but manual | Already paid | Keep as-is; it's the substrate |
| 4 | Codex CLI | Moderate | Very low (no hook by design) | Keep cheap; it costs almost nothing |
| 5 | Copilot CLI / Antigravity CLI | Small audiences, highest fragility (Copilot fails closed on hook errors; Antigravity's semantics were measured against one build on one day) | Highest | Maintain, don't headline |

The Action's architecture already surfaces the verdict in PRs three ways (job summary,
annotations, sticky comment) — the PR-native experience in the task prompt exists and
works. The remaining gaps are documentation coherence and discoverability, not
engineering. One design honesty note to carry into its README: the Action neutralizes
`base_rev` re-stamping but trusts the brief in the PR; local pinning and CI
unskippability do not yet compose, and `ci.md` says so — keep saying so.

## 9. Trust and release gaps

The substance is strong: 13/13 suites pass on a clean clone, CI runs a real OS×Python
matrix, publishing is OIDC trusted-publishing with SHA-pinned actions, versions/tags/
changelog are consistent, and the internal strategy docs are confirmed untracked —
nothing embarrassing can surface on GitHub. The gaps that matter for adoption: the
missing PyPI↔GitHub links (worst gap, cheapest fix — a provenance tool whose own two
artifacts can't be connected); the unpushed hardening commits; the Windows claim being
broader than Windows testing (the encoding suite, which exists for a cp1252 failure
mode, never runs on Windows — either qualify the claim or extend the matrix); no
`--version`; and the flat 11-module top-level namespace, which reads as a script
collection and pollutes shared venvs — right fix is a `prompire/` package directory at
1.0, not now. Skip SECURITY.md for now; with zero users, linking the threat model is
worth more than a stub. One cheap future-proofing step: add a schema-version field to
the brief now, which is what makes *not* freezing the schema safe.

## 10. Things NOT to build

A hosted dashboard, service, or team tier — the internal verdict doc already flags
brief provenance as the missing B2B layer, but building it before ten real external
users exist is validating nothing; the no-service property is the product. More host
adapters — Copilot and Antigravity already cost the most maintenance per user reached;
a fifth host multiplies the hook-contract chase while the authority (the git diff
check) is host-neutral anyway. Further investment in `draft --agent` — it carries the
repo's most intricate risk surface (snapshot isolation, symlink re-aiming) for the
least differentiated capability, and SKILL.md itself says the host model should write
the brief. A schema freeze — premature with zero external briefs in the wild; version
the schema instead. A new adversarial benchmark task — the nine existing catches in the
`bare` arm already prove the checker; cite them. Telemetry of any kind — it would
contradict the trust posture that is the product's main asset.

## 11. Top changes ranked by impact / effort

| Rank | Change | User impact | Effort | Confidence | Why now |
|---|---|---|---|---|---|
| 1 | Fix the second-cycle trap (close→repin) + `__pycache__` false positive, with a two-cycle e2e test | Tool stops breaking on documented use | Medium | High (reproduced twice) | Every other investment funnels users into this wall |
| 2 | Human verdict output for `verify` (JSON behind `--json`) | The moment of truth becomes legible | Low | High | Closes the demo-vs-product credibility gap; cheap |
| 3 | Shop-window sprint: pyproject URLs+classifiers, docs as package data, push commits, 0.9.2, fix `ci.md` pin, `--version`, GitHub topics | Findable, self-explaining, current | Low | High | Almost entirely metadata; a day of work |
| 4 | Benchmark paragraph in README (9/20 bare vs 0/110 briefed) | The one claim skeptics can't dismiss | Very low | High | Evidence already committed; only unpublished |
| 5 | Two-beat demo ending on the pinned-baseline catch | Wedge becomes demonstrable, not argued | Medium | Medium-high | Demo is the top of the funnel; beat one alone invites "git status does that" |
| 6 | Resolve tracked-brief contradiction, then Claude Code plugin manifest, then Action Marketplace | First real discovery surfaces | Medium | Medium | Distribution only after the product survives it |

## 12. P0 launch plan

1. A fresh Python repo can run prepare → verify → close → prepare → verify and exit 0
   both cycles; a new e2e test in `tests/` asserts it.
2. `prompire prepare` on a repo with no `.gitignore` completes without manufacturing a
   `__pycache__` violation, and a lint-failed prepare can be re-run after fixing the
   lint error without hand-editing YAML.
3. `prompire verify` ends every run with one line — `clean`, `caught: N violation(s)`,
   or `no verdict: <reason> — run <command>` — and `--json` preserves today's output;
   golden tests updated.
4. `pip show prompire` lists a Project-URL; the wheel contains SKILL.md, references/,
   examples/; `prompire --version` prints 0.9.2; master is pushed and 0.9.2 released;
   `ci.md` pins the current action version.
5. README leads with the demo transcript and the benchmark numbers, states one rule
   for whether briefs are tracked, and both `ci.md` and SKILL.md agree with it.
6. `prompire demo` shows beat two: a golden-file regeneration plus a known-red-suite
   change, green in "CI," caught by the pinned baseline.
7. `/plugin marketplace add Wake360/prompire` installs a working Claude Code skill
   whose first documented command succeeds.

## 13. Success metrics

Repository metrics: GitHub traffic (unique clones and visitors, from repo Insights — no
telemetry needed); issues opened by people describing real runs on their own repos (the
single strongest signal; an issue quoting a `verify` verdict means the funnel worked
end-to-end); external repos with tracked `.prompire/*.yaml` files or `uses:
Wake360/prompire` in workflows, both findable via GitHub code search; PyPI downloads
via pypistats (noisy, trend only); stars only as a top-of-funnel proxy, never as
adoption.

Product metrics without telemetry: whether the demo→real-use gap closed can be read
from issue content — today a real user's first issue would be "verify prints JSON" or
"second task always red"; after the fixes, first issues should be about briefs and
policies, which is what product-market fit looks like for this tool. An optional issue
template asking "what did Prompire catch?" creates an opt-in catch log that doubles as
marketing evidence and future benchmark tasks.

## 14. Single highest-leverage next move

Make Prompire survive its own README: fix the close→repin trap and the `__pycache__`
false positive so that two consecutive documented cycles in a fresh Python repo both
end green, proven by a new two-cycle e2e test — and land the human verdict line in the
same release, since it is the surface where the fix becomes visible. Everything
else — demo, README, marketplace listings — increases the number of people who reach
the second task. Right now the second task is where the product refutes itself, so
distribution before this fix converts audience into churn, and churn on GitHub is
permanent in a way that a quiet launch is not.

---

Process note: the first-time-user audit left test artifacts only in the session
scratchpad; the repository was not modified by any of the five investigations. All
numbered claims above trace to this session's tool results or repo files; the few
judgment calls (positioning wording, integration ordering) are marked by their framing
as recommendations.
