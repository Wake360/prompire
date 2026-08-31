---
title: Prompire Product Thesis — final research verdict
tags: [prompire, product, thesis, verdict, research]
date: 2026-08-05
source: full-history synthesis session — 12 parallel evidence lanes (experiments, docs, LifeOS book corpus, Reddit-adjacent, X, market) + fresh-context adversarial review
related: [e5-validated-agent-learning-verdict.md, task-compiler.md, universal-prompt-compiler-report.md, execution-compiler-verdict.md, synthesis_verdict.md, PROMPIRE-MONETIZACE.md]
---

# Prompire Product Thesis

## 1. Decision

**NO VIABLE PRODUCT THESIS FOUND.**

After mining the complete experimental record (E1–E5 plus the compiler family), the product documentation, the LifeOS book corpus, developer behavior on public channels, and the mid-2026 competitive landscape, and after a fresh-context adversarial review of the strongest surviving candidate, no new build-forward product mechanism clears the bar. The strongest candidate — compiling human corrections into replay-validated deterministic guards — survived every closed-hypothesis check and the anti-audit gate, and then died on inventory, buyers, and validatability. Its kill is recorded in §19.

What remains is not nothing. The shipped verifier (PyPI 0.12.0) exists, works, and embodies the only mechanism this project ever validated. It has never been shown to a stranger. The one load-bearing unknown left anywhere in this program is distribution, and the instrument for measuring it was frozen in PROMPIRE-MONETIZACE.md on 2026-08-01 and never run. §18 specifies that test. It is a disposal question for an existing asset, not a new thesis.

No further Prompire architecture is proposed.

## 2. Product loop

No loop clears the bar. For the record, the closest finalist's loop was: developer corrects an agent → Prompire compiles the correction into a deterministic guard (constrained DSL, no model-authored executable code) → guard validated by replay against the offending diff → human approves one line → guard renders to Claude Code / Codex / Cursor hooks → the mistake class is blocked in the moment on every future run. The fresh-context verifier confirmed this loop is genuinely not audit-only: denies alter agent trajectories at runtime; remove every report and the enforcement still operates. It failed anyway, for the reasons in §19. Passing the anti-audit gate is necessary, not sufficient.

## 3. Structural lessons from failed Prompire experiments

Six preregistered experiments in ~30 hours (E1, E2, task-compiler, task-context-compiler, universal-prompt-compiler, plus E3/E4 and E5) form one unbroken lineage. The verdicts reduce to a small set of forbidden mechanism shapes, each falsified more than once:

**Generated authority dies.** Four independent implementations of "a model produces the specification a human currently writes" were killed on preregistered gates (E1 3/8; E2 0/8; task-compiler 0/8, kill fired; universal compiler RAW 11.0/12 vs PROMPIRE 10.5/12 with zero positive surfaces, +30% tokens, +100% wall time). The terminal lesson, stated in task-compiler.md §15: nothing establishes authority except a mechanical measurement or a human confirmation. Source-text filters are not a trust boundary. Never execute unreviewed model-authored code.

**The advisory channel dies.** E5: verbatim maintainer rules in the repo's own instruction file did not reduce targeted violations on held-out tasks (§4). Externally replicated three times over before our run (ETH 2602.11988, Guardrails-Beat-Guidance 2604.11088, ICML 2026 unfaithful self-evolvers) and once after (Anthropic deleted >80% of Claude Code's system prompt with no eval loss).

**Economic arbitrage dies at the oracle ceiling.** E3's −45% oracle saving was substantially a corpus artifact (strong-model cost fell from $1.03 to $0.75 per cell on the fresh corpus, compressing the cheap/strong ratio from 0.42 to 0.61). E4: a PERFECT failure detector saves 12.5% against a 20% gate. When the perfect version of a mechanism cannot pay, no implementation can.

**Context hurts.** Helped 3 / hurt 6 in E3's paired flips, with 17 of 20 oracle picks using raw repo access — and this held even though 7 of 24 context packs leaked the gold fix.

