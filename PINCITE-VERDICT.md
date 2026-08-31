# pincite — product investigation verdict

Date: 2026-08-06. Method: 13-agent evidence sweep (local assets + Aug 2026 market
research), 3-tree random forest over Grok Directions A/B/C, competitive kill attempt,
3-tree ratification of flagship/architecture/eval, fresh-context skeptical verifier.
Spec revisions: v1 → v2 after ratification. Final decision at the end of this file.

---

## 1. Executive Verdict

**Build `pincite`: local-first grounded document QA — ask a question over a folder of
visually complex PDFs, get the answer plus the exact page region it came from, down to
the table cell, produced entirely on local hardware.** A Python library + CLI + MCP
server, with a deterministic grounding layer as internal mechanics and a built-in
evaluation harness as a first-class feature.

It came from **Grok Direction B (Document → Agent Pipeline)**, which won the Random
Forest vote **unanimously, 3–0, average confidence 74**, and then survived a
competitive kill attempt, a three-tree ratification, and a fresh-context verifier
(PASS WITH RISKS). The primary user is an ML/agent engineer building document
workflows over private or regulated PDFs (legal, financial, healthcare, consulting)
who cannot ship pages to a cloud API and cannot ship answers without checkable
evidence.

Why it should exist, in one sentence of evidence: commercial vendors (Mistral OCR 4,
Reducto, LandingAI, LlamaParse — $19M Series A) sell "grounded, citation-ready
document understanding" as their headline feature, the loudest repeated developer
pain in local document AI is untrustworthy citations, and no open-source local-first
tool delivers answer-level provenance — the previous occupants of the space are dead
(byaldi, last commit Nov 2024), relicensed and pivoted (Morphik → BUSL, healthcare
vertical), or quiet (localGPT-Vision).

Why the other directions lost: Direction A's own preferred flagship *is* Direction
B's job wearing a riskier "skills" wrapper next to a 1.9M-item slop marketplace
(scores 56–60 across trees); Direction C is runtime territory already owned by
LocalAI/Ollama/LM Studio/MLX-VLM, and any flagship strong enough to save it collapses
into B (scores 33–35).

## 2. Evidence Summary

Only evidence that changed the decision.

**From Prompire and the experiments (VERIFIED first-hand).** The e-series is five
rigorous, preregistered experiments, four of which killed their own hypotheses: E1/E2
rejected the brief-compiler thesis, E4 rejected adaptive model routing at its
theoretical ceiling ("STOP THIS PRODUCT DIRECTION"), E5 (incomplete) shows agent
rules are mostly dead weight. Prompire's own terminal product document (2026-08-05)
concludes "NO VIABLE PRODUCT THESIS FOUND… The engine is worth approximately nothing
on the open market; the discipline that produced it is worth a great deal." Decision
impact: the agent-infrastructure direction is exhausted by the author's own evidence;
the durable asset is the experimental methodology, which becomes pincite's eval
discipline. One E3 finding directly shaped the design: pre-computed context was *net
negative* when the agent could explore the source itself — so the
plain-VLM-with-page-navigation ablation is a published baseline and preregistered
kill gate, not an afterthought.

