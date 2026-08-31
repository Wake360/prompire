# EXECUTION COMPILER OPPORTUNITY CONFIRMED

— with a measured, load-bearing qualification: the headroom is real and passes every
preregistered gate, but the holdout analysis shows a static single-shot router captures
little of it. The capturable form of the headroom is cheap-first execution with
sensor-driven escalation, not pure pre-execution prediction.

Evidence repo: `~/prompire-e3` (git). Preregistration frozen at `8384284`, corpus at
`d90b9c1`, stage 1 at commit "stage 1 frozen", stage 2 at "stage 2 frozen", before any
outcome-dependent decision. One amendment (pack-generator turn cap), recorded before
any matrix cell ran. 323 executor runs, 0 infrastructure errors, 0 excluded cells.
Total spend: $203.81 executor + $4.01 packs, inside the frozen $200–230 estimate.

## 1. Executive result

| policy | solved (2/2) | mean cost/task | mean latency |
|---|---|---|---|
| Best fixed config (`S_RAW_H`) | 20/24 | $1.099 | 231 s |
| Baseline A `S_RAW_M` | 18/24 | $0.734 | 149 s |
| Baseline B `C_RAW_M` (cheap) | 14/24 | $0.431 | 212 s |
| **Cost-oracle (per-task)** | **20/24** | **$0.606** | 204 s |
| Latency-oracle | 20/24 | $0.771 | 165 s |

- **Headroom gate 1a: PASSED.** Cost-oracle matches best-fixed success (20/24) at 55%
  of its cost — a 45% cost reduction at matched success (gate required ≥30%).
- Latency gate 1b: narrowly missed (71.2% vs required ≤70%). Reported, not gated.
- **Diversity gate: PASSED.** Modal oracle config (`C_RAW_H`) covers 50% of solved
  tasks (gate ≤70%); 7 distinct configs chosen; entropy 2.16 bits.
- No ceiling pathology (cheap fixed solves 14/24 reliably), no ERR contamination.

Under the frozen rules the verdict is CONFIRMED.

**The qualification that must travel with the headline.** The oracle knows 2/2
reliability in advance; a router does not. A holdout policy — pick the cheapest config
that succeeded in its stage-1 run, score it only on its held-out stage-2 run — solves
16/24 at $0.588, versus 21/24 at $1.028 for always-strong on the same holdout sample.
Cheap configs are flaky: `C_RAW_M` passed r1 and failed r2 on five tasks. So
one-observation selection loses 5 tasks — unacceptable. The oracle's savings are real
but roughly half selection-on-reliability, which must be predicted or *observed*.
The observed route works: an exploratory escalation policy (run `C_RAW_M`; on failure
rerun with `S_RAW_H`), assuming a perfect runtime failure detector, scores **22/24 at
$0.824 (−20% vs always-strong, +1 task)**. Detection is exactly what Prompire's
deterministic verifier remnants can supply as runtime sensors (§34 of the brief).

## 2. Competitive boundary

Full survey with citations: `analysis/competitive-boundary.md`. Summary: model routers
(OpenRouter, Martian, Not Diamond, academic ACRouter) decide model only; context
engines (Cody, Greptile, Augment) decide retrieval only; runtimes (Devin, Cursor,
Copilot coding agent) fix the model or expose a manual picker; the closest academic
joint work (RTR) covers model + reasoning strategy, general-purpose, not coding.
CodeRouter.io claims the wording but decomposes into separate heuristics; 1-star,
early. Nobody jointly optimizes model + effort + context + strategy + escalation per
coding task. The narrow "per-task model routing" slice is occupied; the joint
execution-configuration slice — especially with runtime escalation — is open. The
difference is load-bearing here precisely because the data says single-axis static
routing (the occupied slice) underperforms, and sensor-driven joint policies (the open
slice) are where the measured value is.

## 3. Configuration matrix

model {C=claude-haiku-4-5, S=claude-sonnet-5} × context {RAW, CTX=compact
repo-intelligence pack, Graphify-proxy, haiku-generated, ≤400 words} × effort
{M=medium, H=high}, all inside claude CLI 2.1.221 headless, identical permission
allowlist, max-turns 100, pinned prompt templates. CTX runs are charged full pack cost
and latency. Eight configs: C/S_RAW/CTX_M/H.

