# Brief schema — the authoritative field list

One definition per field, here. `SKILL.md` shows the shape; this file decides what it
means. The implementation is `brief_common.py`; if the two disagree, that is a bug.

Unknown keys are a warning, not an error: the renderer drops them.

## Top level

| field | required | type | meaning |
|---|---|---|---|
| `goal` | yes | string | one imperative sentence, ≤30 words, one task |
| `scope` | yes | list of paths/globs | the **allowlist**: what the agent may create, edit or delete |
| `forbidden` | no | list of paths/globs | the **denylist**; wins over `scope`. `[]` = considered, nothing off limits |
| `constraints` | no | list of strings | what must stay true; observable, not adjectival |
| `acceptance` | yes | list of entries | the criteria (below) |
| `baseline` | in practice | list of entries | what each criterion said on HEAD (below) |
| `autonomy` | yes | `manual`\|`ask`\|`auto` | `auto` also requires `rollback` |
| `plan_first` | no | bool (a real boolean; B8 rejects a quoted string) | one extra stop inside a writing run: plan, get it approved, then edit. Requires an operator present mid-run — see *Execution modes* below. A compiled draft marks it for confirmation |
| `rollback` | if `auto` | string | the branch or worktree that makes this undoable |
| `manual_checks` | no | list of strings, or `- done: <text>` mappings | what only a human can confirm. A plain string is a review note. The `done:` spelling is the human's declaration that this judgment is the task's completion condition — the only manual shape B17 accepts as carrying done-ness, and one a compiler proposal may not contain |
| `tests_policy` | see B7 | enum | `immutable`\|`named`\|`authoring` |
| `tests_editable` | if `named`/`authoring` | list of globs | the only test paths that may change |
| `oracle` | if `authoring` | string | what judges the work when the local suite cannot |
| `dirty_baseline` | no | list of paths | files already modified before the agent started; the guard ignores them |
| `base_rev` | yes | 7–40 char hex commit SHA | the commit HEAD pointed at when the baseline was measured; `check_scope.py` diffs against it. A branch name or `HEAD` is rejected — it names wherever the ref points when the check runs, not where the work started, which an agent defeats by committing (B16). Missing or non-SHA also makes `check_scope.py` itself refuse to run without an explicit `--base` |
| `notes`, `context` | no | string | facts the agent cannot discover cheaply |

Paths are repo-relative. An absolute path or one containing `..` is an error — it moves
the boundary the guard is supposed to enforce.

## What a compiler may propose

Every compiler frontend — the deterministic heuristic, `draft --agent`/`--agent-cmd`,
and `draft --proposal` — flows through one parser and one serializer in `prompire.py`.
Field by field, the authority classes are:

| class | fields | what enforces it |
|---|---|---|
| propose, human confirms | `scope`, `forbidden`, `constraints`, `tests_policy` (≠ immutable), `tests_editable`, `oracle`, `acceptance` entries — with every sub-key that moves what the criterion decides (`expect`, `requires`, `transition`, `before_after`, `cwd`, `timeout`) named on the marked line — `manual_checks`, `context`, `plan_first` | serialized with `# prompire:unconfirmed` *and* listed in the `unconfirmed:` ledger; `prepare`, `lint` (B18) and `--activate` all refuse while either remains. `plan_first` moved into this class after E1: the one unmarked field determined every delivered execution outcome — a plan gate stops an unattended run, so it is the human's decision, never furniture copied from an example. A proposal's `plan_first` must be a real boolean; a truthy string is refused at the parse |
| propose, no marker | `goal` (rewritten into the draft for editing), `rollback` (inert below `autonomy: auto`) | the linter's ordinary rules. `goal` buys nothing on its own: B17 stopped accepting a behavior-preserving word there as evidence of done-ness precisely because no marker covers this field |
| clamped | `autonomy` | a draft always says `ask`; raising it is a human edit to the confirmed brief |
| measured, never proposed | `baseline`, `base_rev`, `dirty_baseline` | a proposal carrying one is rejected outright — these are written by `baseline.py` and read against the pin |
| human-only, never proposed | the `done:` spelling of a `manual_checks` entry | a proposal carrying one is rejected outright — declaring that a human judgment is what decides done is the human's own act, not a line to confirm (B17) |

