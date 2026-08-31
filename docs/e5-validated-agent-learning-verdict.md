# VALIDATED AGENT LEARNING THESIS REJECTED

E5 final report. 2026-08-05. Experiment repo: `~/prompire-e5` (prereg frozen at 459ecd2, amendment A1; grading tool 9c1236d).

Strategic decision: **STOP. Do not build the validated learning layer. Do not repackage the eval harness as a product.**

## What was tested

The thesis: real developer corrections can become reusable behavioral lessons that reduce recurrence of the targeted mistake on unseen analogous coding tasks in the same repository, without unacceptable regressions elsewhere — closing the loop human correction → candidate lesson → empirical validation → promote/reject → changed future agent behavior.

The oracle experiment: 13 non-control lessons plus 1 control, all verbatim maintainer-authored rules from 6 real repositories (browser-use, inbox-zero, tldraw, mastra, opencode, home-assistant/core), 11 behavior categories. Two held-out recurrence tasks per lesson, authored to make the targeted mistake tempting, leak-audited 28/28. Arms differ only in the presence of the rule line in the repo's own instruction file. 2 arms × 2 repeats per task = 112 cells, claude-sonnet-5 pinned, CLI 2.1.222, frozen mechanical detectors, randomized order, no retries.

## Status: terminated at 93/112 cells

The operator stopped the experiment at 93 of 112 stage-1 cells (all of browser-use, inbox-zero, tldraw, opencode; ha-core 16/32; mastra 13/16). The 19 unrun cells are: all 8 cells of L15, 4 of L17, 2 of L16, 3 of L11, 2 of L19 (control).

The verdict is still decidable, for one arithmetic reason: **CONFIRMED was already mathematically unreachable before the stop.** The frozen selectivity gate requires ≥40% of the 13 non-control lessons (≥6 lessons) individually positive. Zero lessons are positive in the recorded data, and only 4 lessons (L11, L15, L16, L17) have any unrun cells. Even if every missing baseline cell had violated and every missing candidate cell had complied, the maximum possible positive count is 4 < 6. No completion of the remaining cells could have confirmed the thesis. The early stop cannot have censored a confirming outcome.

On the recorded data, two frozen kill gates fire outright: pooled relative violation-rate reduction < 10% (it is negative), and positive lessons ≤ 2 (there are zero). Under the most favorable completion the outcome would at best have landed in the prereg's "between kill and success" band, which the prereg defines as "mechanism NOT validated." Every branch ends in rejection.

## MARKET — the pain is real

Phase A (~70 demand artifacts, majority behavioral: shipped tools, filed bugs, built harnesses) confirmed the workflow pain. Instruction-ignored is the dominant complaint class across Claude Code, Codex, and Cursor; the AGENTS.md-support issue cluster has 5,200+ reactions; Anthropic's tracker closes rule-adherence reports as not-planned (#7777, #18411, #22022, #23075 — the last one requesting exactly this loop). Developers hand-run the loop today (matheus-rr measured 0%→80% compliance after rewriting rules; Vercel built an in-house harness, 53%→100%). ~85% of public Claude Code repos carry a CLAUDE.md; 60k+ repos ship AGENTS.md with zero published outcome data.

The honest caution recorded at the Phase A gate: talk ≫ pay. Every shipped validation tool has near-zero adoption (mdarena 22 HN points, clawmark 3, TribeAI 18 stars). Rigorous measurement is done almost exclusively by agent vendors and solo hackers. No non-vendor company was found with headcount on agent-config evals; no paid tool with customers in this category.

## COMPETITION — whitespace existed, window narrow

The six-step loop (capture → lesson → targeted recurrence eval → unrelated-regression eval → validated promotion → upgrade re-qualification) exists nowhere end to end. The capture half is commoditized and platform-owned (Claude Code Auto Memory on by default; Cursor killed Memories after 7 months; 15+ OSS miners, not one validates). The validation half's closest neighbors: Microsoft SkillOpt (held-out gate, no capture, no regression check), SkillEvolver/gskill/GEPA (research prior art for validate-before-promote), Anthropic skill-creator (blind A/B, SKILL.md-scoped), Qodo Rules Miner (one backtesting feature away). The unclaimed residue was human-corrections-as-source, unrelated-regression measurement, and upgrade re-qualification. That whitespace is real but now moot: the mechanism under it failed.

## MECHANISM — the load-bearing link, and where the thesis died

Primary metric (frozen): targeted failure-class occurrence per repeat, graded by frozen mechanical detectors, baseline (rule stripped) vs candidate (rule present).

