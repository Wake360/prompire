# UNIVERSAL PROMPT COMPILER THESIS REJECTED

## 60.1 Executive result

```text
RAW total:                         11.0 / 12
PROMPIRE total:                    10.5 / 12
delta:                             -0.5

LOW:                               RAW 5.0, PROMPIRE 4.5, delta -0.5
MEDIUM:                            RAW 4.0, PROMPIRE 4.0, delta 0.0
HIGH:                              RAW 2.0, PROMPIRE 2.0, delta 0.0

software surfaces with positive delta: none

median compiler latency:           80.8575 s
median compiler tokens:            51,156
compiler questions:                0
```

The preregistered primary criterion failed. The ceiling rule activated because RAW scored 11.0. PROMPIRE stayed within the permitted 0.5 success regression, but LOW-specificity success regressed and no eligible secondary metric improved by 20%.

There was no methodological blocker. All 24 compilations and 48 executor cells completed. The blind reviewer completed. Infrastructure failures were zero.

## 60.2 Frozen implementation

```text
starting revision: 367d0b608f4fdd0a8481549a29d5003baf940621
final revision:    27b3aa3e9cad13660bdace6ab20e57657cfe57fd
prereg revision:   b2ec97b19841c539099be773164c6d1b443b8308
prereg SHA-256:    d75647b87a54a6368bf38802d8bbc29426e4d9f80ace698e796832a74f0dd166

compiler model:    gpt-5.6-sol, medium reasoning
executor model:    gpt-5.6-sol, medium reasoning
Codex version:     0.146.0
```

`FINAL_PROMPT_COMPILER_REV=27b3aa3e9cad13660bdace6ab20e57657cfe57fd`

No compiler, retrieval, facet, stdlib, Critic, renderer, fixture, or grader change was made after benchmark outcomes were observed.

Pre-freeze validation:

```text
PYTHONDONTWRITEBYTECODE=1 python3 tests/run_all.py --quiet
15 / 15 test modules passed

focused task-context properties: 13 / 13 passed
focused universal benchmark properties: 2 / 2 passed
cross-domain smoke fixtures: 10 / 10 passed
```

The adversarial reviews found no production dependence on UI/web tasks, confirmed unknown-task fallback, removed clear generic filler, confirmed specificity scaling, and confirmed the read-only compiler boundary. The downstream benchmark later exposed one product-invention failure that the pre-freeze review did not catch.

## 60.3 Final architecture

```text
request
  -> bounded read-only repository context
  -> Resolver
       + semantic facets
       + specificity
       + candidate stdlib policies
       + applicability filtering
  -> one fresh-context subtractive Critic
  -> Resolver revision
  -> compact renderer
  -> Codex
```

There are four compiler model calls: retrieval selection, initial Resolver, Critic, and Resolver revision. Facet classification and policy selection occur inside the existing Resolver calls. No classification stage was added.

The original six-field `TaskIR` remains unchanged. Facets, specificity, stdlib provenance, Critic disposition, model configuration, cost, and downstream outcomes are compiler metadata.

## 60.4 Semantic facets

Observed compositions from first compilations:

| Task | Surface | Compiler specificity | Selected facets |
|---|---|---:|---|
| `add retries` | service | LOW | `add`, `library`, `reliability`, `partial_system` |
| `migrate users to UUIDs` | database | LOW | `migrate`, `backend`, `data`, `compatibility`, `data_integrity`, `existing_system` |
| `speed up startup` | performance | MEDIUM | `optimize`, `cli`, `performance`, `compatibility`, `existing_system` |
| `add deployment health checks` | automation | MEDIUM | `add`, `integrate`, `infrastructure`, `reliability`, `deployment`, `existing_system`, `partial_system` |
| `build a small CLI for converting images` | greenfield CLI | LOW | `create`, `cli`, `greenfield` |
| `make dashboard better on mobile` | frontend | LOW | `modify`, `ui`, `frontend`, `mobile`, `ux`, `compatibility`, `existing_system` |
| `rename Foo to Bar in README.md` | documentation | HIGH | `modify`, `document`, `documentation`, `existing_system` |

