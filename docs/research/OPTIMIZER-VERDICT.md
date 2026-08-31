---
title: Behavior-Constrained Optimization of AI-Generated Code — final verifier verdict
tags: [prompire, product, verdict, optimizer, patch-minimization, research]
date: 2026-08-06
source: first-hand measurement of the E3/E4 corpora + live reduction experiment + 10-agent external evidence sweep (TRIM, native simplify, GitButler, Atomic, PL prior art) + three fresh-context adversarial verifiers
related: [product-thesis.md, preregistered-kills.md, PINCITE-VERDICT.md, ../prompire-e3/FINAL-VERDICT.md, ../prompire-e4/FINAL-VERDICT.md]
---

# Behavior-Constrained Optimization of AI-Generated Code

Verdict on the proposal that Prompire become a post-generation optimizer: take a
successful coding-agent patch, apply candidate transformations (dead-change
elimination, existing-code reuse, abstraction reduction, dependency
elimination), validate each against executed tests, and keep only what survives.

Method: measurement first, then market. Every number in §4 was computed
first-hand from this repository's own frozen corpora; the reduction results in
§4 come from building the proposed mechanism and running it. External claims
were gathered by ten independent agents and re-verified by three fresh-context
adversarial verifiers whose only assignment was to break the thesis.

---

# 1. FINAL VERDICT

## FEATURE ONLY

The problem is real but the inventory is nearly empty where the product aims,
and the part that is full is the part the product must not touch.

On this repository's two frozen corpora — 380 successful, hidden-check-passing
agent patches across 61 tasks and ~28 repositories — the median successful agent
patch adds **+3 non-test source lines more than the human gold fix** (E4, ratio
1.21x) and **+1 line** (E3, ratio 1.06x); 30% of agent patches are *smaller*
than the human fix. New classes exceed gold in 1% of runs and dependency files
are touched in 2.5%, so abstraction reduction and dependency elimination have
almost no work to do.

I then built the mechanism and ran it on the six most bloated patches in the
corpus. It achieved 75–99% reduction in 2–41 seconds, and across all six the
total genuinely removable *implementation logic* was about twelve lines.
Everything else it removed was agent litter — `IMPLEMENTATION_SUMMARY.md`,
`debug_lexer.py`, `check_regex2.py`.

TRIM (arXiv:2607.18161, Columbia + Google, 2026-07-20) independently reports the
same shape from a different corpus and implementation: 72.5% of SWE-bench
Verified patches left completely unchanged, and 85.6% of removed lines are
scratch reproduction scripts and build/config files, with source ΔSlop of only
20.4% at an 11.5% share.

Meanwhile the transformations are already free. The `/simplify` prompt extracted
from the installed Claude Code binary (v2.1.223) contains a Reuse angle reading
verbatim "Flag new code that re-implements something the codebase already has —
Grep shared/utility modules and files adjacent to the change, and name the
existing helper to call instead." Anthropic's `code-simplifier` plugin shows
194,361 unique installs in the local install-counts cache.

The one genuine gap — no shipped tool gates cleanup on an executed test run — is
real, and TRIM's Table I proves it matters (deterministic search 17.9–32.9%
ΔSlop versus LLM cleanup at 2.1–8.9%, with the LLM failing outright in 3.8–44.9%
of cases). But that gap is a ~200-line wrapper, it has been built at least four
times already (`patchslim`, created and pushed within two hours on 2026-07-28, 0
stars; `pi-trim` 0 stars; `deslop` 3 stars; `sloppy` 8 stars), and the
prevention-side answer to the same pain has 97,316 stars.

Decisive, and unaddressed by any amount of engineering: **78% of successful
agent patches modify a pre-existing test file**, so the oracle sits inside the
patch being optimized — and when the reducer ran without protecting tests, it
"achieved" 95% reduction by deleting every test the agent wrote.

---

# 2. Product in One Sentence

`NO DEFENSIBLE PRODUCT THESIS`

The strongest honest version is a feature: *after your agent finishes, delete the
scratch files and dead hunks it left behind, and prove each removal against your
test command.* That is true, useful, roughly 200 lines, and already free in
three places.

---

# 3. Monday-Morning User

The sentence cannot be completed honestly at product scale. The nearest true
version is small:

> On Monday morning, a developer has just finished a two-hour agentic feature
> run using Claude Code. They run this because the agent left an
> `IMPLEMENTATION_SUMMARY.md` and three `debug_*.py` files in the repo root and
> they want them gone without reading the diff.

That is a `git clean` problem with a filename heuristic. It needs no behavioral
validation, no candidate search, and no product. The failure of the sentence is
the verdict: everything that survives contact with the evidence is either
trivial or free.

---