## 4. Corpus

24 tasks, 20 repositories, 10 surfaces (library 7, data 4, cli 2, api-service 2,
feature 2, performance 2, refactor 2, automation-build 1, docs-config 1, migration 1),
specificity LOW 9 / MED 9 / HIGH 6. Ten reused validated fix-parent bugfixes (8
tc_corpus, 2 from E2); fourteen fresh authored tasks mined for this experiment. Every
task passed mechanical validation (hidden check fails at pin, passes at gold) before
the corpus froze. Grading is hidden behavioral checks only — no LLM judge, no human
scoring. Frozen list with hashes: `prereg/05-corpus.md`.

## 5. Full task × configuration matrix

`analysis/report-tables.md` holds the complete matrix (success per repeat, per cell)
and per-cell costs are in `runs/stage1.jsonl` + `runs/stage2.jsonl`. Shape: 14 tasks
(all fresh CLI/API/feature/docs/refactor work plus R02) are solved by essentially every
config — there the oracle picks on price. The hard tail is the deep library-bugfix
set: C03, C04, C05, C08 reliably solved by nothing (single lucky runs only), C01
strong-only, F09/F10/F11 strong-or-assisted, R01 strong-only-with-context.

## 6. Oracle choices

C_RAW_H ×10, C_RAW_M ×4, S_RAW_M ×2, S_RAW_H ×1, C_CTX_H ×1, C_CTX_M ×1, S_CTX_M ×1,
unsolved ×4. 15 of 20 solved tasks route to the cheap model; 3 of 20 to a CTX config;
17 of 20 to RAW context.

## 7. Configuration diversity

Yes — different tasks genuinely prefer different configurations, and the split is
interpretable: additive/localized work (CLI flags, API fields, small features, renames,
config edits) is reliably cheap-solvable at ~40–60% of strong cost; deep behavioral
bugfixes in mature libraries need the strong model or fail everything. But diversity
*within* the cheap block (C_RAW_H vs C_RAW_M) is mostly noise-level price differences
between equally-reliable cells, not deep signal. The load-bearing routing dimension is
model tier; the rest is second-order.

## 8. Model-tier analysis

Stage-1 paired (same context/effort): strong wins 11 pairs, loses 6 — the only
dimension with a clear positive direction. Strong-required tasks: C01, F09, F10, F11,
R01 (+ the unsolved tail where strong at least sometimes succeeds). Cheap-sufficient:
the entire additive-work block. Cheap cannot be rescued on the hard tail by context or
effort (C_CTX_*/C_RAW_H all fail C01, C05, C08, F11 reliably).

## 9. Context analysis

Structured context was net negative: stage-1 paired flips 3 helped vs 6 hurt; the
gap-closure metric is undefined because the cheap-vs-strong stage-1 gap it was meant
to close is zero (both 19/24 single-run). Two of three oracle CTX picks (F12
migration, R01) are real context wins — cross-cutting multi-file work — matching the
hypothesis that structure helps connectivity-heavy tasks. Everywhere else the pack
duplicated what the agent finds itself in one or two tool calls, at +$0.10–0.17 and
+40 s. Pack audit (`analysis/pack-audit.md`): 13/24 CLEAN, 4 diagnostic-label, 7
fix-proposal — so CTX results are, if anything, *overstated* in CTX's favor on seven
tasks, and it still lost on net. In this proxy form, Graphify-class input is not a
value driver for Prompire; at best a niche input for migration-class tasks.

## 10. Reasoning analysis

No measurable effect: stage-1 paired flips 6 wins vs 7 losses for HIGH; cost
difference within cheap tier is noise (C_RAW_H total $10.20 vs C_RAW_M $10.84 across
24 tasks); on the strong tier HIGH costs +59% ($28.08 vs $17.70) for +1 task
single-run. Effort is not a routing dimension worth predicting in this range on this
harness.

## 11. Cheap-model gap closure

Not computable as preregistered: the single-run capability gap S_RAW_M − C_RAW_M is 0
(19 vs 19); on reliability (2/2) the gap is 18 vs 14, and neither context nor effort
closes it (cheap+CTX and cheap+HIGH fail the same hard tail). The commercially
relevant closure mechanism found is not configuration but *escalation*: cheap-first +
strong-on-failure closes the reliability gap completely (22/24 ≥ strong's 21/24 on
the holdout sample) at 80% of strong's cost.

