# Changelog

Versions are `MAJOR.MINOR.PATCH`. Below 1.0.0 the schema is not stable: a brief that
lints clean today can fail on the next minor, and this file is where that is recorded.

## Unreleased

### Added

- `verify --record` appends the verdict to `.prompire/runs.jsonl`: the same
  scope and acceptance objects `--json` prints, under a small envelope
  (timestamp, run id, repo-relative brief path and its sha256, base revision,
  sha256 of `git diff --binary` against that base, exit code). Only a run that
  reached a verdict writes a row; an indeterminate run or a refusal writes
  nothing, and a store that cannot be written warns on stderr without changing
  the verdict. `.prompire/**` is always inside the boundary, so the store never
  trips a later scope check.
- `prompire suite add <run>`: promote a recorded run into a pinned suite fixture, but only when its acceptance fails at the pinned base and passes with the recorded patch — a task already green at base is rejected by name (`green-at-base`). The suite manifest is versioned and content-hashed and declares an explicit never-tuned reserve slice.
- `prompire suite run <candidate>`: replay every admitted fixture from its
  pinned bundle through the bench machinery and print a comparison against a
  stored baseline (`--as-baseline` stores one), sliced by acceptance, scope
  and gamed, with the never-tuned reserve slice as its own block. The output
  is always a diff between two result sets — a run with no baseline is
  refused, and a run never changes the manifest or the reserve membership.
  Deterministic candidates `patch` and `noop` replay for free; `claude`,
  `codex` and `antigravity` replay live.

## 0.12.0 — 2026-08-03

**Compiler v2: the five defects E1 reproduced, closed. No new capability — the
pipeline is harder to fool, harder to mis-deliver, and easier to test fairly. E1's
verdict stands; nothing here claims outcomes until E2 runs.**

### Changed — trust model

- `plan_first` moved into the confirmation-required class. E1's one unmarked field
  determined every delivered execution outcome: all eight compile agents copied
  `plan_first: true` from the skill example, and every headless session stalled at
  "Get the plan approved". A proposal's `plan_first` now comes back marked
  `# prompire:unconfirmed` and listed in the ledger, must be a real boolean (a
  quoted string is refused at the parse, and B8 errors on it in a hand-written
  brief), and the renderer emits the approval stop only for a literal `true`.
  `references/schema.md` documents the execution-mode state machine — `autonomy`
  is who acts, `plan_first` is one extra mid-run stop that requires an operator.
  B10 no longer demands a plan gate at `autonomy: manual`, which never writes.
- B17 also stopped accepting two other carriers that carry nothing. A `hold` whose
  measured evidence is "exit 0, nothing printed" freezes the state of every trivial
  command (`python3 -c "pass"`), so it no longer counts — a `hold` over a known
  *failure* still does. A `flip` with no baseline entry is a claim nobody measured,
  and `verify` asks only whether the command passes now, so an already-green
  criterion declared `flip` was satisfied by an untouched tree; that is now a B15
  error and no longer a discriminator. Both were found by adversarial review as
  compiler-proposable equivalents of the manual_checks escape below.
- B17 stopped accepting a manual check's mere existence as a carrier of done-ness.
  E1's T05 and T08 armed with every criterion green on untouched HEAD because a
  non-empty `manual_checks` silenced the rule — and the compiler writes those lines
  freely. The carrier is now the `done:` spelling (`- done: <text>`), a
  human-only declaration: `draft` rejects any proposal whose manual entries are not
  plain strings, so the classification cannot be proposed and rubber-stamped back
  in. Plain strings remain review notes; `hold`, `before_after` and flip criteria
  are unchanged, so preserve-behavior tasks stay expressible.
