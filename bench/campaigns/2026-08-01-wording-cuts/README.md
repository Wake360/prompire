# Campaign 2026-08-01 — host-duplication cuts

Three sentences in the rendered prompt say something a coding agent's own system
prompt already says. This campaign asks whether Prompire has to keep spending
words on them. The prompt has a hard 250-word budget (`render_brief.py`), so a
sentence that buys nothing is a sentence taken from the acceptance criteria.

The comparison the arms come from was made against the published system prompts
of Claude Code (Opus 5, Sonnet 5, Fable 5), Codex (full, 5.6, plan mode) and
GitHub Copilot (CLI, VS Code agent, github). Nothing from those texts is
vendored into this repository, and none of it is grounding: they are the source
of the hypotheses below, and this matrix is the only thing that can accept one.

The same reading found what is **not** under test, and it is worth recording
because it is the stronger result: not one of those nine prompts forbids editing
tests to make them pass. A grep across all of them for modify / delete / weaken /
skip test returns nothing. The closest is Copilot's "run the repository linters,
builds and tests to understand baseline, then after making your changes" — a
procedure, not a prohibition. So `tests_policy`'s sentence and the `hold`
wording are left alone, and `durable_dedupe` is the only arm that touches the
tests sentence at all — by moving it into a durable file, not by deleting it.

## Pre-registration

Written before any cell ran.

Four arms, `current` as the control. Live `claude`, `--repeats 5`.

| variant | what it removes | why it might be free |
|---|---|---|
| `current` | — | control |
| `no_ask_clause` | "Ask before any risky or hard-to-undo step." | Opus 5 carries a near-verbatim equivalent in its harness paragraph; Sonnet 5 has a whole "Executing actions with care" section; Codex has "Destructive Actions". |
| `no_redundant_forbidden` | the `forbidden` bullets no `scope` pattern can reach | `scope` is an allowlist, so `check_scope.py` already refuses them. The bullet restates the boundary rather than adding to it. |
| `durable_dedupe` | `Never touch:`, `Keep true:` and the tests sentence, with AGENTS.md **and** CLAUDE.md installed in the repo carrying them | Codex injects AGENTS.md verbatim into its `USER_INSTRUCTIONS` block; Claude Code injects CLAUDE.md into the system prompt under a header calling the contents overriding. The prompt's copies are strictly weaker duplicates of themselves. |

Tasks: T05 and T06 first — the two the control has taken at 5/5 in two prior
campaigns, so a drop is attributable to the arm rather than to an untested task.
T01 and T02 next if the budget allows.

**Hypothesis: every arm holds the control's solved rate.** Each of these
sentences is claimed to be redundant; redundant text that is removed costs
nothing. Any drop falsifies the redundancy claim for that arm and the cut is
abandoned — not softened, not re-run until it passes.

**One registered counter-prediction.** `no_redundant_forbidden` is expected to
*lose on T05*. T05 names `src/cart.py` in `forbidden` precisely because it is
the trap the task is built around, and `src/cart.py` is disjoint from
`scope: [src/report.py]`, so this arm is exactly what stops naming it. If T05
holds anyway, that is a stronger result than the arm passing quietly — it would
mean the allowlist alone carries the boundary — and it should be replicated
before anyone believes it.

### What this campaign cannot separate

- On every current seed task `constraints` is absent and `tests_policy` is
  `immutable`, so `durable_dedupe` ⊃ `no_redundant_forbidden`: both drop the
  whole `Never touch:` block and `durable_dedupe` additionally moves the tests
  sentence into the durable file. If `durable_dedupe` falls while
  `no_redundant_forbidden` holds, the cause is the tests sentence's *location*.
  If both fall together, the arms cannot tell each other apart on this task set
  and a task carrying `constraints` is needed before reading them separately.
- `durable_dedupe` puts two files in the repo that no other arm has. They are
  committed before `base_rev` (`bench/run.py`'s `prepare()`), so they are
  invisible to the diff — but an agent that *edits* one fails the scope check,
  a failure mode `current` does not have. A `durable_dedupe` row that fails on
  scope must be read against its diff before it is counted against the wording.
- Both hosts' durable files are installed, not just the one the running host
  reads. `render_durable` emits identical rules under either heading
  (`references/rendering.md`), so this removes a filename dependency rather
  than adding a factor — but it does mean the arm is not a measurement of
  either host's pickup behaviour in isolation.
- `no_ask_clause` hands over a brief with `autonomy` dropped, so the enum the
  clause is rendered from does not sit on disk for an agent to read. The half
  of the sentence the arm keeps survives verbatim in the prompt.

## Files

| file | status | contents |
|---|---|---|
| — | not yet run | live cells are a deliberate, costed decision; nothing here has been measured |

## Result

Not yet run. `python3 tests/bench.py` is green with the four arms under
scripted agents (640/640), which is what pins the harness — it is not evidence
about any of the three hypotheses.
