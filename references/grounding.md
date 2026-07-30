# Grounding — where each lint rule comes from

Every rule in `lint_brief.py` traces to a passage in a book extracted under
`~/LifeOS/outputs/book-extraction/`, or is recorded below as an explicit internal
inference (B11, B12). If a rule cannot be traced either way, delete the rule.

Sources:
- **AIE** — Chip Huyen, *AI Engineering* (O'Reilly 2025) → `ai-engineering/source-text.md`
- **BAA** — Michael Albada, *Building Applications with AI Agents* (O'Reilly 2025) → `building-ai-agents/`
- **GDP** — Lakshmanan & Hapke, *Generative AI Design Patterns* (O'Reilly 2025) → `genai-design-patterns/`
- **AM** — Broda & Broda, *Agentic Mesh* (O'Reilly 2026) → `agentic-mesh/`
- **TAP** — Brian Christian, *The Alignment Problem* (Norton 2020) → `alignment-problem/`

---

## goal-and-constraints — the whole minimal core (B1, B2)

AIE ch. 6, "Planning":

> A task is defined by its goal and constraints. For example, one task is to schedule a
> two-week trip from San Francisco to India with a budget of $5,000. The goal is the
> two-week trip. The constraint is the budget.

This is why the brief has exactly two mandatory narrative fields, `goal` and `constraints`,
and why `goal` is capped at one sentence. Everything else in the format is a guardrail, not
a restatement of intent. A brief that needs three paragraphs of goal has more than one task
in it.

## unambiguous-instructions (B3, B5b)

AIE ch. 5, "Write Clear and Explicit Instructions":

> Explain, without ambiguity, what you want the model to do. If you want the model to score
> an essay, explain the score system you want to use. Is it from 1 to 5 or 1 to 10? […] if
> the model outputs fractional scores (4.5) and you don't want fractional scores, update
> your prompt to tell the model to output only integer scores.

And, same section, on output shape:

> If you want the model to be concise, tell it so. […] If the model tends to begin its
> response with preambles such as "Based on the content of this essay, I'd give it a score
> of…", make explicit that you don't want preambles.

Also the basis for the parts of an acceptance entry that are not the command itself
(2026-07-27). "Run the tests" is the 1-to-5-or-1-to-10 failure at the level of execution:
from which directory, with what allowed to be missing, for how long before it counts as
hung. `cwd`, `timeout` and `requires` state those, so a criterion means the same thing to
the person who wrote it, the tool that measures it and the agent that has to satisfy it.
Two entries that normalise to the same `(cmd, cwd)` are rejected for the same reason —
the baseline cannot say which one it measured.

Basis for the vague-language blacklist. "Refactor this properly" is the 1-to-5-or-1-to-10
failure: the word carries no decision. In a `goal` or an acceptance criterion it is an
error; in `constraints` or `notes` it is only a warning, because there it is commentary
rather than the thing being checked.

## acceptance-criteria-before-work (B4)

AIE ch. 4, "Evaluation-Driven Development":

> Before investing time, money, and resources into building an application, it's important
> to understand how this application will be evaluated. I call this approach
> evaluation-driven development. The name is inspired by test-driven development in software
> engineering, which refers to the method of writing tests before writing code. In AI
> engineering, evaluation-driven development means defining evaluation criteria before
> building.

And the diagnosis that makes it urgent:

> I believe that evaluation is the biggest bottleneck to AI adoption.

Basis for: a brief with no acceptance block is not a brief. Refusing to emit one is the
single most valuable thing this skill does.

## criteria must be executable, not prose (B5)

GDP, Pattern 16 (Evol-Instruct) and Pattern 18 (Reflection):

> This approach works well whenever you have an automated evaluator, such as for coding and
> math problems. For coding problems, you could use a compiler to verify that the code
> compiles and a sandbox to run the code and verify that the output meets the desired
> constraints. For example, if the instruction is to write code to sort some data, you can
> verify that the output is sorted.

> The relative cost of doing one more round of reflection compared to the cost of a broken
> build is often significant enough that such systems involve multiple stages of reflection.

Coding work is the lucky case: the evaluator already exists and it is the toolchain. So
each acceptance entry is `cmd` + `expect`, never a sentence. "The tests pass" is a wish;
`pytest -q tests/test_invoices.py` → `exit 0` is a check.

## a score means nothing without the baseline (B15)

AIE ch. 4, on multiple-choice evaluation (`ai-engineering/source-text.md` L5924):

> MCQs are popular because they are easy to create, verify, and evaluate against the random
> baseline. If each question has four options and only one correct option, the random
> baseline accuracy would be 25%. Scores above 25% typically, though not always, mean that
> the model is doing better than random.

Same chapter as the evaluation-driven-development quote above, and the missing half of it.
B4 forces the brief to name a criterion; B15 forces the brief to know what that criterion
said *before* the work. `pytest -q → exit 0` carries no information if the suite was already
red — the agent cannot reach it, and a reviewer cannot tell "the agent broke this" from "this
was broken on arrival". Declaring `must_flip: true` is the legitimate case: the criterion is
red now and turning it green *is* the goal, which is the coding equivalent of a
red-then-green test.

AIE ch. 6 repeats the move for agents specifically:

> You can compare these metrics with your baseline, which can be another agent or a human
> operator.

This rule was added 2026-07-26 after the first real brief (`verbal-beat-gate`) shipped a
whole-suite `pytest tests/python -q → exit 0` criterion that had 6 pre-existing failures. The
lint passed 0/0; the criterion was unreachable from the moment it was written.

**The three transitions and `not_runnable` (2026-07-27).** The random-baseline passage
sets up a comparison, not a single number: a score is read *against* what the measure
said before. Three things a criterion can be doing, and the brief has to say which:
meeting its expect and keeping it (`green`), not meeting it yet on purpose (`flip`), or
meeting it in a way that must be reproduced exactly rather than improved (`hold`). The
fourth case is the honest one — the command could not be run at all, so there is no
baseline to compare against. `not_runnable` plus a reason records the absence instead of
filling it in. Nothing in the passage licenses inventing the missing number, which is
the whole point: 25% is known because it was derived, not assumed.

## proxy criteria get gamed (B7) — the Goodhart rule

TAP ch. 5, on reward shaping, Andre and Teller's RoboCup entry *Darwin United*:

> In soccer, possession of the ball is part of what good offense and good defense looks
> like […] And so Andre and Teller provided a reward—worth a tiny fraction of a goal—to
> their robot for taking possession of the ball. To their astonishment, they found their
> program "vibrating" next to the ball, racking up these points, and doing little else.

And Ng, quoted in the same chapter:

> a difficulty with reward shaping is that by modifying the reward function, it is changing
> the original problem M to some new problem M′ […] it is not always clear that
> solutions/policies found for the modified problem M′ will also be good for the original
> problem M.

Direct translation to coding agents: "make the suite green" is a proxy for "make the code
correct", and an agent that may edit tests will vibrate next to the ball — weaken the
assertion, add a skip, delete the case. So whenever an acceptance command runs a test
suite, the brief must also pin the tests (put them in `forbidden`, or add an acceptance
command asserting the test files are unchanged). This rule is the reason to read the books
at all; no amount of prompt-formatting advice produces it.

**The three arrangements (2026-07-27; five arrangements pruned to three on 2026-07-28 —
see below).** A flat "tests are frozen" cannot express a task whose *purpose* is to add
or repair tests, and briefs that need one were writing the pin out entirely — which is
the failure the rule exists to stop. Ng's objection is the guide: modifying the reward
changes problem M into M′, and a solution to M′ need not be a solution to M. Each of
`immutable`, `named` and `authoring` is a different answer to *how far the agent may
move the measure*, from not at all to freely — and the further it may move, the more
the brief must name something outside the agent's reach that still measures M. That is
what `oracle` is, and why `authoring` cannot be declared without one. `check_scope.py`
enforces the arrangement against the real diff rather than trusting a criterion the
agent could have written itself; the enforcement tooling is engineering, not a book
claim.

`additive` and `external` were dropped by the pre-registered prune rule R1
(`outputs/plans/agent-brief-dogfood-log.md`, "Rule application" section): across the
three real dogfood briefs, neither was chosen, and neither could have expressed any of
the three real tasks — the two tasks with no test edits at all were already exactly
`immutable`, and the one task that did edit tests (the hook build) deleted and rewired
existing assertions, which `additive` structurally forbids and `external` forbids more
broadly still. Losing a policy that fits no observed task is the intended shape of R1,
not a shortfall — the rule was written to prune exactly this.

## autonomy is a declared level, not a vibe (B8)

BAA ch. 3, "The Autonomy Slider":

> As Andrej Karpathy described, effective agentic systems should allow users to smoothly
> adjust an agent's autonomy—from fully manual control to partial automation to fully
> autonomous operation. […] Label these modes in intuitive language, such as "Manual,"
> "Assist," and "Auto," and explain their implications.

> Provide predictable and transparent behavior at each level. Each autonomy level should
> have well-defined behaviors. In partial automation, for example, the agent may draft an
> output but require explicit user approval before execution.

AIE ch. 6 makes the same point per-action:

> If a plan involves risky operations, such as updating a database or merging a code change,
> the system can ask for explicit human approval before executing […] To make this possible,
> you need to clearly define the level of automation an agent can have for each action.

Basis for `autonomy: manual | ask | auto` being mandatory and closed-vocabulary, and for
requiring `rollback` before `auto`.

## least privilege over the file tree (B6, B9, B13, B16)

BAA, tools chapter:

> give the model only the tools it strictly requires, and guard every operation with precise
> boundaries and oversight. Whether your tool runs locally, calls an external API, or
> executes on an MCP server, the same safeguards apply—restrict capabilities, sanitize
> inputs, enforce least privilege, and maintain full observability.

Basis for `scope` being required and refusing `.` — an unbounded scope is the file-tree
equivalent of handing over every tool. Also the basis for gating destructive verbs
(`rm -rf`, `DROP TABLE`, `push --force`, `deploy`, `terraform apply`) behind `manual`/`ask`.

"Enforce least privilege, and maintain full observability" is two requirements, and the
brief only ever satisfied the first: it *declared* a boundary and nothing observed whether
the boundary held. `check_scope.py` (2026-07-27) is the second half — it reads the real
diff against `scope`, `forbidden` and `tests_policy` after the agent stops, needs nothing
from the agent, and treats a widened scope as an edit to the brief rather than something
that can be conceded in conversation. The same passage is why `baseline.py` refuses to
execute a destructive, interactive or repo-writing command in order to measure it.

**"Maintain full observability" has a second half, and `base_rev` is it (B16,
2026-07-27).** `check_scope.py` observes the boundary by diffing the real change against
`base_rev`; without one it defaults to `HEAD`. An agent that commits its own work before
the guard runs moves `HEAD` along with it, so the diff against `HEAD` comes back empty —
the guard exits 0 and reports the boundary held, having observed nothing. A declared
scope that nothing checks is the exact gap the passage warns against, just moved from the
tool layer to the check that is supposed to catch tool misuse. `baseline.py` stamps
`base_rev` into every `baseline:` block it writes, so a brief produced the documented way
never lacks it.

**A ref that can move is the same gap wearing a value (2026-07-27, round 2).** The first
cut of B16 only checked that `base_rev` was present and shaped like something git could
resolve — `\w./-]+` matched `HEAD` and any branch name as readily as a commit SHA. Both
are observability in name only: `HEAD` names whatever commit is checked out *when
`check_scope.py` runs*, which is precisely the value an agent moves by committing.
"Maintain full observability" means observing the state before the work, not a pointer
that tracks the work. B16 now requires the one string shape that cannot move once
written — a 7-to-40-character hex SHA — and `check_scope.py` itself was tightened to
match: with neither `--base` nor a `base_rev` of that shape, it refuses to produce a
verdict at all rather than falling back to `HEAD` silently, because a brief that never
passes through `lint_brief.py` would otherwise hit the exact default the first cut of
B16 was meant to close. An explicit `--base` is left alone regardless of shape — that is
a human choosing a comparison on purpose, not the tool choosing one for them.

## plan before execution when the task is big (B10)

AIE ch. 6, "Planning overview":

> You can couple planning with execution in the same prompt. […] But what if the model comes
> up with a 1,000-step plan that doesn't even accomplish the goal? Without oversight, an
> agent can run those steps for hours, wasting time and money on API calls, before you
> realize that it's not going anywhere. To avoid fruitless execution, planning should be
> decoupled from execution.

Plus AIE ch. 5, "Break Complex Tasks into Simpler Subtasks", and the anecdote that makes it
concrete:

> the accuracy jumped to 70% after I decomposed the task into two steps.

Basis for forcing `plan_first: true` on refactor/migrate/rewrite-shaped goals and on scopes
wider than a few paths.

## errors amplify across steps, so verify intermediates (B14)

AM ch. 2, on multi-step failure:

> Consistency and reliability may erode unless workflow designers establish robust checks,
> fail-safes, and monitoring at each stage of processing. This can include human-in-the-loop
> checkpoints, automated anomaly detection tools, or gates that verify intermediate outputs
> before proceeding to the next step.

Basis for warning when a behavior-preserving task (refactor, port, upgrade) has no
before/after comparison in its acceptance block — a golden file, a snapshot, a diff. Green
tests alone do not show behavior held; they show the tests that exist still pass.

## rules with no book source (B11, B12)

Two enforced rules are not book-traced, and saying so here is the point of this file —
an untraced rule that nobody has written down is how the apparatus grows back.

**B11 — contradictions.** The closest thing to a source is the AIE ch. 6 passage at the
top: a task is its goal plus its constraints. Constraints that cannot all hold at once
therefore define no task, and neither does a `forbidden` pattern that covers the whole
`scope`. That is an inference from the definition, not a passage about contradiction
detection, and it is recorded as an inference. The rule stays because every case it fires
on is a brief that cannot be satisfied as written — it costs nothing and it caught a real
one (a goal that renames while a constraint freezes the public API).

**B12 — unknown keys.** No book source and none is claimed. It is schema hygiene: a
misspelled key is silently dropped by the renderer, so a warning is worth more than the
line it costs. It is a warning and never an error, precisely because there is nothing
behind it but experience with typos.

## deliberately not encoded

Personas (AIE ch. 5, "Ask the model to adopt a persona") and few-shot examples are real
techniques, but they belong to prompting a model for open-ended generation, not to bounding
a coding task. Adding them here would grow the brief without adding a check. Nothing in the
extracted corpus covers requirements engineering or instruction-file syntax; those parts of
the format come from `~/LifeOS/wiki/AGENTS-md-jako-viditelne-instrukce.md`,
`AI-architect-english-as-spec.md`, and `Brief-feedback-loop-mutace-CLAUDE-md.md`, not from
books.