- `B5 unknown-requires` is an error, not a warning. Any `requires` entry makes
  `baseline.py` and `verify` refuse to run the command, so an out-of-vocabulary
  value (E1's T07 gold brief shipped a file path there) silently converts the
  criterion into one nothing ever executes.

### Changed — delivery fidelity

- Acceptance commands execute and render verbatim. `run_one` runs the brief's
  exact text instead of the whitespace-normalised display form, and every renderer
  target shows a command as a fenced verbatim block ("the command below") whenever
  its raw text differs from that display form at all — a newline, a doubled space
  inside quotes, a tab, U+2028 — not only when it is multi-line. E1 delivered a
  never-passing criterion in 3 of 7 prompts by flattening, and the measured
  baseline itself ran a different command than the brief declared. `(cmd, cwd)`
  keying stays normalised, so baselines still match their criteria.
  **Migration:** a brief armed before 0.12.0 whose command carries collapsible
  whitespace was measured against the collapsed spelling, so its recorded
  `evidence` (a `before_after` digest especially) describes a different program.
  Re-measure such a brief — `--deactivate`, `baseline.py --write`, `--activate` —
  rather than trusting the old block. Nothing detects this for you: the pointer
  carries no tool version.
- The safety classifier reads the bytes the shell will run. `DESTRUCTIVE`,
  `WRITES_REPO`, `NETWORKY` and the interactive check now scan the raw command
  with line continuations spliced, as the shell splices them, and skip heredoc
  bodies. Verbatim execution had otherwise opened a gap between what was scanned
  and what ran: `r\<newline>m -rf x` normalised to `r\ m -rf x`, matched no
  pattern, and executed as `rm -rf x` during a baseline. Found by adversarial
  review, not by E1.
- The 250-word render budget is checked at compile time. `draft` previews every
  prompt target through `render_brief.preview_counts()` — the renderer itself over
  a provisional baseline synthesized from each criterion's declared transition, so
  there is no second budget arithmetic to drift (pinned by a test) — and reports
  the overrun with per-section word attribution before any confirmation effort is
  spent. E1's eight briefs all discovered the budget at handoff; T06 burned its
  whole confirmation budget without ever producing a prompt. The budget itself is
  unchanged, `prepare` still refuses, and the preview measures and executes
  nothing.
- The INTERACTIVE heuristic matches command position, not substrings. E1's T06
  baseline refused `stubtest more_itertools.more …` as "interactive (`more`)"; a
  pager name is interactive where a shell would execute it (first word of a
  segment, after pipes/`;`/`&&`), not as an argument, module path or quoted text.
  `--interactive`, `--watch`, `git rebase -i` and friends still match anywhere.
  This also closes 2 of E1's 4 GOLD verify false-negatives, which were this same
  false positive reached through `verify_acceptance`.
- `baseline.py` probes workspace consistency for Python. When a command exercises
  a package this checkout itself defines (an explicit `python`/`py` importing it
  via `-c`/`-m`, or `-m pytest`/`-m unittest` in a repo defining packages) and the
  import resolves outside the checkout, the criterion is refused as unclassified
  instead of measured — E1's T05 baseline signed off the system site-packages copy
  of click, which already contained the upstream fix. A workspace copy shadowing
  an installed one, and dependencies the repo does not define, are untouched; a
  bare `pytest` entry point is a documented gap, not a guess.

- A YAML tag whose *constructor* fails is now an unreadable brief, not a verdict.
  PyYAML raises a bare `KeyError` for `!!bool "1"` — not a `YAMLError` — and every
  tool caught only `YAMLError`, so `lint`, `baseline`, `render` and `check_scope`
  died with a traceback and exit **1**, which in this repo is the code for "found
  a finding": a tool that crashed was indistinguishable from one that decided.
  All four now report exit 2, and `draft --proposal` refuses the tag instead of
  crashing with an empty `--json` stdout its caller has to parse. Found by
  adversarial review.

### Verifier

- `check_scope.py` and `verify_acceptance.py` are byte-identical to 0.11.0, but
  they are not behaviourally frozen: both reach changed code through shared
  modules, and one of those changes moves a `check_scope` exit code. Stated
  exactly, the verify path changes in three places. `load_brief` (used by both)
  now reports a brief with an unconstructable tag as unreadable — `check_scope`
  exits 2 where it previously crashed and exited 1, which is strictly the safe
  direction, since 1 is the code for a real finding. The other two are the
  shared-classifier corrections above, which `verify_acceptance` inherits by
  importing `classify`/`run_one`: the
  command-position interactive match (strictly more permissive — a 65-command
  differential fuzz found no command newly refused) and verbatim execution (see
  the migration note above, which is the one direction that can turn a
  previously-clean armed brief red). The new workspace probe is *not* on the
  verify path — it is called only from `baseline.py`'s own main, so no
  previously-passing acceptance cell newly refuses. The scope guard, the pin, the
  digest and every `check_scope.py` verdict are unmoved; 14 armed scenarios diffed
  identical between 0.11.0 and 0.12.0.

## 0.11.0 — 2026-08-03

**The compiler proposes; the human and the deterministic checks establish
authority; the verifier is unchanged.**

### Added

- `prompire draft --proposal <file|->`: any host or skill can feed an
  already-written YAML proposal through the same parser, validation and marker
  serialization as `--agent`/`--agent-cmd`. One compiler gate, three frontends —
  the deterministic heuristic and the model-assisted paths stopped being
  separate products. `SKILL.md` now routes the skill path through it.
- The draft schema covers every proposable field: `tests_editable`, `oracle`,
  `context`, `plan_first` and `rollback` join the whitelist, so `named`/
  `authoring`, refactor and new-file tasks can be compiled instead of being
  structurally lint-red. `baseline`, `base_rev` and `dirty_baseline` remain
  refused as measured, and `autonomy` stays clamped to `ask`. The
  field-by-field authority classes are recorded in `references/schema.md`.
- `draft` prints how many decisions are marked for confirmation and how many
  facts the repository corroborated; `--json` adds the backend and wall time,
  which is the compiler-side instrumentation a future E1 reads.
- Lint `B17 vacuous-acceptance` (error): a measured brief whose every
  criterion already passes on untouched HEAD — no flip, no hold, no
  `before_after`, no `manual_checks`, no behavior-preserving goal — is
  refused, because `verify` would print `clean` on a repo nobody touched.
  Declared preservation shapes pass: the declaration is the acknowledgment.
- Lint `B18 unconfirmed-draft` (error): a `# prompire:unconfirmed` marker, or a
  remaining `unconfirmed:` ledger block, makes lint exit 1 instead of printing
  "brief is shippable" over it.
- The `unconfirmed:` ledger: a draft lists its open decisions as data, not only
  as comments, and `prepare`, `lint` and `--activate` refuse while it stands.
  Adversarial review armed a six-decision draft — a relaxed `tests_policy`
  among them — by running it through one `yaml.safe_load`/`safe_dump`, which
  is all a formatter, `yq -y .`, or an agent asked to tidy the file does.
  Comments are the one part of a YAML file no round-trip preserves.
- `bench/compile.py`: the offline compiler-stage harness — short request in,
  scored contract out, with a logged mechanical blind-confirm and the
  discrimination triple (untouched HEAD / gold write-set / wrong write-set).
  The hidden gold contract never enters the repo the compiler inspects.

### Changed

- Drafting is enforced read-only: after the agent exits the disposable snapshot
  is audited against both its worktree and the commit recorded before the run,
  so a drafting agent that commits its writes away does not hide them either.
  A run that wrote anything is refused with the paths named — surfaced, never
  silently repaired.
- B17 no longer accepts a behavior-preserving word in the `goal` as evidence of
  done-ness. That escape was reachable through the one field a compiler writes
  freely and no marker covers: "fix the off-by-one and rename the helper"
  linted clean and verified clean on an untouched tree. A refactor states its
  evidence like every other task — `hold`, `before_after`, or `manual_checks`.
- Every acceptance sub-key that moves what a criterion decides — `expect`,
  `requires`, `transition`, `before_after`, `cwd`, `timeout` — is named on the
  marked line. `before_after: true` in particular is one of the shapes B17
  accepts, and it previously rode in unmarked and unnamed.
- A `before_after` criterion whose command printed nothing on HEAD no longer
  satisfies B17, and warns: a digest over empty output reproduces whatever the
  agent does. `python -m unittest -q` on a passing suite is exactly that shape.
- `check_scope.py --activate` refuses a brief still carrying draft markers;
  the confirmation gate is no longer one command deep.
- Marker coverage widened to what the model actually decided: `forbidden`,
  `constraints`, `manual_checks`, `tests_editable`, `oracle` and `context`
  come back marked, and an acceptance entry's authority-moving sub-keys
  (`requires`, a claimed `flip` or `hold`) are disclosed on its marked line.
  A proposed `must_flip` is normalized to `transition: flip`.
- `examples/01-green-baseline.yaml` and the demo brief name a manual carrier
  of done-ness, as B17 now demands of every green-only behavioral brief.

## 0.10.0 — 2026-08-03

**The verdict is legible, the modal task reports its evidence, and the package
carries its own documentation.**

### Changed

- `verify` gathers and reports acceptance evidence when the scope check finds
  zero violations, the base has a record outside the brief (`pin` or `repin`),
  and every open flag is one the checker recognizes as evidence-only, instead
  of holding the evidence hostage to REVIEW flags it can never clear. A
  `tests_policy: named` or `authoring` brief with a perfect in-scope run now
  prints its policy REVIEW *and* its acceptance result. Exit semantics are
  unchanged: any REVIEW still fails the strict run with exit 1, a violation
  still blocks acceptance outright, and an uncorroborated base
  (`base_source: null`) still refuses to execute the brief's commands — in that
  state the brief is agent-writable and its commands run through the shell.
- `verify` in human mode leads with one verdict line — `clean`,
  `caught: N violation(s)`, `caught: acceptance did not pass`,
  `review: N flag(s) — needs a human`, or `no verdict: <reason>` — followed by
  the findings and per-command acceptance rows. An unacknowledged `repin`
  prints the exact `prompire verify <brief> --ack-disarms <digest>` command to
  run after reading the tombstone log. `--json` output is byte-identical
  to 0.9.1.
- A `prepare` that fails after measuring the baseline restores the brief's
  bytes, so a lint failure no longer leaves a half-written
  `baseline:`/`base_rev:` block that refuses the corrected retry. The restore
  never runs after a successful activation — `prepare` decides "activation
  committed" by reading the pointer itself, not by trusting an exit code.
- The checker's coverage claim carries its own limit wherever it appears: what
  is seen is every *git-visible* change, and a write under a gitignored path
  never enters the evidence. `references/threat-model.md` gained the
  limitation row, `references/hosts.md` the instruction to run the verifying
  copy from outside the governed workspace, and `check_scope.py --activate` no
  longer claims a refusal only an installed hook can make.
- `draft --agent` and `--agent-cmd` now run the host model inside a disposable git
  repository holding a copy of the checkout's Git-visible files, removed when the agent
  exits. Ignored files, submodules and nested checkouts are not copied, and the
  snapshot's own `git init`/`commit` runs with `--template=`, an empty `core.hooksPath`
  and `--no-verify`, so a global `init.templateDir` or `core.hooksPath` cannot make
  agent drafting impossible on that machine. A `{root}` placeholder in a host's
  invocation names the snapshot, not the caller's checkout.
- A symlink is carried into the snapshot only where its target resolves inside the
  repository, re-aimed there at the snapshot's own copy. Recreated verbatim, a link
  with an absolute or escaping target still aimed out of the snapshot, so an ordinary
  relative write by the agent landed in the source checkout — reproduced, and now
  covered by a `tests/cli.py` case. Where the target resolves decides, not whether it
  exists: a link that would dangle inside the tree is carried, one that would dangle
  outside it is dropped.
- The isolation is bounded and stated as such in `references/threat-model.md`: it holds
  for paths the agent addresses relative to its workspace. An absolute path the agent
  composes for itself, the network, and credentials are all untouched by it.
- `prompire status` takes its brief argument optionally and defaults to `.`, so
  `prompire status` in any repository reports that repository's armed brief.
- Next-step commands printed by `prepare` and `draft` are quoted for the shell they are
  meant to be pasted into (`shlex.join`, or `subprocess.list2cmdline` on Windows), so a
  brief path containing a space stays one argument.
- Every prompt target now closes with "Do not edit the brief or Prompire's state
  files." It was a `copilot`-only sentence, but the pin makes any edit of the brief
  produce *no verdict* and the hook refuses writes to the state files on every host, so
  the three other targets were the inconsistent ones. `tests/golden.py` asserts it.
- The `copilot` prompt no longer tells the agent the hook cannot see shell commands.
  A prompt states what is checked; the hook's blind spots stay documented in
  `references/threat-model.md`, which is written for the operator deciding whether to
  deploy, not for the agent while it runs.

### Added

- `prompire --version`, and a one-line description per subcommand in
  `prompire --help`. Names and semantics are unchanged.
- `[project.urls]` in the package metadata, and the wheel ships `SKILL.md`,
  `references/` and `examples/` under `share/prompire/`, so a pip install
  carries the documentation the README points at.
- Three ablations in `bench/variants.py` — `no_ask_clause`,
  `no_redundant_forbidden` and `durable_dedupe` — each cutting something a coding
  agent's own system prompt already carries, so the matrix can say whether Prompire
  has to spend the words. `durable_dedupe` needs its rules to exist somewhere, so
  `bench/run.py` gained `REPO_FILES`: files a variant installs in the fixture repo
  inside `prepare()`, committed ahead of `baseline.py --write` so they land in
  `base_rev` instead of the diff. Pre-registration:
  `bench/campaigns/2026-08-01-wording-cuts/`. Nothing moves into `render_brief.py`
  until that campaign runs.

### Removed

- The post-run `git status` comparison `draft --agent` used to make, refusing the draft
  when the agent had changed the tree. Announced under 0.9.0 and superseded: it could
  only report a mutation after it had landed in the caller's checkout, whereas the
  snapshot means the write has nowhere to land. Gone with it: the up-front refusal when
  `git status --porcelain` could not answer at all, which used to make agent drafting
  unavailable rather than unsupervised.

## 0.9.1 — 2026-08-01

**First PyPI release; the package ships all three host adapters.**

### Fixed

- `hook_antigravity_guard` was missing from the package's `py-modules`, so a pip
  install of 0.9.0 carried the Claude Code and Copilot adapters but not the
  Antigravity one. `tests/package.py` now asserts every `hook_*.py` adapter in the
  tree is shipped, so leaving the next one out fails the suite.

## 0.9.0 — 2026-08-01

**`prompire draft` can delegate the drafting to a host model.**

### Added

- `prompire draft --agent claude`, `--agent codex`, and `--agent-cmd "<command>"` for
  any other CLI: the drafting prompt goes to the host on stdin, the reply must be a
  YAML mapping and is treated as data — parsed, checked, and re-serialized, so the
  model's own comments never reach the file. `baseline`, `base_rev` and `dirty_baseline` in the reply are
  refused as measured rather than drafted, unknown keys are refused, and `autonomy` is
  always written as `ask`.
- The re-serialized draft keeps the confirmation gate: every scope entry, every
  acceptance command and any `tests_policy` other than `immutable` is marked
  `# prompire:unconfirmed`, and `prepare` refuses until a human deletes each marker.
  Commands the repository evidences keep their evidence in the marker note; the rest
  are labelled agent-proposed. Scope entries matching nothing tracked say so.
- Codex CLI is a documented host in `references/hosts.md`: skill discovery at
  `~/.codex/skills/`, `~/.agents/skills/` and repository `.agents/skills/`, the
  existing `codex` renderer target for the handoff, and no pre-write hook — the
  post-hoc git-diff check is the whole enforcement there. The full lifecycle
  (`draft --agent codex`, `prepare --target codex`, `codex exec`, `verify`, `close`)
  was run live against codex-cli 0.146.0 on 2026-08-01.
- Antigravity CLI (`agy`) is a documented host with a third PreToolUse adapter,
  `hook_antigravity_guard.py`: skill discovery at repository `.agents/skills/` and
  global `~/.gemini/config/skills/`, hooks at `.agents/hooks.json` and
  `~/.gemini/config/hooks.json`, `draft --agent antigravity`. The adapter reads
  `write_to_file`, `replace_file_content` and `multi_replace_file_content` and speaks
  agy's deny-decision JSON; the boundary is the same `hook_policy.verdict_for()` the
  other two adapters call. Failure direction measured against agy 1.1.8 on
  2026-08-01 — crash, non-zero exit, unparseable output and timeout all let the call
  proceed, so the host's native convention already fails open — and the full
  lifecycle (skill discovery, `draft --agent antigravity`, `prepare`, an `agy` run
  under the armed hook with an out-of-scope write refused, `verify`, `close`) was run
  live against the same version.
- `draft` with any agent now snapshots `git status` around the agent run and refuses
  the draft when the tree changed, naming the changed paths: claude drafts under
  write-permission denials and codex under a read-only sandbox, but headless agy has
  no read-only mode, and `--agent-cmd` can name anything.
- `bench/run.py` accepts `codex` and `antigravity` as live agents beside `claude`.
  Each CLI's stats reader is pinned from a live smoke (codex-cli 0.146.0, agy 1.1.9;
  neither reports a model or a cost), one live cell of each ran end-to-end on T01,
  and `bench/report.py` reads liveness per agent — `model` for claude, usage for the
  other two — so a codex row is never marked ERR for a field its CLI cannot report.
  What the cells cannot be stripped of is documented in `references/benchmark.md`:
  codex loads personal skills despite `--ignore-user-config`, and agy cannot shed
  its user-level configuration at all.

