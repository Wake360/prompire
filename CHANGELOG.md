# Changelog

Versions are `MAJOR.MINOR.PATCH`. Below 1.0.0 the schema is not stable: a brief that
lints clean today can fail on the next minor, and this file is where that is recorded.

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