The catalog contains 13 operation facets, 18 surface facets, 13 quality facets, and 3 project-state facets. Unknown labels are not required from users. Tests confirm that unfamiliar software tasks fall back to valid general metadata and still compile.

Compiler specificity differed from the preregistered evaluator label for U06, U07, and U10 in both repeats. Across the preregistered distribution, median prompt length still decreased from 161 words at LOW to 134.5 at MEDIUM and 28 at HIGH.

## 60.5 Prompt Compiler Stdlib

The frozen stdlib contains 44 policy fragments. Representative policies:

| Domain | Policy | Guidance |
|---|---|---|
| bug fixing | `bugfix.broader-invariant` | Inspect callers and sibling paths before special-casing the literal reported example. |
| migration | `migration.persisted-data` | Account for existing persisted data and dependent readers when representation changes. |
| API | `api.validation-error-shape` | Reuse existing endpoint validation and error-shape conventions. |
| CLI | `cli.machine-readable-output` | Keep machine-readable output free of human diagnostics and preserve exit-code and stderr conventions. |
| data | `data.schema-semantics` | Preserve null, ordering, encoding, and schema semantics relied on by downstream consumers. |
| infrastructure | `infrastructure.deployment-conventions` | Fit existing deployment, health, and configuration conventions rather than adding a parallel mechanism. |
| performance | `performance.measure-baseline` | Use existing benchmarks or a focused before/after measurement and preserve correctness. |
| reliability | `reliability.bounded-retries` | For retry behavior, distinguish transient from permanent failures, bound total attempts, and preserve the final failure. |
| accessibility | `accessibility.interaction` | Preserve keyboard, focus, labels, and assistive semantics for affected interactive behavior. |
| greenfield | `greenfield.minimum-structure` | Choose the smallest conventional structure that supports the requested behavior without inventing product scope. |

Facet matches only form the candidate set. The Resolver selects policies only when they add applicable information. The Resolver revision can remove them after Critic review.

Across 24 benchmark compilations:

```text
candidate policy occurrences: 104
adopted policy occurrences:     6
rejected policy occurrences:   98
```

The six adoptions were `reliability.bounded-retries` twice, `migration.persisted-data` twice, `compatibility.observable-behavior` once, and `accessibility.interaction` once. Most enrichment was repository-derived rather than copied from the stdlib.

## 60.6 Example compilations

Each example is repeat 1 from the frozen compiler. The text after RAW is the exact user request. The compiled output preserves it as `TASK`.

### Service, LOW

RAW:

```text
add retries
```

Compiled:

```text
TASK
add retries

INFERRED REPOSITORY GUIDANCE (ADVISORY)
Treat these as leads, not requirements or edit boundaries.

LIKELY RELEVANT
- relay/client.py
- tests/test_relay.py

LIKELY CONTEXT
- README.md defines UploadClient retries as at most three total attempts for transient transport failures.
- TransientError and PermanentError already define the failure categories; UploadClient.upload currently sends once.

LIKELY BEHAVIOR TO PRESERVE
- UploadClient's constructor, upload call shape, and successful return value.
- Propagate PermanentError immediately after one attempt.

POTENTIAL PITFALLS
- Apply retries only at the existing UploadClient transport boundary.
- For retry behavior, distinguish transient from permanent failures, bound total attempts, and preserve the final failure.

USEFUL CHECKS
- Transient failures can recover within three total attempts.
- PermanentError is raised after one attempt.
- Three transient failures make exactly three attempts and raise the final TransientError.

Inspect or change additional implementation files if needed.
Implementation details are yours. Keep the change focused.
Make reasonable assumptions from repository evidence; ask only if product semantics remain materially ambiguous.
```

### CLI, MEDIUM

RAW:

```text
add JSON output to the users list command
```

Compiled:

