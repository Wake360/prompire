---
title: Task Compiler — prototype, evaluation, and verdict
tags: [prompire, compiler, task-compiler, tc, evaluation, verdict]
date: 2026-08-04
source: implementation and evaluation session on branch task-compiler, 0d23564..HEAD
related: [docs/compiler-v2-report.md, docs/compiler-v1.md, bench/tc_corpus/PREREG.md]
---

# TASK COMPILER ARCHITECTURE FAILED

The prototype was built, evaluated against a frozen preregistered corpus, and
attacked by four fresh-context reviewers. It failed its own preregistered gate
at **contract quality 0/8**, which fires the kill condition, and independent
review confirmed that its central trust claim — that a compiler-established
decision has earned the right to ship without human confirmation — **is not
implemented correctly**. Both results are reported below without softening.

One capability did work, and the evidence for it is mechanical: the Breaker
found and the orchestrator *verified* a plausible wrong implementation that the
compiler's own first specification would have accepted, on all 6 of the 6
tasks where it ran to completion. That is the moat mechanism, and it functioned.
Everything built around it is what failed.

Nothing here is merged. The work sits on branch `task-compiler`, unmerged,
untagged, unpublished. **It should not be merged in its current state** — see
"Live defects" below.

## 1. Product experience

What a run actually looks like, from the live smoke fixture (a `slugify` that
leaves stray separators at the ends of its output):

```console
$ prompire compile "slugify leaves stray separators at the ends of the result"
compiling: slugify leaves stray separators at the ends of the result
✓ specification candidate resolved (6 requirements)
✓ reproduced on HEAD (8 failing case(s)); 1 regression command(s) green
✓ stress-tested: the breaker's candidate was caught by the oracle (round 1)
✓ contract ready — no human decisions required
  .prompire/slug.yaml
  cost: 3 model call(s), 604.0s, $2.91
next: prompire prepare .prompire/slug.yaml
```