## 0.8.0 — 2026-07-30

**The brief now enforces its own scope at write time, and supports live demonstration.**

### Added

- `prompire draft`, which proposes a brief skeleton from repository evidence. It runs a
  deterministic heuristic to find test commands: `package.json` scripts, pytest config,
  Makefile, Cargo.toml, and go.mod are scanned; only commands the repository evidences
  are proposed. Every proposed acceptance criterion and boundary path is marked
  `# prompire:unconfirmed` until manually edited. Documented in README as step 0 of the
  primary workflow.
- `prompire prepare` now refuses (exit 2) any brief carrying an `# prompire:unconfirmed`
  marker, before any baseline, lint, render or arm side effect can run.
- `prompire demo`, which creates a temporary git repository and walks through the full
  workflow: building a brief, running `prepare`, validating an in-scope edit, catching
  an out-of-scope write from the real diff, then cleaning up. An optional `--keep` flag
  preserves the repository for inspection. Documented in README under "What a catch
  looks like".
- `manual_checks` entries now render in all four prompt targets (`claude`, `generic`,
  `codex`, `copilot`) under a `Human review — no command covers these` section, where
  before only `copilot` carried them. The `checklist` target already rendered them, under
  its own `Manual — no command covers these:` heading, and is unchanged. The durable
  targets `agents.md` and `claude.md` still exclude them deliberately — a stale task in a
  repo-durable file is worse than no file.