**From LifeOS (VERIFIED).** The 2026-07-06 user veto — "no more audit tool… I am
rejecting every candidate with just audit" — plus the D4 disqualifier framework.
Toulmin (`~/toulmin`, v0.3.0, 244 tests, never pushed) supplies the verdict-law
lineage: green only on deterministic verbatim evidence, model estimates visually
distinct — and its honest G2 failure (local NLI too weak to judge) is why pincite's
verdict path contains no learned component. The knowledge corpus supplied operative
principles now baked into the eval design: rank-weighted metrics, locked test
splits, n-run confidence intervals (the author's own ~9% temp-0 flip measurement),
failure-taxonomy discipline.

**From the supplied Hugging Face screenshots.** Document Question Answering and
Visual Document Retrieval are first-class Multimodal task categories — the flagship
territory is a recognized ML task, not an invented one.

**From current market research (five agents, Aug 2026, spot-verified via the GitHub
API and web).** The conversion layer (PDF→markdown) is saturated and converging (~1
point separates leaders); grounding is the open layer. ViDoRe V3 (ACL 2026) exists
with bounding-box evidence annotations and is far from saturated (leader nDCG@10
63.42; even humans agree at only F1 0.602 on evidence boxes). CiteVQA — from
MinerU's own org — formalizes exactly this task and shows the gap: GPT-5.4 answers
87.1% correctly but only 59.0% with correct evidence attribution; the best *open*
model manages 22.5. The commodity recipe (ColPali retrieve → VLM answer) is in every
vendor tutorial; answer-level grounding is in none.

**Corrections to the mission brief (VERIFIED).** `e4-tokenize` does not exist
anywhere on disk and tokenization was never part of E4. The "Grok Directions A/B/C"
text exists nowhere locally (`.grok` is just the CLI installation) — the mission
brief itself was the operative source. `LifeOS/outputs/book-extractions` is actually
`book-extraction`. Reference hardware is an **Intel** MacBook (i7-9750H, 16GB, no
Apple Silicon, no CUDA) — this shaped the CPU-first MVP constraint and the M0
latency spike.

## 3. Grok Candidate Ranking

**1st — Direction B (Document → Agent Pipeline), sharpened to grounded document
QA.** Differentiation: verified vacant OSS slot with commercial proof of demand.
Problem evidence: the strongest in the entire packet (HN mega-threads on
undetectable VLM error rates, kotaemon's broken citation highlighting, AnythingLLM
page-citation requests open since 2023, tool choice decided on "answer
traceability"). Feasibility: solo-buildable from active primitives (colpali-engine,
ColModernVBERT-class 250M retrievers, sub-1B doc-VLMs, deterministic localization).
Measurable: ViDoRe V3, CiteVQA, MMLongBench-Doc all unsaturated. Demo: answer +
highlighted table cell is instantly legible. Audit-tool risk: real but manageable —
provenance is a native property of the answer, never a checker of others' outputs.

**2nd — Direction A (High-Signal Multimodal Skills + Runtime).** The genuine
finding in its favor: "multimodal skills" is an unclaimed category and superpowers
proves few-deep-skills wins (267.7k stars from ~14 skills — verified). But its own
preferred flagship is B's job, the runtime is the hard undifferentiated part, and
quality-plus-evaluation as the headline value fails the Prompire-removal test. The
skills surface survives *inside* B as the MCP interface.

**3rd — Direction C (Local Multimodal Toolkit + Agentic Layer).** Breadth without a
wedge. LocalAI (48.3k stars), MLX-VLM, LM Studio, llama.cpp already own the runtime
layer; a solo builder inherits a brutal multi-backend maintenance matrix; and the
direction must borrow A's or B's flagship to produce any demo. "LocalAI but
multimodal" was the failure mode the mission itself predicted.

## 4. Random Forest — Grok Product Direction

**Tree A — Product & Differentiation.** Decision: **B**. Confidence: **74**. Key
evidence: packaged local visual-doc-RAG slot verified vacant while a commercial
cluster sells exactly this; grounding is the most repeated developer blocker with no
OSS system returning cell-level provenance from a scanned table; solo-feasible with
unsaturated benchmarks. Main risk: evidence attribution drifts into the banned audit
shape, or the E3 lesson generalizes and pre-computed grounded context is
net-negative versus an agent reading raw pages. Falsifier: docling or another
maintained incumbent ships end-to-end local bbox-grounded QA. Scores: A 60 / B 80 /
C 35.

**Tree B — Technical Feasibility & Risk.** Decision: **B**. Confidence: **76**. Key
evidence: commercial validation with a vacant OSS slot; "no OSS system returns
cell-level provenance for a numeric answer from a scanned table" is a precise
unclaimed wedge; the stack (colpali-engine active, ColModernVBERT 250M within 0.6
nDCG@5 of ColPali, sub-1B doc-VLMs) is solo-feasible and reuses Toulmin's
deterministic core plus the eval methodology. Main risk: gravitational pull toward
audit framing plus the E3 pre-digested-context trap — must ship as query-time
grounded answering over documents agents cannot otherwise read. Falsifier: the
commodity ColPali+VLM recipe matches the pipeline on multi-page tasks, leaving bbox
provenance as the only differentiator. Scores: A 56 / B 80 / C 33.

**Tree C — Quality & Anti-Slop (tie-breaker, not needed).** Decision: **B**.
Confidence: **73**. Key evidence: verified vacancy with paying commercial
validation; grounding pain verified across independent sources; credible
unsaturated public benchmarks exist for exactly this task, unlike A's diffuse
per-skill eval story or C's metric-free toolkit. Main risk: the wedge collapses
from either side — incumbents ship bbox provenance, or positioning drifts from
"produces grounded answers" into "checks your citations." Falsifier: an E3-style
ablation showing a plain local VLM with page-navigation tools matches the pipeline
on accuracy and grounding. Scores: A 58 / B 79 / C 34.

**Ensemble result.** Majority winner: **Direction B, 3 of 3 votes**. Winning
average confidence: **74.3**. Material disagreement: none on the winner; all three
trees independently flagged the same two design risks (audit drift, E3 ablation),
folded into the spec as a hard non-goal and a preregistered baseline respectively.

## 5. Grok Decision Gate

### GROK DIRECTION ACCEPTED

Direction B survived as a strong winner (Outcome 1) — unanimous vote, confidence
well above the weak-winner threshold, and it subsequently survived the competitive
attack and the fresh verifier. Claude-originated discovery was therefore not
permitted to activate.

## 6. Claude-Originated Discovery

`NOT ACTIVATED — a Grok-originated direction survived evaluation.`

## 7–8. External Validation / Random Forest for Claude-Originated Winner

Not applicable — the fallback never activated.

## 9. Product Definition

**Name:** `pincite` — a real legal term meaning a pinpoint citation to the exact
page. Verified free on PyPI (JSON API 404); GitHub collisions are three 0-star
repos. Fits the legal/financial verticals the product serves.

**One-liner:** pincite answers questions about your PDFs locally and points at the
exact page region — down to the table cell — the answer came from.

**Core value proposition:** VLM document pipelines fail plausibly — fluent answers,
undetectable error rate. Existing local tools cite chunks, not answers: RAGFlow
highlights the retrieved chunk rectangle, kotaemon's fuzzy highlighting breaks with
small models, docling's grounding is a notebook example. Commercial APIs sell
grounded, citation-ready document understanding; no open-source local-first tool
owns it.

pincite makes grounding a property of the answer: every answer carries page +
bounding box + a tier — VERIFIED (the cited region deterministically and uniquely
contains the normalized answer), DERIVED (a declared arithmetic over VERIFIED
operand cells, operands cited), or ESTIMATED (model claim only). It runs CPU-first
as `pip install pincite` over a SQLite+files workspace — no Docker, no
Elasticsearch, no Kubernetes. Per the verifier's instruction, the public framing
leads with *pointing* (cell-level provenance); the verdict tier is internal
mechanics, keeping the product clear of the banned audit category.

**Primary user:** an ML/agent engineer building document workflows over private or
regulated PDFs who cannot send pages to a cloud API and cannot ship answers without
evidence a reader can check.

**Primary job-to-be-done:** grounded document QA over a local corpus: question in →
answer + page + bbox + tier out. Schema-driven field extraction (fields + per-field
provenance) is the named M2 deliverable, because the commercial comparables are
extraction-shaped.

**Explicit non-goals (v1):** no chat UI or conversation memory; no generic text-RAG
over markdown/web; no document conversion product (pincite consumes
docling/PaddleOCR/pypdfium2 output, never competes on conversion); no cloud
service; no auditing of third-party outputs — pincite grounds only its own answers;
no fine-tuning; no learned component in the verdict path.

## 10. Flagship Capability

**Task:** grounded Document Question Answering (HF tasks: Document Question
Answering + Visual Document Retrieval; grounding per ViDoRe V3 / CiteVQA /
BBox-DocVQA formulations).

**Input:** a directory of PDFs (born-digital or scanned) plus a natural-language
question, or a field-extraction schema.

**Processing:** ingest (page rendering + one parser backend producing a versioned
intermediate representation of words, boxes, and table cells with per-element
source and OCR confidence; born-digital text layers cross-checked against OCR) →
visual retrieval (late-interaction page embeddings, brute-force MaxSim at M1) →
answering (pluggable small doc-VLM returning answer + claimed evidence quote) →
grounding resolution (verify the claimed quote first, fuzzy quote-to-region; then
match the answer *only within that region*; corpus-wide string search forbidden;
ambiguous multi-matches downgrade to ESTIMATED; numeric/date/currency
normalization).

**Output:** JSON `{answer, page, bbox[], verdict, operands?, retrieval_trace}` plus
an optional rendered page thumbnail with the region highlighted. The undefined
`confidence` field was deleted from v1 by ratification; a calibrated version is an
M2 candidate only with calibration evidence.

**Quality signal:** headline metric is **verified-correct rate** — the probability
that the answer is correct (ANLS threshold) AND the tier is VERIFIED/DERIVED AND
the evidence hits the annotated region (IoU@0.5, or cell-hit for table cells).
Paired with a first-class safety metric: **false-VERIFIED rate** with a
preregistered ceiling. Plus P(correct | VERIFIED) vs P(correct | ESTIMATED),
retrieval nDCG@5, ANLS/EM, latency and peak RAM on the reference machine — all
with n-run bootstrap confidence intervals.

**Canonical example:** generated by script from the locked golden set, never
staged. A scanned annual report: "What was operating margin in Q3?" → "14.2%",
page 23 thumbnail, table cell highlighted, VERIFIED — displayed next to aggregate
failure rates of the baselines on the visually complex subset.

**Why this task:** it sits exactly on the verified vacant slot; it has unsaturated
public benchmarks; and the commodity alternative (retrieve pages, let a VLM answer,
cite nothing) is precisely what the demo measurably beats. Ensemble decision
summary: flagship ratified APPROVE/REVISE/REVISE at confidence 78–82, with all
REVISE amendments incorporated (verdict-law constraints, DERIVED tier, headline
metric replacement, fair baselines).

## 11. Core Architecture

| Component | Responsibility | Input → Output | Implementation direction | Status |
|---|---|---|---|---|
| Workspace store | Corpus state, content-hashed ingest | PDFs → pages + records | SQLite + page-image files | CORE |
| Parser IR + one backend | Normalized words/boxes/cells with provenance and OCR confidence | PDF page → versioned IR | PaddleOCR-VL or docling (decided at M0 spike); round-trip fixture tests | CORE |
| Visual retriever | Page-level late-interaction retrieval | question → top-k pages | colpali-engine, ColModernVBERT-class 250M; brute-force MaxSim at M1, pooled+quantized index at M2 if latency demands | CORE |
| Answerer | Answer + claimed evidence quote | pages + question → structured claim | Pluggable VLM backend (llama.cpp / Ollama / transformers; cloud adapter optional); reference model fixed by M0 spike | CORE |
| Grounding resolver | Verdict law: quote→region→unique containment; normalization; ambiguity downgrade | claim + IR → bbox + tier | Deterministic; OCR-source tag on every verdict for failure attribution | CORE |
| Eval harness | Golden set, benchmark runners, regression suite | corpus + labels → metrics | CiteVQA + ViDoRe V3 + MMLongBench-Doc subsets (hashed, judge protocol pinned); `pincite bench` on own corpus; locked test split | CORE |
| Interfaces | Developer surface | — | Python API + CLI + MCP server | CORE |
| Page viewer | Demo rendering | answer → HTML page + highlight | Static HTML | OPTIONAL |
| Cloud adapters | Optional stronger answerers | — | OpenAI-compatible endpoints | OPTIONAL |

**End-to-end data flow:** point pincite at a folder; it renders pages, runs the
parser backend once, embeds pages, and stores everything in a local workspace. When
a question arrives (CLI, Python, or an agent via MCP), it retrieves the most
relevant pages, has the VLM answer from page crops while naming its evidence, then
deterministically resolves that evidence against the OCR layer: if the normalized
answer is uniquely contained in the claimed region, the answer ships as VERIFIED
with the exact box; if it is a declared computation over verified cells, DERIVED
with operand boxes; otherwise ESTIMATED. The JSON answer with its provenance goes
back to the caller, and every question/answer can be promoted into the golden set
to grow the regression suite.

## 12. Prompire + Experiment Reuse Map

| Folder | Classification | Evidence | Relevance |
|---|---|---|---|
| `prompire` | ADAPT | Shipped verification layer (PyPI 0.12.0); terminal verdict "no viable product thesis"; methodology docs | No runtime code in pincite. Adapted: eval-design principles (executable acceptance, discrimination-validated graders, pinned grading surfaces), optionally briefs for delegating pincite's own build tasks |
| `prompire-e1` | LEARNINGS ONLY | Compiler thesis rejected; grader-validation triple discipline | Validate every golden-set grader fail-at-pin/pass-at-gold/fail-at-plausible-wrong |
| `prompire-e2` | LEARNINGS ONLY | Compiler thesis rejected on codex host; contamination lessons | Deny-by-default isolation for eval runs; schema-validate all model output |
| `prompire-e3` | LEARNINGS ONLY | Routing headroom confirmed then killed in E4; packs were net-negative | The B3 ablation baseline exists because of this finding; oracle-headroom analysis before building any component |
| `prompire-e4` | LEARNINGS ONLY | Adaptive runtime rejected at oracle ceiling; sealed-grading harness | Preregistration + sealed graders + n-run CIs template for pincite's eval program |
| `e4-dev` | DROP | 24 dev-fixture workspaces of E3's burned coding tasks | No relevance to document ML |
| `e4-work` | DROP | ~320 salted run workspaces (artifacts live in e4-artifacts) | Archival only |
| `e4-tokenize` | NOT VERIFIED | Does not exist anywhere on disk; grep confirms tokenization was never part of E4 | None |
| `e4-agent-config` | DROP | Isolated CLAUDE_CONFIG_DIR for E4 cells; OAuth-seeding incident documented | One operational lesson (never seed isolated configs with live credentials); no code reuse |
| `e5ws` | DROP | Clones of six OSS repos used as E5 task substrates | None |
| `prompire-e5` | LEARNINGS ONLY | Incomplete; emerging: rules are floors, enforcement beats advice | Encode pincite's invariants as executable checks, not instructions; APFS-clone workspace templates for fast eval cells |

No fake reuse: the product code is all new; what transfers is a genuinely unusual
experimental discipline.

## 13. Evaluation Design

**Dataset strategy:** three public benchmarks run as hashed, frozen subsets —
CiteVQA (element-level attribution, the closest formalization of the task), ViDoRe
V3 (retrieval + bbox grounding, 6 languages), MMLongBench-Doc subset (long
multi-page, judge protocol pinned or numbers marked non-comparable) — plus a
hand-built golden set over real documents (annual reports, contracts, forms) grown
to ≥150 questions with page/bbox/cell labels before any kill decision, with a
locked never-touched test split. Real examples dominate; synthetic cases only for
the failure taxonomy's edge classes.

**Baselines:** B1 — fair text pipeline: docling/markitdown *with OCR enabled* →
chunk-embedding RAG → the same VLM checkpoint and context budget. B2 — commodity
visual RAG: ColQwen retrieval → same VLM, no grounding. B3 — the E3 ablation as a
published baseline: the same VLM given list/view/zoom page tools over the raw
corpus (≥10 docs, ≥300 pages), matched token budget, graded identically.

**Metrics:** verified-correct rate (headline), false-VERIFIED rate (safety,
preregistered ceiling), P(correct | tier), ANLS/EM, nDCG@5 and recall@5, IoU@0.5
and cell-hit, VERIFIED+DERIVED coverage per question type (published, so the
extractive limitation is measured rather than hidden), latency and peak RAM. Every
comparison with bootstrap CIs over n runs.

**Regression suite:** the golden set is the living spec — every production failure
is promoted to a case; frozen thresholds in a hashed eval config; CI runs the
locked split with declared variance tolerance.

**Failure taxonomy:** retrieval miss / OCR failure in the IR / localizer failure
(missed or ambiguous snap) / VLM answer hallucination / VLM evidence-quote
hallucination / wrong-region VERIFIED (the safety class) / cross-page composition
failure / table-structure failure / latency-memory breach.

**Acceptance criteria:** settable now — grounding ≥59.7% IoU@0.5 on
localization-comparable items (published training-free baseline); retrieval within
a stated margin of published ColModernVBERT numbers; pincite ≥ B2 on accuracy and
> B1 by a preregistered margin on visual questions. `TO BE ESTABLISHED FROM
BASELINE` at M0/M1: absolute ANLS on the golden set, verified-correct rate, the
false-VERIFIED ceiling, the latency budget.

Ensemble decision summary: eval design ratified REVISE×3; all amendments (headline
metric replacement, false-VERIFIED as first-class, fair B1, preregistered B3,
≥150-question kill threshold, pinned judge protocols) are incorporated above.

## 14. Canonical Demo

```
pip install pincite
pincite ingest ./samples/annual-report/     # 40-page scanned PDF, ~2 min
pincite ask "What was operating margin in Q3?"
```

Output: the answer, the page number, an HTML thumbnail path with the table cell
highlighted, the tier, and the machine-readable JSON. Then:

```
pincite bench ./samples/ --baselines text-rag,visual-rag
```

prints the comparison table: verified-correct rate and accuracy for pincite vs B1
vs B2 on the bundled 50-question sample set — the numbers, not adjectives. The
README shows exactly this session, generated by a script from the locked golden
set, alongside one honest failure case with its taxonomy tag. A developer
understands the problem, the difference, and the measurement in under two minutes,
offline, with no API key.

## 15. Milestones

**M0 — Falsification spike (~3 days).** (a) The verifier's dangerous-assumption
experiment: on 30–50 scanned table pages from BBox-DocVQA/CiteVQA, measure OCR
answer-recoverability (the hard ceiling on VERIFIED coverage), wrong-value
unique-containment rate (the floor on false-VERIFIED exposure), and small-VLM
evidence-quote faithfulness. (b) CPU latency spike on the Intel 16GB reference
box; parser backend and reference VLM chosen; budgets frozen. Completion:
measured numbers exist; preregistered go/no-go thresholds applied (recoverability
roughly below 60–70% or quote-faithfulness collapse = pivot or stop).

**M1 — Vertical slice.** Ingest→retrieve→answer→ground end-to-end CLI on 10+ real
documents, one parser backend, brute-force retrieval; golden set grown to ≥150
questions; measured against B1 with CIs. Completion: runs CPU-only on 16GB;
verified-correct and false-VERIFIED measured; CI-separated win over B1 on the
visually complex subset.

**M2 — Evaluated system.** CiteVQA + ViDoRe V3 + MMLongBench-Doc subset results;
B2 and B3 published; field-extraction deliverable; quantized two-stage index if
latency requires; regression harness; thresholds frozen from M1. Completion: the
full bench table exists and is reproducible from a clean checkout.

**M3 — Serious public repository.** Script-generated canonical demo, docs, tests,
MCP server, PyPI release, contribution path (parser backends and bench tasks as
good first issues). Completion: a stranger reproduces the demo and the bench table
in under 15 minutes.

## 16. Competitive Differentiation

**RAGFlow** (87k stars, Apache-2.0). They do: self-hosted RAG with chunk-level PDF
citations (DeepDoc, page + rectangles) behind a Docker/Elasticsearch stack. We do:
answer-level provenance with deterministic tiers in an embeddable `pip install`
library returning JSON. Why it matters: an agent builder needs a grounded answer as
a function call, not a deployed platform; and a chunk rectangle doesn't tell you
which cell the number came from or whether the citation actually contains the
answer. Evidence: VERIFIED.

**Snappy** (MIT, ~90 stars). They do: ColPali patch-relevance propagated to OCR
boxes — grounding *query relevance*, 59.7% IoU@0.5. We do: ground the *answer*;
Snappy's technique is a candidate component for our ESTIMATED tier, not a
competitor for the job. Evidence: VERIFIED.

**LlamaIndex LiteParse + visual citations.** They do: free local model-free parsing
with per-block bboxes and visually cited answers — for born-digital PDFs, with
cloud LLM answering, substring matching. We do: scanned documents (OCR-based IR),
local answering, normalization-aware unique-containment, an eval harness. Why it
matters: this is the strongest direction-of-travel threat (distribution, momentum)
— tracked in kill criterion 5. Evidence: VERIFIED.

**kotaemon** (25.7k stars). They do: chat UI with fuzzy text-highlight citations
that break with small local models (their open bug). We do: the deterministic
localizer that doesn't depend on the LLM's citation ability — their failure mode is
our design center. Evidence: VERIFIED.

**docling** (64.3k stars). They do: best-in-class parsing with provenance fields
and a visual-grounding *notebook*. We do: consume docling as a backend; the
differentiation is everything after parsing. Watched in kill criteria — they own
the substrate. Evidence: VERIFIED.

**ARIAL** (NeurIPS 2025 workshop). Near-identical published recipe, no code, 27B
model. Feasibility evidence, and proof "first" is not the claim — "shipped, local,
measured" is. Evidence: PARTIALLY VERIFIED.

**anydoc** (firecrawl/anydoc, checked 2026-08-06: created 2026-08-03, 6.9k stars in
three days, Rust, MIT). They do: fast office-format → Markdown conversion — pure
Rust, explicitly no ML models, no OCR (scanned PDFs only via their hosted API), no
QA/retrieval, no bounding boxes or provenance. We do: everything after conversion.
No collision — it lives entirely in the saturated conversion layer pincite declares
a non-goal, and it cannot serve as a parser backend (no spatial metadata). Its
significance is as evidence: the conversion layer is crowded enough that a
well-backed newcomer gets 6.9k stars in three days, and Firecrawl's distribution
power is a live example of kill-criterion-5 risk if they move up the stack.
Evidence: VERIFIED.

Honest overall statement: the attack verdict was DIFFERENTIATION WEAKENED, not
SURVIVES. Nothing ships the full job, and "cell-level provenance for a numeric
answer from a scanned table" survived every search — but the grounding step is
commoditizing and incumbents are circling. The window is real and it is months, not
years.

## 17. Why This Could Grow on GitHub

Concrete adoption mechanics, mapped to the verified growth patterns of the
reference repos: it removes one universal bottleneck with one function call
(markitdown's pattern) — "answers I can show my users, from PDFs I can't upload";
the demo is legible in two minutes offline with no API key; the numbers are
checkable (`pincite bench` reproduces the README table, and CiteVQA/ViDoRe V3 give
it an external leaderboard context); the MCP server rides the agent-ecosystem
narrative (Graphiti's pattern); the parser-backend interface and bench-task format
are natural first contributions; and the privacy-bound verticals that need this
most (legal, finance, healthcare) are exactly the ones that show up in r/LocalLLaMA
threads about being forced local. The honest counterweight, from the verifier: the
author's distribution track record is 0 stars and an unpushed repo — so M3's
definition of done is a public, reproducible artifact, and shipping publicly is
part of the product, not an afterthought.

## 18. Kill Criteria

1. **M0 falsification fires:** OCR answer-recoverability on scanned tables below
   ~60–70%, or small-VLM quote-faithfulness collapses — the verdict law fails on
   the flagship substrate. Pivot or stop before any CORE component is built.
2. **B3 ablation gate fires:** the same VLM with page-navigation tools lands within
   the frozen delta (5pp) of pincite on both ANLS and verified-correct at ≤3×
   median latency — the pipeline adds no value over a bare model.
3. **B1 gate fires:** pincite cannot beat the fair OCR-enabled text-RAG baseline on
   visually complex questions with CI separation at M1.
4. **False-VERIFIED ceiling unholdable:** the preregistered ceiling can't be met
   without collapsing VERIFIED coverage below usefulness.
5. **The window closes:** docling, MinerU, RAGFlow, or LlamaIndex ships
   answer-level grounded local QA before M2 — re-evaluate immediately; the
   differentiation analysis says this is a live, months-scale risk.

## 19. Fresh Verifier Result

### Verdict

`PASS WITH RISKS`

### Objections (five, condensed faithfully)

1. The VERIFIED tier's ground truth is a noisy oracle: OCR errors on scanned
   small-print cells can both collapse VERIFIED coverage and produce correlated
   false-VERIFIEDs; CiteVQA shows the best open model reaches only 22.5
   strict-attributed accuracy, and pincite proposes a 2B-class model with
   unmeasured quote-faithfulness.
2. The Prompire-removal test passes only narrowly: the product survives on
   "scanned + cell-level + local" grounds, not on the verdict language the spec
   emphasized — README framing must lead with pointing, verdict as internal
   mechanics (adopted in section 9).
3. The Intel 16GB CPU budget will *probably* fail — treat a miss as likely, not
   tail risk; llama.cpp server multimodal is still experimental; downscaling pages
   destroys the very cells the demo needs (adopted: M0 spike is the gate, with
   descope paths).
4. Scope is at the outer edge for a solo builder — the eval program is nearly as
   large as the product; M1 as written is ~2× optimistic (adopted: M0 shrunk to a
   falsification spike; golden-set annotation acknowledged as weeks of work).
5. The adoption story runs against the author's track record (Prompire 0 stars,
   Toulmin unpushed) while LiteParse has distribution and momentum; the "months"
   window may be shorter than the M2 timeline (adopted: shipping publicly is part
   of M3's completion condition; kill criterion 5).

### Most Dangerous Assumption

That on scanned documents, the chain "small VLM emits a faithful evidence quote →
fuzzy quote-to-region against noisy OCR → unique answer containment" yields
VERIFIED coverage high enough to be useful *and* a false-VERIFIED rate low enough
to be honest, simultaneously, on CPU. Every differentiator sits downstream of it —
and it is settleable in 2–3 days with the M0 experiment, before any product code.

No FAIL occurred, so no forced revision cycle ran; the spec was nonetheless revised
once (v1 → v2) on ratification evidence before the verifier saw it, which is why
the verifier's objections landed on residual risks rather than design defects.

## 20. Final Recommendation

# BUILD

**First engineering objective:** run the M0 falsification spike — on 30–50 scanned
table pages drawn from BBox-DocVQA/CiteVQA, measure (a) OCR answer-recoverability
at the correct location (the hard ceiling on VERIFIED coverage), (b) wrong-value
unique-containment rate (the floor on false-VERIFIED exposure), and (c) the
candidate 2B VLM's evidence-quote faithfulness, plus end-to-end per-question
latency on the Intel 16GB reference machine — with the go/no-go thresholds
preregistered before the first measurement: answer-recoverability ≥70%,
quote-faithfulness sufficient to ground a majority of correct answers, and a
latency budget a developer would tolerate. If it passes, M1 proceeds on measured
ground; if it fails, the project pivots or stops having spent three days instead of
three months — which is exactly how every good experiment in this repository has
ever ended.