```text
TASK
add JSON output to the users list command

INFERRED REPOSITORY GUIDANCE (ADVISORY)
Treat these as leads, not requirements or edit boundaries.

LIKELY RELEVANT
- forge/cli.py
- tests/test_forge.py

LIKELY CONTEXT
- `users list` currently prints an ID/name table from `USERS`.

LIKELY BEHAVIOR TO PRESERVE
- Keep the existing human-readable table as the default behavior.

USEFUL CHECKS
- `users list --json` emits only valid JSON containing the complete user array and returns 0.
- `users list` retains its current table output and returns 0.

Inspect or change additional implementation files if needed.
Implementation details are yours. Keep the change focused.
Make reasonable assumptions from repository evidence; ask only if product semantics remain materially ambiguous.
```

### Frontend, preregistered MEDIUM and compiler LOW

RAW:

```text
make dashboard better on mobile
```

Compiled:

```text
TASK
make dashboard better on mobile

INFERRED REPOSITORY GUIDANCE (ADVISORY)
Treat these as leads, not requirements or edit boundaries.

LIKELY RELEVANT
- web/dashboard.html
- web/dashboard.css
- README.md

LIKELY CONTEXT
- The dashboard uses fixed-width cards, a 900px chart and table, and a horizontal header navigation.

LIKELY BEHAVIOR TO PRESERVE
- Keep all dashboard information available on mobile.
- Keep the desktop dashboard usable.

POTENTIAL PITFALLS
- At 360px, prevent chart or table overflow from making the whole page horizontally scrollable.
- Keep month labels ordered and distinguishable rather than allowing them to collapse into wrapped prose.
- Avoid cramped or overlapping header controls.

USEFUL CHECKS
- At a 360px viewport, confirm any necessary horizontal scrolling is contained within the relevant chart or table region.
- Confirm all month labels remain clearly associated with the chart and retain their sequence.
- Confirm desktop information and layout remain usable.

Inspect or change additional implementation files if needed.
Implementation details are yours. Keep the change focused.
Make reasonable assumptions from repository evidence; ask only if product semantics remain materially ambiguous.
```

### Documentation, HIGH control

RAW:

```text
rename Foo to Bar in README.md
```

Compiled:

```text
TASK
rename Foo to Bar in README.md

CHECK
- Confirm both Foo occurrences in README.md are changed to Bar and no Foo occurrences remain.

Implementation details are yours. Keep the change focused.
```

## 60.7 Benchmark population

The frozen population used 12 tasks, 12 surface labels, and 6 repositories/projects. No surface supplied more than one task. There were 6 LOW, 4 MEDIUM, and 2 HIGH tasks. Eleven tasks used existing or partial repositories; one was near-greenfield.

| Task | Request | Repository | Surface | Specificity | Grading method |
|---|---|---|---|---|---|
| U01 | add retries | relay-service | service | LOW | deterministic hidden behavior |
| U02 | add an idempotency key to POST /jobs | relay-service | API | MEDIUM | deterministic hidden behavior |
| U03 | migrate users to UUIDs | ledger-data | database | LOW | deterministic hidden behavior |
| U04 | add JSONL export to the event converter | ledger-data | data | MEDIUM | deterministic hidden behavior |
| U05 | add JSON output to the users list command | forge-cli | CLI | MEDIUM | deterministic hidden behavior |
| U06 | speed up startup | forge-cli | performance | LOW | deterministic hidden behavior |
| U07 | add deployment health checks | ops-kit | automation | LOW | deterministic hidden behavior |
| U08 | build a small CLI for converting images | image-cli | greenfield CLI | LOW | deterministic hidden behavior |
| U09 | fix CSV export | reporting-ui | bugfix | LOW | deterministic hidden behavior |
| U10 | make dashboard better on mobile | reporting-ui | frontend | MEDIUM | blind independent rubric |
| U11 | rename Foo to Bar in README.md | forge-cli | documentation | HIGH | deterministic hidden behavior |
| U12 | rename DEFAULT_WAIT to DEFAULT_TIMEOUT in forge/config.py | forge-cli | refactor | HIGH | deterministic hidden behavior |