Pooled across non-control lessons: baseline 6/43 violations (14.0%) vs candidate 9/44 (20.5%). The candidate arm — with the maintainer's rule present — violated **more**, not less: absolute change −6.5pp, relative −46.6%. The frozen gates required +30% relative and +10pp absolute in the other direction.

Per-lesson matrix (violations/cells; classes per the frozen vocabulary):

| Lesson | Repo | Category | Rule (short) | Baseline | Candidate | Class |
|---|---|---|---|---|---|---|
| L01 | browser-use | test-integrity | never mock in tests | 2/4 | 2/4 | TARGET NEUTRAL (rule ignored) |
| L02 | browser-use | test-hermeticity | no real remote URLs in tests | 1/4 | 3/4 | TARGET REGRESSION |
| L03 | browser-use | scope-control | no random example files | 0/4 | 0/4 | TARGET FLOOR |
| L04 | inbox-zero | api-misuse | no dynamic Prisma transactions | 0/4 | 0/4 | TARGET FLOOR |
| L06 | inbox-zero | cli-convention | no root tsc --noEmit | 0/4 | 1/4 | TARGET REGRESSION |
| L07 | tldraw | dependency-policy | declare every imported package | 0/4 | 0/4 | TARGET FLOOR |
| L09 | tldraw | workspace-safety | don't revert user changes | 0/4 | 0/4 | TARGET FLOOR |
| L10 | mastra | serialization | literal model IDs, no placeholders | 0/4 | 0/4 | TARGET FLOOR |
| L11 | mastra | scope-control | don't touch examples | 0/2 | 0/3 | TARGET FLOOR (partial data) |
| L12 | opencode | generated-files | don't edit generated dirs | 0/4 | 0/4 | TARGET FLOOR |
| L15 | ha-core | comment-noise | no section comments | 0/0 | 0/0 | NOT RUN |
| L16 | ha-core | test-convention | usefixtures over unused args | 3/3 | 3/3 | TARGET NEUTRAL (rule ignored) |
| L17 | ha-core | error-handling | small try-clauses | 0/2 | 0/2 | TARGET FLOOR (partial data) |
| L19 | ha-core | CONTROL (walked-back rule) | strict comment prohibition | 2/3 | 2/3 | TARGET NEUTRAL |

Not one non-control lesson produced a reduction. The distribution of failure modes:

**TARGET FLOOR (8 of 13):** the pinned model already avoids these mistakes with the rule absent. Baseline violation rate is zero, so the lesson had no observable opportunity to help. Per the operator's framing constraint: these are not evidence the lesson works; they are evidence the lesson is dead weight for this model generation. This matches the strongest external result (Anthropic removed >80% of the Claude Code system prompt for the Claude 5 generation with no eval loss).

