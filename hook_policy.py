#!/usr/bin/env python3
"""Host-neutral core of the Prompire PreToolUse guard.

One question, asked the same way for every agent host: *given these paths and this
working directory, is there a definite reason to refuse this tool call?* Everything
above this module is a protocol adapter — `hook_scope_guard.py` speaks Claude Code's
stdin/stderr/exit-2 convention, `hook_copilot_guard.py` speaks GitHub Copilot CLI's
stdin/stdout-JSON convention — and neither of them is allowed its own opinion about what
`scope` means. Both call `verdict_for()`, which calls `brief_common`'s `boundary_verdict`
and `tests_verdict`, which is what `check_scope.py` calls afterwards. A second
interpretation of the boundary is the one thing this split must never grow.

Fails open, deliberately, and that property belongs to this module rather than to either
adapter: it runs on every watched write in every project on the machine, so a missing
repo, an unreadable brief or a parse error must yield *no verdict* rather than a
refusal. It answers with a verdict only when it has one. What an adapter does with "no
verdict" is the adapter's business — Claude Code exits 0, Copilot CLI emits nothing —
but neither of them may turn silence into a refusal, and neither may turn its own
trouble into an approval it did not compute.

Two roots can matter for one write: the target's own location (repo B's brief speaks
for repo B's files) and the session's cwd (an agent bound by repo A's brief must not
escape into repo B just because B's brief happens to permit the path). Both are
checked when they differ; either can block. And a broken pointer never shadows a real
one above it — the walk continues upward past anything that doesn't load, including a
pointer that isn't even readable as UTF-8.
"""
import os
import pathlib
import sys
import traceback
import unicodedata

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

MAX_LOG_BYTES = 1_000_000  # ~1MB. hook-errors.log is a diagnostic trail, not an audit
                            # log — check_scope.py and git history are the audit trail —
                            # so it resets rather than rotates once it gets large.

# The sentence every refusal closes with, on every host. One copy, here, because the
# wording is the part an agent actually reads and acts on: two hosts explaining the same
# boundary in two places is how the two explanations quietly stop agreeing, and the
# thing they would drift on is whether the boundary is negotiable in conversation. The
# adapters differ in framing only — Claude Code puts this on stderr, Copilot CLI puts it
# at the end of `permissionDecisionReason`.
CONTRACT_LINE = ("The brief is the contract. Widening `scope` is an edit to the brief "
                 "followed by a fresh baseline, not a decision to make mid-task.")


def find_root(start):
    """The FARTHEST ancestor of `start` holding a `.prompire/ACTIVE` file, or None —
    regardless of whether that pointer's own brief loads. Used only to pick a location
    for `log_exception`'s diagnostic write, where an exception can originate from
    anywhere in `verdict_for()` and there is no already-known governing root to reuse.

    Outermost, not nearest: a pointer planted to shadow a subtree is by construction
    nested below the real one, and logging at the nearest one would put the trace
    inside the attacker's own planted directory instead of where an operator would
    look. There is normally only one pointer on the chain at all, so this picks the
    same location a nearest-match would have in the overwhelmingly common case.

    Deliberately not `git rev-parse`: this runs on every write in every session, and a
    directory walk costs nothing extra when nothing is armed. The loop already
    terminates at the filesystem root (`p.parent == p`), so no depth bound is needed.
    """
    p = pathlib.Path(start).resolve()
    found = None
    while True:
        if (p / ".prompire" / "ACTIVE").is_file():
            found = p
        if p.parent == p:
            return found
        p = p.parent


