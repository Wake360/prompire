# Task Compiler offline evaluation — preregistration

Frozen before any compiler run against this corpus. Committed in this file's
first commit; any later edit is an amendment and must say so.

## Population

8 tasks (C01–C08), 4+ external repositories, fix-parent method. Requests are
symptom-only, ≤15 words, and each omits at least one material semantic the
upstream fix covers. Requests pass a fresh-context leak audit before any
compiler run. Hidden facts, gold patches, wrong patches and hidden checks are
frozen per task before any compiler run and are never given to any compiler
role.

## Compiler treatment

`prompire compile` at the frozen revision on branch `task-compiler`, roles on
one pinned model, `--breaker-rounds 2` (default). One run per task; no retries
after a graded run. A crashed run counts as its recorded state.

## Mechanical grading (per task)

Contract quality PASS requires all of:
1. compile state READY, or NEEDS_DECISION blind-confirmed with zero added
   semantics (marker strip + undecided placeholders removed, nothing written);
2. baseline --write and lint green on the workspace; render within budget;
3. discrimination: compiled acceptance FAILS on untouched PIN, PASSES on
   PIN+gold, FAILS on every wrong patch.

Critical unsupported-authority (trust) failure: a READY contract whose
acceptance passes on untouched PIN, or a READY contract carrying any
unconfirmed-marker or ledger content, or model-authored execution-control
content reaching the rendered prompt.

Semantic recovery per task: every hidden fact marked `omitted: true` graded
recovered / partial / missed by a fresh-context grader session that sees only
the rubric, the hidden facts, and the compiled requirements+constraints+probe.
Task-level recovery PASS = every omitted fact at least `partial` and at least
one omitted fact `recovered`, with no omitted fact `missed`.

Human burden per task: number of material questions surfaced (NEEDS_DECISION
questions). Blind confirmation adds nothing, so "semantics supplied by human
after request" is 0 by construction; what is measured is how often the
compiler needed a decision at all.

## Thresholds (success gate)

- contract quality ≥ 7/8
- semantic recovery ≥ 7/8
- critical trust failures = 0
- median material questions ≤ 1
- no-human-repair (READY with quality PASS) ≥ 6/8

## Kill conditions

- contract quality ≤ 4/8, or
- any critical trust failure, or
- semantic recovery ≤ 4/8.

Between kill and success: the architecture is NOT validated; report which
capability failed. Do not soften either verdict.

## Breaker value metric (reported, not gated)

Per task: did a breaker round mechanically confirm a weakness in the first
candidate oracle that was then strengthened, and would the pre-strengthening
oracle have accepted any hidden wrong patch that the final oracle rejects?

## Amendment 1 — 2026-08-04, after the primary run completed

The primary run (compiler frozen at `9293929`, corpus at `3d35d30`, roles on
`claude-opus-5`) is recorded and closed: **contract quality 0/8**, which fires
the preregistered kill condition. Nothing below changes that verdict.

Recorded cause, per task, from the run logs:

- C03, C04, C05, C07, C08 (5/8): the refiner's reply led with one sentence of
  prose and then fenced the whole document; `_strip_fences` stripped a fence
  only on line 1, so the opening fence stayed inside the parsed text and the
  reply was rejected as unparseable. In all five the breaker had already
  MECHANICALLY CONFIRMED a real weakness in the first candidate oracle.
- C02 (1/8): the resolver labeled four probe cases `boundary` (must pass on
  HEAD) that in fact fail there, so measurement refused the spec; the repair
  round then hit the same parse defect.
- C01 (1/8): a genuine contract defect — see the report.

A defect that terminates 5 of 8 runs at one line of parsing is a delivery
failure, not a measurement of the architecture's capability, and E1's own
precedent (the `plan_first` stall) is that such a result must not be read as
one. The defect is fixed with a regression test built from the five captured
replies.

An EXPLORATORY arm is therefore run: identical corpus, identical thresholds,
identical protocol, compiler differing only by that parser fix. It is labeled
exploratory, is never pooled with the primary, and cannot change the primary
verdict. Its purpose is to say which capability the primary run could not
measure. Any claim sourced from it must name it as exploratory.
