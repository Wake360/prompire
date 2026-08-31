# TASK CONTEXT COMPILER READY FOR PRODUCT BENCHMARK

## 1. Architecture

```text
request
→ repository context
→ resolver
→ critic
→ resolver revision
→ renderer
→ Codex
```

- `repo_context.py` provides bounded, read-only repository evidence.
- `task_resolver.py` selects evidence and builds the first Task IR.
- `critic.py` attacks the interpretation once.
- The Resolver adopts supported critic findings once.
- `task_renderer.py` produces an advisory prompt capped at 250 words.
- `prompire.py` exposes `compile` and `run --agent codex`.

## 2. Removed complexity

Not carried forward:

- generated probes
- proof obligations
- authority promotion
- verifier coupling
- hard inferred scope
- generated test execution
- oracle or probe runtimes
- contract authority states
- embeddings, indexes, or vector storage
- recursive critique loops

The existing verifier was not modified.

## 3. Task IR

```python
TaskIR(
    objective: str,
    likely_relevant: tuple[str, ...],
    context: tuple[str, ...],
    preserve: tuple[str, ...],
    watch_for: tuple[str, ...],
    checks: tuple[str, ...],
)
```

- `objective`: preserves the original request unchanged.
- `likely_relevant`: gives advisory tracked paths.
- `context`: records repository facts useful before coding.
- `preserve`: identifies behavior likely to regress.
- `watch_for`: captures likely superficial fixes.
- `checks`: points to existing commands or behavioral checks.

Implementation freedom is fixed renderer text, not another IR field.

## 4. Repo retrieval

Available operations:

- tracked-file overview
- file listing with bounded patterns
- fixed-string `git grep`
- bounded file-range reads
- local file history
- staged and unstaged diff inspection

Limits include eight queries, 32,000 total evidence characters, 8,000 characters per result, 200 returned lines, one million scanned characters, and bounded Git output/time.

Git hooks, external diff drivers, text conversions, inherited `GIT_*` redirection, and repository writes are disabled.

The Resolver receives ranked tracked paths first, then requests only task-specific evidence. It does not receive a repository dump.

## 5. Resolver

The Resolver infers:

- useful repository facts
- likely affected paths
- behavior to preserve
- likely failure modes
- useful existing checks

It does not select exact edits, prescribe an implementation plan, restrict edits to predicted paths, or create acceptance code.

Compiler questions are zero by construction. Material ambiguity may still be surfaced by the downstream coding agent.

## 6. Critic

The Critic receives the original request, selected evidence, and Task IR v1.

It asks exactly:

> What is the most likely way a competent coding agent could satisfy this task superficially while still missing the user's intent?

It returns at most three issues. One Resolver revision follows. There is no recursive loop.

Metrics record issues found and adopted.

## 7. Renderer

Example from the real CSV demo, 176 words:

```text
TASK
fix CSV export with quoted newlines

INFERRED REPOSITORY GUIDANCE (ADVISORY)
Treat these as leads, not requirements or edit boundaries.

LIKELY RELEVANT
- csv_export.py
- tests/test_csv_export.py

LIKELY CONTEXT
- `csv.writer` already quotes fields containing embedded newlines, delimiters, or quotes.
- Current preprocessing replaces embedded `\n` with a space, breaking round-trip fidelity.

LIKELY BEHAVIOR TO PRESERVE
- Custom delimiter behavior.
- Record terminator remains `\n`. Embedded `\n`, `\r`, and `\r\n` remain unchanged in field values and non-string values retain existing handling.

POTENTIAL PITFALLS
- Use `csv.writer` quoting semantics; do not manually quote multiline fields.
- Fix export behavior rather than weakening test expectations or changing parser setup.
- Do not confuse embedded quoted newlines with record terminators.

USEFUL CHECKS
- Multiline fields round-trip to the original rows through `csv.reader`.
- Fields combining newlines with quotes or the configured delimiter round-trip unchanged.
- Custom delimiter output remains `a;b\n`.

Inspect or change additional implementation files if needed.
Implementation details are yours. Keep the change focused.
Make reasonable assumptions from repository evidence; ask only if product semantics remain materially ambiguous.
```