**New this run — the free-substrate market shape.** Deterministic verification gates on native hooks have real demand and no adopters: wtcraft (Prompire's exact design, 206 commits, 3 stars), six independent Stop-hook verification gates (0–3 stars each), Checkout's internal "Vector" built in days on free hooks with "peer orgs built the same," TRACE/TellOnce at 5 stars, no funded startup in the niche. Demand that is satisfied by an afternoon of internal work against a free substrate does not convert into a product. This is a market-shape kill, orthogonal to mechanism quality.

**New this run — the lint-selection effect.** When a correction is cleanly mechanizable, real repositories mechanize it with existing lint and it never becomes a prose rule (E5's L14 was dropped for exactly this reason: "already linter-enforced upstream"). The prose-rule population — the trigger stream for any correction-compilation product — is pre-selected against compilability. This kills the entire "compile the correction" family, not just one variant.

**Vendor absorption base rate.** Orchestration-layer workarounds get absorbed natively within ~12 months (ralph loops → /loop, /goal, /batch; worktree scripts → native worktrees; cost runaway → native budget controls). Claude Code and Codex both shipped /goal — the pinning UX — in 2026. The one loop vendors have not closed deterministically: whether the delivered diff is what a pinned contract allowed. /goal's evaluator is a small model reading the transcript; the working agent still owns its own grading surface.

## 4. Latest E5 result

Result: REJECTED, terminated at 93/112 cells with CONFIRMED already arithmetically unreachable. The deep-dive this session sharpened the reading beyond the verdict document:

Instrument: sound implementation (prereg frozen before any graded run, leak audit 28/28, detectors unit-tested) inside a structurally insensitive experiment. Nine or ten of 13 non-control lessons sat at a zero-violation baseline floor — the pinned model already avoids those mistakes without the rule. Only three lessons (L01, L02, L16) were measurable at all, on six baseline violation events.

Correction to the verdict document's own overclaim: the pooled direction (6/43 baseline vs 9/44 candidate) is noise (Fisher p=0.57). "The rule arm was worse" must not be carried forward as a claim. The supported claim is: no reduction anywhere, and the frozen gates were unreachable.

Causal mechanism where measurable: in both rule-ignored lessons, the repository's own code contradicts the written rule in the exact file the agent edited (browser-use tests already mock httpx.AsyncClient; home-assistant tests violate the usefixtures rule at 4/4, 10/12, 6/11 in the touched directories). The agent said it was "mirroring the existing test style" and never mentioned the rule. Prose loses to concrete in-context exemplars.

What is falsified, precisely: verbatim maintainer prohibitions in a repo's own instruction file do not reduce targeted violations on held-out tasks for claude-sonnet-5, and fail hardest where repo code contradicts them; separately, most real rules are inert for this model generation. Mechanism failure, not implementation failure. Transfer failed where it was answerable and was floor-unanswerable everywhere else. Both halves are fatal for the promotion-loop product: the inventory is empty and the promotable candidates are inert or harmful.

Demand context preserved from Phase A: the pain is real (four closed Anthropic tracker issues including #23075 requesting exactly this loop; a 5,200+ reaction AGENTS.md cluster; Vercel's in-house harness 53%→100%; 79 catalogued verbatim maintainer corrections) and the paid demand is absent (every shipped validation tool at near-zero adoption; no non-vendor company with headcount on agent-config evals). Talk ≫ pay.

## 5. Product/document evidence

The shipped product (0.12.0) is a deterministic, LLM-free verification layer: human-authored YAML brief (scope allowlist + executable acceptance), baseline measured on untouched HEAD, sha256-pinned outside agent reach, PreToolUse speed-bump on three hosts, post-hoc verdict from the real git diff. Most P0 fixes from the August verdict documents shipped (human verdict line, package docs, --version, truth-boundary corrections, named/authoring acceptance evidence).

The decisive documentary facts: there is no evidence of external adoption anywhere on disk or on the public internet (598 all-time PyPI downloads, ~195 last month, 0 GitHub stars, zero indexed web mentions of "prompire" — FACT, verified 2026-08-05). The launch prescribed by PROMPIRE-MONETIZACE.md Phase 1 never happened. The three preregistered post-launch field experiments (catch incidence, loop tolerance, demo conversion) were never run. Every experiment this project has run measured mechanisms; the experiment that measures demand has never been run. That asymmetry, not any mechanism question, is the program's actual open frontier.

Also recovered: E2's verdict exists only in ~/prompire-e2/FINAL-VERDICT.md and is referenced by no document in docs/; the task-compiler exploratory re-run (parse defect fixed) scored 0/4 and is recorded nowhere but gitignored bench/results/tcx_s*.jsonl. Both belong in the record: the parse fix did not rescue the architecture.

## 6. AI and mathematics corpus findings

Findings that materially affected the decision, with provenance to ~/LifeOS/outputs/book-extraction/:

**Verification/finding asymmetry** (gowers-princeton-companion): generation sits on the hard side, checking on the cheap side. This is the cleanest external frame for why every compiler died while the verifier works — and why re-adding generation machinery should stay forbidden.

**Why E5 had to fail** (islp, goodfellow, understandingdeeplearning, foundations-ml-mohri): DAgger's result — generalized rules distilled from clean corrected trajectories do not produce recovery at the states the learner actually visits; only on-policy correction does. No-Free-Lunch: a universal rule is a universal regularizer, which is not a thing. Local-vs-extreme generalization: applying a stated rule in a novel context is exactly the generalization mode LLMs are weakest at. Three independent theory accounts converge on E5's empirical null.

**Enforcement beats advisory, formally** (goodfellow, via the CNN-as-infinite-penalty result): architectural constraints are hard exclusions from the hypothesis space; prompts are soft preferences within it. This is the book-form of the community's "hooks are deterministic, CLAUDE.md is probabilistic" — and it fed the guard-compiler finalist, which then died on market grounds, not on this principle.

**Commitment devices** (schelling-strategy-conflict, dixit-nalebuff-strategy, zimmerman-accounting, hofstadter-geb): a commitment must be visible and irrevocable; delegation requires decision rights, measurement, and consequence assigned together, with measurement never self-reported; a system cannot verify its own invariant from inside the process that produced it. Three-way triangulation explaining why the pinned, agent-uneditable contract is the sound half of the design and why blending generation with verification was structurally doomed.

**Breadth over per-decision skill** (grinold-kahn-apm): value scales with skill × √breadth — the one genuinely generative book idea (invest in many small independently-checked tasks over sophistication of any single contract). It died at the same gate as everything else: the decomposition author would be a model, which is generated authority.

**Ecosystem hygiene** (ddia, ddia-storage): idempotency keys, compensating transactions, dead-letter states for stuck tasks. Sound engineering guidance for any future harness work; none of it is a product.

The mathematics corpus contained no direct treatment of value-of-information or optimal stopping (grepped; zero hits) — the sequential-testing lens the mining brief hoped for is not actually in these books. Lakatos's lemma-incorporation taxonomy (proofs-refutations) is a useful human-facing vocabulary for contract repair and nothing more.

## 7. Reddit evidence

Method honesty first: direct Reddit access was tool-blocked for the entire session (every subdomain and mirror; WebSearch surfaced zero reddit.com permalinks). Evidence comes from the same population on adjacent-primary venues — GitHub issue trackers, Cursor's Discourse forum, HN via Algolia, Blind, engineering blogs — plus secondary paraphrases of Reddit threads, labeled INFERENCE and never treated as FACT.

The strongest recurring pains, with levels: instruction files ignored across all five major tools, Sep 2025–Aug 2026, vendor-acknowledged as structural (Cursor: rules are "strong guidance," not "fail-closed guards"; Cline: "context dilution"; OpenAI: logged as training feedback for a year) — WORKAROUND-level, with users building gate systems (matheus-rr's 7-gate git enforcement) — COMMITMENT-level at the tail. Destructive agent actions with real damage (terraform destroy on production erasing 2.5 years of data; a `git checkout --` loop destroying two hours of work; subagents deleting 20–30 production files) — the adopted remediation in each case was a hard tool-permission gate, not more instructions. "Reports success but did nothing" is a folk category with its own naming convention in the Claude Code tracker. Parallel-agent coordination pain produced a proliferation of tiny worktree orchestrators (most at single-digit traction).

Professional-community signal: Bryan Finster's production team independently converged on Prompire's exact validated mechanism (executable acceptance fixed before the agent runs, verified after, no manual review) — found by search, not seeded. Jellyfish's 2.16M-PR study: AI adoption 14%→51% of PRs with flat bug rates and only 1.11–1.16× speed — against both hype narratives.

Negative evidence, deliberately collected: one severe multi-symptom "instructions ignored" cluster was tied to a specific model regression window and self-resolved by switching models in two days; several documented pains disappeared with newer models; hooks themselves are unreliable in parts of the ecosystem (Cursor deny-that-doesn't-block, confirmed by staff); and the loudest tracker pains by an order of magnitude are model quality and pricing, not workflow scaffolding.

## 8. X evidence

x.com returns HTTP 402 to fetches; posts were verified via search-index renderings at real status URLs plus secondary coverage, and are labeled accordingly.

Three behavioral clusters. First, standing-rule mechanisms are collapsing in public: three independent 2026 papers, Anthropic's 80% system-prompt deletion, position reversals by prominent users, and skills purges by heavy users; swyx's framing — a stale AGENTS.md is "an indirect prompt injection you perform on yourself" — is the sharpest public statement of what E5 measured. Second, executable verification is the one thing everyone independently rediscovers: Boris Cherny ranks "give Claude a way to verify its work" the single highest-leverage practice; Simon Last's 13-day run rests on it; Kent Beck wants tests markable immutable; Evil Martians: "every rule you can encode as a tool is a rule the LLM can't forget." The insight is validated and it is not proprietary. Third, the mechanism already has shipping neighbors: agent-spec (443 stars — but it is a spec compiler, closed hypothesis #1 rebuilt), spec-kit (125k stars, LLM-generated specs), wtcraft (Prompire's design, 3 stars).

Behavior-over-virality checks: practitioners who parallelize keep the human merge gate; practical concurrency caps at 4–8 agents per developer with review as the stated bottleneck; heavy users are actively deleting accumulated instructions and skills as models improve — accumulated advisory artifacts age into liabilities.

## 9. Cross-source synthesis

Survived triangulation (experiment + docs + social + market + books): instructions are advisory and enforcement is the only binding layer (E5 + vendor docs + community framing + CNN-regularizer theory + TRACE/ContextCov numbers). Executable acceptance criteria are the load-bearing field of a delegation contract (E-bench + Finster + Cherny + Bun's conformance suite). Generated specification does not help and generated authority cannot be trusted (E1–E4 + Dex Horthy + spec-driven criticism + Tessl's unshipped compiler). Violation floors rise with each model generation (E5 floors + Schmalbach's 0-violations-in-64-runs + Anthropic's prompt deletion).

Failed triangulation: "developers will adopt third-party verification tooling" — contradicted everywhere it was measurable (wtcraft, six gates, mdarena/clawmark/TribeAI, Vector-class internal builds, Prompire's own 598 downloads). "Everyone is hand-rolling hooks" — 13.3% of public Claude Code repos use hooks at all. "Drift is a mass daily pain" — internal 9/20 was measured on temptation-authored tasks; Schmalbach found zero drift in both arms on modern agents; drift is real as a catastrophic tail, not as a daily base rate.

## 10. User pain

The precise recurring event, honestly sized: a developer delegating multi-file tasks to a CLI agent hits, at low frequency but occasionally catastrophic severity, a mechanically-describable misbehavior — out-of-scope edits, destructive commands, test-oracle tampering, false completion claims. The daily version of this pain is shrinking with each model generation (floors). The tail version (production destruction) persists and drives real post-incident adoption of deterministic gates. The mass-market daily pains are model quality and price, which are not addressable by this project.

## 11. Existing workaround

What developers actually do today, in observed order of prevalence: nothing (trust + spot review); native permission modes, sandboxes, and settings.json deny rules; worktree isolation; keeping the human merge gate and reviewing diffs; the sophisticated tail hand-builds deterministic gates on free native hooks in an afternoon (Vector, matheus-rr, Jamon Holmgren's pre-commit lint gates) and does not look for a vendor afterward.

## 12. Competitive boundary

Native: Claude Code and Codex both ship /goal (hand-authored completion condition, model-evaluated from the transcript), ~30/11 blocking hook events, native worktrees, sandboxing, budget controls, task lists, and three tiers of LLM diff review. Cursor ships parallel agents, /best-of-n, Bugbot. The single deterministic slot vendors have left open: a verdict on the delivered diff against a pre-pinned contract that needs no cooperation from the agent. Prompire occupies exactly that slot — and the market evidence says the slot has no buyers, because everyone capable of wanting it can build it on the free substrate.

Nearest tools: agent-spec (spec compiler, closed shape), spec-kit (generated specs, closed shape), wtcraft (same design, 3 stars), Caliper (AI convention review, closed #7, live), TRACE/TellOnce (research-grade correction-to-enforcement, 5 stars), Beads (memory ledger, closed #6, genuinely adopted at 249k downloads — proof that git-native CLI primitives can reach six-figure installs, so distribution failure is a shape problem, not a channel problem).

## 13. Why a frontier coding agent does not make Prompire obsolete

Answered honestly in the falsifying direction: mostly, it does. The floors that emptied E5's inventory rise every generation; Schmalbach's zero-drift result suggests routine scope discipline is already largely internalized; vendors absorb orchestration workarounds on a ~12-month cycle and have shipped the pinning UX natively. What structurally survives model improvement is exactly one property: a verdict computed outside the agent, from the real git diff, against a contract the agent cannot edit — no model improvement makes the agent's self-report trustworthy, because the issue is incentive structure, not capability (the agent owns its grading surface in every native flow, /goal included). That property is real, durable, already built — and repeatedly demonstrated to attract no adoption as a standalone product. A durable moat around an unwanted position is still an unwanted position.

## 14. Smallest useful product

Not applicable under this verdict. The killed finalist's minimum slice — `prompire guard "<correction>"` compiling to a replay-validated hook rendered across three tools — is specified in §2 and §19 and should not be built: its informative failure modes (inventory, buyers, class-generalization) are not addressable by building it.

## 15. Economics and friction

The finalist's unit economics were fine (~1 model call per guard, millisecond runtime, zero context tax) and irrelevant: the binding economics are inventory (a few compilable, still-violated, non-native, idiosyncratic corrections per quarter per developer, trending down) and validation cost (proving a guard covers its class requires authored held-out tasks per guard — E5-scale spend per unit, the same inconclusive-ceiling wall E1 hit). The shipped verifier's economics are fine and unmeasured against demand; its friction (per-task YAML authoring, repin ceremony) is documented and real.

## 16. Compounding advantage

Nothing found compounds. Guard sets saturate at ~5–10 and go inert as floors rise. Briefs are deliberately disposable. Accumulated advisory artifacts are demonstrated liabilities (heavy users purge them). The only asset in this program that has compounded is the evidence corpus itself — five preregistered experiments plus this synthesis — which has negative product value but has now paid for itself by preventing a sixth build.

## 17. Biggest remaining uncertainty

One, exactly: whether any external developer will adopt the already-built verifier when it is actually shown to them. Every mechanism question this program raised has been answered with preregistered evidence. The demand question has never been tested — no launch, no interviews, zero marketing, 598 uninformative downloads. This is the only uncertainty whose resolution changes any decision.

## 18. Fast kill test

The frozen Phase-1 distribution test from PROMPIRE-MONETIZACE.md (2026-08-01), run as specified, without modification:

HYPOTHESIS: at least a niche of developers delegating weekly agent tasks will adopt a pinned-contract verifier when exposed to it.
LOAD-BEARING ASSUMPTION: the no-buyers pattern observed for every neighboring tool does not apply when the artifact is complete, benchmarked, and properly presented.
SMALLEST TEST: execute the already-planned launch (shortened README; HN, X, r/ClaudeAI), then measure for 2 months using only public traces (issues, discussions, public Action usage, stars, pypistats trend). Optionally attach the small hand-written guard pack (settings.json denies + a few hooks for the destructive-command tail) as a feature — a pack, not a compiler.
SUCCESS: ≥5 unique external users leaving a footprint → run the three frozen field experiments (catch incidence, loop tolerance, demo conversion) on those real users.
KILL: <5 → demand confirmed absent; archive Prompire as a finished OSS side project; the program ends cleanly.
COST: tiny (marketing effort only; zero build).
WHAT SUCCESS TEACHES: the market-shape kill (F2, §19) was wrong for a complete artifact; a product question reopens with real users attached.
WHAT FAILURE TEACHES: the F2 pattern holds even for a complete, benchmarked artifact; every future "agent workflow tool" idea inherits this prior.

The alternative fast test considered and rejected: a ~$150 E5-corpus replay measuring whether compiled guards block recurrence. The fresh-context verifier showed it cannot fail informatively — it would measure a deny mechanism already known to work, on a temptation-authored population, with no power on false-fire rates — a mechanism experiment standing in for the demand experiment again. Rejected to break exactly that habit.

## 19. Rejected finalists

**Correction-to-Guard Compiler** (the winner until adversarial review). Corrections compile to deterministic guards in a constrained DSL, replay-validated, human-approved, rendered to hooks across tools. Survived: every closed-hypothesis check (E5 killed the advisory channel; this is the enforcement channel, named as the rival conclusion in E5's own Phase A findings, with external positive evidence — TRACE/TellOnce 100%→2% on held-out OOD tasks), the anti-audit gate (denies change behavior mechanically), and the E1 trust lesson (authority via mechanical replay plus human confirmation, no model-authored executable code). Killed by: (F1) the addressable inventory is the intersection of mechanically-checkable ∧ still-violated ∧ not-native-settings-expressible ∧ not-ordinary-lint ∧ idiosyncratic, and E5's own corpus measures that intersection as near-empty — compounded by the lint-selection effect (§3); (F2) no buyers — every demand exhibit is someone who self-served without a compiler; the six 0–3-star gates are this product's market test, already run by others; (F3) replay validation is blind exactly where guards leak (it proves the instance, never the class; zernie's 84% silent-leak is the expected default and the human one-line approval is rubber-stamp by design). Also noted: end-state rules are ill-posed at PreToolUse time and collapse back to lint/CI, and the vendor owns both the substrate and the authoring moment.

**Contract-judged best-of-N** (run N decorrelated attempts in worktrees, select by the pinned executable contract). Killed by native absorption (Cursor ships /best-of-n; Claude Code ships dynamic workflows), by N× cost in a price-sensitive market, and because the deterministic-judge differentiator is a weekend build on the free substrate.

The pre-existing "ship the verifier and sell it" thesis was not re-adjudicated as a finalist: as a product bet it fails the same no-buyers evidence, and its Schmalbach exposure (the 9/20 drift premise measured on temptation-authored tasks vs zero drift in real-world arms) weakens the headline claim. What survives of it is only its experiment (§18).

## 19b. Second search round (same day, after the first verdict was challenged)

The first round's candidate set was generated by one orchestrator and had a systematic flaw: every candidate triggered on a *rare* event. A second round ran seven independent generators against deliberately under-searched lenses — daily-frequency trigger hunt, the cost/quota/reliability pains dismissed in round one, the merge decision, redeployment of the existing engine, multi-agent reality, work outside the agent loop, and a greenfield lens ignoring the sunk asset — producing ~40 candidates. Three survived the hard gates. All three were killed by fresh-context adversarial review with verified sources:

**Verified landing gate** (admit a merge only if a pre-pinned red flipped green on a grader harvested from the repo). Four of seven generators independently derived it. Killed: the admission rule is logically broken — a green main branch has no red at base, so for features, refactors, and chores the fail-to-pass set is empty by construction; enforce it strictly and it blocks nearly all legitimate work, waive it and a do-nothing diff satisfies every remaining clause and lands, falsifying the headline claim. The repair (a human-authored failing test per task) is TDD, and reinstates exactly the authoring cost the candidate claimed to remove. Separately, `funador/claude-code-merge-queue` occupied the same slot on 2026-07-10 and reached 119 stars in three weeks.

**Deterministic regression localizer** (hunk/turn bisection over a dirty tree against a pinned baseline). Killed on prior art: `Willmac16/git-bifurcate` implements it — exit-code oracle, hunk-level strategy, even the hard dependency-ordering flag — self-described as vibe-coded, active ten months, 2 stars and 0 forks. Plus an action pincer: surgical revert is correct only when the culprit hunk is incidental, which is the case rising floors are erasing; when the culprit is the intended edit, the tool degrades to a report.

**Out-of-process run watcher** (agent-done vs agent-dead). Killed: the claimed structural moat is false — the spawner owns the pid and gets child-exit free, and every real way these agents run has a parent. The enabling bugs it cited carry 0–1 reactions each and are closed not-planned.

### The finding that actually decides this

Round two produced one fact worth more than every mechanism argument in this document. **Vibe Kanban — the superset of everything above (spawn parallel agents in worktrees, watch status, review the diff, land it), multi-vendor, 27,676 stars, npm distribution — is shutting down.** Its own announcement (vibekanban.com/blog/shutdown, fetched 2026-08-05): "the vast majority are free users and we couldn't find a business model that we could get excited about." Not lack of adoption. Not acquisition. No revenue model.

That reframes the entire program. Prompire's problem was never that its mechanism was wrong or that its execution was poor. Every candidate in two search rounds died against the same wall in different costumes: **this category does not monetize for anyone.** Beads has 249k downloads and no revenue. Superpowers has 267k stars and is free. HumanLayer and container-use are dormant. The best-funded spec-compiler attempt has not shipped in nine months. The category leader with 27k stars is closing. Six Stop-hook gates, wtcraft, git-bifurcate — every neighbor at every scale converges on adoption without payment.

Corollary facts from round two, each killing a lane with data rather than judgment: measured against 2,857 real sessions / 134,954 requests / ~2.77B tokens from one heavy user, there is no large mechanically-detectable class of wasted in-session spend (0.03–5% per class) — the cost lane is empty. The loudest tracker pain (model quality, 3,286 reactions) had two of three causes server-side per Anthropic's own postmortem — not locally addressable. Multi-agent complaints top out at 108 reactions and are ergonomic (terminal panes, directory paths), not correctness — the parallel-integration thesis is unsupported by the people actually running fleets.

## 19c. Third search round — the buyer axis

Rounds one and two both asked "what will an individual developer install?" Round three asked the question never asked: **who has a budget.** Six lenses — organizations currently blocked from using agents at all; where revenue actually flows in adjacent categories; whether any regulation creates a forced buyer; non-coding domains where agents write to production; post-incident and outsourced-work buyers; and one lens whose assignment was to prove no buyer exists — produced ~27 candidates with primary-source verification throughout.

**The regulatory null, verified rather than assumed.** Nothing in force in 2026 requires evidence about *how* code was authored. Checked directly against the EU AI Act (weakened by the Omnibus), the Cyber Resilience Act, the Product Liability Directive, CMMC, PCI DSS, SOC 2, DO-178C, and the SIG questionnaire. Every compliance instrument that exists terminates in a named accountable human, which converts any machine verdict into a productivity claim — the exact claim rounds one and two already killed. The apparent counter-evidence online is AI-generated SEO content.

**Four walls recurred independently across lenses.** Compliance instruments end in a human, not a verdict. Attestation monetizes only as an attachment to something the founder does not have (a seat base, a framework mapping, a platform, a balance sheet). The real-world agent bans are motivated by data egress and destructive shell actions — both explicitly outside this engine's documented view (gitignored paths invisible, shell tools unwatched). And wherever the verifier and the doer are different parties, the verifier already controls an execution substrate that yields the verdict for free.

Two candidates cleared the gates and both were then killed as products:

**Verified-task supply to RL/eval buyers** (sell frozen, leak-audited task corpora with the grader attached; the engine's pin-outside-the-actor property is literally the specification of a reward-hack-resistant environment). Killed: the market has exactly two tiers and a solo outside supplier is locked out of the paid one. Frontier labs build environments in-house; the exclusive vendors are Mercor (~$450M run rate) and Surge (~$1.2B revenue); Mechanize pays ~$500k salaries to engineers who author environments. The tier reachable by an individual prices at zero (SWE-smith, MIT, 52k instances, free automatic fail-to-pass validation; SWE-rebench; Prime Intellect's Environments Hub) or at contractor gig rates — Mercor's supply door for one person is hourly contract work. Additional defect: the corpus mines public upstream fix commits, so gold solutions sit in every frontier model's pretraining data, and the repo's "leak audit" audits request wording, not pretraining contamination — the segment that pays premiums pays precisely for freshness this method cannot produce.

**Outcome-priced remediation with the verdict as the acceptance clause** (fixed-price agent-delivered migration, accepted on a pre-agreed mechanical verdict). Killed on its own load-bearing claim: acceptance is "the buyer re-runs on their own machine," and a buyer doing that already has an unforgeable zero-cooperation verdict from native git plus their own CI — `git diff --name-only BASE..DELIVERED` is the file scope and the suite either passes or it does not. The engine defends against an agent gaming checks *inside the operator's environment*, a problem that does not exist on the buyer's side of a two-party deal. Strip the decoration and it is commodity consulting that uses none of the asset. Also: a Gartner Magic Quadrant already exists for AI-Augmented Code Modernization with Moderne as a named Leader, and the CRA's September 2026 date is a vulnerability-reporting duty, not a code-remediation deadline.

## 19d. Fourth search round — constraint relaxation, and the terminal answer

Rounds one to three all held the founder's *self-imposed* constraints fixed and searched ideas. Round four inverted that: each of six lenses dropped one constraint and searched the space it opened — no telemetry, local-first with no hosted service, cross-vendor neutrality, reuse of the Prompire engine, open-source-first, solo with no SOC 2, and the audience itself. Twenty-six candidates.

**Verdict: the emptiness is constraint-independent.** No relaxation opened a product. The decisive evidence is that every relaxation had already been run as a live experiment by a better-resourced company, and every one failed:

Hosted plus telemetry plus team plus paid subscriptions — bloop ran all of it. Vibe Kanban had a funded team, hosted cloud services, existing paid subscriptions, multi-vendor support, 27,700 stars and 30,000+ active users, and wound the company down anyway: "the vast majority are free users and we couldn't find a business model that we could get excited about." That is two relaxations executed simultaneously at roughly 27,000× this project's distribution, and it died. Team plus funding plus closed source — Tessl raised $125M and pivoted *out* of the domain entirely into an enterprise skills registry, which is a funded team's revealed judgment on the original thesis. Vendor alignment — obra/superpowers is Claude-Code-native at 267k stars and $0, and no coding-agent platform has a paid plugin rail at all (2,298 community plugins, zero paid developer tools, every Gumroad link checked returns 404). Audience — round three already granted that relaxation and returned empty. What *does* carry a price tag confirms the null rather than breaking it: Conductor gives its entire local orchestrator away and charges only for cloud compute hours and SSO/SCIM/DPA plumbing — infrastructure resale and procurement features, neither of which touches verification.

The cross-cutting cause of death, present in every kill across four rounds and immune to every relaxation: **money in this space flows to exactly three places — model inference, the agent as labor, and code review consolidated into platforms — and to nothing in the tooling-around-the-agent layer, at any resource level.** Git plus the buyer's own CI is a free, unforgeable, universally trusted verifier, so there is no trust gap to sell into. Where a genuine verification gap does exist (insurance, pharma, healthcare, procurement), what is actually purchased is institutional standing — a Lloyd's paper, an accreditation, a SOC 2 — which a solo founder cannot manufacture and which rigor cannot substitute for.

Two candidates passed every hard gate, and both did so *by ceasing to be products*. Environment and eval engineering as hired labor: the only strong-confidence candidate in 116, with verified funded demand (~25–50 organizations worldwide pay for this; Mercor at a $10B valuation, Surge ~$1.2B revenue, Mechanize paying ~$500k to author environments in-house), a two-to-five-day test that needs no new code, and the useful correction that the Prompire engine is *not* dead weight there — it is a grader harness, which is precisely the artifact that lane hires for. Parity-gated migration delivery: a weak solo services wedge worth one preregistered 30-day test, whose own reviewer flagged that the prescribed n=5 cold-outreach test is statistically void and would manufacture a false kill.

## 20. Recommendation

**NO VIABLE PRODUCT THESIS FOUND — and, after round four, this is a statement about the domain rather than about Prompire.** Four independent search rounds, ~116 candidates, adversarial kills on every survivor, primary-source verification throughout.

Round one exhausted desk-derived mechanisms. Round two exhausted mechanism space with seven generators against deliberately under-searched lenses and found that the category does not monetize for anyone. Round three exhausted the buyer axis and found no forced buyer exists, because no instrument in force asks the question this engine answers. Round four dropped every self-imposed constraint one at a time and found that none of them was load-bearing — better-funded teams had already run each relaxation and failed.

The four rounds fail for four *different* reasons, which is what makes the conclusion robust rather than repetitive: no mechanism gap, no revenue in the category, no buyer with an obligation, and no constraint whose removal changes any of that. A fifth round is not information-generating, and round four's terminal lens was explicitly invited to name a methodological flaw that would justify one. It declined, on the record.

What remains is not a product and should not be described as one. Three tests cost days rather than months and each carries a preregistered kill: send the eight frozen tasks with a per-accepted-task quote to three to five eval-vendor delivery leads (kill: no paid pilot in 4–6 weeks — a "join our platform" reply confirms the kill rather than refuting it); pitch ten fixed-price remediation SOWs against dated EOL and pen-test events (kill: zero signatures in a quarter; note this is a consulting practice, not a company); and run the frozen Phase-1 distribution test on the existing artifact (kill: fewer than five external users in two months). One costless email to an existing attestation vendor (Kosli, TestifySec) offering the verdict engine as a component, with "we will build it ourselves" as the expected reply.

The most valuable asset produced by this program is not the code. It is the demonstrated ability to design preregistered experiments that kill the author's own hypotheses — five of them, with frozen criteria, honored after the results came in. Round three's own market data prices that skill directly: environment and eval authoring is what labs pay ~$500k salaries for, and rigorous adversarial task construction is the scarce input. The engine is worth approximately nothing on the open market; the discipline that produced it is worth a great deal, and it is employable immediately.

Do not build the guard compiler. Do not build another architecture. Do not reposition the harness as an audit product. The single remaining action with any information value costs approximately nothing to build and two months to observe: run the frozen distribution test on the artifact that already exists, and let its preregistered kill criterion make the final call. If it kills, Prompire ends as a completed, honestly-documented OSS project with an unusually clean evidence trail. If it survives, the next thesis will be written with something this program has never had: users.
