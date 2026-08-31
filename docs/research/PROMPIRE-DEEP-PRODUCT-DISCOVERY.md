# Prompire — Deep Product Discovery, Technical Validation, and Open-Source Strategy

Research snapshot: 2026-08-06

## 1. Executive Decision

DO NOT PIVOT YET.

The best candidate was an evidence-linked compiler that turns technical documents into executable agent procedures. It failed the whitespace test: Anything2Skill, Resource2Skill, SIGIL, OSOP, and Compile, Then Page now cover most of the thesis.

The other candidates scored lower or were already crowded.

Keep Prompire v0.12 as a maintained artifact. Do not make its verification function the future product.

Run five narrow falsification experiments before changing the repository.

```text
BUILD:
Validation prototypes only.

DO NOT BUILD:
Video studio, generic skills framework, generic document-to-agent pipeline,
local multimodal wrapper, memory/KG library, context compiler, synthetic-data pipeline.

CONFIDENCE:
88/100
```

## 2. What I Found in the Knowledge Corpus

### Corpus coverage

FACT — The requested `LifeOS/outputs/book-extractions/` path does not exist. The actual corpus is [LifeOS/outputs/book-extraction](/Users/filipvachek/LifeOS/outputs/book-extraction).

I recursively processed:

- 40 complete `source-text.md` files.
- 44.5 MB of source text.
- 41 concept packs containing 364 structured concepts.
- All 1,220 Markdown files under [LifeOS/wiki](/Users/filipvachek/LifeOS/wiki).
- Concept and term intersections across memory, graphs, retrieval, compilation, multimodality, inference, compression, evaluation, temporal reasoning, and local execution.
- Raw source text for every claim that materially affected the decision.

This was corpus mining, not book-by-book summarization.

### Strongest cross-source connections

| Concept cluster | Foundation | AI application | Prompire implication |
|---|---|---|---|
| Information preservation | Gowers: a homomorphism can preserve some relations while collapsing the original structure. An isomorphism preserves enough structure to reverse the mapping. [Source](/Users/filipvachek/LifeOS/outputs/book-extraction/gowers-princeton-companion/source-text.md:848) | Document conversion that emits plausible prose can still destroy control flow, exceptions, ordering, and provenance. | Any document compiler needs a traceable, structure-preserving IR. Markdown is insufficient. |
| Compression as modeling | MacKay connects compression and modeling. [Source](/Users/filipvachek/LifeOS/outputs/book-extraction/mackay-itila/source-text.md:4180) He also argues that the posterior distribution matters more than a single MAP answer. [Concept](/Users/filipvachek/LifeOS/outputs/book-extraction/mackay-itila/concepts.md:235) | Context selection and extraction should preserve uncertainty, not silently commit to one interpretation. | Extraction candidates should carry evidence and confidence. Uncertain nodes require review or abstention. |
| Schema timing | DDIA: “schemaless” data still has an implicit schema; the choice is whether it is enforced on read or write. [Source](/Users/filipvachek/LifeOS/outputs/book-extraction/ddia-storage/source-text.md:1967) | Raw documents are schema-on-read. Executable procedures need schema-on-write before execution. | Compilation should be a real type boundary, not another prompt. |
| Reproducible derived state | DDIA event sourcing derives materialized views reproducibly from immutable events. [Source](/Users/filipvachek/LifeOS/outputs/book-extraction/ddia-storage/source-text.md:2648) | Procedure artifacts should be reproducible from source versions and compiler versions. | Source hashes, node provenance, incremental rebuilds, and replay logs are first-class data. |
| Judgment versus mechanism | The wiki repeatedly separates human judgment from replayable execution. [Judgment/execution substrate](/Users/filipvachek/LifeOS/wiki/Meta-pattern-judgment-vs-execution-substrate.md:27) | Agents are useful for ambiguous interpretation. They are poor places to repeatedly reconstruct fixed control flow. | Deterministic nodes belong to code. Semantic decisions belong to the model. |
| Rigid versus emergent structure | Low-entropy, known-shape operations benefit from an explicit schema; high-entropy knowledge benefits from emergent structure. [Source](/Users/filipvachek/LifeOS/wiki/Emergent-vs-rigidní-taxonomie.md:17) | SOPs, CLI operations, retries, and preconditions are low entropy. Background knowledge is not. | A hybrid representation is better than forcing everything into a graph or everything into prose. |
| Relations over similarity | The wiki notes that vector search is only one part of retrieval; freshness, permissions, routing, and reranking are harder. [Source](/Users/filipvachek/LifeOS/wiki/Vector-search-neni-retrieval.md:18) | Procedures depend on explicit order and state transitions, not nearest-neighbor similarity. | Vector retrieval can locate evidence. It cannot be the procedure representation. |
| Bounded context | The wiki targets substantial context compression while preserving decision-relevant details. [Source](/Users/filipvachek/LifeOS/wiki/Context-engineering-komprimace.md:17) | Long procedures should page the current frame rather than repeatedly load the whole manual. | This supported a context compiler candidate, but current research already covers it. |
| Generation/checking asymmetry | Gowers’ complexity discussion distinguishes finding a structure from checking one. [Concept](/Users/filipvachek/LifeOS/outputs/book-extraction/gowers-princeton-companion/concepts.md:277) | Prompire’s existing verification succeeded where its generated specifications repeatedly failed. | Existing evidence machinery is reusable. Generated authority is not. |

### Main synthesis

INFERENCE — The corpus points toward this abstraction:

```text
raw technical sources
→ evidence graph
→ typed hybrid procedure IR
→ executable harness
→ replay evidence
```

That was a strong internal product thesis.

It was not a novel external thesis by August 2026.