def _find_governing(start, load_brief, brief_error, norm_path):
    """The nearest ancestor of `start` whose `.prompire/ACTIVE` points at a brief that
    actually loads — walking upward past any pointer that is empty, unloadable, or not
    even readable as UTF-8, instead of stopping at it. Returns
    ((root, rel_brief, brief) or None, seen), where `seen` is the FARTHEST ancestor that
    had *any* `ACTIVE` file at all, loadable or not (or None) — the caller reuses it to
    log a diagnostic without a second walk purely to find where. Farthest, matching
    `find_root` and for the same reason: the nearest pointer is where a planted one sits
    by construction, and a trace written inside the plant is a trace nobody reads.

    This is what keeps a corrupted or planted pointer from shadowing a real brief above
    it: without walking on, the nearest broken pointer would end the search right
    there, and every write beneath it would be judged against nothing at all. The read
    and the parse are one `except`, deliberately: an unreadable or non-UTF-8 pointer
    must walk on exactly like an unloadable one, not escape as an uncaught exception
    that fails the *whole* call open before any other root even gets a turn.
    """
    p = pathlib.Path(start).resolve()
    seen = None
    while True:
        active = p / ".prompire" / "ACTIVE"
        if active.is_file():
            seen = p
            try:
                # Line 1 is the brief path; anything after it is a record check_scope.py
                # keeps out here, out of the write tools' reach (the pinned base). Read
                # the first line only — the whole file would resolve to no brief at all
                # and disarm the guard the moment a second line exists.
                head = active.read_text(encoding="utf-8").strip().splitlines()
                rel_brief = norm_path(head[0]) if head else ""
                brief = load_brief(str(p / rel_brief)) if rel_brief else None
                if brief is not None:
                    return (p, rel_brief, brief), seen
            except (brief_error, OSError, UnicodeDecodeError):
                pass
        if p.parent == p:
            return None, seen
        p = p.parent


def _as_written(target):
    """Where this write will actually land, in the WRITE TOOL's path semantics.

    `..` is collapsed lexically FIRST, and only then are symlinks resolved — because that
    is the order Claude Code's Write/Edit tools use, and the guard's whole job is to judge
    the file the tool is about to open. `Path.resolve()` alone is `realpath`, which
    follows a symlink *before* applying a following `..`, so it reads `link/..` as the
    parent of the link's TARGET while the tool reads it as the parent of the LINK. The two
    agree on every path with no symlink, or no `..`, or a `..` before every symlink; they
    disagree on `<symlink>/../…`, and that one shape is a total disarm — with an ordinary
    `node_modules/.bin/*` entry as the pivot, `Write node_modules/.bin/x/../../../
    .prompire/spec.yaml` is judged under `node_modules/` and lands on the active brief.

    So: never "simplify" this to a bare `.resolve()`. The hook must reproduce the tool's
    model of the path, not the OS's, or it decides about a different file than the one
    that gets written.
    """
    return pathlib.Path(os.path.normpath(str(target))).resolve()


def _same_file(a, b):
    """True if `a` and `b` name the same file by OS-level identity (device + inode), not
    by spelling. `os.path.samefile` resolves symlinks, `..` segments, and — critically —
    the filesystem's own case- and Unicode-normalisation folding, so it is correct
    regardless of which of several equivalent spellings a write target uses. A string
    compare, however case-folded or Unicode-normalised, can always be fooled by a
    spelling nobody enumerated; identity cannot. If either path doesn't exist, they
    cannot be the same *existing* file — the ordinary case of a Write creating a
    brand-new path is correctly not a match.
    """
    try:
        return os.path.samefile(a, b)
    except OSError:
        return False


# The current state directory, and its address before the 0.4.0 rename. Every repo
# that used this tool before the rename has real disarm history at the second one
# (`~/LifeOS/.agent-brief/ACTIVE.tombstones` is a live example), and that history is
# exactly as forgeable/erasable by a bare Write as the current pointer is — so it gets
# the same unconditional protection, not a second copy of the rule that could drift
# from this one. See `check_scope.py`'s `legacy_tombstone_path` for the other half.
_STATE_DIRS = (".prompire", ".agent-brief")