- `bench/`: behavioural benchmark — task × prompt-variant × agent matrix measured by
  `verify_acceptance` + `check_scope` (`references/benchmark.md`).

### Changed

- A brief's `context` now renders under a Reference context heading, wrapped in
  `<context>…</context>` delimiters. This reorganization treats context as labelled data
  rather than executable instructions, improving readability in prompted renderings.
- README reorganized: the central guarantee and threat model now live in
  `references/threat-model.md`, and the main README leads with value and workflow.
- The GitHub Action `.github/actions/prompire-verify` gained two optional inputs:
  `comment` (whether to post a sticky PR comment with findings; skipped on fork PRs) and
  `artifact-name` (uploads the summary, the JSON verdict, and the brief itself to run
  artifacts). Both are opt-in; the default behavior is unchanged. Brief filenames and
  finding paths are made inert before entering the summary markdown, preventing a
  crafted brief filename from forging action outputs or injecting markdown into the
  sticky comment.

### Limits

- `prompire draft` only proposes standard test-runner configurations. A build system not
  listed (Bazel, SCons, Nix) or a non-standard shell script will not be detected; in
  such cases, the acceptance criteria are left empty and must be filled manually.
- The `context` delimiter change is a rendering change only; the schema and structure of
  the `context` field are unchanged.