## Execution modes — plan_first and autonomy

Two fields describe how a run proceeds, and they answer different questions.

`autonomy` is who acts: `manual` — the agent proposes and never writes (the plan *is*
the deliverable, reviewed between runs); `ask` — the agent confirms risky steps with an
operator who is present; `auto` — the agent runs unattended on `rollback`.

`plan_first: true` is one extra stop inside a writing run: produce the plan, get it
approved, then edit. It requires an operator mid-run by definition. That is why a
compiled draft marks it for confirmation: delegated work is often fire-and-forget, and
a session with nobody there to approve stalls at the gate and delivers nothing — E1
measured exactly that, eight tasks out of eight. Keep it only for an attended run;
delete it for unattended delegation and let the confirmed contract be the control.
The renderer emits the approval stop only for a literal boolean `true` (B8 rejects
anything else), and a brief without the field renders with no mid-run stop at all.

Confirmation is the *absence* of both records, and Prompire owns the serialization:
model comments never survive the parse, so model output cannot manufacture a confirmed
line. The two records exist because they fail differently — the comment markers are
what a human reads, and the `unconfirmed:` ledger is what survives `yq -y .`, a
formatter, or an agent asked to tidy the file. A draft that loses its comments still
refuses to prepare or arm.

## Acceptance entry

| field | required | meaning |
|---|---|---|
| `cmd` | yes | the command you would actually run. A shell command line: pipes, redirects, quoting and newlines are part of it. It executes **verbatim** — `baseline.py` and `verify` run the exact text, and every renderer shows a multi-line command as a verbatim block (E1: flattening one produced a different, invalid command). Only matching on the `(cmd, cwd)` key is whitespace-normalised |
| `expect` | yes | the observable result, in prose a human reads |
| `cwd` | no | repo-relative directory to run it in; default `.` |
| `timeout` | no | positive whole seconds; default 300 in `baseline.py` |
| `requires` | no | `network`, `credentials`, `services`, `docker`, `database`, `display`, `interactive`, `writes-repo`, `manual`. Any entry means `baseline.py` (and `verify`) will not run it — which is why a value outside this vocabulary is a lint error (B5), not a warning: a typo would silently disable the criterion |
| `transition` | no | `green` (default), `flip`, `hold` — see below |
| `before_after` | no | its stdout must reproduce the digest recorded in the baseline |
| `must_flip` | legacy | the pre-2026-07-27 spelling of `transition: flip`; accepted, warned |

**Entries are keyed on `(cmd, cwd)`**, both whitespace-normalised. Two entries with the
same key are an error: the baseline could not tell them apart, and neither could you.

**`expect` is read by a human, and by `baseline.py` only where it recognises the form.**
It parses `exit N`, `exit != 0` (and "non-zero exit"), and `empty output` / `no matches`.
Anything else is prose: the command still runs, the evidence is still printed, and the
status is left blank for you to fill in. It never guesses.

**stdout / stderr / exit status.** The exit status is what `expect: exit N` compares.
`empty output` looks at stdout only. Nothing inspects stderr — if stderr matters, put a
grep in the `cmd` and expect its exit code.

**Working directory and environment.** `cwd` is the only environment the schema
declares. Everything else — a virtualenv, a running service, credentials — is declared
by naming it in `requires`, which makes the baseline `not_runnable` with that reason
instead of running something that will fail for the wrong reason.

**Workspace consistency (Python).** When a command exercises a package this checkout
itself defines — an explicit `python`/`py` interpreter importing it in `-c`, running
it with `-m`, or running `-m pytest`/`-m unittest` in a repo that defines packages —
`baseline.py` first probes where that import resolves. If it resolves outside the
checkout (a site-packages copy shadowing an uninstalled `src/` layout), the criterion
is refused as unclassified instead of measured: E1's T05 baseline signed off the
system copy of the library, which already contained the fix. A workspace copy that
shadows an installed one, and imports of dependencies the repo does not define, are
untouched. A bare `pytest`/`tox` entry point is not probed — its interpreter is not
knowable from the command line, and that gap is documented rather than guessed at.