def _looks_like_active_pointer(rel):
    """Does this rel path have the SHAPE of a `<state-dir>/ACTIVE*` file, at any depth,
    under either state-directory name — not identity with one real pointer. A pointer
    planted below the root (`src/.prompire/ACTIVE`) is a distinct, not-yet-existing
    file, so `_same_file` can't see it; this is a structural match instead. All the
    literals involved are pure ASCII, so Unicode-normalising them is a no-op in
    practice — case-folding is what actually matters — but both are applied for the
    same reason `_same_file` is used above: the filesystem's own folding, not an
    enumerated list of tricks, is what has to be matched.

    Two names, not a prefix: `ACTIVE.tombstones` records that a guard was disarmed, and
    a record of a disarm that the disarmed party can delete is not a record. They are
    enumerated rather than matched with `startswith("active")`, which also caught
    ordinary files like `.prompire/active-notes.md` — the rest of `.prompire/` (and of
    `.agent-brief/`) is where working notes and renders live and has to stay writable,
    or the guard starts costing something it was never meant to cost.

    The match is on a `.prompire`/`.agent-brief` segment followed by one of those names
    ANYWHERE in the path, not on the last two components, so it also refuses a write
    *beneath* one of them. `.prompire/ACTIVE.tombstones/x` has parent
    `active.tombstones`, so a last-two-components test let it through — and the write
    creates a directory where the log file belongs, which is not a small thing:
    `--deactivate` then dies on IsADirectoryError without disarming, and a state file
    that cannot be written is a state file that records nothing. One allowed Write, and
    the record is gone for good.
    """
    parts = [unicodedata.normalize("NFC", s).casefold() for s in rel.split("/")]
    return any(seg in _STATE_DIRS and parts[i + 1] in ("active", "active.tombstones")
               for i, seg in enumerate(parts[:-1]))


def _active_record_verdict(target, cwd):
    """Is this write's target the guard pointer or its disarm log — refused whether or
    not any brief governs here. Returns a verdict 4-tuple, or None.

    These two files are what RECORD whether a guard is armed and whether it was ever
    disarmed. Gating their protection on a brief already governing gets that backwards:
    it leaves them unprotected in exactly the state whose whole job is to describe —
    unarmed, or disarmed. One allowed Write then forges a clean `.prompire/ACTIVE`
    with no brief ever having been armed (`corroborate()` reads it as a `pin`), or empties
    `.prompire/ACTIVE.tombstones` in the unarmed window between two tasks and erases
    the record that a disarm ever happened. The same is true, unchanged, of a repo's
    legacy `.agent-brief/ACTIVE.tombstones` from before the 0.4.0 rename: once
    `any_disarm()` reads it too (see `check_scope.py`), it is exactly as load-bearing as
    the current log and gets exactly the same protection.

    `_looks_like_active_pointer` needs no root to answer this — it matches the SHAPE of
    a `.prompire` OR `.agent-brief` segment followed by `ACTIVE`/`ACTIVE.tombstones`, at
    any depth, however the path is spelled. The resolved absolute target already
    contains that shape wherever it occurs, so checking it directly, before any
    governing brief is even looked for, is a superset of the check `_check_against` used
    to make per governing root — not a second copy of it.
    """
    if not _looks_like_active_pointer(str(target)):
        return None
    try:
        rel = str(target.relative_to(pathlib.Path(cwd).resolve()))
    except ValueError:
        rel = str(target)
    return (rel, "self-edit", "this is the guard pointer or its disarm log",
            "use `check_scope.py --deactivate`, which is auditable")