Oversized advisory items are dropped whole. The user request is never truncated.

## 8. Security

Confirmed:

```text
no model-authored code executed
compiler read-only
```

Compiler Codex sessions run in empty temporary directories with a read-only sandbox. Shell, browser, computer, image, plugin, app, agent, MCP, and related tool surfaces are disabled.

Generated checks and commands remain text. Only the downstream coding agent receives workspace-write access after compilation succeeds.

## 9. Cost

Three sequential development fixtures ran against the frozen candidate:

| Fixture | Time | Calls | Total tokens | Prompt words | Critic |
|---|---:|---:|---:|---:|---:|
| Cached-token metrics | 37.615s | 4 | 47,171 | 139 | 3/3 |
| Invalid repository read | 59.176s | 4 | 64,069 | 204 | 3/1 |
| Prompt budget | 51.572s | 4 | 66,255 | 205 | 3/3 |
| **Median** | **51.572s** | **4** | **64,069** | **204** | **3/3** |

Cached input tokens were zero. Prompt-token counts are estimates; compiler model usage comes from Codex.

The measured median passes the three-minute target and 90-second stretch target.

## 10. Superpowers boundary

The normal workflow contains:

- no compiler dialogue
- no alternatives workshop
- no section approval
- no design document
- no implementation plan

It is one request, autonomous repository inspection, an internal critique, a compiled prompt, and a coding agent.

The fresh complexity reviewer judged it distinct from brainstorming/design-before-code.

## 11. Tests

```text
PYTHONDONTWRITEBYTECODE=1 python3 tests/run_all.py --quiet
```

Result: 14/14 suites passed:

```text
battery, e2e, examples, golden, docs, hook, encoding,
verify, bench, cli, runner, task_context, package, ci
```

Additional checks:

```text
PYTHONDONTWRITEBYTECODE=1 python3 tests/task_context.py
7/7 task-context cases pass

python3 -m py_compile repo_context.py task_ir.py task_resolver.py \
  critic.py task_renderer.py task_compiler.py prompire.py
pass

git diff --check HEAD^..HEAD
pass
```

Real demo:

```text
prompire run "fix CSV export with quoted newlines" --agent codex
```

The downstream agent changed one implementation file. Independent verification passed:

```text
python3 -m unittest discover -s tests -v
Ran 2 tests
OK
```

## 12. Known weaknesses

- Four sequential model calls consume a median 64,069 tokens.
- One demo compilation timed out at 180 seconds; an identical retry succeeded.
- Retrieval is selected as one batch. It cannot request a second file after discovering an unexpected symbol in initial search output.
- Inferred prose remains probabilistic. Tracked-path filtering removes invented paths, but other incorrect guidance can still appear.
- The compiler has no clarification path. Material ambiguity may reach the coding agent.
- The three-fixture cost sample is not the product benchmark.

## 13. Benchmark readiness

Stable base:

```text
0d23564cb03d2ab711d1870008599d1f971cbb27
```

Frozen candidate:

```text
branch: task-context-compiler
revision: 367d0b608f4fdd0a8481549a29d5003baf940621
```

The abandoned `task-compiler` branch remains at `bb21937` with its historical files and local changes untouched.

RAW and PROMPIRE cells must use the same downstream Codex flags, model, reasoning effort, repository revision, and fresh session.

No RAW-vs-PROMPIRE benchmark has been run yet.

## 14. Claims allowed

- Prompire implements repository-aware task compilation.
- Compilation uses bounded read-only repository operations.
- The original request remains unchanged.
- One critic pass refines the Task IR.
- Rendered prompts are advisory and capped at 250 words.
- `prompire run` can launch Codex with the compiled prompt.
- The development fixtures and CSV demo completed as reported.

## 15. Claims forbidden

Until measured:

```text
Prompire improves agent outcomes
humans specify less
Prompire increases coding-agent success
the Critic improves downstream results
```

## 16. Single next action

Freeze this revision and run the RAW-vs-PROMPIRE product benchmark.
