# Rendering targets

`render_brief.py brief.yaml --target <one or more, comma-separated>`. Default:
`generic,checklist` — the prompt for the agent and the checklist for the human. Output
is deterministic, so `tests/golden/` pins every target against every example.

## The wording rules

These hold for every target and are asserted in `tests/golden.py`:

1. **Nothing may authorise a write outside `scope`.** Not "ask before writing outside
   scope", not "confirm first". At `ask`, the autonomy sentence is *"Ask before any step
   that is risky or hard to undo. The listed paths are the whole boundary: widening it
   needs a revised brief, not a yes in chat."* An agent that reads "ask and you may" will
   ask and then do it.
2. **Every criterion carries its state**: green today and must stay green, red today and
   must end green, or frozen exactly as measured. A bare list of commands loses the only
   distinction the reviewer needs.
3. **Prompts stay under 250 words.** Over budget is exit 1, not a warning.
4. **No role-play, no motivation, no restated field.** "You are a senior engineer" buys
   nothing and costs words.
5. **Manual checks appear as manual.** Never mixed into the numbered command list.
6. **Every prompt names the external check.** The agent should know the diff is checked
   from outside by `check_scope.py` after it stops.

## The targets

**`claude` / `generic`** — one prose block: goal, the paths, `Never touch:`,
`Keep true:`, the numbered criteria with their state, the tests sentence, the autonomy
sentence, the external-check sentence, then `context` if present. `claude` names the
brief file in the external-check sentence; `generic` says "the brief". That is the only
difference between them.

**`codex`** — the same content as markdown sections: `## Task`, `## Files you may edit`,
`## Never touch`, `## Keep true`, `## Verify`. Forbidden paths and constraints stay in
separate sections: a path you must not touch and an invariant you must preserve are
different instructions.

**`agents.md`** and **`claude.md`** — the durable half only: `## Never touch`,
`## Keep true`, `## Tests`, `## Verify`. No goal, no scope, no autonomy, no baseline,
because those describe a task that will be finished next week, and a stale task in a
repo-durable file is worse than no file. A `hold` criterion is left out of `## Verify`
too — "reproduce this exact failure" is true of one commit, not of the repo.
`agents.md` renders an H1; `claude.md` renders an HTML comment marker so the block can
be appended to an existing `CLAUDE.md`. They are otherwise identical by design.

**`checklist`** — for the human, after the agent stops. First box is always
`check_scope.py`, rendered whether or not the brief mentions it, because it is the one
check that does not depend on the agent's cooperation. Then one box per criterion with
the long form of its state and its baseline evidence, then `manual_checks`, then — when
the tests policy lets test files move — a box telling the reader to read the test diff
themselves. It closes with: *if any box is unchecked, the task is not done regardless of
what the agent reported.*

The checklist has to be enough to verify completion without re-reading the diff. That is
why each box carries the evidence string and not just the command.