## Transitions

`transition` says what must change, and it is the only thing that distinguishes the
three cases a reviewer has to tell apart.

| | meaning | valid baseline status |
|---|---|---|
| `green` | meets its `expect` today and must keep meeting it | `pass` (a `fail` here is error B15) |
| `flip` | does not meet its `expect` today; making it do so is the goal | `fail`, `not_runnable` |
| `hold` | meets its `expect` today and must reproduce it **exactly**; do not "fix" it | `pass`, and `evidence` is required |

## Baseline entry

| field | required | meaning |
|---|---|---|
| `cmd`, `cwd` | yes | must match an acceptance entry's key verbatim |
| `status` | yes | `pass` \| `fail` \| `not_runnable` |
| `reason` | if `not_runnable` | why it was not run |
| `evidence` | strongly | one line: exit code, the number that mattered, and a digest for `before_after` |

**`status` answers one question: did the command meet its own `expect` on untouched
HEAD.** Not "was the suite green". A known-red suite is written `expect: exit 1` and its
status is `pass` — it is doing today exactly what the brief says it should keep doing.

`not_runnable` is for a command that was never executed: it needs credentials or a
service, it writes to the repo, it is destructive or interactive, it timed out, or its
`cwd` does not exist yet. It always carries a `reason`. Paired with `transition: flip`
it is the canonical shape for *"this cannot run until the code exists"*. Paired with
`transition: green` it is a warning: that criterion cannot tell the agent's work from
the state it started in.

## How scope resolves against a real diff

`check_scope.py` classifies every path that differs from `base_rev`, including staged,
committed and untracked files, plus **both sides of a rename**. It never defaults to
`HEAD` silently: without an explicit `--base`, a `base_rev` that is missing or not a
fixed SHA (a branch name, `HEAD`) makes it refuse to produce a verdict at all. `--base`
overrides `base_rev` and is accepted as given, moving ref or not — that is a human
choosing the comparison on purpose.

The brief is a file the agent can edit, and `base_rev` is not the only field in it worth
buying — one `dirty_baseline` entry excuses a violation outright. So `--activate` records
both the declared base *and a digest of the whole brief* in `.prompire/ACTIVE`, and
`check_scope.py` refuses to produce any verdict (exit 2) when the brief on disk no longer
matches what was armed. While a guard is armed the pointer decides which brief a verdict
is about: `--base` still chooses the revision, but it does not override the pointer, and
`--deactivate` — which appends to `.prompire/ACTIVE.tombstones` — is the way out. Once
anything has been disarmed in a repo, every later arm reports as `repin` rather than
`pin` and corroborates nothing, whatever the brief is called.

Unarmed, none of that exists: the brief's committed copy at `base_rev` can raise a REVIEW
about a re-stamp but never refuses (a reusable brief slot produces the identical
evidence), and with nothing at all the summary line reads `base uncorroborated`. Run
`--strict` for review — it turns those flags into a non-zero exit. Every run prints which
source established the base, because a verdict is worth what its base is worth.

- A pattern with no wildcard, or ending in `/`, also covers everything beneath it:
  `src/render/` and `src/render` both match `src/render/pdf.py`.
- `**` crosses directory separators, `*` does not.
- Order: `forbidden` first (it wins), then `scope`, then the tests policy.
- **Deleted** files are checked against the same lists as modified ones. **Added** files
  too — a generated file is not special, and if the build writes it, it belongs in
  `scope`.
- **Renames** must have both the old and the new path allowed.
- **Symlinks** are checked as the link, not the target, and raise a REVIEW flag.
- **Directories** are never checked — git tracks files.
- `.prompire/**` and the brief itself are always allowed.
- `dirty_baseline` paths are ignored: they were already modified when the brief was
  written, so they are not the agent's edit.

## What tests_policy means

`tests_editable` (for `named` and `authoring`) is allowed **without** being repeated in
`scope`. What may happen to it once inside is the policy. Full matrix, and what is
mechanical versus what needs a human: `rules.md`, section B7.