## 3. Prompire Repository Assessment

### Current state

FACT — Prompire is currently a deterministic contract and verification system for coding-agent work.

The current README defines:

```text
human-authored task brief
→ measured baseline
→ pinned base revision
→ agent work
→ real git diff
→ scope and acceptance verdict
```

The repository has:

- Python 3.11 and one runtime dependency, PyYAML.
- A CLI with drafting, preparation, verification, closing, and demo flows.
- Typed-by-convention YAML contracts.
- Git-diff-based evidence.
- Host hooks.
- 14 test suites.
- Bench campaigns and compiler experiments.
- MIT licensing and PyPI packaging.

The current branch also contains extensive untracked research verdicts. One states that no viable product thesis had yet been found: [product-thesis.md](/Users/filipvachek/prompire/product-thesis.md:15).

FACT — No repository files were modified during the research.

### Verification result

`python3 tests/run_all.py --quiet` produced:

- 11 of 14 suites passing.
- 72 of 73 end-to-end cases passing.
- One end-to-end and one benchmark failure caused by an external `tests` package resolving from `/Users/filipvachek/e4-work/...`.
- Nine documentation-consistency failures involving missing explicit UTF-8 encodings in new compiler test and benchmark files.

This was a dirty-worktree diagnostic, not a clean CI result. See [tests/run_all.py](/Users/filipvachek/prompire/tests/run_all.py:1).

### Component map

| Component | Purpose today | Keep | Refactor | Delete | Reason |
|---|---|---:|---:|---:|---|
| `brief_common.py` | Brief loading, normalization, path and acceptance semantics | Yes | Later | No | Mature deterministic parsing and boundary logic. |
| `baseline.py` | Measure commands before work begins | Yes | Later | No | Useful for replay baselines and procedure tests. |
| `check_scope.py` | Pinned revision and real-diff evidence | Yes | Yes | No | Pinning, hashing, and provenance transfer directly to compiled artifacts. |
| `verify_acceptance.py` | Evaluate executable criteria | Yes | Yes | No | Useful as a procedure replay evaluator. |
| Hook policy and host adapters | Runtime intervention for coding agents | Partial | Yes | Partial | Keep adapter patterns. Remove current product-specific policy surface. |
| `compile_task.py` and `compile_prompts.py` | Experimental generated task compiler | Evidence only | No | From product | The experiments falsified generated authority. Preserve as research history. |
| Benchmark harness | External scoring, preregistration, raw rows | Yes | Yes | No | One of the strongest repository assets. |
| Tests and goldens | Contract and compatibility coverage | Yes | Yes | Partial | Preserve infrastructure. Retire current brief-specific fixtures only after replacement coverage exists. |
| CLI implementation | Current user workflow | Partial | Yes | Partial | Parser and reporting patterns are reusable. Commands and product vocabulary are not. |
| Brief schema | Scope and acceptance contract | Partial | Yes | No | Source hashes, tests, permissions, and evidence can become Procedure IR fields. |
| README and examples | Audit-product positioning | No | No | Yes | They violate the new product constraint if kept as the main surface. |
| CI and packaging | Test, publish, and action workflows | Yes | Yes | No | Preserve working release machinery. |
| Research verdict documents | Experimental evidence | Yes | Archive | No | They prevent repeating failed mechanism shapes. |

### Bottom line

Preserve the engineering substrate.

Retire the current value proposition if a new thesis passes validation.

Do not rewrite working evidence code for style.

## 4. Market Landscape

Snapshot date: 2026-08-06. Star counts are distribution signals, not proof of retained usage.