def _check_against(root, rel_brief, brief, target, tests_policy_of, tests_verdict,
                    boundary_verdict, norm_path, fs_fold):
    """Is this write allowed under this one (root, brief) pair? None means yes; otherwise
    a verdict 4-tuple.
    """
    try:
        written = _as_written(target).relative_to(root)
    except ValueError:
        return (str(target), "outside-repo",
                f"outside the repository the active brief governs ({root})",
                "the brief's `scope` cannot speak for this path")
    # Probed only now that the target is confirmed under `root` — the cross-repo escape
    # check above hits `outside-repo` on most calls to a repo the write isn't even in,
    # and a filesystem probe is not worth paying for a verdict that returns before using
    # it. The active-brief and pointer checks just below are OS-level identity or a
    # deliberately unconditional shape match — neither needs this. `scope`/`forbidden`
    # matching does: `fold` is a property of the volume `root` actually lives on
    # (probed, not assumed), and it is what stops a `forbidden` entry from being
    # defeated by a case- or normalisation-variant spelling on a folding filesystem.
    fold = fs_fold(root)
    rel = norm_path(written, fold)

    # The brief is the contract; an agent that can edit its own scope has no scope. The
    # active-brief check is OS-level identity, not a string compare: APFS/HFS+ are both
    # case- and Unicode-normalisation-insensitive, so a differently spelled write can
    # land on the very same directory entry as the canonical name.
    # `_as_written`, never a raw string: `os.stat` raises ENOENT/ENOTDIR on any spelling
    # whose parent is missing or is not a directory (`.prompire/nope/../spec.yaml`,
    # `src/cart.py/../../.prompire/spec.yaml`), `_same_file` reads that as no-match —
    # while the write tool normalises `..` lexically before it touches the disk and lands
    # on the brief regardless. `verdict_for` normalises at the boundary already; both uses
    # here keep the precondition next to the checks that silently mis-answer without it.
    # Every site in this module that turns a write target into a path goes through
    # `_as_written` — that is the invariant, and it is greppable.
    #
    # The guard pointer and its disarm log are NOT re-checked here: `verdict_for()`
    # already refused them unconditionally, before a governing brief was even looked for
    # (see `_active_record_verdict`). Re-testing the same shape here would be a second
    # copy of that rule, and two copies drift.
    if _same_file(_as_written(target), root / rel_brief):
        return (rel, "self-edit", "this is the active brief",
                 "revise it with the guard off, re-run baseline.py, re-activate")

    policy = tests_policy_of(brief)
    for verdict in (tests_verdict(brief, rel, policy, fold=fold),
                    boundary_verdict(brief, rel, policy, fold=fold)):
        if verdict:
            return (rel, *verdict)
    return None


def verdict_for(targets, cwd):
    """The first definite reason to refuse this tool call, or None.

    `targets` is every path the call would create, replace, rename, delete or modify,
    as `pathlib.Path`s already made absolute against `cwd` by the adapter. Order is the
    adapter's; the first target that draws a verdict decides the whole call, because a
    tool call is atomic — a multi-file patch whose second file is out of scope is an
    out-of-scope patch, not a partially compliant one.

    A verdict is `(displayed_path, rule, message, fix)`. None means this module found no
    reason to refuse — which is NOT the same as "checked and approved". It is also what
    a missing repo, an unloadable brief and an unparseable pointer all produce, so an
    adapter must render it as "nothing to say", never as an approval that would skip a
    permission check the host would otherwise make.
    """
    # PASS 1 — everything that needs no brief, no `brief_common`, and no PyYAML. This
    # runs to completion for every target BEFORE the import below, and the order is not
    # a tidiness preference: `.prompire/ACTIVE` and `.prompire/ACTIVE.tombstones` are
    # documented as protected *unconditionally* (README's guarantee paragraph, CLAUDE.md's
    # Architecture section), and an import that can fail ahead of these checks makes them
    # conditional on PyYAML being installed and importable. It is not a theoretical
    # window — a half-installed venv or an interpreter upgrade produces it, and the
    # adapters' catch-alls would then turn a forged-pointer write into a permitted one.
    # Keep these two checks above the import. `tests/hook.py`'s `broken-import-*` cases
    # pin it by making `import yaml` raise for real.
    resolved = []
    for target in targets:
        # A NUL byte names no file on any POSIX filesystem, and `Path.resolve()` raises
        # ValueError on one — from inside the root walk, before any brief is found,
        # which an adapter's catch-all would turn into a fail-open on a string the agent
        # chose. Fail closed instead: this is not the infrastructure trouble the
        # fail-open rule is for, and no write tool can create this path either, so
        # nothing legitimate is refused.
        if "\x00" in str(target):
            return (str(target).replace("\x00", "\\x00"), "unnameable-path",
                    "this path contains a NUL byte, so it names no file a brief can "
                    "speak for",
                    "write a path the filesystem can name")
        # Resolved once, here, so every consumer below — the root walks, the identity
        # check, the relative_to — sees the path the write will actually land on rather
        # than the spelling the agent chose. Four rounds of this module's defects were
        # one spelling or another reaching a check unresolved; the boundary is the place
        # to end that. The fifth was this line resolving with the OS's semantics instead
        # of the write tool's — see `_as_written`, and do not replace it with a bare
        # `.resolve()`.
        written = _as_written(target)

        # Checked before anything else below, and unconditionally — no governing brief
        # has to load for this one to bite. `.prompire/ACTIVE` and
        # `.prompire/ACTIVE.tombstones` are what record whether a guard is armed and
        # whether it was ever disarmed; gating their protection on a brief already
        # governing leaves them open in precisely the state each of them exists to
        # describe (unarmed, or disarmed). See `_active_record_verdict`.
        active_record = _active_record_verdict(written, cwd)
        if active_record:
            return active_record
        resolved.append(written)

    # PASS 2 — the brief-dependent half. `brief_common` pulls in PyYAML, and this runs
    # on every watched write on the machine whether or not anything is armed, so it is
    # imported here rather than at module scope: an unarmed machine never pays for it.
    from brief_common import (
        BriefError,
        boundary_verdict,
        fs_fold,
        load_brief,
        norm_path,
        tests_policy_of,
        tests_verdict,
    )

    # Memoised across every target in one call: on the common path cwd and the targets
    # share one root, and without this the same brief file is re-opened and re-parsed
    # once per path.
    cache = {}

    def _load_cached(path):
        if path not in cache:
            cache[path] = load_brief(path)
        return cache[path]

    for written in resolved:
        # The write's own location is the PRIMARY authority — repo B's own brief speaks
        # for repo B's files, even when the session is cd'ed into repo A. But cwd's brief
        # must not be silently dropped: without it, an agent bound by A's narrow scope
        # could escape into any other armed repo whose brief happens to permit the path.
        # When both resolve to different roots, both are checked and either can block;
        # target's verdict is checked first since it is primary. When either resolves to
        # no loadable brief anywhere on its chain (nothing there, or everything there is
        # broken), that side simply contributes nothing — it does not disarm the other.
        governing = []
        t, t_seen = _find_governing(written.parent, _load_cached, BriefError, norm_path)
        if t is not None:
            governing.append(t)
        c, c_seen = _find_governing(cwd, _load_cached, BriefError, norm_path)
        if c is not None and (t is None or c[0] != t[0]):
            governing.append(c)

        if not governing:
            seen = t_seen or c_seen
            if seen is not None:
                log_disarmed(seen, written)
            continue

        for root, rel_brief, brief in governing:
            result = _check_against(root, rel_brief, brief, written, tests_policy_of,
                                     tests_verdict, boundary_verdict, norm_path, fs_fold)
            if result:
                return result
    return None