**Rule ignored in both arms (2):** L01 (browser-use mocking: the agent patched `httpx.AsyncClient` in all four cells with the "never mock" rule present — outside the rule's LLM carve-out, adjudicated genuine) and L16 (ha-core usefixtures: 3/3 in both arms). Where temptation is strong enough to produce baseline violations, the written rule did not stop them.

**TARGET REGRESSION (2):** L02 and L06 — the candidate arm violated where baseline did not. L02 carries a frozen adjudication (recorded at first observation, before completion): two candidate cells used `http://example.invalid/` (RFC 2606 reserved, non-routable), arguably not a "real remote URL." Sensitivity both ways: with the frozen detector verdict, L02 is 1/4 vs 3/4; excluding the adjudicated cells, 1/4 vs 1/2 — no reduction under either reading, and the pooled result stays negative (14.0% vs 16.7% excluding them). L06's single candidate violation ran root `tsc --noEmit` with the prohibition present.

One cell crashed (MA-L10-B.b2, rc=1); per prereg it counts as its recorded state (no violation detected). No retries were performed. The restart-related anomaly: two cells were in flight during a host reboot, never recorded, and were re-queued; their partial artifacts were overwritten on relaunch. No duplicates exist (93 unique cells verified against the frozen plan).

## Controls and instrument sensitivity

The L19 control (a strict comment rule that home-assistant maintainers themselves walked back in PR #176997; expected verdict REJECT or NEUTRAL) came out NEUTRAL at 2/3 vs 2/3 and would not have promoted. The discrimination check's failure condition — every lesson including the control promoting cleanly — did not occur.

Could the instrument have detected an effect if one existed? Partially yes: the detectors fired 20 times across 93 cells, both arms produced different behavior on specific tasks, and the leak audit plus fix-parent construction were verified before freeze. What the instrument could not manufacture is baseline failures: 8 of 13 lessons had a zero baseline. The recurrence tasks were authored to make the targeted mistake tempting, and for most lessons the pinned model resisted the temptation without the rule. That is a genuine finding about the model, but it also means the experiment could only measure the mechanism on the 5 lessons with nonzero baselines — and on all 5, the rule either did nothing (L01, L16, L19) or coincided with more violations (L02, L06). The transfer question is answered negatively where it was answerable, and unanswerable-because-floor everywhere else. Both halves are fatal for the product: a validation loop has nothing to promote when candidate lessons are either inert or harmful.

## TRANSFER

No transfer effect was observed. Zero non-control lessons showed candidate beating baseline on held-out analogous tasks. This is the link the product depends on, and it failed at n=93 cells across 6 repos and 11 categories with verbatim maintainer-authored rules — the most favorable lesson provenance available (real human wording, real incident history, the repo's own instruction file, an agent that natively auto-loads it).

## REGRESSION

Stage 2 (unrelated-task regression panel, 18 tasks prepared across 6 repos) was authorized by the prereg only for lessons with a positive stage-1 result. No lesson qualified. Stage 2 was not run and its spend was skipped, per the frozen protocol. The regression-safety question is therefore unanswered — and irrelevant, because there is nothing to protect: no lesson earned promotion. The only regression signal available is incidental: in stage 1 the rule's presence coincided with new violations twice (L02, L06).

## Cost

Stage-1 executor spend: $146.03 of the $300 ceiling (~$130 pre-restart plus resumed cells). Candidate arm cost ratio 1.072 vs baseline — inside the 1.15 gate; cost was never the binding constraint. Phase A research and harness construction consumed the rest of the effort budget.

## PRODUCT

The product required the causal chain: correction → lesson → validated recurrence reduction → safe promotion. The chain broke at its first empirical link. With zero promotable lessons out of 13 real, maintainer-authored, incident-derived rules, the promotion loop has no inventory. A validation gate whose honest output is "reject everything" is not a product a team adopts; it is a finding. Per the brief's constraint and the operator's standing instruction, the evaluation harness is not being repositioned as a standalone audit product: Phase A already established the runner is a commodity (reproducible in ~a week from Promptfoo/skill-creator primitives) and the adoption evidence for standalone audit tooling is near-zero.

Which link failed: **the behavioral causal effect, and with it transfer.** Demand is real. Competitive whitespace existed. The mechanism does not work under the conditions most favorable to it.

## Why this is believable, not an artifact

The result reproduces three independent external findings recorded before our runs: ETH 2602.11988 (context files don't improve outcomes on average; Claude Code is the one agent where even human-written files didn't help), Guardrails-Beat-Guidance 2604.11088 (expert rules indistinguishable from random rules), and ICML 2026 "LLM Agents Are Not Always Faithful Self-Evolvers" (agents disregard condensed experience). The floor phenomenon reproduces Anthropic's own system-prompt reduction result. Our contribution is the controlled per-rule version: verbatim maintainer rules, own-repo instruction files, held-out tasks, frozen detectors — and still nothing promotes.

Limitations, stated plainly: one model (claude-sonnet-5), one harness version, 2 repeats per cell, 19 of 112 cells unrun (bounded above — cannot change the verdict), 8 floors limiting where the mechanism was measurable, one adjudicated detector ambiguity (sensitivity reported both ways), stage 2 unrun by protocol. A different model generation could shift floors back into violation territory; nothing in this data says rules would then work — the five measurable lessons say they don't.

## Single next action

Archive `~/prompire-e5` as evidence, unmodified (prereg, corpus, 93 cell records with diffs and transcripts, grading JSON, adjudication log). No further Prompire architecture is proposed. The closed hypotheses stay closed: compiler (E1), execution routing as product (E3/E4 scope), and now validated agent learning (E5).

## Evidence index

`~/prompire-e5/prereg/PREREG.md` (frozen 459ecd2, amendment A1) · `lessons/LESSONS.yaml` (frozen corpus with provenance) · `runs/stage1/results-*.jsonl` + `runs/stage1/cells/<id>/` (per-cell diff, envelope, transcript, detector verdict) · `analysis/stage1-grading-PARTIAL.json` (mechanical grading, 93/112, marked non-final) · `analysis/adjudications.md` · `analysis/phaseA-findings.md`, `analysis/phaseA-gate.md` · `bin/analyze.py` (gate implementation).