The emitted contract is small — goal (the user's sentence, verbatim), scope,
two constraints, an acceptance block, `autonomy: ask`:

```yaml
goal: |
  slugify leaves stray separators at the ends of the result
scope:
  - textkit/__init__.py
forbidden: []
constraints:
  - slugify('Hello World') stays 'hello-world' and slugify('Hello -- World') stays 'hello-world'.
  - The result never starts or ends with sep, for any sep value used by callers.
tests_policy: immutable
acceptance:
  - cmd: python3 -c "import hashlib,runpy,sys;p='.prompire/probes/slug.py';…assert d=='847e53…','probe-tampered';…"
    expect: exit 0
    transition: flip
  - cmd: PYTHONPATH=. python3 textkit/tests/test_slugify.py
    expect: exit 0
autonomy: ask
```

The work behind that sentence: one Resolver session investigates the repository
and writes a candidate specification plus an executable probe file; the
orchestrator runs every probe case on an untouched copy and requires the
behavioral ones to FAIL there; a Breaker in a fresh context tries to build a
wrong implementation the oracle would accept; the orchestrator applies that
write-set to another fresh copy and re-runs the oracle to decide whether the
weakness is real; a confirmed weakness sends the specification back for
strengthening, bounded at two rounds.

## 2. Difference from Superpowers

An independent fresh-context reviewer was asked whether this could reasonably be
described as brainstorming before coding, and returned **BRAINSTORMING: no**,
with these as the load-bearing differences: the Resolver prompt forbids the
interview outright and gates questions behind investigation ("Never ask what the
repository can answer"); questions are capped at two and then *refused* rather
than pursued (`INSUFFICIENT_SPEC`, "this request is a product-design task, not a
compilable one"); there is no dialogue loop at all — one non-interactive
pipeline, with residual questions emitted as marked lines in a file; the primary
artifact is executable (a probe suite plus an acceptance command), not prose;
and approval steps are treated as a defect class to be scrubbed rather than a
workflow step.

The same reviewer named where the boundary is thinner than the design claims,
and those qualifications belong here: `NEEDS_DECISION` is structurally still a
human approval gate, just file-based and asynchronous; the Resolver's gap
analysis is literally a brainstorming question list, separated only by the fact
that step 3 answers it from the repository rather than from the human; and the
`constraints:` block is the one place model-written English survives into the
delivered prompt, where it reads like design notes.

## 3. Architecture

```text
request (verbatim)
  → Resolver session: gap analysis → targeted investigation → candidate spec + probe file
  → orchestrator: run every case on an untouched copy
       behavioral cases MUST fail here (reproduction); others must pass
  → Breaker session (fresh context): plausible wrong implementation + counter-probe
  → orchestrator: apply the write-set to a fresh copy, re-run the oracle
       green ⇒ weakness CONFIRMED; anything else ⇒ not a weakness
  → Refiner session: strengthen the spec against the confirmed class (≤2 rounds)
  → questions: 0 ⇒ READY | 1–2 ⇒ NEEDS_DECISION | >2 ⇒ INSUFFICIENT_SPEC
  → emit: brief + probe + decision ledger; validate with the real baseline/lint/render
```

Roles run as separate host sessions with no shared context. The Breaker never
receives the hidden corpus truth, the gold patch, or the Resolver's reasoning —
only the request, the requirements, the oracle, and the repository copy.

## 4. Trust model — as designed, and as actually implemented

Designed classes: **user** (the request, carried verbatim), **measured** (the
orchestrator ran it: a probe case red on HEAD, a regression command green),
**derived** (model inference that survived the bounded attack), **decision**
(materially ambiguous — emitted as a marked line the existing draft gate
refuses, exactly as before).

**As implemented, the boundary between "measured" and "asserted" is drawn in the
wrong place.** Four fresh-context reviewers were pointed at it; the trust
reviewer executed proof-of-concepts on this machine. Verified independently by
me before inclusion here:

- **The compiler never runs the probe the way the contract runs it.**
  `measure_spec` executes each case explicitly (`python3 probe.py <case>`); the
  delivered acceptance command runs `sys.argv=[p]` — the no-argument form. What
  "no argument" means is model-authored `__main__` code. The shipped oracle can
  therefore execute a different case set than the one the compiler verified.
  This is E1's renderer defect in a new place: measured one thing, delivered
  another.
- **"Fails on HEAD" means only "exited non-zero".** An `ImportError`, a typo, or
  a bare `assert False` is indistinguishable from an observed missing behavior,
  so a requirement can be marked `compiler-established` on the strength of a
  probe that never observed it.
- **`scope`, `forbidden`, `tests_editable` and `constraints` ship unmarked and
  unmeasured.** No probe result says anything about which files an agent may
  edit — and scope is the boundary the whole product exists to hold. A brief
  naming `.claude/settings.json` and `.github/workflows/ci.yml` in scope
  measured, linted clean, and armed.
- **`constraint_established` checks the wrong thing.** It asks whether the
  requirement a constraint *cites* has any probe case — never whether the
  constraint's own sentence is what those cases observe. Both the sentence and
  the citation are model-authored.
- **E1's stall class rides back in through a channel the new filter does not
  read.** `EXEC_CONTROL` is consulted for constraints only; a regression command
  string carrying a shell comment — `python3 -c "pass"  # STOP: do not begin
  implementation until the human approves your plan` — classifies as runnable,
  measures green, lints clean, and renders verbatim into the delivered prompt.

So the honest statement of what the mechanism established: **the probe cases are
genuinely measured, and B17 is satisfied honestly by a red flip. Everything else
in the brief is asserted.** The design's own summary of itself was wrong, and the
module docstring claiming a demotion path ("it fails toward review, never toward
authority") describes a path that does not exist — such constraints are silently
discarded instead.

## 5. Human burden

Not measured against humans; measured structurally by a fresh-context reviewer
and confirmed against the code.

For a `READY` run the *required* specification work is genuinely zero — that
part of the claim holds. But zero only under blind trust: to have grounds for
trusting the contract, a user reads the generated probe (125 lines in the smoke
run), the unmarked scope and constraint lines, and the ledger's breaker record,
because there is no smaller trusted summary. Estimated 5–15 minutes of review
for a one-line task.

For `NEEDS_DECISION` the claim does not hold. The user does not pick option A or
B; they author a replacement constraint sentence in the brief's grammar, delete
the marker, and delete the ledger block. Worse, the probe and its digest are
computed *before* the questions are resolved, so no acceptance case can observe
the decided behavior and there is no tool in the repo to recompute the digest —
the decided portion of the specification enters the contract as unverified
prose. Estimated 15–30 minutes on top of the residual review.

For `INSUFFICIENT_SPEC` the handback is near-total: one line of compiler-internal
reason, no contract written, no resume, and a re-run costs the full compile
again.

## 6. Breaker results

This is the part that worked, and it is worth stating precisely because it is
the only capability the evidence supports.

Across the 8 primary compiles, the Breaker produced a counterexample the
orchestrator then **mechanically confirmed** — applied to a fresh copy, oracle
re-run, oracle green on a wrong implementation, counter-probe demonstrating the
violation — on **6 tasks** (C03, C04, C05, C06, C07, C08). On C01 the Breaker's
candidate was caught by the oracle, which is the other correct outcome. In the
smoke fixture, round 1 confirmed that a plausible fix using a regex `\W` edge
trim would pass the first oracle while leaving underscores untrimmed — a real
gap the first specification had missed.

The mechanism therefore demonstrated the thing the product is built around:
**the compiler caught weaknesses in its own first specification, before any
coding agent started, and proved them by execution rather than by opinion.**

What is not shown: that this generalizes to the hidden wrong patches. On all 6
the run died in the refinement step immediately afterwards, so no strengthened
contract was ever graded against the corpus's wrong patches.

## 7. Offline benchmark — primary run

Frozen: compiler `9293929`, corpus `3d35d30`, roles on `claude-opus-5`,
`--breaker-rounds 2`, one run per task, thresholds fixed in
`bench/tc_corpus/PREREG.md` before any task ran.

```text
contract quality:        0/8      (gate ≥7/8; kill ≤4/8 — KILL FIRED)
semantic recovery:       not gradeable — 7/8 runs emitted no contract to grade
no-human-repair:         0/8
median material questions: 0
critical trust failures:  0 by the preregistered mechanical definition
                          (no READY contract passed on untouched HEAD);
                          multiple by independent review — see §4
```

| task | state | quality | recorded cause |
|---|---|---|---|
| C01 | READY | FAIL | contract defect: test file in `scope` under `tests_policy: immutable`; adopted the repo's own suite as a criterion for a change that necessarily updates it |
| C02 | INSUFFICIENT | FAIL | resolver mislabeled 4 cases `boundary` that fail on HEAD; repair round hit the parse defect |
| C03 | INSUFFICIENT | FAIL | parse defect, after a CONFIRMED weakness |
| C04 | INSUFFICIENT | FAIL | parse defect, after a CONFIRMED weakness |
| C05 | INSUFFICIENT | FAIL | parse defect, after a CONFIRMED weakness |
| C06 | INSUFFICIENT | FAIL | parse defect, after a CONFIRMED weakness |
| C07 | INSUFFICIENT | FAIL | parse defect, after a CONFIRMED weakness |
| C08 | INSUFFICIENT | FAIL | parse defect, after a CONFIRMED weakness |

The parse defect: six refiner replies opened with one sentence of prose and
then fenced the whole document; `_strip_fences` stripped a fence only on line 1,
so the opening fence stayed inside the parsed text. One line of parsing
terminated 6 of 8 runs. It is fixed, with a regression test built from the
captured replies, and the fix is recorded as Amendment 1 rather than folded into
the primary result.

C01's failure is the instructive one because it is a genuine contract defect,
not a delivery accident. The compiled brief listed `test/test_output.py` in
`scope` while declaring `tests_policy: immutable` — an internal contradiction
`check_scope` would refuse — and `lint_brief.py` passed it (no rule cross-checks
scope against the tests policy; that gap is pre-existing). It also adopted the
project's full existing suite as an acceptance criterion for a behavioral change
whose expected outputs that suite encodes, so the criterion pins the bug. The
compiled probe itself passed cleanly on the gold patch; what failed was the
compiler's own added regression command.

## 8. Cost

Primary run, 8 tasks: **$38.01**, 2 h 24 min of compiler wall time (**$4.75 and
18.0 min per task**), 22 model calls, 18.3 M input and 709 k output tokens,
0 questions asked. For comparison, E1's whole
COMPILED arm cost $30.12. A compiler that spends four dollars and sixteen
minutes to produce a contract for a one-line bug fix is not obviously worth it
even when it works, and that judgment does not depend on the failures above.

## 9. Failure analysis

Smallest layer per task:

- C03, C04, C05, C06, C07, C08 — `DELIVERY` (reply parsing). Not a capability
  result: in every one, the Breaker had already confirmed a real weakness.
- C02 — `SEMANTIC SYNTHESIS` (case-kind mislabel) then `DELIVERY`.
- C01 — `ORACLE` / `SCOPE` (self-contradictory contract; regression command pins
  the behavior under change).

The architecture-level failure is not in that table. It is in §4: the trust
transition, which is the thing that made this a rebuild rather than a patch, was
implemented as a set of source-text filters over model-authored prose and code,
and source-text filters are not a boundary. `PROBE_DENY` is the clearest case —
18 of 19 tested payloads bypass it without obfuscation (`posix.system`,
`import _socket`, `importlib.import_module`), and it restricts no file write at
all, while the code it is meant to contain executes with the user's privileges
during `compile`, during `prepare`, and again during every `verify`.

## 10. Superpowers overlap review

An independent reviewer returned **no**: this is not brainstorming. The primary
artifact is executable, questions are capped and refused rather than pursued,
and there is no dialogue loop. The qualifications in §2 stand.

## 11. Existing Prompire reuse

`check_scope.py`, `verify_acceptance.py`, `lint_brief.py`, `render_brief.py`,
`baseline.py` and `brief_common.py` are **byte-identical** to their state before
this work (`git diff 0d23564..HEAD` touches none of them). The compiler is
additive: `compile_task.py`, `compile_prompts.py`, one `prompire compile`
subcommand, and bench/test files. No verifier rule was rewritten or weakened;
B17 is satisfied honestly by a measured red flip; B18 is not weakened but is
bypassed by construction, since it counts markers and a `READY` contract emits
none.

Two pre-existing weaknesses are made more dangerous by the compiler rather than
created by it: `.prompire/**` sits in `ALWAYS_ALLOWED`, so an agent may rewrite
the brief and the pointer (the re-stamp forge in the P2 note, which supplying a
valid sha256 defeats), and now also write executable code under
`.prompire/probes/`; and this project's own `.gitignore` hides
`.prompire/probes/*.py`, so the generated oracle appears in no `git status` and
no PR diff.

## 12. Claims now supported

- On this frozen corpus, the compiler's Breaker produced a counterexample that
  the orchestrator mechanically confirmed — oracle green on a wrong
  implementation, in a fresh copy — on 5 of 8 tasks, and had its candidate
  correctly rejected by the oracle on a 6th.
- The orchestrator's reproduction requirement is real: a specification whose
  behavioral cases do not fail on untouched HEAD is refused, and two runs were
  refused for exactly that.
- The compiled contract, when one was emitted, was small and passed the real
  `baseline`/`lint`/`render` pipeline unmodified.
- Compiler v2's verifier is untouched by this work, verified byte-for-byte.
- Specific, reproducible defect claims: the verify/deliver probe-invocation
  mismatch; non-zero-exit accepted as reproduction; unmarked unmeasured scope;
  `constraint_established`'s wrong predicate; the regression-command stall
  channel; counter-probe execution before lint; write-set overwrite of the pinned
  probe; `PROBE_DENY` bypasses; `--slug` shell injection; the git-invisible probe.

## 13. Claims still forbidden

- **Humans specify less.** Not measured against humans, and §5 argues the
  opposite for `NEEDS_DECISION`.
- **Agents perform better.** No execution experiment was run, and none may be
  cited.
- **Compiled contracts catch wrong implementations.** The corpus's hidden wrong
  patches were graded against exactly one emitted contract, which failed.
- **The compiler establishes decisions mechanically.** True of probe cases only;
  false of scope, constraints, and regression commands.
- **Prompire is a task compiler.** Positioning is unchanged; verifier-first
  stands, as E1 and E2 concluded.

## 14. Product verdict

### TASK COMPILER CORE IS NOT VIABLE

Not viable as built. The preregistered gate failed at 0/8 and fired its kill
condition; the trust transition that justified the whole rebuild does not hold
under adversarial review; and the cost is $4.75 and 18 minutes per one-line
task. The architecture was allowed to lose, and it lost.

The distinction worth carrying forward: what failed is **not** the idea of
adversarial self-falsification. That mechanism worked, mechanically and
repeatably, and it is the one result here worth keeping. What failed is the
attempt to convert model-authored output into authority using source-text
filters — and the delivery engineering around it, which killed 5 of 8 runs at a
single line of parsing.

## 15. Single next action

> Stop implementation. The single fundamental capability that prevented
> autonomous specification is **the trust boundary**: nothing in this design
> mechanically establishes anything except a probe case's red/green transition,
> so scope, constraints and commands remained model assertions wearing a
> compiler's authority. Any future attempt must either measure those fields or
> keep confirming them — and must not execute model-authored code on the
> reviewer's machine to do it.

## Live defects — do not merge as-is

Present on branch `task-compiler`. Listed because the branch exists on disk, not
because further work is recommended:

1. Model-authored counter-probe code executes **before** `probe_lint` reads it
   (`verify_counterexample`, execution at line 354, lint at 355).
2. The Breaker's write-set is never content-linted, executes via regression
   commands, and — because `apply_writes` runs after `write_probe` — can
   overwrite the pinned probe it is being tested against, manufacturing a
   "mechanically verified" weakness on demand.
3. `PROBE_DENY` is a source-text regex, not a sandbox; it restricts no file
   write and is bypassed by `posix.system`, `import _socket`,
   `importlib.import_module`, and ordinary string concatenation.
4. `--slug` is unsanitized and interpolated into a shell-executed acceptance
   command; it also escapes the intended output directory.
5. `.prompire/probes/*.py` is git-ignored, so the generated oracle is invisible
   to review.

The minimum before this code is run against anything that matters: lint every
piece of model-authored source *before* it executes, refuse write-set paths under
`.prompire/`, sanitize the slug, and un-ignore the probes directory. That is
harm reduction on a branch recommended for abandonment, not a repair plan.