def _append_log(root, text):
    try:
        log = root / ".prompire" / "hook-errors.log"
        if log.is_file() and log.stat().st_size > MAX_LOG_BYTES:
            log.write_text("", encoding="utf-8")
        with open(log, "a", encoding="utf-8") as f:
            f.write(text)
    except Exception:
        pass


def log_exception(cwd):
    """Best-effort trace of an unexpected exception, so a broken guard leaves a mark
    instead of looking exactly like a compliant agent (fail-open stays the behavior;
    only the silence changes). Never stderr — stderr on a Claude Code PreToolUse hook
    reads as the block message itself, and on a Copilot CLI hook it is noise the
    operator sees on every unrelated write. Written only if the caller got far enough to
    know which repo this call concerned; `cwd` is None when even the stdin payload
    didn't parse, and there is nowhere sane to log that against.

    Same limitations as the rest of `hook-errors.log`, unchanged by having two hosts
    write to it: it is agent-writable, truncatable and forgeable, so it is a diagnostic
    trail and not an audit log. The audit trail is `check_scope.py` plus git history.
    """
    if not cwd:
        return
    try:
        root = find_root(cwd)
        if root is not None:
            _append_log(root, traceback.format_exc() + "\n")
    except Exception:
        pass


def log_disarmed(root, target):
    """A `.prompire/ACTIVE` pointer exists somewhere on the walk but nothing loaded
    from it anywhere in the chain — the guard is failing open, but that is a different,
    much rarer state than the ordinary "no brief active at all" case. `root` is the
    pointer-holding directory the enforcement walk already found (`t_seen`/`c_seen`);
    the ordinary case never reaches here and is silent, since it is the overwhelming
    majority of writes on an unarmed machine and logging it would flood this file for
    no reason.
    """
    _append_log(root, f"disarmed: a pointer exists at {root} but no ancestor brief "
                f"loaded for target={target}\n")