| Area | Current leaders | Current signal |
|---|---|---|
| Video generation | [MoneyPrinterTurbo](https://github.com/harry0703/MoneyPrinterTurbo): ~101.9k stars. [OpenMontage](https://github.com/calesthio/OpenMontage): ~45.5k. | Strong demo demand. Very low whitespace. OpenMontage already has 12 pipelines, tools, skills, checkpoints, local/cloud providers, and rendering. |
| Agent skills | [Anthropic skills](https://github.com/anthropics/skills): ~166.7k. [Vercel skills](https://github.com/vercel-labs/skills): ~28.2k. | Fast-growing format, but vendors control loading, discovery, and runtime behavior. |
| Document conversion | [MarkItDown](https://github.com/microsoft/markitdown): ~171.9k. [Docling](https://github.com/docling-project/docling): ~64.3k. | Parsing and Markdown conversion are mature, active categories. |
| Document-to-agent | [Paper2Agent](https://github.com/jmiao24/Paper2Agent): ~2.3k. [AutoSkill](https://github.com/ECNU-ICALK/AutoSkill): ~544. [Resource2Skill](https://github.com/microsoft/Resource2Skill): ~369. | Early adoption, but high 2026 research density. |
| Local multimodal runtime | [LocalAI](https://github.com/mudler/LocalAI): ~48.3k. [ComfyUI](https://github.com/Comfy-Org/ComfyUI): ~124.3k. | Unified local APIs and media graphs already exist. Maintenance is dominated by model, driver, and dependency churn. |
| Agent memory | [Mem0](https://github.com/mem0ai/mem0): ~62.7k. [Graphiti](https://github.com/getzep/graphiti): ~29.6k. | Strong incumbents with active releases, large contributor surfaces, temporal memory, provenance, and hybrid retrieval. |
| Synthetic data | [Meta Synthetic Data Kit](https://github.com/meta-llama/synthetic-data-kit): ~1.6k. | It already converts PDFs and videos into text or multimodal QA datasets, curates them, and exports training formats. |

### Five supplied hypotheses

#### A — Agentic multimodal video studio: REJECT

- OpenMontage already covers the more technical version of this idea.
- MoneyPrinterTurbo owns the simple five-second story.
- [VEBench](https://arxiv.org/abs/2605.03276) confirms operational video editing remains hard, but solving it requires research and data beyond a solo orchestration project.
- Provider cost, asset rights, GPU support, and creative evaluation create high maintenance.

#### B — Agent Skills framework: REJECT

- The format is already standardized around `SKILL.md`.
- [SkillsBench](https://arxiv.org/abs/2602.12670) found curated skills improve average pass rate by 16.2 points, but 16 of 84 tasks became worse and self-generated skills provided no average benefit.
- [Skill Usage in the Wild](https://arxiv.org/abs/2604.04323) found gains approach the no-skill baseline under realistic retrieval conditions.
- A new format or registry would be copied or absorbed.

#### C — Document → Agent: REJECT in generic form

- [Anything2Skill](https://arxiv.org/abs/2606.09316) already turns heterogeneous records into evidence-backed skill contracts with lifecycle management.
- [Resource2Skill](https://arxiv.org/abs/2606.29538) already covers tutorial videos, repositories, articles, artifacts, provenance, and multimodal skill composition.
- Paper2Agent already handles code-backed scientific repositories.
- The refined compiler variant remains the best validation target, but not a current GO.

#### D — Local multimodal toolkit: REJECT

- “One API for text, image, audio, and video” already exists.
- LocalAI and ComfyUI have more contributor capacity and much larger integration surfaces.
- Install conformance and VRAM planning are useful features, not a defensible product thesis.

#### E — Agent memory / knowledge graph: REJECT

- Graphiti already provides incremental bi-temporal graphs, episode provenance, custom ontologies, and hybrid retrieval.
- Mem0 owns the simpler memory-layer story and has a large ecosystem.
- A local-first variant would still inherit expensive extraction, graph storage, and benchmark problems.

### Hugging Face capability map

The conditional compiler could use several HF tasks as implementation components:

| Workflow stage | HF task | Candidate model or library | Role |
|---|---|---|---|
| Parse visual documents | Image-Text-to-Text | [Granite Docling 258M](https://huggingface.co/ibm-granite/granite-docling-258M) | Local page structure, tables, formulas, code, layout. |
| Find source evidence | Visual Document Retrieval | [ColPali in Transformers](https://huggingface.co/docs/transformers/main/tasks/visual_document_retrieval) | Retrieve visually relevant pages without discarding layout. |
| Extract grounded values | Document Question Answering | [Transformers task](https://huggingface.co/docs/transformers/en/tasks/document_question_answering) | Resolve parameters, conditions, and exceptions from pages. |
| Process tutorials | Video-Text-to-Text plus ASR | [Transformers video task](https://huggingface.co/docs/transformers/tasks/video_text_to_text) | Extract ordered operations from screen recordings. Not v0.1. |
| Link evidence | Sentence Similarity and Text Ranking | Local embedding and reranker models | Candidate evidence selection only. |
| Emit typed nodes | Text Generation with constrained output | Small local instruct model | Produce schema-constrained extraction candidates. |
| Learn graph policies | Graph ML | Later research | Not justified for v0.1. |

FACT — No Hugging Face screenshot attachments were accessible in the research thread or found in the workspace. Screenshot observations were not invented. The analysis uses the supplied taxonomy and current official HF pages. This reduces confidence slightly.

## 5. Candidate Longlist

| ID | Candidate | What it would do | Verdict |
|---|---|---|---|
| A | Agentic multimodal video studio | Research, script, source assets, edit, render | Kill: incumbents already cover the workflow and demo. |
| B | Agent Skills framework | Package, retrieve, compose, and run skills | Kill: format and host integration are controlled by incumbents. |
| C | Generic document-to-agent | Convert documents into skills or MCP tools | Kill: Anything2Skill, Resource2Skill, AutoSkill, and Paper2Agent. |
| D | Local multimodal toolkit | Unified local inference across modalities | Kill: one API is not differentiation. |
| E | Temporal agent memory graph | Consolidation, forgetting, temporal facts, retrieval | Kill: Mem0 and Graphiti cover most of it. |
| F | Evidence-bound procedure compiler | Compile code-backed docs into typed hybrid procedures | Best validation target. Still NO-GO due direct competition. |
| G | Token-budget context compiler | Build a query-specific context bundle using code, graph, retrieval, and compression signals | Real pain, but crowded and easily absorbed by agent hosts. |
| H | Multimodal evidence graph | Parse documents, images, and video into a provenance-linked graph | Strong representation, weak standalone job-to-be-done. |
| I | Active multimodal dataset compiler | Convert technical corpora into evidence-backed training data with active review | Benchmarkable, but Meta’s kit and data platforms cover much of the workflow. |
| J | Trace-to-program distiller | Infer reusable parameterized state machines from successful agent traces | Research-heavy and directly overlapped by SkillDisCo, SkillSmith, and SIGIL. |

## 6. Scoring Matrix

Scores are 0–10. Totals apply the requested weights.

Abbreviations: problem severity `P`, differentiation `D`, moat `M`, v0.1 feasibility `F`, timing `T`, whitespace `W`, repeat use `R`, benchmarkability `B`, demo `G`, HF leverage `H`, extensibility `E`, local-first `L`, maintenance `S`.

| Candidate | P12 | D15 | M10 | F10 | T8 | W10 | R8 | B7 | G6 | H5 | E4 | L3 | S2 | Total |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| A Video studio | 6 | 4 | 3 | 6 | 8 | 2 | 5 | 4 | 10 | 7 | 7 | 3 | 2 | 51.0 |
| B Skills framework | 6 | 3 | 2 | 8 | 9 | 1 | 5 | 6 | 6 | 2 | 8 | 8 | 7 | 49.7 |
| C Document-to-skill | 7 | 4 | 3 | 6 | 9 | 2 | 7 | 7 | 8 | 8 | 7 | 5 | 6 | 57.4 |
| D Local multimodal toolkit | 7 | 3 | 2 | 3 | 8 | 1 | 8 | 6 | 8 | 10 | 9 | 10 | 1 | 52.5 |
| E Temporal memory/KG | 8 | 4 | 5 | 4 | 8 | 2 | 9 | 6 | 6 | 7 | 7 | 6 | 3 | 56.7 |
| F Procedure compiler | 8 | 6 | 5 | 6 | 9 | 4 | 8 | 9 | 8 | 7 | 8 | 7 | 6 | 68.3 |
| G Context compiler | 8 | 5 | 4 | 7 | 9 | 3 | 9 | 8 | 5 | 5 | 7 | 8 | 6 | 63.0 |
| H Multimodal evidence graph | 7 | 5 | 5 | 5 | 8 | 3 | 8 | 7 | 8 | 9 | 8 | 6 | 4 | 61.7 |
| I Active dataset compiler | 7 | 6 | 5 | 6 | 7 | 3 | 7 | 9 | 7 | 10 | 9 | 6 | 5 | 64.5 |
| J Trace-to-program distiller | 7 | 4 | 4 | 5 | 9 | 2 | 8 | 8 | 8 | 5 | 7 | 8 | 5 | 58.1 |

Notable scores:

- A has the best demo and poor whitespace.
- D has maximum HF and local leverage but unacceptable maintenance.
- E has strong retention and weak competitive whitespace.
- F scores highest because it has a clear primitive and objective benchmark.
- I is highly benchmarkable but is becoming another synthetic-data integration.
- No candidate reaches a reasonable pre-red-team GO threshold of 75.

## 7. Top Three Finalists

### 1. Evidence-bound procedure compiler

```text
Product score: 68.3/100
Confidence in assessment: 93/100
```

Problem: Agents retrieve relevant technical documentation but reconstruct multi-step operations on every run. They skip prerequisites, checks, branches, and recovery actions.

Mechanism:

- Parse documents and repositories.
- Extract source-anchored procedure candidates.
- Bind actions to real CLI, Python, or MCP schemas.
- Represent deterministic actions separately from model-owned judgment.
- Lower the graph into an executable harness.
- Replay cases in a sandbox.
- Recompile affected nodes when sources change.

Engineering difficulty: high but tractable.

Research uncertainty: medium-high. The central unknown is whether extraction from real documents is accurate enough without extensive manual repair.

Requirements:

- CPU works for text and repository sources.
- A small local VLM is optional for visual PDFs.
- No proprietary API is required.
- A useful corpus needs code-backed manuals, source versions, and executable task validators.
- The hardest failure is source incompleteness, not parsing.

Why it nearly won: clear IR, clear user action, strong benchmark, good repository fit.

Why it did not: SIGIL already implements the core typed-IR insight.

### 2. Active multimodal dataset compiler

```text
Product score: 64.5/100
Confidence in assessment: 80/100
```

Problem: Teams can generate large synthetic datasets, but labels are often redundant, ungrounded, and selected by the same models that generated them.

Mechanism:

- Parse multimodal technical sources.
- Generate candidate tasks and labels.
- Preserve page, bounding-box, span, and source hashes.
- Maintain a label distribution rather than a single answer.
- Use disagreement, entropy, and expected information gain to request a small number of human labels.
- Export Hugging Face Datasets and TRL-compatible formats.

Engineering difficulty: medium-high.

Research uncertainty: high. Synthetic-data quality is difficult to establish without downstream model training, which makes iteration expensive.

Requirements:

- Local VLM or LLM.
- Dataset licensing and derivative-use tracking.
- Downstream training and held-out benchmarks.
- Active-learning calibration.

Why it ranked: measurable, local-first, strong HF surface, contributor-friendly.

Why it did not win: [Meta Synthetic Data Kit](https://github.com/meta-llama/synthetic-data-kit) already performs PDF/video ingestion, multimodal QA generation, curation, and export. Cleanlab and annotation platforms cover adjacent quality work. The remaining differentiation is mostly workflow integration.

### 3. Token-budget context compiler

```text
Product score: 63.0/100
Confidence in assessment: 76/100
```

Problem: Coding and research agents waste context on discovery, duplicate evidence, and irrelevant history.

Mechanism:

- Build lexical, structural, dependency, temporal, and semantic indexes.
- Optimize a query-specific evidence bundle under a hard token budget.
- Preserve exact source handles.
- Emit a receipt showing what was included, excluded, and cut by budget.
- Allow recursive expansion.

Engineering difficulty: medium.

Research uncertainty: high. Better retrieval does not reliably produce better end-to-end agent behavior.

Requirements:

- Tree-sitter, LSP, or document structure extraction.
- BM25, graph expansion, reranking, and budget optimization.
- RepoQA/SWE-bench-like evaluation.
- Per-agent and per-model experiments.

Why it ranked: frequent usage, local execution, clear performance metrics.

Why it did not win: recursive context systems, hierarchical memory, learned compressors, and coding-agent context tools already cover the design space. Hosts can absorb the feature.

## 8. Red-Team Results

### Procedure compiler failure case

Strongest failure argument:

- [Anything2Skill](https://arxiv.org/abs/2606.09316) covers heterogeneous source-to-skill compilation.
- [Resource2Skill](https://arxiv.org/abs/2606.29538) covers multimodal source compilation.
- [SIGIL](https://arxiv.org/abs/2607.27309) already introduces AG-IR, node ownership, provenance, and deterministic lowering. It reports 86% mandated-step execution versus 56% for prose, 2.3× more complete procedures, and 0.58× median tokens.
- [Compile, Then Page](https://arxiv.org/abs/2607.11346) compiles SOP constraints and pages active stack frames.
- [OSOP](https://www.osop.ai/docs) already defines executable workflow graphs, logs, replay, diff, and synthesis.
- Anything left—incremental recompilation and code-backed source binding—is a feature set, not yet a category.

Result: no demonstrated moat.

### Active dataset compiler failure case

Strongest failure argument:

- Meta already owns the simple README demo.
- Quality requires downstream training, not a fast unit test.
- Human-review reduction depends on calibrated uncertainty from changing models.
- Generated labels and their evaluator may share the same errors.
- Source licensing becomes a permanent maintenance obligation.
- A weekend prototype can combine Docling, an LLM, Cleanlab, and HF Datasets.

Result: differentiation collapses into integration.

### Context compiler failure case

Strongest failure argument:

- Host agents already inspect repositories dynamically.
- Better evidence recall can fail to improve task success.
- Context policies are model-specific and change with model releases.
- Learned compression research requires training resources beyond a solo project.
- The feature is highly absorbable by Claude Code, Codex, Cursor, or an LSP tool.

Result: no stable distribution boundary.

### Post-red-team scores

| Finalist | Before | After | Confidence |
|---|---:|---:|---:|
| Procedure compiler | 68.3 | 57.9 | 93 |
| Context compiler | 63.0 | 57.1 | 76 |
| Active dataset compiler | 64.5 | 56.0 | 80 |

No finalist survives the 75-point GO threshold.

## 9. Winner

No project won.

The least-bad validation target is:

```text
Prompire Evidence-bound Procedure Compiler
```

It is not approved for full implementation.

### Technical thesis

Problem: Code-backed technical documents contain valuable procedural knowledge, but agents consume them as prose and repeatedly infer the execution structure.

Insight: Such documents mix low-entropy mechanism with high-entropy judgment. Those parts should not share the same execution substrate.

Mechanism: Compile sources into a provenance-carrying Procedure IR containing typed actions, state, conditions, branches, retries, evidence anchors, permissions, and model-owned judgment nodes.

Evidence: SIGIL and Compile, Then Page demonstrate that structured procedures can improve step execution. Prompire’s existing repository demonstrates that external replay and pinned evidence can be implemented cleanly.

Differentiation hypothesis: Source-to-runtime binding, code-backed completeness checks, incremental recompilation, and cross-host replay.

Proof required: Beat Anything2Skill or a curated skill on task success, mandated-step coverage, source precision, repair time, and cross-host portability.

Current conclusion: the mechanism is credible. The differentiation is not.

## 10. Why This Has Whitespace

It does not yet have enough whitespace.

| Competitor | Already covers | Remaining possible gap | Is the gap enough? |
|---|---|---|---|
| Anything2Skill | Documents, logs, trajectories, evidence windows, skill contracts, lifecycle | Real tool binding and deterministic lowering | No proof. |
| Resource2Skill | Videos, repositories, articles, code, visual examples, provenance | Deterministic procedure runtime | SIGIL covers it. |
| SIGIL | Typed AG-IR, model/code ownership, provenance, lowering, execution traces | Multi-source compilation and incremental refresh | Feature-level gap. |
| Compile, Then Page | Compiled SOP programs, stack runtime, active-frame paging | Automatic extraction from raw sources | Anything2Skill covers extraction. |
| OSOP | Workflow IR, execution, logs, diff, replay, optimization | Automatic evidence-backed compilation | Useful, but copyable. |
| Paper2Agent | Repositories and tutorials to tested MCP tools | Portable non-MCP procedure IR | Narrow gap. |
| Agent SOP | Natural-language SOP format and runtime support | Stronger compilation guarantees | SIGIL covers guarantees. |

Why incumbents could absorb it:

- SIGIL can add multi-source ingestion.
- Anything2Skill can add typed lowering.
- OSOP can add document import.
- Docling can add another structured export.
- Agent hosts can add replay or procedure-node enforcement.

This is why the recommendation is NO-GO despite a sound technical mechanism.

## 11. Product Specification

Conditional specification only.

### Name

Prompire

### Tagline

Compile code-backed technical documents into source-linked procedures that agents can execute and replay.

### Category

Procedural knowledge compiler and hybrid agent runtime.

### Target user

Maintainers of scientific, infrastructure, and developer-tool projects whose users must execute multi-step CLI or Python workflows from substantial documentation.

### Job to be done

Turn documentation, examples, tool schemas, and repository evidence into portable procedures that an agent can execute without reconstructing the workflow from prose.

### Pain

- RAG returns passages, not execution structure.
- Skills are interpreted rather than enforced.
- Manuals omit operational details present in examples or source code.
- Fixed steps consume model tokens repeatedly.
- Source changes silently make skills stale.

### Existing alternatives

Anything2Skill, Resource2Skill, Paper2Agent, AutoSkill, SIGIL, OSOP, Agent SOP, custom skills, custom MCP servers, RAG, and handwritten scripts.

### Core insight

A procedure contains two different things:

```text
mechanism: order, state, commands, checks, retries
judgment: interpretation, selection, diagnosis, open-ended authoring
```

Compile mechanism into program structure. Invoke a model only for judgment.

### Core primitive

A typed, provenance-carrying Procedure IR.

Minimal node types:

- `Action`
- `Decision`
- `Guard`
- `Branch`
- `Retry`
- `HumanApproval`
- `Output`
- `SourceAnchor`

### Core workflow

```text
manuals + repository + tool schemas + examples
→ parse and hash sources
→ retrieve evidence
→ extract candidate procedures
→ bind actions to capabilities
→ type-check and resolve gaps
→ lower to executable harness
→ replay test cases
→ emit procedure + source map + evidence
```

### Killer capability

Change one relevant paragraph or tool schema. Prompire identifies the affected executable nodes, marks them stale, recompiles them, and replays only their dependent cases.

HYPOTHESIS — This is the narrowest potentially defensible capability. It is not yet validated.

### Moat

No moat has been demonstrated.

A possible future moat would be:

- A benchmark corpus pairing source versions, procedures, tasks, and executable validators.
- High-precision incremental compilation.
- Cross-host replay data.
- Repair feedback accumulated across real code-backed tools.

### Anti-features

Prompire should not become:

- An agent framework.
- A skills directory.
- A generic MCP generator.
- A document chatbot.
- A model router.
- A provider abstraction.
- A workflow GUI.
- A policy or compliance product.
- A general video/document/media pipeline.
- A system where generated tests establish their own authority.

### Initial wedge

```text
Long-term category:
Procedural knowledge compiler.

Initial wedge:
Code-backed CLI manuals to tested executable procedures.

First user:
Maintainer of an OSS CLI with 50+ documentation pages and repeat support questions.

Pain:
Agents find the correct page but skip prerequisites, ordering, verification, or recovery.

Current workaround:
Handwritten skills, shell scripts, copied documentation, or RAG.

Prompire's mechanism:
Source-linked Procedure IR, tool-schema binding, deterministic lowering, sandbox replay.

Why it is dramatically better:
Only if it measurably improves task success and source-change handling over curated skills.
This has not yet been shown.
```

### 30-second pitch

> Prompire is a source-to-procedure compiler for maintainers of code-backed technical tools.
>
> Unlike RAG or prose skills, it moves fixed control flow into an executable harness and leaves semantic decisions to the model.
>
> Under the hood it uses a provenance-carrying Procedure IR, tool-schema binding, and sandbox replay.
>
> The result is a portable procedure whose behavior can be tested and rebuilt when its sources change.

The pitch is precise. It is also too close to SIGIL to justify building today.

## 12. Technical Architecture

Conditional architecture:

```text
Input layer
  docs, repositories, examples, tool schemas
↓
Source layer
  parsing, page structure, git revisions, content hashes
↓
Evidence layer
  spans, bounding boxes, code symbols, example executions
↓
Procedure IR
  typed nodes, state, ownership, branches, retries, source anchors
↓
Compiler
  capability binding, gap detection, deterministic lowering
↓
Inference
  local model only for extraction and Decision nodes
↓
Runtime
  sandboxed tools, approval gates, resumable execution
↓
Evidence
  node traces, outputs, source versions, replay results
↓
Developer interface
  Python API and CLI
```

### Recommended implementation

- Language: Python 3.11+.
- Schema: Pydantic v2.
- Document parsing: Docling as an optional extra.
- Visual parsing: Granite Docling 258M.
- Retrieval: BM25 first; ColPali optional for visual pages.
- Graph: plain typed adjacency structures. No graph database in v0.1.
- Storage: content-addressed source blobs plus SQLite metadata.
- Serialization: versioned JSON. YAML only for human-authored cases.
- Constrained generation: Transformers with JSON-schema enforcement.
- GPU abstraction: PyTorch device selection through Accelerate.
- Runtime: subprocess and Python-call adapters in isolated fixtures.
- Optional server: none in v0.1. FastAPI only after repeated demand.
- UI: none in v0.1. Generate a static HTML source graph for the demo.
- Cloud models: optional adapters after the local baseline works.
- Tests: unit tests for parsing and lowering, golden IR fixtures, mutation tests for source changes, and end-to-end sandbox tasks.
- Benchmarks: deterministic environment validators. No LLM judge as the primary metric.

### Minimal API

```python
from prompire import compile

procedure = compile(
    sources=["docs/backup.md", "src/backup.py"],
    tools="examples/backup_tools.py",
)

result = procedure.run(
    "Create a backup, verify it, then restore one file.",
    case="cases/restore.yaml",
)

print(result.passed)
print(result.source_trace)
```

```bash
prompire compile docs/ src/backup.py \
  --tools examples/backup_tools.py \
  --output backup.prompire.json

prompire replay backup.prompire.json --cases cases/
```

## 13. Killer Demo

### Scenario

Input:

- A substantial backup-tool manual.
- Its Python or fake CLI implementation.
- A task requiring initialization, backup, integrity verification, snapshot selection, and restore.
- A small local model.
- A sandbox with a deterministic validator.

### Terminal

```text
$ prompire compile docs/ tools.py

12 source files
4 procedure candidates
31 typed nodes
24 code-owned
5 model-owned decisions
2 unresolved source gaps

$ prompire replay backup.prompire.json --cases cases/

raw docs       11/20 tasks passed
prose skill    14/20 tasks passed
prompire       18/20 tasks passed
```

Those values are target presentation only. They must not appear until measured.

### Visualization

A small graph shows:

- Blue nodes: deterministic actions.
- White nodes: model decisions.
- Lines back to exact source spans.
- Red nodes: stale after a documentation change.
- Green nodes: replayed successfully.

### Before/after

Before:

- Agent skips integrity verification.
- It chooses a snapshot before listing available snapshots.
- It reports completion from prose.

After:

- Program structure enforces the fixed sequence.
- The model selects only among valid snapshots.
- Completion comes from the sandbox validator.

### README GIF

A 45-second capture:

1. Compile the manual.
2. Show the graph.
3. Run the local model.
4. Catch a skipped verification in the prose baseline.
5. Complete it with the compiled procedure.
6. Edit one source paragraph.
7. Show affected nodes turning stale and being replayed.

## 14. Benchmark Strategy

### Baselines

- Full documentation in context.
- BM25 or vector RAG.
- Handwritten focused Agent Skill.
- Anything2Skill or AutoSkill output.
- Manually authored OSOP.
- SIGIL configuration if code and licensing permit.
- Prompire Procedure IR.

### Dataset

- 20 code-backed CLI or Python projects.
- 10 executable tasks per project.
- At least two source versions for incremental compilation.
- Hidden parameter and recovery cases.
- Repository-level train/test separation.
- Human-authored source anchors for an evaluation subset.

### Primary metrics

| Metric | What it proves |
|---|---|
| End-to-end task pass rate | The procedure performs useful work. |
| Applicable mandated-step recall | Required steps were executed. |
| Invalid tool-call rate | Capability binding works. |
| Source-anchor precision and recall | Compilation is grounded. |
| Human repair minutes | Automatic extraction saves effort. |
| Cross-host pass rate | Artifact portability. |
| Token use | Program structure reduces repeated interpretation. |
| Incremental impact precision/recall | Source changes invalidate the correct nodes. |
| CPU/GPU latency and memory | Local feasibility. |
| Compile success rate | Setup burden is acceptable. |

### Minimum GO threshold

Prompire must satisfy all of these:

- At least +10 absolute task-success points over the strongest automated baseline.
- At least 95% source-anchor precision.
- At least 90% applicable mandatory-step recall.
- At least 80% unchanged cross-host replay success.
- Median human repair below five minutes per accepted procedure.
- At least 95% recall of nodes affected by source changes.
- No unsafe side effect in the benchmark.
- No primary result dependent on an LLM judge.

Failure on differentiation or human-repair time kills the product.

## 15. MVP

Only after validation passes.

### v0.1

- One core abstraction: Procedure IR.
- One source class: code-backed text/PDF manuals.
- One capability class: Python functions and fake CLI tools.
- One lowering target: local Python harness.
- One exporter: Agent Skill for comparison, not as the runtime.
- One benchmark: 200 executable tasks.
- One killer demo.
- No server, UI, video, memory system, graph database, or provider matrix.

### v0.2

Only if v0.1 users request them:

- Incremental recompilation.
- Real CLI adapters.
- One additional host exporter.
- Visual page retrieval where text extraction fails.
- Human repair workflow based on observed extraction errors.

### v1.0

- Stable versioned IR.
- Reproducible compilation lockfile.
- Cross-host compatibility suite.
- Permissions and approval semantics.
- Source-change impact analysis.
- Public benchmark with external submissions.
- Documented failure modes and supported source classes.

## 16. Migration From Existing Prompire

Do not migrate until the validation gates pass.

### Preserve

- Brief loading and normalization.
- Baseline execution.
- Content hashes and pinned revisions.
- Real external evidence.
- Acceptance evaluation.
- Host adapter patterns.
- Benchmark harness.
- Tests, goldens, and CI.
- Experimental verdict history.

### Rewrite

- Product terminology.
- Main CLI workflow.
- Package description and classifiers.
- README.
- Schema around Procedure IR.
- Runtime from task-verification to procedure execution and replay.

### Remove from the primary product

- Audit and compliance positioning.
- Scope linting as the user-facing value.
- Current coding-agent contract examples.
- Current hook configuration as the hero workflow.
- Generated task-spec compiler.

### Introduce

- Versioned Procedure IR.
- Source anchors.
- Capability schemas.
- Compiler and linker.
- Deterministic lowering.
- Sandbox replay.
- Source-change impact graph.
- New benchmark corpus.

### Compatibility

Backward compatibility is not worth preserving in the new main CLI.

If the pivot passes validation:

- Tag the existing code as `verifier-v0.12`.
- Maintain a `0.12.x` branch for critical fixes.
- Release the compiler as a breaking `1.0.0`.
- Provide no automatic brief-to-procedure migration unless a real use case appears.

### Git history

Keep the current repository and history.

Do not squash the failed experiments away. They explain architectural constraints.

Create the new implementation on a branch after the validation prototype passes. Do not let legacy module layout force the new domain model.

## 17. First 10 GitHub Issues

Do not open these until Experiments 1 and 2 pass.

| # | Goal | Technical scope | Acceptance criteria | Dependencies |
|---:|---|---|---|---|
| 1 | Freeze benchmark specification | Define project selection, tasks, validators, splits, metrics, and kill thresholds | Schema validates; 20 sample tasks run deterministically twice | None |
| 2 | Define Procedure IR v0 | Pydantic models for nodes, state, edges, ownership, anchors, capabilities | Round-trip JSON; invalid graphs rejected; ten golden fixtures pass | 1 |
| 3 | Implement source ingestion | Hash files, preserve revisions, parse Markdown and plain text, emit anchors | Same source produces identical IDs; changed spans get new hashes | 2 |
| 4 | Add Docling adapter | Convert PDFs to structured source blocks with page and bounding-box anchors | Five fixture PDFs reproduce expected blocks and anchors | 3 |
| 5 | Define capability adapters | Introspect Python functions and fake CLI schemas into typed capabilities | Fixture tools expose stable parameter and permission schemas | 2 |
| 6 | Build constrained extractor | Extract candidate nodes and evidence references into IR fragments | At least 95% schema-valid output on frozen fixtures; no unanchored accepted node | 3, 4, 5 |
| 7 | Implement linker and gap detector | Bind candidate actions to capabilities; report ambiguity and missing facts | All benchmark candidates produce bound, ambiguous, or missing states; none silently fall through | 5, 6 |
| 8 | Implement deterministic lowering | Lower Action, Guard, Branch, Retry, and Decision nodes into a Python harness | Golden IR produces expected node trace without model calls for code-owned nodes | 2, 7 |
| 9 | Build sandbox replay and scoring | Run cases, capture traces, enforce permissions, compute primary metrics | Repeated runs produce identical deterministic traces and validator results | 1, 8 |
| 10 | Ship CLI, demo, and benchmark report | `compile`, `inspect`, `replay`; backup demo; baseline comparison | Fresh install runs demo; benchmark command emits raw JSONL and reproducible report | 6–9 |

## 18. Validation Experiments

### Experiment 1 — Source sufficiency

```text
Hypothesis:
Code-backed documentation contains enough information to compile useful procedures.

Method:
Select 20 real procedures across five OSS tools. Give an expert the docs, repository,
and examples. Mark every required execution fact and where it was found.

Metric:
Fraction of required facts available in the source set; repair time for missing facts.

Success threshold:
At least 90% of facts available and median manual completion below five minutes.

Failure threshold:
More than 20% of procedures require undocumented operational knowledge.

Decision if it fails:
Kill the document compiler. Do not compensate with stronger prompting.
```

### Experiment 2 — Extraction and grounding

```text
Hypothesis:
A local model can extract typed procedure nodes with precise source anchors.

Method:
Create 100 manually labeled clauses. Compare Granite Docling plus a small local
instruct model against a cloud reference model.

Metric:
Node precision/recall, anchor precision/recall, schema validity, abstention rate.

Success threshold:
≥95% anchor precision, ≥85% node recall, ≥95% schema-valid output.

Failure threshold:
<90% anchor precision or >20% unsupported accepted nodes.

Decision if it fails:
Kill automatic compilation. A manual DSL is not enough product differentiation.
```

### Experiment 3 — Incremental impact analysis

```text
Hypothesis:
Source provenance permits precise invalidation and partial recompilation.

Method:
Apply 50 controlled document and tool-schema mutations: wording-only, parameter,
precondition, ordering, exception, and deletion changes.

Metric:
Affected-node recall, false invalidation rate, replay selection accuracy.

Success threshold:
≥95% affected-node recall and ≤10% unaffected nodes invalidated.

Failure threshold:
<90% recall or >25% false invalidation.

Decision if it fails:
Drop incremental compilation as differentiation and rescore the product.
```

### Experiment 4 — End-to-end advantage

```text
Hypothesis:
Compiled procedures outperform raw docs, RAG, and focused skills.

Method:
Run 200 sandbox tasks with a fixed local 7B-class model across four arms:
raw docs, RAG, curated skill, Prompire.

Metric:
Task pass rate, mandatory-step recall, invalid tool calls, tokens, latency.

Success threshold:
Prompire beats the strongest baseline by ≥10 absolute pass-rate points,
reaches ≥90% step recall, and uses ≤70% of its tokens.

Failure threshold:
Gain below five points or any increase in unsafe tool calls.

Decision if it fails:
Kill the product. Do not add more integrations.
```

### Experiment 5 — Competitive replication

```text
Hypothesis:
Prompire adds value beyond SIGIL and Anything2Skill rather than reproducing them.

Method:
Reproduce comparable public tasks and add source-version changes and real tool binding.
Use the same models and validators where possible.

Metric:
Task success, source precision, human repair time, incremental rebuild quality.

Success threshold:
Win at least two material dimensions without losing more than two points of task success.

Failure threshold:
Prompire's only improvement is UI, export format, or setup convenience.

Decision if it fails:
NO-GO remains final. Archive the prototype.
```

## 19. README Positioning

Conditional README only.

### Above the fold

```text
# Prompire

Compile code-backed technical documents into source-linked procedures
that agents can execute and replay.

pip install prompire

prompire compile docs/ --tools tools.py
prompire replay procedure.prompire.json --cases cases/
```

Directly below:

- The 45-second measured demo.
- One benchmark sentence containing real numbers.
- A small source-to-node trace.
- “Local by default. No API key required.”
- Explicit support boundary: code-backed technical procedures, not arbitrary documents.

Do not place architecture diagrams, provider logos, feature grids, or future promises above the fold.

### README structure

1. Hero.
2. Killer demo.
3. Why Prompire.
4. Install.
5. 60-second example.
6. What a Procedure IR contains.
7. How compilation works.
8. Benchmark methodology and raw data.
9. Comparison with RAG, Agent Skills, Anything2Skill, and SIGIL.
10. Architecture.
11. Supported sources and tools.
12. Failure modes.
13. Examples.
14. Roadmap.
15. Contributing.
16. License and model-license notes.

Claims such as “reliable,” “portable,” or “local-first” should appear only beside their measured boundary.

## 20. Final GO / NO-GO

```text
DECISION: NO-GO
PROJECT: Prompire Evidence-bound Procedure Compiler — validation target only
CATEGORY: Procedural knowledge compiler and hybrid agent runtime
CORE PRIMITIVE: Typed, provenance-carrying Procedure IR
INITIAL WEDGE: Code-backed CLI manuals to sandbox-tested executable procedures
PRIMARY DIFFERENTIATOR: Incremental source-to-runtime binding and cross-host replay
KILLER DEMO: Compile a backup manual, execute it with a local model, then recompile only stale nodes after a source change
BIGGEST TECHNICAL RISK: Real documents omit or ambiguously express required execution facts
BIGGEST PRODUCT RISK: SIGIL, Anything2Skill, Resource2Skill, and OSOP already cover most of the category
CONFIDENCE: 88/100
```