# 4. Problem Evidence

## VERIFIED — measured first-hand, reproducible

Corpora: `~/e4-artifacts` (276 successful patches, 40 tasks, 23 repos,
claude-sonnet-5 / claude-haiku-4-5) and `~/prompire-e3/runs` (104 successful
patches, 21 tasks, surfaces including feature, cli, api-service, refactor,
performance, migration). "Successful" means the hidden held-out check passed.
"Gold" is the human upstream fix. All figures are non-test source unless stated.

| Measurement | E4 (n=276) | E3 (n=104) |
|---|---|---|
| Added lines, agent vs gold | 17 vs 12 (**1.21x**) | 8 vs 7 (**1.06x**) |
| Median excess over human fix | **+3 lines** | **+1 line** |
| Runs smaller than gold | 30% | 29% |
| Files touched, ratio | **1.00x** | 1.00x |
| Ratio distribution ≤2x | 77% | 84% |
| Adds ≥1 new class | 9% (exceeds gold in **1%**) | 4% (exceeds gold in **0%**) |
| Adds ≥3 new defs | 10% | 9% |
| Touches a dependency file | **7/276 (2.5%)** — gold: 0/276 | — |
| Modifies a pre-existing test file | **78%** | — |
| Deletes lines from a pre-existing test file | 11% | — |
| Composition of added lines | 48% source / 46% tests / 6% litter | 19% source / 81% tests |
| Add-to-remove ratio | agent 10.5 : 1, gold 3.9 : 1 | — |

No E3 task surface exceeds a 2.0x median ratio. The highest are performance
(2.00x, n=9), migration (1.68x, n=5), cli and data (1.51x, 1.50x).

**The confound that matters.** The first pass measured 3.75x and 82% of agent
patches touching test files. Only 6 of 276 gold patches contain test files, so
the ratio was measuring "agents write tests, upstream fix commits do not." Once
tests are excluded from both sides, 3.75x becomes 1.21x. This is the E3-to-E4
corpus-artifact pattern repeating: the attractive number was an artifact, and
the correction was cheap and available before building anything.

**Where the excess actually lives.** 52% of everything an agent adds is test
code — the one surface an optimizer must not touch, and the surface that
constitutes its own oracle.

**Turn count correlates weakly with bloat**, which is the directional core of
TRIM's hypothesis: runs ≤25 turns produce patches at 0.89x gold; runs >50 turns
at 1.64x (Pearson r = 0.25, n = 275). The direction holds; the magnitude in this
regime is about six lines.

## VERIFIED — live reduction experiment

The proposed mechanism, built in ~60 lines of Python: split the patch into
per-file chunks and per-hunk units, greedily attempt removal largest-first,
materialize each candidate in the workspace, run the hidden held-out check, keep
the removal if it still passes.

Run against the six worst-bloat successful patches in E4, with test files hard-protected:

| Task | Repo | Source lines before → after | Reduction | Runs | Wall |
|---|---|---|---|---|---|
| H03 | PyCQA/flake8 | 59 → 43 | 27% | 6 | 9s |
| H32 | seperman/deepdiff | 208 → 8 | 96% | 5 | 30s |
| H13 | pallets/flask | 200 → 20 | 90% | 7 | 3s |
| H01 | adrienverge/yamllint | 171 → 43 | 75% | 10 | 6s |
| H19 | andialbrecht/sqlparse | 141 → 2 | 99% | 8 | 2s |
| H05 | rubik/radon | 121 → 13 | 89% | 6 | 9s |

What was removed, in full: `IMPLEMENTATION_SUMMARY.md` (113), `PYTHON_MODULE_USAGE.md`
(86), `JSON_ERRORS_FEATURE.md` (124), `JSON_FORMAT_DEMO.md` (128),
`FAIL_ABOVE_EXAMPLE.md` (107), `example_json_errors.py` (47), `debug_lexer.py`
(45), `trace_lexer.py` (42), `trace_lexer2.py` (27), `check_function.py` (15),
`check_regex2.py` (9), `check_flatten.py` (8), `check_regex.py` (8), plus four
source hunks totalling **11 lines**.

Across the six worst patches in a 276-patch corpus, the total removable
implementation logic is about twelve lines. The rest is markdown self-reports
and debug scratch scripts, which a filename rule finds for free with zero
validation runs.

**The objective-function failure, demonstrated.** Running the same reducer on
H03 *without* protecting test files yields 840 → 44 added lines, a 95%
reduction, achieved by deleting all thirteen test files the agent wrote. The
metric is maximized by destroying the tests. Protecting them costs 46–81% of the
addressable surface by fiat.

