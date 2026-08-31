# VERIFIER REMAINS THE STRONGER PRODUCT

— with one structural finding the verifier-first analyses missed, and a conditional, redesigned path for the compiler thesis. Repo state examined: HEAD `e18b3b5`, branch `p1-truth-boundary`, with untracked prior-phase verdict files present and untouched. All load-bearing claims below were verified live by four sub-investigations plus an adversarial review that returned in full; the repository was not modified.

## 1. Executive conclusion

What Prompire actually does today: it verifies. The thing its benchmark proves is that a **hand-authored contract** changes execution — on the only contamination-free comparison (same revision, same tasks, claude), the full brief solved 10/10 where the goal line alone solved 0/10, and all 9 boundary-leaving runs among 180 committed rows belong to the no-brief arm. The thing its benchmark never measures is Prompire producing that contract: `prompire.py` is not invoked anywhere under `bench/`; every experiment starts from a gold brief. Compiler cost, confirmation burden, and compiled-contract quality have zero rows.

"Human writes less → agent performs better" is **not currently supported**. The deterministic `draft` makes zero decisions (it echoes the intent, hardcodes `autonomy: ask`, and probes six config files — on Prompire's own repo it proposes no acceptance command at all). `draft --agent` is capability-capped by an eight-key whitelist that makes three lint rules unsatisfiable from its own output — the goal of the project's own benchmark task T06 ("extract…") cannot yield a lint-clean agent draft. The skill path is the only real compiler, and it has no confirmation gate at all. The human's typing shrinks only in the skill flow; the human's *decisions* — scope and acceptance relevance — shrink in none.

The structural finding that reframes the whole question: **acceptance is the field that carries the measured benefit (necessary and sufficient on the contract tasks; `plus_acceptance` 20/20 with no scope list and no guard announcement) and simultaneously the field nothing verifies.** Reproduced live: a brief whose only criterion is green-on-HEAD and unrelated to the goal lints clean ("0 errors, 0 warnings"), prepares, arms, and `verify` prints `clean` on a completely untouched tree. The verdict is unforgeable *by the agent* and entirely forgeable *by the brief*. A compiler therefore doesn't extend the verifier — it relocates the one unverified authority step from the human to a model. That makes compilation a trust change, not a convenience feature, and it is why the compiler thesis cannot be promoted on current architecture, only tested after one defect is fixed.

Should P5 positioning change? No. The verifier claims P5 makes are the supported ones. The honest sentence for the compiler half is: "specify the same decisions, get a verdict the agent cannot forge."

## 2. Actual intent-to-agent pipeline

```
                          short human intent
                                 │
     ┌───────────────────────────┼───────────────────────────────┐
     │ A: prompire draft         │ B: draft --agent / --agent-cmd │ C: skill path (SKILL.md)
     │ 6 config probes only      │ snapshot repo → host model     │ host model reads repo freely,
     │ (package.json, pytest,    │ 158-word instruction; reply    │ ≤2 questions, writes full-
     │ Makefile, Cargo, go.mod); │ parsed vs 8-key whitelist;     │ schema YAML directly
     │ goal echoed, scope []     │ scope+cmds+relaxed policy      │ NO unconfirmed markers exist
     │ 2 markers                 │ marked; forbidden/constraints/ │ on this path
     │                           │ manual_checks/sub-keys UNMARKED│
     └───────────────┬───────────┴───────────────┬───────────────┘
                     │  human resolves markers   │ human reviews (nothing enforces it)
                     ▼                           ▼
              confirmed brief  ──────  prompire prepare
              (marker gate is ONLY here; lint says "shippable" over markers,
               and check_scope --activate arms a marker-laden brief)
                     │
        baseline.py --write  → measured base_rev + per-criterion status/evidence
        lint (16 rules)      → relevance/discrimination never checked
        render (250-word hard cap; baseline evidence withheld from agent,
                given to the human checklist)
        --activate           → pin outside the brief
                     │
              ~130-word agent prompt  →  coding agent  →  prompire verify
                                          (same contract judges: real git diff + re-run criteria)
```

The reinforcing loop (same contract guides and judges) is real and is the product's best property. Its weak point is the contract's entry.

## 3. Compiler capability matrix

| Capability | deterministic draft | draft --agent | skill | renderer |
|---|---|---|---|---|
| `goal` | echoed verbatim | yes, unmarked | yes | yes |
| `scope` | `[]` marked only | yes, each entry marked | yes | yes |
| `forbidden` / `constraints` | no | yes, **unmarked** | yes | yes |
| `acceptance` cmds | detected-only (6 probes), marked | yes, marked; sub-keys (`expect,cwd,timeout,requires,transition,before_after`) **unmarked** | yes | yes, with measured-state label; evidence digest withheld |
| `tests_policy` | no | yes (marked if ≠ immutable) | yes | yes |
| `tests_editable`, `oracle` | no | **refused** → `named`/`authoring` drafts guaranteed lint-red | yes | yes |
| `plan_first`, `rollback` | no | **refused** → refactor/4+-path drafts guaranteed lint-red (B10) | yes | yes |
| `context` (only semantic carrier) | no | **refused** | **only path** | yes, `<context>` data-not-instructions block |
| `baseline`, `base_rev` | measured only | refused (correct) | measured only | withheld from agent |

The three paths are three different products. The whitelist mechanism is deliberate; the resulting capability gap is documented nowhere in the tree.

## 4. Existing evidence

| Claim | Existing experiment | Result | Evidence quality |
|---|---|---|---|
| A. Brief beats goal-only | 2026-07-31 runC vs runD, same rev, T05/T06, claude | 10/10 vs 0/10 (bare also 1/5 T02, 0/5 T04, no contemporaneous control) | VERIFIED raw rows, but: bare arm post-hoc, gold brief not compiler output, n=2 tasks clean |
| — older 30/30 vs 13/30 | first live matrix | rows destroyed (`bench/results/` gitignored) | HISTORICAL TESTIMONY only |
| B. Reduces scope drift | all 180 rows | 9 of 180 runs left boundary (18 paths), all bare, all test-file edits; 0 in 160 briefed rows | VERIFIED, cleanest result in corpus |
| C. Acceptance necessary+sufficient | runA/B/C four-sided closure T05/T06 | no_acceptance 0/10, plus_acceptance 20/20 | VERIFIED, but tied to superseded renderer wording; only `current` replicated after |
| D. Bounds | plus_bounds 10/10 boundary, 0/10 contract; **plus_acceptance also 10/10 on boundary** (coupled) | sufficiency VERIFIED; necessity NOT ESTABLISHED (no_bounds: 0 surviving rows) | mixed |
| E. Measured state | no_state | 0 surviving rows, self-repudiated testimony | NOT ESTABLISHED |
| F. Guard announcement | plus_* arms carry **no** `check_scope.py` line, still 20/20 in-scope | content, not deterrence, carried the tasks | VERIFIED (indirect, live-recheckable) |
| G–J. Turns/tokens/$/time | clean T05/T06 comparison | brief adds ~1.5 turns, ~10s, ~10% $ — but vs a 0%-success arm ("finishing costs more than not finishing"); plus_bounds was 12.5% *cheaper* than bare on T02/T04 | NOT ESTABLISHED either direction |
| K. Diff size | — | no metric exists in any row | NOT ESTABLISHED |
| L. Human effort | — | no experiment contains a human | NOT ESTABLISHED |
| M. Cross-agent | 90-run matrix, `current` only | claude 30/30, codex 30/30, agy 20/25 (3 of 5 ERR rows actually left green repos) | PARTIAL: brief works on 3 hosts; the *gap over bare* tested on claude only |
| N. Benefit vs compile cost | — | compiler never invoked in `bench/` | NOT ESTABLISHED — cost side is blank |

## 5. What the current benchmark does NOT prove

It does not measure Prompire's compiler — only hand-authored briefs. It does not test underspecified input: `bare` is a distilled goal line back-formed by an author who knew the answer, not a naive request. Necessity of state, bounds, and the guard announcement is unestablished (zero surviving ablation rows; the old testimony is self-repudiated as leak-contaminated for `no_state`/`no_bounds`). It shows no efficiency benefit and cannot address diff size. Effective n for generalization is 6 tasks on one 13-file synthetic fixture with one model set — per the benchmark's own rule that repeats measure stability, not sampling. Ablation conclusions are statements about a renderer wording that was rewritten on 2026-08-01. Pooling across campaigns is forbidden by the instrument itself (`bench/report.py` renders MIXED and exits 2); 30 of 50 `current`×claude rows also name pre-rewrite commits that no longer exist. And its isolation is insufficient for any future compiler benchmark three ways: the harness plants the gold brief inside the repo, live cells aren't sandboxed for claude/agy, and the fixture's planted bug is committed in this very repository.

## 6. Human-effort analysis

Genuinely saved: baseline measurement (facts nobody can bluff, ~16 words/criterion the human never types), command validity (a broken, missing, or red command is caught by B5/B15 without the human running anything — verified with three bogus commands), boundary enforcement and base pinning (write `scope` once; enforcement needs no cooperation), and deterministic rendering (26 human words → 96-word prompt + 78-word checklist).

Genuinely moved, not saved: choosing scope (correct *and* complete — nothing checks either; the tracked-path test catches typos only), acceptance **relevance** (100% human, 0% assisted, unflagged — the load-bearing decision in the product), `tests_policy` adjudication, and lint warnings. In the CLI flow the drafter contributes 42% of the final brief's words and zero of its decisions. Marker counts (2 deterministic, 6 for a richer agent draft) should be read as **compiler coverage, not burden** — a compiler that emits fewer markers has made fewer decisions or hidden them; today's count already understates what the model decided, since `forbidden`, `constraints`, `manual_checks`, and all acceptance sub-keys pass through unmarked. Any "reduce confirmations" fix moves in the wrong direction.

## 7. Total-efficiency model

The correct unit is total cost per task outcome, with four terms: compiler cost (host-model tokens, tool calls, wall clock — observable only via the host; `run_draft_agent` records nothing today), human confirmation (marker count is cheaply loggable now; minutes are not), execution cost (tokens/turns/$/wall — already captured by the bench harness for claude), and retries/re-arms (partially visible via tombstone timestamps). Cost *per solved task* is undefined exactly where the product matters (RAW solving 0), so report cost per attempted task alongside solved rate, under a fixed ceiling. Three zero-telemetry collection steps, in cost order: timestamp `.prompire/ACTIVE` at activation (yields arm→verify wall clock), print the marker count on `draft`'s stdout, and append `verify --json` + timestamp to a gitignored `.prompire/runs.jsonl`.

## 8. Compiler gaps

| Rank | Gap | Evidence | Product impact | Needs code? |
|---|---|---|---|---|
| 1 | Nothing requires acceptance to discriminate done from not-done; all-green brief verifies `clean` on an untouched tree | reproduced end-to-end | the verdict's worth is unbounded below; any compiled acceptance is unauditable | Yes (lint rule; small) |
| 2 | Marker gate exists only in `prepare`; `lint` prints "shippable" and `render`/`--activate` proceed over unconfirmed lines | reproduced | the model-proposes/Prompire-establishes distinction is one command deep | Yes (lint warn; small) |
| 3 | `draft --agent` 8-key whitelist vs lint: `named`/`authoring`/refactor/4+-path tasks structurally lint-red from agent drafts; T06's own goal cannot compile | code + live probes | CLI compiler cannot express the modal delegated task; three-products incoherence | Yes, *if* the CLI compiler is kept as a surface; alternatively document skill path as the compiler |
| 4 | Unmarked pass-through of `forbidden`, `requires` (can neuter a criterion to `not_runnable` at warning level), `transition` | code, verified | model output acquires authority without confirmation | Yes (marking; small) |
| 5 | Compiler instrumentation absent (no tokens/latency/markers recorded) | code | thesis untestable without it | Minimal |

## 9. Minimal missing experiment (E1, redesigned after adversarial review)

Precondition: gap #1's lint rule exists (otherwise compiled acceptance can't be trusted even when green). Tasks: **8 tasks on 3 small external repos never referenced in this tree**; each task's ≤15-word request is taken from the repo's real issue tracker (or written before deep exploration), and its hidden grading contract, gold brief, gold patch, and one plausible-but-wrong patch are authored afterwards and kept outside every visible workspace. Arms: RAW (request → claude), COMPILED (request → skill-path compile in Claude Code → **blind confirmer** who never sees the hidden contract or patches, edits logged, 10-min cap → prepare → prompt → claude), GOLD (author brief, reported as calibration only — it is graded by its own author and carries no information beyond ceiling). 2 repeats, claude only; a codex arm only if the primary result is positive. Compiler stage scored before execution: required paths ⊆ scope, no invented commands, tests_policy valid, and the discrimination triple — compiled acceptance red on HEAD, green on the gold patch, **red on the wrong patch**. Primary metric: tasks uniform-solved (both reps, graded from outside by the author's hidden contract). Decision rules are task-level, not run-level: **success** = COMPILED uniform-solves ≥3 more tasks than RAW and every task GOLD solves except at most one, with ≥7 of 8 compiled contracts passing the discrimination triple; **kill** = COMPILED ≤1 task over RAW, or ≥2 of 8 contracts invent a command or fail the triple, or median blind confirmation exceeds 10 minutes. Total-cost accounting per §7, ceiling ~$60 execution + compile tokens logged from the host CLI. No arithmetic against the existing `bare` rows — different request populations.

## 10. Exact falsifiable hypothesis

> Starting from the same ≤15-word real-world request on repositories absent from every existing fixture, the skill-compiled, blind-confirmed contract uniform-solves at least three more of eight tasks than the raw request, with at least seven of eight compiled contracts passing the red-on-HEAD / green-on-gold / red-on-wrong-patch discrimination check, at a median blind-confirmation time under 10 minutes.

Thresholds derive from the observed near-determinism of cells (5/5-or-0/5) and the 4-task spread of the existing bare arm; run-level statistics are unavailable at this n by the benchmark's own rule.

## 11. Product-positioning verdict

**VERIFIER.** One sentence: "Prompire pins what a delegated task may change and how done is measured before the agent starts, and reads the verdict from the real git diff after it stops — you still decide the contract; nothing the agent claims can forge the result."

## 12. Implication for P5

### Keep P5 as currently designed

One caution, not a reframe: P5 must not amplify SKILL.md's "compile a one-line request" sentence into a README claim — the CLI draft paths do not deliver it, and no row supports it. P5's drift/done-ness headline with the committed numbers (stated per-campaign, never pooled — the instrument itself refuses pooling) is exactly what the evidence carries.

## 13. What NOT to build

No `context` auto-generation or semantic repo summaries — zero benchmark tasks use `context`, no outcome evidence exists, and the 250-word render budget (exit 1 on overflow) is the existing mechanism that correctly prices any addition against the acceptance criteria. No expansion of `draft --agent`'s key surface before E1 — it would grow the third compiler before knowing whether the first is worth having. No auto-confirmation or marker reduction — markers measure coverage; reducing them converts model guesses into authority. No LLM judge in the verdict path — the relevance hole gets a deterministic gate (red-on-HEAD requirement, warning-level for pure-refactor/hold shapes where a no-op legitimately passes acceptance and done-ness rests on the human reading the diff). No persona/boilerplate prose — the `persona` variant sits untested at zero rows and everything measured says the criteria, not the wording, carry the outcome.

## 14. Single next action

Fix one defect before any experiment: add the deterministic discrimination check to `lint_brief.py` — an error when no acceptance criterion distinguishes the untouched tree from done (every baseline `pass` with `transition: green`), a warning for the refactor/hold shapes where that is inherent — plus the one-line marker warning in lint. Then run E1 as specified in §9. Without this fix, a compiled brief that verifies `clean` proves nothing, and E1 would measure noise.