- Making filenames and finding paths inert prevents two specific forgeries, and only
  those two: a crafted name cannot open a row, a cell or a comment of its own in the
  summary table, and cannot write a second `key=value` line into `GITHUB_OUTPUT` to
  overwrite the verdict. `tests/ci.py` pins both. It says nothing about how the text
  reads — a filename is still free to be confusing, and the summary reproduces it.

### Clarifications

- `references/grounding.md` now acknowledges that rules B11 and B12 are explicit
  internal inferences rather than requirements traced to external reference.

## 0.7.0 — 2026-07-30

**The verdict now runs where the author of the change is not the one running it.**

### Added

- A composite GitHub Action, `.github/actions/prompire-verify`, which checks a pull
  request's diff against the brief the pull request carries.
- `references/ci.md`, and a `## Continuous integration` section in the README.
- `tests/ci.py`, driving the Action's runner against real repositories.

### Changed

- `.gitignore` tracks `.prompire/*.yaml` and keeps ignoring the guard's state files. A
  brief has to be in the repository for CI to read it.

### Limits

- The Action takes its base from `git merge-base`, so a re-stamped `base_rev` buys
  nothing. It fixes nothing else in a brief written by the same pull request.
- A brief *added* by a pull request draws no finding: `check_scope.py` flags the brief on
  modification, rename and deletion, not on addition.
- It reads the whole difference between the merge-base and the head, so it is correct
  only for a pull request carrying one task.
- Acceptance commands are off by default and refused outright on `pull_request_target`.

## 0.6.0 — 2026-07-29

**Prompire now has a host-neutral, cross-platform command.**

### Added

- `prompire prepare`, which measures, lints, renders, writes artifacts, and arms in that order.
- `prompire verify`, which combines the strict git-diff verdict with post-work acceptance checks.
- `prompire status` and `prompire close`.
- `pipx`, `uv tool`, and `python -m prompire` entry points.
- CLI workflow coverage for macOS, Linux, and Windows.

### Compatibility

- Existing YAML briefs are unchanged.
- Existing Python script entry points remain supported.
- Existing renderer output remains byte-identical.

### Limits

- The CLI does not launch or supervise agents.
- Generic hosts do not receive a pre-write hook. They receive the rendered contract and the post-run git-diff verdict.
- Commands declared unsafe or environment-dependent are reported as `NOT RUN`; Prompire does not execute them automatically.

## 0.5.0 — 2026-07-29

**GitHub Copilot CLI is now a supported agent host, alongside Claude Code.** CLI only —
Copilot's cloud agent loads hooks only from `.github/hooks/*.json` on the default branch,
and nothing in this tree has been run or tested against it; do not configure Prompire for
it on the strength of this release. The brief, the linter, the baseline and the boundary
are unchanged and unaware hosts exist at all — only the hook and the renderer needed to
learn a second protocol.

### Added

- **The hook is split into a host-neutral core and two thin adapters.**
  `hook_policy.py` is the new core: it holds `verdict_for()`, which is the only caller of
  `brief_common.py`'s `boundary_verdict`/`tests_verdict` left in either hook, so the hook
  and `check_scope.py` still cannot disagree about what `scope` means. `hook_scope_guard.py`
  is now a thin Claude Code adapter over that core — its stderr wording and exit codes are
  byte-for-byte unchanged. `hook_copilot_guard.py` is the new Copilot CLI adapter.