Corpus-wide, litter appears in only 3% of successful patches but accounts for
11% of all non-test added lines, at a median of 128 lines when present —
concentrated exactly in the tail, matching the reduction runs.

## VERIFIED — external, independently convergent

TRIM leaves 237 of 327 SWE-bench Verified patches (72.5%) completely unchanged.
Of the lines it does remove, 49.6% are scratch reproduction scripts and 35.8%
are build/config files; source is 11.5% of removed lines at 20.4% ΔSlop. Its
DD-Hunk baseline, which uses no trajectory at all, scores 31.5% against TRIM's
32.9% (p = 0.50). LLM cleanup with full test-suite access, a 6-hour and $5.60
budget: 2.1–8.9% ΔSlop, failing outright in 3.8–44.9% of cases via patch
inflation, file mismatch, or bug reintroduction.

## PLAUSIBLE

"To Add Is Machine, To Delete Is Human" (arXiv 2607.28887): passing patches
retain 28.3–34.8% of required deletions, 1.67x median size ratio versus the
developer patch, 29% Guard-and-Go wrap-instead-of-delete. This corpus partially
replicates the direction — agents add 10.5 lines per line deleted against the
human 3.9 — though absolute deletion counts are 1–2 lines.

METR: grader-passing agent PRs merge at ~50% against 68% for gold, a 24.2pp
grader-versus-maintainer gap. Google: 43.5% of test-passing patches judged
invalid by LLM-as-judge. GitClear (623M changed lines): copy/paste 9.4% → 15.7%,
refactoring line-moves down 70%.

## WEAK

Dependency inflation (2.5% inventory here, no quantitative literature found).
Abstraction over-generation (1% inventory here, no literature at all).
Duplicated-functionality reuse (no measurement anywhere).

## FALSE as stated