Each task used two fresh repeats per arm. RAW received only the exact request. PROMPIRE received a fresh frozen compilation for each repeat. Repository revisions, model, reasoning effort, workspace-write executor permissions, time limits, and interaction policy were held constant. Execution order was randomized with seed `20260804`.

## 60.8 Task-level results

`pass/pass` means both fresh repeats succeeded. Scores are successful repeats divided by two.

| Task | Surface | RAW repeats | PROMPIRE repeats | RAW | PROMPIRE | Delta |
|---|---|---|---|---:|---:|---:|
| U01 | service | pass/pass | pass/pass | 1.0 | 1.0 | 0.0 |
| U02 | API | pass/pass | pass/pass | 1.0 | 1.0 | 0.0 |
| U03 | database | pass/pass | fail/pass | 1.0 | 0.5 | -0.5 |
| U04 | data | pass/pass | pass/pass | 1.0 | 1.0 | 0.0 |
| U05 | CLI | pass/pass | pass/pass | 1.0 | 1.0 | 0.0 |
| U06 | performance | pass/pass | pass/pass | 1.0 | 1.0 | 0.0 |
| U07 | automation | fail/fail | fail/fail | 0.0 | 0.0 | 0.0 |
| U08 | greenfield CLI | pass/pass | pass/pass | 1.0 | 1.0 | 0.0 |
| U09 | bugfix | pass/pass | pass/pass | 1.0 | 1.0 | 0.0 |
| U10 | frontend | pass/pass | pass/pass | 1.0 | 1.0 | 0.0 |
| U11 | documentation | pass/pass | pass/pass | 1.0 | 1.0 | 0.0 |
| U12 | refactor | pass/pass | pass/pass | 1.0 | 1.0 | 0.0 |

Uniform-solved task count was 11 for RAW and 10 for PROMPIRE.

For U10, the blind reviewer assigned RAW scores 10 and 9, and PROMPIRE scores 9 and 10. Mean blinded quality was 9.5 in both arms. No critical regression was found.

## 60.9 Low-specificity result

No. Prompire did not make underspecified prompts materially more effective.

LOW scored 5.0 for RAW and 4.5 for PROMPIRE. The delta was -0.5 against the preregistered requirement of +1.5. Five LOW tasks tied. The database migration regressed in one PROMPIRE repeat. No LOW task improved.

## 60.10 Cross-domain result

No. There was no positive task-level delta in any software surface. Eleven surface comparisons tied and the database surface regressed by 0.5.

The implementation compiled service, API, database, data, CLI, performance, automation, greenfield, bugfix, frontend, documentation, and refactor tasks without a taxonomy failure. That demonstrates coverage of the tested inputs, not downstream benefit or universality.

## 60.11 Precise-prompt result

Yes. Prompire knew when to add little for the two HIGH controls.

Both arms scored 2.0/2.0. HIGH prompts were 25 to 32 words. No stdlib policy survived into any HIGH output. Median prompt words by preregistered specificity were:

```text
LOW:     161.0
MEDIUM:  134.5
HIGH:     28.0
```

This supports near-identity compilation for the tested precise edits. It does not offset the missing LOW-specificity benefit.

## 60.12 Cost

Compiler cost across 24 fresh PROMPIRE compilations:

| Metric | Value |
|---|---:|
| Calls | 96 total; 4 per compilation |
| Tokens | 1,220,042 total; 51,156 median |
| Input tokens | 1,184,501 total; 49,510.5 median |
| Output tokens | 35,541 total; 1,580.5 median |
| Summed wall time | 1,985.078 s |
| Median latency | 80.8575 s |
| Prompt words | 136.5 median; 217 maximum |
| Questions | 0 |

Executor cost:

| Metric | RAW | PROMPIRE |
|---|---:|---:|
| Total executor tokens | 4,192,169 | 4,245,472 |
| Median executor tokens | 174,890.5 | 171,109.0 |
| Total input tokens | 4,133,249 | 4,181,858 |
| Total output tokens | 58,920 | 63,614 |
| Summed executor wall time | 2,026.998 s | 2,068.402 s |
| Median executor wall time | 86.5965 s | 84.7515 s |
| Executor turns | 24 | 24 |
| First-attempt successes | 22 | 21 |
| Human interventions | 0 | 0 |
| Visible regressions | 0 | 0 |

Including compilation, PROMPIRE used 5,465,514 product tokens versus 4,192,169 for RAW: 1,273,345 extra tokens, or 30.37%. Summed product wall time was 4,053.480 seconds versus 2,026.998 seconds: 99.97% higher.

Median executor tokens improved by 2.16%, below the 20% ceiling threshold. Median executor wall time improved by 2.13%, but this was not a preregistered ceiling metric and was much smaller than compiler latency.

The stored summary's unnecessary-change metric is invalid. The harness stripped leading whitespace from the first `git status --short` line before slicing its status prefix, dropping the first character of one path per cell. A post-benchmark read-only recomputation from preserved diffs found one unnecessary non-test file in each arm, or 0.0417 per cell. The corrected improvement is 0%, not the stored 4.17%. This does not change the decision; both are below 20%. The frozen harness was not changed.

## 60.13 Failure analysis

### U03 PROMPIRE repeat 1: `Critic damage`

The repository said old integer-ID files must remain readable. The initial semantic policy only said to account for persisted data. The Critic then asserted that an agent could “UUID only new users and call the migration complete.” The adopted revision rendered:

```text
Do not leave persisted legacy records on integer IDs while only assigning UUIDs to new users.
Existing integer IDs are migrated to UUID strings when records are persisted.
```

Codex followed that instruction. `save_users` replaced legacy integer IDs with random UUIDs. The hidden compatibility check then failed because `get_user(path, 7)` no longer found the old user. RAW preserved legacy IDs in both repeats. PROMPIRE repeat 2 also preserved them and passed.

This was not missing repository evidence. It was an unsupported product decision introduced by the Critic and adopted despite conflicting preservation language.

### U07 both PROMPIRE repeats: `grading/infrastructure`

Both RAW repeats and both PROMPIRE repeats implemented the same observable behavior: rollout once, probe the configured endpoint up to three times, return `True` on health, and return `False` after three failures. Their visible tests passed.

The hidden grader required an exception after three failed probes. The repository only said “fail the deployment,” while the existing function returned a boolean. Returning `False` is a plausible reading of that contract. The hidden exception requirement was not recoverable from repository evidence. This absolute task failure therefore does not identify a compiler disadvantage and contributed zero arm delta.

There were no other PROMPIRE failures and no PROMPIRE wins.

## 60.14 Component diagnostics

### Facets and specificity

All 24 compilations produced valid compositional facets. Cross-domain and unknown-task tests passed. Facets varied between repeats for some tasks, including `existing_system`, `backwards_compatibility`, and `integrate`. No task-level win is attributable to a facet. The only negative delta came after a valid migration/data composition.

The compiler classified 10 outputs LOW, 10 MEDIUM, and 4 HIGH. The preregistered task labels would imply 12 LOW, 8 MEDIUM, and 4 HIGH outputs across repeats. U06 and U07 were raised to MEDIUM; U10 was lowered to LOW. Prompt size still scaled down for more specific tasks.

### Stdlib

The Resolver rejected 98 of 104 candidate policy occurrences. This prevented template-like output. The two migration-policy adoptions produced one pass and one failure; the failure itself was introduced by Critic interpretation rather than the policy text. The remaining four policy adoptions all led to passing cells, but the matching RAW cells also passed. There is no measured positive policy effect.

### Critic

```text
issues found:     59
issues adopted:   55
issues rejected:   4
```

