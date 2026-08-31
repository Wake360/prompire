---
title: Five preregistered experiments that killed their own hypotheses
tags: [prompire, methodology, evaluation, preregistration, portfolio]
date: 2026-08-05
source: E1–E5 experiment repos and the Prompire benchmark corpus
related: [product-thesis.md, e5-validated-agent-learning-verdict.md, execution-compiler-verdict.md, task-compiler.md]
---

# Five preregistered experiments that killed their own hypotheses

Between July and August 2026 I built a coding-agent governance tool and then ran five preregistered experiments to find out whether its central ideas worked. All five said no. Every success and kill criterion was frozen in a committed preregistration before any graded run, and every one was honored after the results landed — including the two cases where honoring it terminated a working prototype.

This document is the methodology record. The claim it supports is narrow and checkable: I can design evaluations of autonomous agent behavior that are capable of producing a negative result, and I do not move the gates afterwards.

## The instrument

The measurement engine underneath all five: pin a base commit and a file-scope allowlist outside the acting agent's reach; measure a baseline of executable commands on untouched HEAD; after the agent stops, compute a verdict from the real git diff plus a re-run of those commands. The verdict requires zero cooperation from the agent and cannot be forged by it — editing the pinned contract produces *no verdict* rather than a favourable one. Roughly 9,500 lines of adversarial test suites cover the checker itself. In reinforcement-learning terms this is a grader held outside the policy's reach; that is what it was built to be, under a different name.

Stated limits, because they matter for what the instrument can be trusted to say: gitignored paths are outside its view, the pre-write hook does not watch shell tools, and it makes no semantic judgment about whether work is *good* — only whether the diff stayed inside declared scope and whether declared commands now pass.

## E1 — Does an LLM-generated task contract beat a raw request?

Preregistered gate: contract quality ≥7/8. Kill: ≤4/8. Result: **3/8. Rejected.** The follow-up on a rebuilt implementation (E2, a different model family) scored 0/8 on contract quality and 3/8 on strict semantic recovery against a 6/8 gate; its pipeline failed closed and produced zero executions, so its 0/8 is an authority-machinery failure rather than an execution result — recorded as such rather than as a stronger negative than it was.

## E3 — Is there cost headroom in execution routing?

24 tasks × 8 configurations, 323 runs, $204. This one *passed* its frozen gates: a cost oracle solved 20/24 at 55% of best-fixed cost, −45%. The preregistration also required a holdout check, which showed a static router losing 5 tasks — so the passing result was recorded as an oracle ceiling, not a shippable mechanism, and the only capturable form was named explicitly as depending on an untested assumption (a perfect failure detector).

## E4 — Does the capturable form survive on a fresh corpus?

40 tasks, 23 repositories, 320 executor cells, $216, zero infrastructure errors. Frozen product requirement: adaptive success ≥ always-strong AND cost ≤80% of always-strong. **Rejected twice over.** A *perfect* cheap-to-strong detector saves 12.5% against the 20% gate — so no amount of sensor work could reach it. The real detector hit 79% recall against a required 90%, and its 49 false escalations cost more than its 30 correct ones saved. The single variable that flipped E3's result was the realized cost ratio (0.42 → 0.61), not the sensors: E3's headroom was substantially an artifact of a corpus on which the strong model happened to be expensive. Recording that is what made the E4 rejection trustworthy.

## E5 — Do human corrections transfer as reusable behavioral rules?

The most careful of the five. 13 verbatim maintainer-authored rules plus one control, drawn from six real repositories (browser-use, inbox-zero, tldraw, mastra, opencode, home-assistant/core) across 11 behavior categories, each with commit-level incident provenance. Two held-out recurrence tasks per rule, authored to make the targeted mistake tempting, leak-audited 28/28. Arms differ only in the presence of the rule line in the repository's own instruction file. 2 arms × 2 repeats = 112 cells, model pinned, CLI version pinned, frozen mechanical detectors, randomized order, no retries.

Terminated at 93/112 cells, and the verdict is still decidable for an arithmetic reason recorded at the time: the selectivity gate required ≥6 individually positive rules, zero were positive, and only 4 rules had any unrun cells — so confirmation was already unreachable before the stop. **Rejected.**

What it found: 9–10 of 13 real maintainer rules sat at a zero-violation baseline — the model already avoided the mistake without being told. Only three rules were measurable at all. The pooled direction (6/43 vs 9/44) is noise at Fisher p=0.57, and I record it as noise rather than as the more quotable "the rule arm was worse." Where temptation was real, the agent mirrored contradicting exemplars in the repository's own code and never mentioned the rule.

The control worked as designed: a rule the maintainers themselves later walked back came out neutral and would not have promoted.

## The benchmark corpus

Eight frozen fix-parent tasks across five repositories, leak-audited, with hidden gold patches and plausible-but-wrong patches held outside every visible workspace, and mechanical triple grading. Preregistration committed before any task ran. The compiler evaluated against it scored 0/8 on contract quality and fired its own kill condition; the failure analysis separates the delivery defect (one line of reply parsing terminated 6 of 8 runs) from the architecture verdict (model-authored fields shipped unmeasured), because conflating them would have overstated the negative. Artifacts: `tc-evidence/`, `bench/tc_corpus/PREREG.md`.

## What the instrument did establish

On the one question it was built for, the measurement is clean and reproducible: across 20 undirected runs the agent edited a forbidden test file 9 times, caught from outside every time; across 160+ runs governed by a pinned contract, zero left declared scope. Stated with its own caveat: those tasks were authored to tempt the failure, and an independent 2026 replication on modern agents found zero scope violations in both arms — so the number describes the corpus as much as the mechanism, and I do not cite it as a general drift rate.

## Practices used throughout

Preregistration committed before any graded run, with kill criteria as explicit as success criteria. Fresh-context adversarial review of every conclusion, by reviewers whose only assignment was to break it — two of which materially changed the result. Leak audits between task construction and grading. Mechanical detectors unit-tested against synthetic violating diffs before use. Adjudications recorded at first observation, before completion, with sensitivity reported in both directions. Negative and inconclusive results written up at the same length as positive ones. Where a verdict document overstated its own data, the correction is in the record next to it.

## Reading order

`product-thesis.md` — the terminal synthesis and what all of it was for. `e5-validated-agent-learning-verdict.md` — the most complete single experiment. `execution-compiler-verdict.md` — the oracle-ceiling result. `task-compiler.md` — the architecture that failed and the failure analysis that separates delivery from mechanism. `bench/tc_corpus/PREREG.md` and `tc-evidence/` — the frozen corpus and its raw rows.