"Successful agent patches are materially larger than they need to be." At the
median they are not — they are +3 lines. Two independent real-world agentic-PR
rejection taxonomies (33,596 and 3,225 PRs) contain **no over-engineering
category**; PRs die of reviewer abandonment (38%), duplication (23%), and CI
failure (17%). Patch size is a weak discriminator of merge outcome
(Cliff's delta = −0.17).

---

# 5. Competition Map

## Native and bundled — free, zero install

**Claude Code `/simplify`**, verified by extracting the prompt from the installed
binary at `~/.local/share/claude/versions/2.1.223`. Menu description: "Clean up
the changed code without changing behavior." Phase 0 runs `git diff
@{upstream}...HEAD`. Phase 1 fans out to four parallel subagents on angles
Reuse, Simplification, Efficiency, Altitude. Phase 2 applies the fixes.
**Zero occurrences of test, build, verify, or revert in either prompt variant.**
Behavior preservation is delegated to the model: "Skip any finding whose fix
would change intended behavior… or that you judge to be a false positive."

Lifecycle from the official changelog: added v2.1.63; renamed to `/code-review`
and cleanup-and-fix removed at v2.1.147; restored at v2.1.152; re-split at
v2.1.154; five cleanup finders merged at v2.1.196; autonomous invocation removed
at v2.1.215. Six iterations in six months — an actively staffed surface.

**`code-simplifier@claude-plugins-official`**: 194,361 unique installs, 5th most
installed official plugin (local `install-counts-cache.json`, fetched
2026-04-16, so likely higher now). Its agent file explicitly warns against
removing "helpful abstractions that improve code organization" — the direct
opposite of the de-abstraction pass.

**GitHub Copilot** ships a "cleanup specialist" custom agent that removes dead
code, simplifies complex logic, consolidates duplicates, and already prescribes
the gate: "Always test changes before and after cleanup." GitHub's agentic
autofix already ships the exact loop, pointed at CodeQL alerts: "reruns the
original analysis to confirm the fix closes the alert."

## Research prior art

**TRIM** (arXiv:2607.18161, 2026-07-20, Mathai / Iyer / Nogikh / Maniatis /
Ivančić / Yang / Ray). Deterministic hierarchical delta debugging over agent
trajectories: replay including undos, normalize to (file, before, after),
coarse-to-fine removal at edit-sequence, file, and edit-action granularity,
accept iff the test suite passes and patch length strictly decreases. No LLM in
the loop. No code release 17 days post-publication. Explicitly subtractive by
design: "Rather than synthesizing a new solution from scratch, minimization asks
which parts of the agent's existing solution are unnecessary."

**PyTy** (ICSE 2024) Algorithm 1 is hunk-level ddmin over `diff(f_old, f_new)`
with a parsability guard and a type-checker oracle, O(N log N), audited at 94/100
minimal. **DEPTEST** (SANER 2021) reduced 41.01% of already-manually-purified
Defects4J human patches by a further 4.3 lines on average. **GenProg** (TSE 2012)
used delta debugging to compute a 1-minimal repair-edit subset against a test
suite, and chose tree edits over diff hunks precisely because partial tree edits
are never syntactically ill-formed. **ORBS** (FSE 2014) documents the
coupled-lines problem and solves it with a moving deletion window.

## Direct OSS — all pre-traction

| Project | What it is | Stars |
|---|---|---|
| `Apex-Studio-He/patchslim` | "Test-guided minimization for Git diffs." Worktree isolation per candidate, file-then-hunk delta debugging, quick/full gate tiers, candidate caching, evidence artifacts. Created and pushed within two hours on 2026-07-28. | **0** |
| `sergeytimoshin/pi-trim` | Faithful TRIM implementation, bash oracle, revert-on-fail. No activity in 16 days, on a harness with 84.7k stars. | **0** |
| `agent-sh/deslop` | "AI slop cleanup with minimal diffs and behavior preservation." Auto-fixes, runs the suite, rolls back — all-or-nothing. | **3** |
| `braedonsaunders/sloppy` | Mechanical keep-if-tests-pass loop. Stale. | **8** |
| `LeonardNJU/code-humanizer` | Same family. | **41** |

`patchslim`'s own README states the honest ceiling: "A passing candidate is
evidence relative to the configured checks, not proof of complete behavioral
equivalence."

## Prompt-side incumbents — enormous traction

`addyosmani/agent-skills` (82,653 stars) contains a `code-simplification` skill
that is model-agnostic, scoped to changed code, targets "factory-for-a-factory,
strategy-with-one-strategy" and dead code, and prescribes this product's loop
verbatim: "FOR EACH SIMPLIFICATION: 1. Make the change 2. Run the test suite
3. If tests pass → commit 4. If tests fail → revert and reconsider."

`DietrichGebert/ponytail` (97,316 stars, created 2026-06-12) attacks the same
pain from the prevention side — make the agent write less up front.

## Substitutes

**Gitar**, acquired by Sonar 2026-05-21, five weeks after a $9M launch. Homepage
verbatim: "Not just comments. Real fixes, validated against your CI pipeline."
Transformation-plus-validation inside a vendor with a twenty-year code-smell
taxonomy that already names dead code, redundant abstraction, and duplicated
logic. **Greptile TREX** (beta ~2026-06-15) runs the PR branch in a sandbox and
writes and runs tests, proving the execution primitive is now table stakes for
review vendors.

## The two assigned boundary targets

**GitButler** (21,418 stars, $17M a16z Series A 2026-04-08). Ships change
*organization* exclusively: virtual and stacked branches, hunk-level assignment,
commit split/squash/amend/move/absorb, a `but` CLI, AI commit messages, AI
conflict resolution. No test execution, no behavior validation, no diff
reduction anywhere in docs, releases 0.21.0–0.22.0, or 2026 blog posts. Its own
agentic benchmark measures version-control operation efficiency, not code
quality. **ADJACENT / LOW.**

**Atomic** (`atomicdotdev/atomic`, 75 stars, 6 forks, Apache-2.0, Rust, $2.5M
pre-seed, created 2026-02-23). Distributed semantic change graph with token-level
CRDT layer and a provenance DAG that classifies agent tool calls as
Exploration / Commitment / Verification. It classifies but does not execute; its
docs contain no testing, refactoring, or change-reduction commands. Positioning
is epistemic ("Trust what you can prove"), orthogonal to optimization.
**PRIMITIVE / LOW.**

---

# 6. Closest Collision

**Claude Code's bundled `/simplify`.**

Not because it is better — it is strictly weaker on the one axis that matters,
since it never executes anything. It is the closest collision because it occupies
the exact slot at zero acquisition cost inside the tool that produced the patch,
covers three of the four proposed passes with a transformation vocabulary that
matches almost word for word, and has been iterated six times in six months by a
team that clearly owns it. A product whose entire delta over a free bundled
command is "and we also ran your tests" is a wrapper.

Runner-up, and more dangerous commercially: **Sonar/Gitar**, which already ships
apply-fix-then-validate-against-CI with enterprise distribution.

---

# 7. Actual Whitespace

## NO DEFENSIBLE WHITESPACE

There is a real *mechanical* gap: nothing shipped gates cleanup on an executed
test run. It is narrow and it is not defensible, for four independently
sufficient reasons.

**It has already been built by strangers.** `patchslim` implements file-then-hunk
delta debugging with worktree isolation and evidence artifacts; its git history
shows creation and final push within two hours. Zero stars. So does `pi-trim`.
Three more sit at 3, 8, and 41. That is the market test, already run, four times,
by other people.

**The algorithm is published, three times, twice at exactly hunk granularity over
a diff.** Any novelty claim on the reduction core dies in one search.

**The value delivered is not what the pitch describes.** TRIM's file-type
breakdown says 85.6% of removed lines are scratch and build/config files; the six
reduction runs here removed markdown self-reports and debug scripts and about
twelve lines of real logic. Deleting `debug_lexer.py` does not need a behavioral
oracle — it needs a filename rule, which is what this repository's existing scope
allowlist already is.

**Three of the four passes are outside the gate's reach in principle.** A test run
can confirm that removing X is safe. It can never confirm that rewriting X into Y
is better, that Y is more idiomatic, or that Z should have been removed. Reuse
substitution, de-abstraction, and idiomatic rewrite are synthesis; the gate
validates only subtraction. The defensible mechanism and the valuable
transformations do not overlap.

---

# 8. Native Feature Risk

## HIGH

Not a forecast — the present state. `/simplify` shipped, was removed, was
restored, and has been refined five more times since. The remaining step (swap
the LLM verifier for the repo's test command) is a sandboxing and configuration
problem, not a research problem, and GitHub already ships the identical loop
pointed at CodeQL alerts.

FATAL is withheld only because the execution gate genuinely has not shipped and
vendors have visible reasons to avoid running arbitrary user test commands.

---

# 9. Technical Depth

## OLD TECHNIQUE REPACKAGED

Delta debugging is from 1999. PyTy's Algorithm 1 is this product's V1 in about
thirty lines of pseudocode. A working version took ~60 lines of Python here and
produced correct minimal subsets on six real patches in 5–18 validation runs and
2–41 seconds each.

The failure modes are all documented in advance: syntactically invalid hunk
subsets (GenProg avoided diff-level minimization for exactly this reason),
coupled lines that only delete in tandem (ORBS solves it with a δ=3 moving
window), and the granularity ceiling where a patch arrives as one large hunk and
hunk-ddmin does nothing.

One honest engineering claim survives: execution evidence has precision static
analysis lacks. In the technical verifier's own run, hunk-level ddmin removed
exactly the two genuinely dead functions with zero false positives, where
`vulture` at 60% confidence flagged seven functions of which five were live.
Reachability cannot distinguish "exported but unused" from "dead"; a test run
can. That is real, and it is a feature.

---

# 10. Behavior Oracle Risk

## SEVERE — structurally worse than a weak-test-suite problem

**The oracle is inside the patch.** 78% of successful agent patches in E4 modify
a pre-existing test file and 11% delete lines from one. The keep/discard signal
was authored, in part, by the same agent whose output is being optimized. This
repository's own E4 postmortem documents the concrete case: an agent rewrote
three pre-existing yamllint tests to assert its own wrong behavior, the suite
went green, `D_differential_tests` reported DISCRIMINATES in 112 of 112 accepts,
and only the hidden held-out check caught it. An optimizer trusting that suite
would have confirmed the wrong behavior as preserved.

**The oracle is blind by construction to exactly this content.** arXiv 2607.28887
establishes that this bloat exists *because* tests do not detect its removal —
adding deletion-sensitive tests cost 21.3pp of resolution. A keep/discard rule of
"tests still pass" inherits the precise blind spot that created the bloat. It
will delete untested guards, log lines, and error paths with perfect confidence.

**The objective is maximized by destroying the oracle.** Demonstrated above: run
the reducer without protecting test files and it achieves 95% reduction on a real
patch by deleting all thirteen test files the agent wrote. The metric and the
goal point in opposite directions, and the correction removes most of the
addressable surface.

Mutation testing, generated tests, and differential testing do not rescue this.
Each costs more compute than the reduction saves, and generated tests are
authored by a model against the patch being audited.

No marketing claim stronger than `patchslim`'s own caveat is licensed.

---

# 11. Shape Ranking

**1st — Shape A, Patch Minimizer.** The only shape whose claims survive. Clarity
high, depth low (published algorithm), competitive risk high (built four times at
0–8 stars), complexity ~200 lines, GitHub potential low, absorption risk high.
Ranked first because it is the only one that is *true*, not because it is viable.

**2nd — Shape B, Behavior-Constrained Optimizer.** The proposed product. Its
three extra passes are synthesis, which the gate cannot validate; the gate would
be checking an LLM rewrite against a suite the same class of model wrote. It
inherits `/simplify`'s competition on the transformations and Shape A's on the
mechanism, facing both without owning either. Its dependency and abstraction
passes address a 2.5% and 1% inventory respectively.

**3rd — Shape C, Full Change Compiler.** Dominated on every axis. Patch
atomization is GitButler's shipped, funded product. Multi-candidate comparison is
best-of-N, native in Cursor, already killed in `product-thesis.md` §19 for
native absorption. Change IR is Atomic's substrate, and better than a diff parser.

---

# 12. Prompire Asset Reuse

## DIRECT REUSE

The **E3 corpus** is the strongest asset on disk: 25 tasks, 331 recorded agent
patches (251 passing), hidden checks, gold patches, and 202 MB of local bare
mirrors for offline replay. The **E4 corpus** adds 40 tasks, 40 gold patches, 40
hidden held-out checks, and 530 patches under `~/e4-artifacts`. **E5** adds 49
tasks and 93 patches in TypeScript/JS with full transcripts.

`bench/tc_eval.py::clone_at` + `apply_patch` + `grade_arms` is already
"materialize repo@rev + patch, run tests, get per-arm pass/fail."
`verify_acceptance.py::verify` with `baseline.py::run_one` / `verdict` is the
run-command-get-structured-verdict kernel.

## REFACTORABLE

`prompire-e3/bin/mkws.py` with `prompire-e4/bin/prune_mirrors.py` is a hardened
isolated-checkout primitive with per-task leak-proofing.
`check_scope.py::changed()` handles renames and untracked files correctly.
`brief_common.py`'s glob engine is reusable for path policies — protecting test
files, for instance. `e2lib.py::capture_patch()` is the inverse operation.
`prompire-e4/bin/test_isolation.py` is a mechanical isolation self-test worth
adapting.

## IRRELEVANT

`prompire.py` (1,456 lines), the brief lint/compile/render family, all four hook
guards, `bench/run.py`, `bench/variants.py`.

## MUST BE BUILT — does not exist anywhere across six repos

Hunk-level patch mutation. Nothing parses an `@@` header, splits a patch into
hunk objects, or re-serializes a subset. Confirmed by grep across the main repo
and all five experiment repos. It is the only genuinely missing primitive, and it
is a weekend.

## SHOULD DELETE

Nothing. The corpora retain value independent of this direction — they are the
artifact that eval-environment work pays for, which round three of
`product-thesis.md` already identified.

---

# 13. Previous-Lesson Check

This direction repeats **four** of the five documented Prompire failure patterns.

**Empty inventory at the model's baseline floor (E5).** E5 died because 9–10 of
13 real maintainer rules sat at a zero-violation baseline — the model already
avoided the mistake without being told. Same shape here: median excess +3 lines,
abstraction inventory 1%, dependency inventory 2.5%. The mechanism is aimed at
behavior current models have largely stopped exhibiting.

**The corpus-artifact pattern (E3 → E4).** E3's −45% headline became 12.5% on a
fresh corpus once the cost ratio was corrected. Here 3.75x became 1.21x once one
confound was corrected. Both times the attractive number was an artifact, and
both times the correction was cheap and available before building.

**The market-shape kill (`product-thesis.md` §3).** "wtcraft, Prompire's
exact design, 206 commits, 3 stars; six independent Stop-hook verification gates,
0–3 stars each." Substitute `patchslim` (0), `pi-trim` (0), `deslop` (3),
`sloppy` (8), `code-humanizer` (41) and the paragraph is unchanged. Demand
satisfied by two hours of work against a free substrate does not convert into a
product — and this time somebody has already done the two hours.

**The vendor-absorption base rate.** Prior verdict measured ~12 months for
orchestration workarounds. Here absorption already happened: `/simplify` covers
three of four passes and has been iterated six times in six months.

**The one pattern that does NOT repeat, and it deserves credit.** Every prior
experiment found the simple baseline beating the sophisticated mechanism — RAW
11.0 vs PROMPIRE 10.5, context helped 3 / hurt 6, a perfect detector saving 12.5%
against a 20% gate. Here the sophisticated mechanism genuinely wins: TRIM's
deterministic search scores 17.9–32.9% against LLM cleanup's 2.1–8.9%, with the
LLM failing outright in up to 44.9% of cases. That is the strongest fact in this
direction's favour and it is why the verdict is FEATURE rather than KILL. It is
not enough, because what the mechanism wins is mostly the right to delete scratch
files.

---

# 14. Competitive Verifier

**Verdict: NARROW BUT REAL GAP.**

- **Most Dangerous Competitor:** Sonar/Gitar — apply-fix-then-validate-against-CI
  with enterprise distribution and a mature code-smell taxonomy. OSS runner-up:
  `Apex-Studio-He/patchslim`, a strictly better artifact than `pi-trim`, built in
  two hours, 0 stars.
- **Most Dangerous Native Feature:** Claude Code `/simplify` v2.1.223, verified by
  binary extraction independently three times.
- **Most Dangerous Research Prior Art:** TRIM — commoditizes the subtractive
  pillar, kills the trajectory differentiator by its own ablation (DD-Hunk 31.5%
  vs 32.9%, p=0.50), and its file-type breakdown reveals the reduction is mostly
  scratch files.
- **Most Dangerous Old-School Technique:** hunk-level ddmin, published as PyTy
  Algorithm 1 (ICSE 2024).
- **12-Month Kill Risk:** high.

Methodological caution carried forward: two agents asserted "GitHub search returns
zero relevant repos" while `patchslim` had been public for nine days. Absence of
evidence in this niche has repeatedly been wrong.

---

# 15. Technical Verifier

**Verdict: FEATURE.**

The verifier built and ran the baseline rather than reasoning about it, and
cross-checked against Zeller 1999, DDJ/DDP (ESEC-FSE 2018), C2D2 (ISSTA 2024),
Perses, Vulcan, ProbDD, and LPR. Concurring evidence from the run in §4: 60 lines
of Python, 5–18 validation runs per patch, 2–41 seconds.

Its strongest dissent, on the record: hunk-level ddmin removed exactly the two
genuinely dead functions with zero false positives where `vulture` at 60%
confidence flagged seven, five of them live. Execution evidence is more precise
than reachability analysis. That is a real capability. It is a feature.

---

# 16. User-Demand Verifier

**Verdict: WEAK PULL.**

The job is real and daily — HN 48458586 (501 points), user `kaydub`: "for every
prompt of building I'm going to have 1-5 prompts of refinement." But the thing
people reach for is a *prompt*, free and in-session, not a tool requiring a
context switch.

The decisive datapoint is a natural experiment on the same problem at two
timings: prevention (`ponytail`) has 97,316 stars in under two months; post-hoc
test-gated minimization (`pi-trim`) has 0 stars and no activity in 16 days, on a
harness with 84.7k stars. Roughly five orders of magnitude, same pain, opposite
timing.

Recorded dissent, because it is the best case anyone made: HN commenter `verall`
— "giving it 'rules' not to do this does nothing, but a separate pass… does
okay" — and JetBrains measured `ponytail` at 15.4% reduction against its
advertised 54%, self-activating zero times without a forcing hook. Prevention may
be winning on distribution while losing on efficacy. That is the one thread worth
remembering, and it is not enough to carry a product.

---

# 17. Kill Criteria

| # | Criterion | Result | Evidence |
|---|---|---|---|
| 1 | Patch bloat not materially real | **FAIL** | Median excess +3 lines (E4) / +1 (E3); 30% smaller than gold; abstraction inventory 1%, dependency 2.5%. Real only as a 5% tail, and that tail is litter. |
| 2 | Users do not care enough | **WARNING** | Pain verified (97k-star prevention skill, 194k plugin installs, 7,520 CLAUDE.md files mentioning over-engineering). Pull toward *this shape* weak: 0 stars on the built article. |
| 3 | Native `/simplify` captures most value | **FAIL** | Verified in binary v2.1.223: Reuse, Simplification, Efficiency, Altitude; free; six iterations in six months. Misses only the gate. |
| 4 | ddmin/TRIM captures most value | **FAIL** | PyTy ICSE 2024 is hunk-ddmin over a diff. TRIM published with both mandatory baselines. `patchslim` is the packaged version, 0 stars. |
| 5 | Weak test suites make optimization unsafe | **FAIL** | 78% of patches modify pre-existing tests; unprotected reduction deletes all tests for a 95% "win"; the bloat exists precisely because tests don't detect it (21.3pp cost of deletion-sensitive tests). |
| 6 | GitButler already solves the user job | **PASS** | Organization only; `git diff --stat` unchanged after it runs. The distinction is real, not wordplay. |
| 7 | Atomic can absorb the product trivially | **PASS** | 75 stars, runs no tests, displacing Git is its own problem. Watch, don't fear. |
| 8 | Differentiation is only "execution-backed" | **FAIL** | Confirmed by three independent verifiers. It is ~200 lines and it is the entire delta. |
| 9 | Optimization cost exceeds review savings | **WARNING** | Cost is low (2–41s, 5–18 runs). Savings are also low: ~3 lines at the median, ~12 lines of logic across the six worst cases. |
| 10 | Smaller patches are not consistently better | **FAIL** | arXiv 2606.21804 (1,377 instances, 78 repos): LOC and complexity have minimal predictive power for downstream harm; contract drift does. Anthropic's own simplifier warns against removing "helpful abstractions." |
| 11 | Requires invasive agent integration | **PASS** | Post-hoc, diff-only. Genuinely model-agnostic. |
| 12 | Only works with recorded trajectories | **PASS** | Refuted by TRIM's own ablation: DD-Hunk 31.5% vs 32.9%, p=0.50. Do not build trajectory capture. |
| 13 | Secretly an audit tool again | **PASS** | Genuinely clears the anti-audit gate — it produces the artifact, not a report. The strongest structural argument in its favour. |
| 14 | README demo compelling, daily usage weak | **FAIL** | The 95%-reduction demo is achievable and would be dishonest (it deletes the tests). The honest number is 27% on the worst case and ~0% at the median. |
| 15 | Existing Prompire code gives little leverage | **PASS** | Strongest PASS in the table. Corpora and isolation machinery are directly reusable and substantial. |

Seven severe FAILs. Criteria 1, 5, and 10 are individually decisive: the
inventory is empty, the oracle is compromised, and the objective is not
correlated with the goal.

---

# 18. Recommended Experiment

**Not applicable — and the reason matters more than the non-recommendation.**

The preregistered GO gate as drafted (≥20% median reduction in changed LOC, and
≥10pp over strong-LLM cleanup) **would pass on evidence that already exists**.
TRIM reports 17.9–32.9% against an LLM baseline of 2.1–8.9%. Running a 50–100
task version would reproduce a published result, clear the bar, and teach
nothing — because the metric is wrong. Changed LOC is maximized by deleting
scratch files and, if unguarded, by deleting tests. Both are precisely what
TRIM's file-type table and the six runs in §4 show the reduction consists of.

Rewrite the gate to measure what the product actually claims — reduction in
non-test, non-scratch, non-config implementation lines, with test files
hard-protected — and the answer is already on the table from two directions:
TRIM's source ΔSlop of 20.4% over an 11.5% share, and this repository's corpora
at a median excess of +3 lines. That reformulated gate fails.

This is the habit `product-thesis.md` §18 named and rejected: a mechanism
experiment standing in for the demand experiment. Do not run it.

---

# 19. What Result Would Make This Exciting?

On ≥50 real agent patches from *feature-shaped* tasks — not SWE-bench bug fixes —
with test files hard-protected and scratch, markdown, and config files excluded
from the metric:

**≥25% median reduction in implementation lines, with ≥15pp of that surviving a
held-out oracle the optimizer never saw, and zero held-out regressions across the
corpus.**

Plus one thing no quantity of reduction substitutes for: a demonstration that the
removals are ones a reviewer *agrees* should go. METR's data says test-passing and
merge-ready differ by 24.2 percentage points, so a reduction metric with no human
agreement measurement is measuring the wrong endpoint.

The corpus gap is the real obstacle: feature-shaped tasks have no gold reference,
so minimality cannot be defined empirically. You would be optimizing toward an
unknown target.

---

# 20. What Result Would Kill It Immediately?

Already obtained: **with test files protected, the median successful agent patch
yields under 5% removable implementation lines, and the six worst-bloat patches in
a 276-patch corpus yield about twelve lines of real logic between them — the rest
is scratch files a filename rule finds for free.**

---

# 21. Final Decision

## FEATURE ONLY

Build nothing new. If the litter cleanup is wanted, it is a ~200-line subcommand
on the existing verifier — file-level then hunk-level reduction, test paths
hard-protected, honest evidence output — and it should be described as tidying,
never as optimization.

The Prompire product search stays closed. The 2026-08-06 decision to build
`pincite` stands. The corpora are the durable asset and are worth keeping.

---

## Appendix — reproduction

Measurements in §4 were computed from `~/e4-artifacts/{adaptive,grades}.jsonl`
plus `~/e4-artifacts/<cell_key>/final.patch` against `~/prompire-e4/gold/`, and
from `~/prompire-e3/runs/stage2.jsonl` plus `~/prompire-e3/runs/diffs/` against
`~/prompire-e3/gold/`. "Successful" is `final_pass == true` / `success == true`,
i.e. the hidden held-out check passed. Test-file classification regex:
`(^|/)(tests?|testing)/|(^|/)test_[^/]*$|_test\.[a-z]+$|conftest\.py$`.

The reduction experiment cloned each repo at the task pin, ran the task's own
`setup` block, applied candidate subsets with `git apply`, and used
`~/prompire-e4/hidden/<TASK>/check.py` as the oracle. Baseline failure and
full-patch pass were confirmed before each reduction.

Limits, stated plainly. Both corpora are Python-ecosystem, bounded tasks with
hidden checks completing in under 120 seconds, run by claude-sonnet-5 and
claude-haiku-4-5 with median 41 turns. They under-sample large greenfield feature
work, which is where the bloat hypothesis is most plausible and where no gold
reference exists to measure against. The reduction experiment is n=6, chosen as
the entire top of the bloat tail rather than a random sample. `/simplify` was
verified by string extraction from the shipped binary, not by executing it.