The Critic was subtractive in precise controls: it removed the documentation consistency policy from U11 and kept the result near identity. It also rejected irrelevant findings in four cases. Its adoption rate was 93.2%, and one adopted migration finding caused the only negative arm delta. No tuning was performed after observing this.

### Renderer and records

All prompts stayed below 250 words. The maximum was 217. HIGH prompts were 25–32 words. The objective always remained the exact raw request, and relevant paths remained advisory.

All 24 PROMPIRE compilations persisted raw request, repository identifier, prompt hash, facets, specificity, evidence identifiers, candidate/adopted/rejected policies, Critic findings and disposition, final `TaskIR`, rendered prompt, compiler configuration and costs, downstream model and outcome, downstream tokens, and human intervention. No private reasoning was persisted.

## 60.15 ML readiness

### Context selector — TRAINING NOT JUSTIFIED

There are only 24 outcome-labelled PROMPIRE executions across 12 tasks. No loss was classified as wrong context or missing context, and there were no task-level wins. There is no measured loss share or preference signal for learning context utility. A held-out split would be too small.

### Semantic-policy selector — TRAINING NOT JUSTIFIED

Only six policy occurrences were adopted. Five were in cells that passed, but their RAW controls also passed. One migration cell failed after a Critic expansion not present in the policy text. This cannot separate policy value from resolver, Critic, or executor variance. There is no sufficient outcome-labelled ranking set.

### Prompt optimizer — TRAINING NOT JUSTIFIED

The downstream target is clear in principle, but this experiment provides no positive task-level preference pair and only one clean compiler-induced negative repeat. Twelve tasks are insufficient for training and held-out evaluation. A learned optimizer cannot be justified as a quality, latency, or cost intervention from these results.

No custom model was trained. If future independent outcome data ever justifies learning, the preferred order remains context/policy reranking, then a compact preference-trained prompt optimizer, then broader adaptation only if held-out evidence requires it.

## 60.16 Security

Confirmed:

```text
compiler remained read-only
no model-authored executable source ran
no generated patches were applied during compilation
```

Compiler Codex calls ran in a read-only sandbox with tools disabled. Model output was accepted only as structured metadata, `TaskIR`, Critic findings, or natural-language guidance. Tests rejected tool events and protected target, repository, and Git-administration paths.

The downstream Codex executor used the same workspace-write permission in both benchmark arms. That write access was downstream task execution, not compilation.

## 60.17 Claims supported

- The frozen compiler composes facets across the 12 tested surfaces.
- It filters most candidate stdlib policies rather than rendering a template.
- It preserves exact objectives, advisory path semantics, zero compiler questions, and a 250-word cap.
- It adds less text to the two tested HIGH-specificity controls and does not reduce their success.
- It keeps compilation read-only and records local outcome metadata without private reasoning.
- On this model and benchmark, it does not improve Codex success and increases full-product tokens and wall time.

## 60.18 Claims forbidden

- Do not claim universality outside these tasks, repositories, surfaces, or `gpt-5.6-sol` at medium reasoning.
- Do not claim that semantic facets or stdlib policies improve downstream outcomes. This benchmark measured no task-level win.
- Do not claim learned optimization works. Nothing was trained.
- Do not claim the U07 hidden exception contract was recoverable from repository evidence.
- Do not claim the stored unnecessary-file metric is accurate; use the diff-derived correction.

## 60.19 Strategic decision

### STOP COMPILER R&D

The simplified universal architecture did not produce downstream leverage. It scored 0.5 below RAW, regressed the LOW-specificity wedge, improved no software surface, and added 30.37% total tokens and 99.97% summed wall time. Precise prompts were protected, but that is not enough to justify the compiler.

The only clean compiler-induced loss was a Critic product invention. This dataset does not establish a broader learnable bottleneck, a sufficient training signal, or a viable held-out training evaluation.

## 60.20 Single next action

Preserve the benchmark as the final feasibility dataset and stop compiler architecture iteration unless it identifies a concrete learnable bottleneck with a new testable hypothesis.