- **`hook_copilot_guard.py`**, the Copilot CLI `preToolUse` adapter. It reads `create`,
  `edit`, `str_replace_editor` and `apply_patch`, plus the Claude-compatible `Write`,
  `Edit`, `MultiEdit` and `NotebookEdit` names for a PascalCase entry reusing a
  Claude-format hook. Paths are read from `path`, `file_path` and `notebook_path`; for
  `apply_patch` they come from the patch envelope carried in `input` or `patch`, read for
  every `*** Add File:`, `*** Update File:`, `*** Delete File:` and `*** Move to:` header.
  Both documented payload shapes are accepted — the native camelCase `preToolUse` event
  and the PascalCase VS Code-compatible one — and `toolArgs` is read both as an object and
  as a JSON-encoded string, because both occur in practice.
- **The `copilot` renderer target.** `render_brief.py --target X` now accepts `claude`,
  `generic`, `codex`, `copilot`, `agents.md`, `claude.md` and `checklist`.
- **`references/hosts.md`**, the reference for both hosts: install locations (repo
  `.github/hooks/`, user `~/.copilot/hooks/`, `%USERPROFILE%\.copilot\hooks\`,
  `$COPILOT_HOME/hooks/`, hook config `version: 1`), the failure-semantics table, the
  supported tools and argument shapes, and skill install locations for both hosts.
  `examples/hooks/*.json` holds four validated configs it points at.
- **The failure-semantics difference this forced a second adapter to handle.** Copilot CLI
  is fail-closed on a command `preToolUse` hook: a crash, an exit 2, or any non-zero exit
  is read as a **denial**. Prompire's guard is required to fail open on its own trouble —
  a missing repo, an unreadable brief, a parse error — because it runs on every write in
  every project on the machine, and a guard that denies whenever it has a bug gets
  uninstalled. Claude Code's own convention already matches that requirement, which is why
  `hook_scope_guard.py` needed no rewrite; Copilot CLI's is the exact reverse, so
  `hook_copilot_guard.py` translates explicitly and **never exits non-zero**: a definite
  violation is exit 0 plus one `{"permissionDecision":"deny","permissionDecisionReason":…}`
  object on stdout, and everything else — an in-scope path, no brief armed, an unreadable
  or malformed brief, a payload or patch the adapter cannot interpret, any unexpected
  exception — is exit 0 with empty stdout. Neutral is deliberately **not**
  `permissionDecision: "allow"`: allowing would skip the permission prompt Copilot would
  otherwise show the operator, a real approval bought with the hook's silence for the
  reason that the hook did not understand the question.

  Two things make "never exits non-zero" true rather than merely intended, and both were
  found by reviewing this release rather than by writing it. **The unconditional checks
  run before the import.** `.prompire/ACTIVE`, `.prompire/ACTIVE.tombstones` and a
  NUL-byte path are refused in a first pass inside `verdict_for()` that touches no brief
  and imports nothing; only the brief-dependent half sits below
  `from brief_common import …`. Hoisting that import — which the refactor did, briefly —
  made protection this project documents as unconditional depend on PyYAML being
  installed and importable, so a half-installed venv let a forged-pointer write through
  on both hosts. **A closed stdout is not a denial.** If Copilot stops reading, Python's
  flush at interpreter exit raises `BrokenPipeError`, prints to stderr and exits 120,
  which Copilot reads as a refusal nobody decided on; the adapter now swallows that and
  points fd 1 at the null device so the interpreter's own final flush cannot fail either.
  Both are pinned in `tests/hook.py`.

### Reproduced limitation

- **An `apply_patch` envelope the adapter cannot parse draws no verdict at all.** The
  adapter refuses to guess which files a patch touches from a partial read — a multi-file
  patch whose second file is out of scope would otherwise read as compliant because its
  first file was fine — so an unparseable patch is silently not checked by the hook.
  `check_scope.py` on the resulting git diff is what catches it; this is the same
  "silence over a guess" rule the rest of the guard already follows, reproduced at the one
  new place a host gave it a chance to matter.

### Intentionally unsupported

- **Shell interception.** `bash` and `powershell` are deliberately not matched on either
  host, exactly as `Bash` is not matched on Claude Code. A shell write bypasses the early
  guard entirely; it is caught only by `check_scope.py` on the final git diff, because git
  sees the write whatever tool made it. Inspecting a command line for the files it will
  touch is a much weaker claim than reading a diff, and a guard that made it would be worse
  than one with a stated hole.
- **Copilot cloud agent.** Not implemented, not tested. See the opening paragraph.

## 0.4.0 — 2026-07-28

**The project is renamed: `agent-brief` is now Prompire.** The state directory this tool
writes to and reads its own record from moved with it, `.agent-brief/` →
`.prompire/`. This is a breaking change, and the break is not cosmetic: it is a
security hole, closed in this same release.

### Breaking

- **The state directory renamed, and an upgrade that skips the migration below silently
  degrades a real disarm history into an invisible one.** `any_disarm(root)` — the
  function that decides whether a guard was ever disarmed anywhere in a repo — now reads
  `.agent-brief/ACTIVE.tombstones` (the old address) in addition to
  `.prompire/ACTIVE.tombstones` (the new one). **What a user sees if they upgrade an
  existing repo and do nothing:** the first `check_scope.py --activate` after the
  upgrade reports `repin`, not `pin`, if that repo's old `.agent-brief/
  ACTIVE.tombstones` is non-empty — because the tool now reads it, not because anything
  broke. **That is the safe direction, and it is deliberate**: the alternative — a repo
  with a real past disarm quietly reporting a clean `pin` the moment its state directory
  changed name — is the exact class of bug this project has spent seven review rounds
  closing, a favourable verdict obtained without anyone deciding to grant it, with `git
  pull` standing in for an attacker this time. Nothing on the machine was armed at
  rename time, so this degraded no currently-active guard; it would have degraded the
  *next* arm in every repo carrying pre-rename disarm history, silently, the first time
  each one upgraded.

  **The migration, one command's worth:** append the legacy log's contents to the new
  one, then delete the old file —
  ```
  cat .agent-brief/ACTIVE.tombstones >> .prompire/ACTIVE.tombstones
  rm .agent-brief/ACTIVE.tombstones
  ```
  (create `.prompire/ACTIVE.tombstones` first, empty, if it does not exist yet). After
  that, `any_disarm()` reads one combined log again and `check_scope.py --ack-disarms`
  works exactly as before. **Until it is done, `--ack-disarms` refuses to bind at all**
  — exit 2, on any digest, printing this same two-step fix — because a disarm history
  split across two files is not a set one digest can speak for, and the old behaviour
  (matching the current log alone) would let an acknowledgement quietly not cover the
  legacy half.
- **The PreToolUse hook protects the legacy state-directory pair too.** As soon as
  `.agent-brief/ACTIVE.tombstones` is load-bearing for `any_disarm()`, it inherits the
  `0.3.1` C2 hole — one `Write` empties it — unless the hook refuses that write exactly
  as it refuses one to `.prompire/ACTIVE`/`.prompire/ACTIVE.tombstones`. It now does, at
  any depth, under the same case-folded/NFD/lexical-`..` spellings the current pair
  already withstood; `.agent-brief/active-notes.md` and ordinary files stay writable,
  same narrowness as before.

## 0.3.1 — 2026-07-28

Security fix, no schema change. Both defects were pre-existing and both were found by
the same review that shipped `0.3.0`'s `--ack-disarms` flag; they live in
`hook_scope_guard.py`'s unarmed fail-open, not in that flag.

### Fixed

- **The PreToolUse hook's unarmed fail-open let a bare `Write` forge or erase the
  guard's own state (2 Critical).** `.agent-brief/ACTIVE` and `.agent-brief/
  ACTIVE.tombstones` are the two files that record whether a guard is armed and
  whether it was ever disarmed, and their protection used to be conditional on a brief
  already governing the write — backwards, since "nothing governs here" is exactly the
  state each of them exists to describe. In a repo where no guard had ever been armed,
  one allowed `Write` created a three-line `.agent-brief/ACTIVE` — a brief path, a
  `base_rev` already naming a commit that contained the agent's own work, and a
  matching `sha256` — and `check_scope.py` read it back as a clean `pin`, zero
  findings, `--strict` exit 0, for work nothing had ever governed. The same hole, in
  the unarmed window between two tasks (after an honest `--deactivate`, before the
  next `--activate`), let one `Write` truncate `.agent-brief/ACTIVE.tombstones` to
  empty — erasing the record that a disarm had ever happened and letting the next arm
  read back as a full `pin` instead of a `repin`. Both are now refused unconditionally,
  before any governing brief is even looked for — at any depth, under the same
  case-folding, Unicode-normalisation and lexical `..`-traversal spellings the
  armed-state check already withstood, and whether the write names the pointer/log
  file itself or a path beneath it.
- **`corroborate()` trusted the pointer's own `repin` marker over the tombstone log
  sitting beside it.** A forged `.agent-brief/ACTIVE` naming this brief and its
  current base, with a matching digest but no `repin` line, used to read as a clean
  `pin` even in a repo whose tombstone log recorded a real disarm — the marker lives
  in a file the same kind of `Write` can recreate from scratch. `corroborate()` now
  reads a pin as a `repin` whenever `any_disarm(root)` says a disarm happened anywhere
  in the repo, independent of what the pointer claims about itself.

**Blast radius for a repo that has never armed a guard:** unchanged, with one narrow
exception. A `Write`/`Edit`/`MultiEdit`/`NotebookEdit` targeting a path shaped like
`.agent-brief/ACTIVE` or `.agent-brief/ACTIVE.tombstones` — at any depth, in any
case-folded or Unicode-normalised spelling — is now refused even where no brief has
ever been armed there. Every other write, in every repo the hook has never heard of,
is judged exactly as before: the new check is a string match against the path alone,
no filesystem access, that returns immediately for anything not shaped like the
pointer or its log — no new probing, no new REVIEW, no added cost to the overwhelming
majority of writes on the machine.

## 0.3.0 — 2026-07-28

Additive, no breaking change. `0.2.0` made one legitimate `--deactivate` turn `--strict`
red forever — every later arm reports `repin`, by design, and nothing reversed that. The
cost was that `--strict` stopped being believed on a repo with one honest disarm in its
past, which is the same as it not being run.

### Added

- **`check_scope.py --ack-disarms DIGEST`.** A reviewer's way of saying "I have read
  `.agent-brief/ACTIVE.tombstones` and accept the disarms recorded there" — for the log
  exactly as it reads right now. `DIGEST` is a 12–64 hex-character prefix of the log's
  sha256; the `repin` REVIEW note and the `--deactivate` output both print a ready-made
  one to copy. A matching digest stops the `repin` finding alone from failing `--strict`
  — the finding is still produced, still printed, and its text gains a clause saying it
  was acknowledged; any other REVIEW and any VIOLATION still exit 1 exactly as before.
  The base-source label is still `repin`, never promoted to `pin` — the base is exactly
  as corroborated as it was; only what the tool exits with changes, never what it
  claims. A digest that does not match refuses a verdict outright (exit 2) and prints
  the current one to re-run with. **The one property that makes the flag worth having:**
  one more `--deactivate` changes the log's bytes and therefore the digest, so an old
  acknowledgement stops matching and `--strict` goes red again until a fresh one is
  given for the new log.
- `--json` gains one key, `ack_disarms_bound` (bool) — whether the given digest matched
  the tombstone log on this run. `base`, `base_source`, `violations`, `reviews` and
  `findings` are unchanged in shape and meaning.

## 0.2.0 — 2026-07-28

The release that makes the guard's verdict hard to buy. Before this, `base_rev` was a
field in a file the agent could edit, so an agent that committed its own work and
re-stamped the base handed the checker an empty diff and got a clean verdict for it.

### Breaking

- **`tests_policy` values `additive` and `external` are removed.** The accepted values
  are now `immutable`, `named` and `authoring`. **A brief using either deleted value now
  fails `lint_brief.py` with an unknown-value error.** They were dropped under a
  pre-registered prune rule after none of the three real dogfood runs chose either, and
  after checking the harder question — whether either *could* have expressed one of those
  three tasks — and finding it could not. To migrate: `additive` becomes `named` with the
  test files listed in `tests_editable`, or `authoring` if the task rewrites existing test
  content; `external` becomes `immutable`.
- **`base_rev` is mandatory and must name a fixed commit SHA** (lint rule `B16`, error).
  A brief without one, or naming `HEAD` or a branch, no longer lints. **This bites real
  briefs, not hypothetical ones**: both of the pre-existing briefs on the author's machine
  at release time — written before the rule existed, neither of them a test fixture — now
  fail with `1 error(s) — B16 missing-base-rev`. They are local files and are not in this
  repository, so you cannot inspect them; the point is only that the two briefs that
  existed before this rule both failed it, which is what a real breaking change looks
  like. Expect any brief you wrote against 0.1.0 to need the same one-command fix.

  The rule is right and is not being softened to accommodate them. A brief with no
  `base_rev` names no starting point, so there is nothing to diff against that an agent's
  own commits cannot move: the base would have to be `HEAD`, and an agent that commits its
  work then hands the checker an empty diff, which reads as total compliance without the
  boundary ever having been looked at. Both halves of that hole close in this release —
  `check_scope.py` refuses to produce a verdict at all when there is no usable base (exit
  2, it never falls back to `HEAD`), and `B16` moves the failure to lint time, where it
  costs one command to fix. **The fix is `python3 baseline.py <brief> --write`**, which
  measures the criteria and stamps the real SHA.

  Neither of those two briefs was broken by the `tests_policy` removal above — checked,
  and neither declares a `tests_policy` at all.

### Added

- **`--activate` / `--deactivate`.** `--activate` records the brief path, its declared
  `base_rev` and a sha256 of the whole brief file in `.agent-brief/ACTIVE`, outside the
  brief. While the pointer stands, editing any byte of the brief, or checking a different
  brief, produces no verdict at all (exit 2) instead of a favourable one. An explicit
  `--base` is the deliberate exception: a human choosing the comparison range still gets a
  verdict, labelled `base given on the command line`, with a REVIEW naming both revisions.
  `--deactivate` is the only way out and appends to `.agent-brief/ACTIVE.tombstones`, so a
  pointer written over a disarm reports as `repin` rather than `pin`.
- **A base-source label on every summary line** — `pin`, `repin`, `--base`, or
  `base uncorroborated` — because a verdict is worth what its base is worth.
- **`hook_scope_guard.py`**, a PreToolUse hook that refuses an out-of-scope write before
  it lands. Watches `Write`, `Edit`, `MultiEdit`, `NotebookEdit`; deliberately does not
  watch `Bash`. Fails open on its own trouble. ~75 ms per watched write. Install
  instructions and the full limitation list are in `README.md`.
- **`README.md`, `CHANGELOG.md`, `VERSION`** — first release documentation, including the
  central guarantee and six reproduced limitations.
- `tests/hook.py`, a sixth suite; the six now run from `tests/run_all.py`.

### Fixed

- `scope` and `forbidden` are matched fold-aware, so on a case-folding volume
  `forbidden: [src/golden/**]` is no longer defeated by a diff entry spelled
  `src/GOLDEN/x.txt`.
- A rename out of the test tree is judged as a test-file change instead of escaping the
  policy, under `immutable` and `named` alike.
- The tombstone log is keyed on a disarm having happened rather than on which brief was
  disarmed, so copying a brief to a new name and arming that no longer launders a
  re-stamped base into a full `pin`.
- An unreadable disarm log — a directory planted at its path, a symlink loop — now reads
  as `unreadable` rather than as a clean slate. `Path.exists()` swallows the underlying
  OSError and answers False, which used to hand out the strongest label precisely because
  the record could not be read.
- `baseline.py` writes a `baseline:` block that reads back as what it measured: a `cmd`
  spelling a YAML keyword (`no`, `off`, `null`, `007`) is now quoted instead of re-reading
  as a boolean, None or a number.
- `baseline.py` skips the brief's own directory at any depth, not just at the git root.
  Vendored one directory down, writing a brief used to make its own baseline refuse to
  run as an unclean tree.
- `--deactivate` no longer dies with a traceback when the pointer cannot be removed; it
  reports that the guard is still armed and exits 2.
- The `SKILL.md` workflow now includes `--activate`. Without it the documented path
  produced the weakest state the tool has, and the strongest one was undiscoverable.

## 0.1.0 — 2026-07-26

First working version: the brief schema, `lint_brief.py` with rules `B1`–`B15`,
`baseline.py`, `render_brief.py`, `check_scope.py`, five worked examples, and five test
suites.