## 12. Economic headroom

Cost at matched success: −45% (oracle $0.606 vs best-fixed $1.099 at 20/24 each).
Latency at matched success: −28.8% (latency-oracle, misses the 30% gate). Success at
matched cost: at the cheap-fixed budget ($0.43) nothing beats 14/24; at ~$0.82 the
escalation bound reaches 22/24 — more solved than any fixed config at 75% of
best-fixed cost.

## 13. Oracle vs best fixed configuration

The primary comparison passed: same success, 45% cheaper, diverse choices. The honest
decomposition: ~half the saving is task-type routing (predictable from task features —
additive vs deep-bugfix), ~half is reliability knowledge a static router cannot have
in advance but a sensor-equipped runtime can observe cheaply after a $0.40 first
attempt.

## 14. Router feasibility

The gate passed, so the question is live. Task features carry real signal: surface +
specificity separate the cheap-reliable block from the strong-required tail almost
perfectly in this corpus (fresh additive tasks vs reused deep bugfixes). But n=24 with
that correlation partly baked into corpus construction; a learned router trained here
would overfit provenance. The defensible Phase 2 is not a static classifier but a
two-stage policy: (1) coarse pre-execution triage (cheap-first vs strong-first) from
task/repo features; (2) runtime escalation on cheap failure, using deterministic
sensors (tests, build, diff-emptiness, focused validation). The holdout says (1)
alone loses 5 tasks; the escalation bound says (1)+(2) beats always-strong on both
axes. The binding constraint is detector quality, not routing-model capacity.

## 15. ML recommendation

RULE-BASED ROUTER WORTH TESTING — as the triage stage of an escalation policy, with a
handful of interpretable features (operation type additive-vs-bugfix, blast radius,
repo maturity). NO NEURAL ROUTER: 24 tasks of provenance-correlated data cannot
justify one, and the measured value concentrates in escalation logic + sensors, not
in prediction finesse.

## 16. Existing Prompire asset reuse

Keep as product-relevant: the deterministic verifier remnants repositioned as runtime
failure sensors (this experiment shows they are the gating asset for capturable
headroom); the benchmark/orchestration harness (mkws/run_cell/orchestrate — 323 runs,
0 ERR); the fix-parent corpus method and validation tooling; agent adapters/CLI.
Historical only: prompt compiler, semantic stdlib, contract renderer, verifier-as-UX.

## 17. Product definition

**Prompire runs coding tasks cheap-first and escalates on evidence — an execution
policy layer that picks the starting configuration per task and uses deterministic
runtime sensors to decide when to spend more.** "Compiles software tasks into
optimized coding-agent runs" remains the category umbrella, but the evidence favors
the policy/escalation wording over pure ahead-of-time compilation.

## 18. Strategic decision

BUILD EXECUTION COMPILER MVP — scoped to the validated mechanism: model-tier triage +
cheap-first escalation with sensor-based failure detection. Do not build context
integration (measured net-negative in proxy form) or effort routing (no effect) into
the MVP.

## 19. Single next action

Build the smallest escalation router: rule-based triage (additive → haiku-first,
deep-bugfix → sonnet-first) + one deterministic failure sensor + automatic
re-dispatch, and measure captured headroom against `S_RAW_H` on a fresh held-out task
set. Target from this data: ≥20% cost reduction at ≥ equal success.

## Limitations (disclosed)

Two repeats per decisive cell — oracle eligibility on 2/2 carries winner's-curse
inflation; the holdout section quantifies it. Single harness/vendor (claude CLI;
haiku/sonnet) — cross-harness and cross-vendor headroom untested. Python-only,
small-to-mid OSS repos; corpus difficulty correlates with provenance (fresh authored
tasks easier than reused fix-parent bugfixes), which flatters the surface→routing
signal. Executor sessions inherit the user's global claude config (constant across
cells). Pack generator leaked partial diagnosis on 7/24 tasks (audited) — biases the
experiment *toward* context value, strengthening the net-negative context finding.
Escalation bound assumes a perfect failure detector; real sensors will capture less.
