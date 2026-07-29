#!/usr/bin/env python3
"""Check a working tree against the brief's scope, forbidden list and tests policy.

Usage: python3 check_scope.py brief.yaml [--base REV] [--json] [--strict]
                             [--ack-disarms DIGEST]
       python3 check_scope.py brief.yaml --activate     # arm the PreToolUse hook
       python3 check_scope.py --deactivate              # disarm it
Exit 0 = every change is inside the declared boundary, 1 = at least one violation,
2 = the brief or the repository could not be read, the brief declares no scope to arm,
there is no fixed base to diff against (`base_rev` missing/not a commit SHA and no
`--base` given — this never defaults to HEAD, see references/rules.md B16), the base
the brief names is contradicted by a record kept outside the brief (see `corroborate`),
or `--ack-disarms` was given a digest that does not match `.prompire/ACTIVE.tombstones`
as it reads right now, or a leftover `.agent-brief/ACTIVE.tombstones` from before the
0.4.0 rename is still present (`--ack-disarms` refuses to bind while a repo's disarm
history is split across both files — see CHANGELOG.md 0.4.0 for the migration).

`--ack-disarms DIGEST` lets a reviewer accept the disarms recorded so far: DIGEST is a
12-64 hex prefix of the sha256 of the tombstone log's bytes. It stops the `repin` REVIEW
alone from failing `--strict` — every other REVIEW and any VIOLATION still does — and it
does not relabel the base as `pin`. A later `--deactivate` changes the log's bytes and
therefore the digest, so the same DIGEST stops matching and `--strict` goes red again
until a fresh acknowledgement is given for the new log.

This runs *after* the agent, from the outside. It does not need the agent's
cooperation and there is nothing the agent can add to its own acceptance block to
satisfy it. Semantics: references/schema.md (scope, forbidden, tests_policy).

VIOLATION is mechanical: the path changed and the brief did not allow it.
REVIEW is a flag for a human: something a diff can show but no checker can judge.
"""
import contextlib
import hashlib
import json
import os
import pathlib
import re
import subprocess
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from brief_common import (
    ALWAYS_ALLOWED,
    SKIP_MARKERS,
    BriefError,
    _fold_in,
    as_list,
    boundary_verdict,
    fs_fold,
    is_test_path,
    load_brief,
    matches_any,
    norm_path,
    tests_policy_of,
    tests_verdict,
)


SHA_RE = re.compile(r"[0-9a-fA-F]{7,40}")

# `--ack-disarms` takes a prefix of the tombstone log's sha256 — same shape rule as
# `base_rev`'s short SHA (see `SHA_RE`, `same_commit()`), scaled to a hash instead of a
# commit: long enough that a reviewer cannot type a fragment ambiguous with some other
# state of the log, short enough to read off a terminal.
ACK_DIGEST_RE = re.compile(r"[0-9a-fA-F]{12,64}")
LOCK_WAIT_SECONDS = 5

# How the base being diffed against was established. Printed on every run: a reader who
# does not know which of these applied cannot know how much the verdict is worth.
BASE_SOURCE = {
    "pin": "brief and base recorded in .prompire/ACTIVE when the guard was armed",
    "repin": "recorded in .prompire/ACTIVE, but only at a re-arm after a --deactivate",
    "--base": "base given on the command line",
    None: "base uncorroborated — the brief's own claim",
}


class RepoError(Exception):
    pass


def git(root, args, check=True):
    r = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True)
    if check and r.returncode != 0:
        raise RepoError(f"git {' '.join(args)}: {r.stderr.strip()}")
    return r.stdout


def repo_root(start):
    r = subprocess.run(["git", "-C", str(start), "rev-parse", "--show-toplevel"],
                       capture_output=True, text=True)
    if r.returncode != 0:
        raise RepoError(f"{start} is not inside a git repository")
    return pathlib.Path(r.stdout.strip())


def active_path(root):
    return pathlib.Path(root) / ".prompire" / "ACTIVE"


def state_lock_path(root):
    return pathlib.Path(root) / ".prompire" / "ACTIVE.lock"


@contextlib.contextmanager
def guard_state_lock(root):
    lock = state_lock_path(root)
    lock.parent.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + LOCK_WAIT_SECONDS
    while True:
        try:
            lock.mkdir()
            break
        except FileExistsError:
            if time.monotonic() >= deadline:
                raise RepoError(f"timed out waiting for guard-state lock {lock}")
            time.sleep(0.01)
        except OSError as exc:
            raise RepoError(f"could not acquire guard-state lock {lock}: {exc}") from exc
    try:
        yield
    finally:
        try:
            lock.rmdir()
        except OSError as exc:
            raise RepoError(f"could not release guard-state lock {lock}: {exc}") from exc


def tombstone_path(root):
    return pathlib.Path(root) / ".prompire" / "ACTIVE.tombstones"


def legacy_tombstone_path(root):
    """The disarm log's old address, from before the 0.4.0 rename moved the state
    directory `.agent-brief/` -> `.prompire/`. Every repo that used this tool before
    that rename has its disarm history here, not at `tombstone_path()` — and
    `any_disarm()` has to read it too, or upgrading silently turns a genuine past
    disarm into a clean `pin` the next time someone arms a guard. See `any_disarm`."""
    return pathlib.Path(root) / ".agent-brief" / "ACTIVE.tombstones"


def digest_of(path):
    """sha256 of the brief's bytes, or None if it cannot be read.

    The whole file, not one field: `base_rev` was never the only value in here worth
    buying. `dirty_baseline`, `scope` and `forbidden` are all the agent's to write, and
    appending one `dirty_baseline` entry turns a violation into a clean verdict just as
    effectively as moving the base does.
    """
    try:
        return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()
    except OSError:
        return None


def read_pointer(root):
    """What `.prompire/ACTIVE` records: brief, base_rev, sha256, repin.

    Line 1 is the brief path and nothing else — that is the entire contract the
    PreToolUse hook reads, and it has to stay that way. Lines after it are `key value`
    records this tool keeps *outside* the brief, in files the hook refuses to let a write
    tool touch at any depth.

    `.strip()` before `splitlines()`, exactly as the hook does it: with a leading blank
    line the hook still finds the brief and stays armed while this side read line 1 as
    empty and quietly stopped binding the pin — armed-looking and unpinned is the worst
    of the available states, and the two parsers must not disagree about it.
    """
    out = {"brief": None, "base_rev": None, "sha256": None, "repin": False}
    try:
        lines = active_path(root).read_text(encoding="utf-8").strip().splitlines()
    except (OSError, UnicodeDecodeError):
        return out
    out["brief"] = (norm_path(lines[0]) if lines else "") or None
    for ln in lines[1:]:
        key, _, val = ln.strip().partition(" ")
        val = val.strip()
        if key in ("base_rev", "sha256") and val:
            out[key] = val
        elif key == "repin":
            out["repin"] = True
    return out


def _loads(path):
    """Does this path hold a brief the hook would enforce? Same test the hook applies."""
    try:
        load_brief(str(path))
        return True
    except BriefError:
        return False


def active_brief(root):
    """The repo-relative brief enforced by the live pointer, or None."""
    cur = read_pointer(root)
    rel = cur["brief"]
    return rel if rel and _loads(pathlib.Path(root) / rel) else None


def _activate_locked(brief, rel_brief, brief_path, root):
    """Point .prompire/ACTIVE at this brief so the PreToolUse hook enforces it, and
    record what the brief said while it still said it honestly.

    The hook reads the first line and nothing else. Keeping the pointer separate from the
    brief means activating is a deliberate act, not something a brief does by existing —
    and it is what makes the pointer the right home for the record. The brief is a file
    the agent can edit: re-stamping `base_rev` at a commit that already contains the work
    empties the diff, and appending a `dirty_baseline` entry excuses a violation outright.
    Both are one Write. A copy of the base *and a digest of the whole file* out here give
    check_scope.py something that can disagree with either.

    Re-arming is refused whenever it would quietly replace an existing record — with
    another brief's, or with this brief's own changed claim. `--deactivate` is the way
    out, and it leaves a tombstone: a pin written over one is reported as the weaker
    thing it is, because otherwise `--deactivate && --activate` launders a bought base
    into the strongest label this tool prints.
    """
    if not as_list(brief.get("scope")):
        print("refused: the brief declares no `scope`, so there is no boundary to enforce")
        return 2
    declared = str(brief.get("base_rev") or "").strip()
    pin = declared if SHA_RE.fullmatch(declared) else None
    cur = read_pointer(root)
    # A pointer whose brief does not load is not a live guard — the hook walks straight
    # past it — so it must not lock arming out of the repo either. That covers a pointer
    # with no path line at all, whose first line reads as some other record entirely.
    live = active_brief(root)
    if live and live != rel_brief:
        print(f"refused: `{live}` is already active here, and arming a second "
              "brief would overwrite what was recorded for it.\nrun `check_scope.py "
              "--deactivate` first — turning a guard off is meant to leave a trace")
        return 2
    # Only a pointer that names *this* brief can speak about it. A pointer with no
    # readable path is garbage, not a record, and must not lock activation out forever.
    if cur["brief"] == rel_brief and cur["base_rev"] and cur["base_rev"] != pin:
        print(f"refused: this brief was armed at base_rev {cur['base_rev']} and now "
              f"declares {pin or 'no usable base_rev'}.\nRe-arming would replace the "
              "pinned base with the brief's own current claim, which is the one thing "
              "the pin exists to be able to contradict.\nif the base genuinely changed, "
              "`--deactivate` first and say so out loud")
        return 2
    repin = any_disarm(root)
    sha = digest_of(brief_path)
    p = active_path(root)
    p.parent.mkdir(exist_ok=True)
    p.write_text(rel_brief + "\n"
                 + (f"base_rev {pin}\n" if pin else "")
                 + (f"sha256 {sha}\n" if sha else "")
                 + ("repin\n" if repin else ""), encoding="utf-8")
    print(f"guard active: {rel_brief}")
    print("writes outside `scope` are refused before they happen")
    print("the brief is recorded as it stands: any later edit to it — the base, the "
          "scope, a `dirty_baseline` entry — makes check_scope.py refuse a verdict")
    if not pin:
        print("no `base_rev` to pin: nothing outside the brief will corroborate the base "
              "it claims later — run `baseline.py <brief> --write` first")
    if repin == "unreadable":
        print(f"WARNING: {tombstone_path(root)} is not a readable log. Nothing legitimate "
              "puts anything but a file there, so this arm is recorded as a `repin` and "
              "check_scope.py will refuse a verdict until the path is a file again")
    elif repin:
        print("a guard has been disarmed in this repo before, so what is recorded here is "
              "only as old as this arm; check_scope.py reports it as `repin`, not `pin`")
    print("run `check_scope.py --deactivate` when the task is done")
    return 0


def activate(brief, rel_brief, brief_path, root):
    try:
        with guard_state_lock(root):
            return _activate_locked(brief, rel_brief, brief_path, root)
    except RepoError as exc:
        print(str(exc))
        return 2


def any_disarm(root):
    """Has any guard been disarmed in this repo? True, False, or "unreadable".

    Three answers, not two. "There is no log" and "there is something at the log's path
    that cannot be read as a log" are opposite facts, and collapsing them into False is
    what turns a jammed record into a silent full-strength label: one Write creating a
    *directory* at that path used to make this return False forever, so every later arm
    reported the strongest label the tool prints. Nothing legitimate puts a non-file
    there, so it counts as at least as suspect as a recorded disarm.

    Not: has *this* brief's path been disarmed.

    Append-only, and protected by the same hook rule as the pointer itself. Without it
    `--deactivate && --activate` is a two-command laundry: the re-arm refusal is only
    worth what re-pinning costs, and re-pinning otherwise costs nothing.

    Keyed on the log being non-empty rather than on a path in it, because a path is
    exactly what the evader controls: copy the armed brief to a new name with `base_rev`
    re-stamped — one Write that `.prompire/**` allows — then disarm the old name and
    arm the new one, and a path-keyed check calls it a first arm and prints the strongest
    label it has. It also fixed the incentive: with path keying, revising a brief in
    place cost `repin` forever while renaming it restored a full `pin`, so the cheapest
    honest path was the attack. Now neither buys anything.

    The read is the test, not a preceding `exists()`. `Path.exists()` swallows OSError and
    answers False, so an unreadable log — a directory at that path, a parent the process
    cannot traverse — used to come back as "no disarm ever recorded" and earn the
    strongest label this tool prints, which is the one answer it must never give for an
    obstructed record. Reading it is also the only way to learn which of the three answers
    applies without a check that can go stale between the two calls.

    Two paths, not one, since the 0.4.0 rename: `tombstone_path()` is where this version
    writes, `legacy_tombstone_path()` is where every pre-rename repo already has real
    disarm history. Both are read unconditionally — never short-circuited on the first
    finding a disarm — because "unreadable" has to win over "found one already": a repo
    with a genuine disarm in the current log and an obstructed legacy log is exactly as
    suspect as one with the obstruction alone, not less.
    """
    found = False
    for p in (tombstone_path(root), legacy_tombstone_path(root)):
        try:
            text = p.read_text(encoding="utf-8")
        except FileNotFoundError:
            continue
        except (OSError, UnicodeDecodeError):
            return "unreadable"
        if any(ln.strip() for ln in text.splitlines()):
            found = True
    return found


def _unreadable_tombstone_path(root):
    """Which of the two tombstone-log paths is the one `any_disarm()` just called
    "unreadable" — so the refusal it prints names the actual offending file, current or
    legacy, instead of always blaming `tombstone_path()`. None if neither is."""
    for p in (tombstone_path(root), legacy_tombstone_path(root)):
        try:
            p.read_text(encoding="utf-8")
        except FileNotFoundError:
            continue
        except (OSError, UnicodeDecodeError):
            return p
    return None


def _deactivate_locked(root, expected_brief=None):
    cur = read_pointer(root)
    if expected_brief is not None:
        expected_brief = norm_path(expected_brief)
        live = active_brief(root)
        if live != expected_brief:
            current = f"`{live}` is active" if live else "no brief is active"
            print(f"refused: `{expected_brief}` is not active; {current}")
            return 2
    p = active_path(root)
    if p.exists():
        # Turning the guard off must succeed even when the log cannot be appended to —
        # otherwise a directory planted at the log's path wedges the operator's own exit
        # path, ACTIVE is never unlinked, and clearing the jam by hand is the thing that
        # loses the record. The disarm is still counted: `any_disarm` reads an unreadable
        # log as at least as suspect as a recorded one.
        recorded = False
        if cur["brief"]:
            try:
                with open(tombstone_path(root), "a", encoding="utf-8") as f:
                    # The digest too: with it a reader can tell that the brief armed
                    # afterwards is not the brief that was disarmed, even once the old
                    # file is gone. That is what makes `repin` readable rather than
                    # merely alarming.
                    f.write(f"{cur['brief']} {cur['base_rev'] or '-'} "
                            f"{cur['sha256'] or '-'} "
                            f"{time.strftime('%Y-%m-%dT%H:%M:%S')}\n")
                recorded = True
            except OSError as e:
                print(f"WARNING: could not record the disarm in {tombstone_path(root)}: "
                      f"{e}\nNothing legitimate writes anything but a file there. Turning "
                      "the guard off anyway; every later arm here reports `repin` until "
                      "that path is a readable log again.")
        try:
            p.unlink()
        except OSError as e:
            # Fails closed: the pointer stands, so the guard is still armed and the next
            # write is still judged. The disarm is already in the log above, which is the
            # right way round — a recorded disarm that did not happen is noise, an
            # unrecorded one that did is a hole.
            print(f"could not remove {p}: {e}\nThe guard is STILL ARMED — nothing was "
                  "disarmed. The attempt is already recorded in "
                  f"{tombstone_path(root)}, so every later arm here reports `repin` "
                  "even though this one did not take effect.")
            return 2
        print("guard off")
        if recorded:
            print("recorded in .prompire/ACTIVE.tombstones — every later arm in this "
                  "repo reports `repin`, which is not the same claim as a pin from the "
                  "start")
            tomb = digest_of(tombstone_path(root))
            if tomb:
                print(f"to accept this in `--strict`: `--ack-disarms {tomb[:12]}` — a "
                      "later `--deactivate` changes this digest, so the acknowledgement "
                      "does not carry forward")
    else:
        print("no active brief")
    return 0


def deactivate(start, expected_brief=None):
    p = pathlib.Path(start).resolve()
    if p.is_file():
        p = p.parent          # callers pass the brief, not the directory holding it
    try:
        root = repo_root(p)
        with guard_state_lock(root):
            return _deactivate_locked(root, expected_brief)
    except RepoError as e:
        print(str(e))
        return 2


def git_show(root, rev, rel):
    """The file's content at that revision, or None if it was not tracked there."""
    r = subprocess.run(["git", "-C", str(root), "show", f"{rev}:{rel}"],
                       capture_output=True, text=True)
    return r.stdout if r.returncode == 0 else None


def armed_verdict(ptr, rel_brief, digest_now, declared):
    """What the armed pointer says about this brief, independent of where `base` came
    from. A string means: produce no verdict at all. None means: nothing here objects.

    This is the half of the guarantee that does not depend on the base at all. `base_rev`
    was never the only field worth buying — `scope`, `forbidden` and above all
    `dirty_baseline` are the agent's to write too, and check_scope.py skips a
    `dirty_baseline` path unconditionally, so appending one line to the brief turns a
    violation into "every change is inside the declared boundary". The digest recorded at
    `--activate` covers the whole file, so every one of those edits lands here.
    """
    if ptr["brief"] and ptr["brief"] != rel_brief:
        return (f"the guard here is armed on `{ptr['brief']}`, not on `{rel_brief}`.\n"
                "A verdict for a brief nobody armed is not a verdict for the task in "
                "progress, and a copy of the active brief with a wider `scope` is one "
                "Write away — `.prompire/**` is always inside the boundary.\nNo "
                "verdict was produced. `--deactivate` first if the task is over; while a "
                "guard is armed, the pointer says which brief the verdict is about and "
                "`--base` only says which revision.")
    if ptr["brief"] != rel_brief:
        return None
    if ptr["sha256"] and digest_now and ptr["sha256"] != digest_now:
        moved = (f"`base_rev` now says {declared}, where the brief said "
                 f"{ptr['base_rev']} when the guard was armed. "
                 if ptr["base_rev"] and ptr["base_rev"] != declared else "")
        return (f"the brief changed since the guard was armed. {moved}"
                "A digest of the whole file is recorded in .prompire/ACTIVE at "
                "`--activate`, because the base is not the only field that buys a "
                "verdict: one `dirty_baseline` entry excuses a violation, and a wider "
                "`scope` excuses all of them.\nNo verdict was produced. Revise a brief "
                "the way the brief itself demands — `--deactivate`, edit, re-run "
                "baseline.py, `--activate` — and the change is on the record instead of "
                "inside the verdict.")
    if ptr["base_rev"] and ptr["base_rev"] != declared:
        # Only reachable for a pointer written before digests existed; the digest above
        # catches this shape too, and with a better message.
        return (f"`base_rev` says {declared}, but the guard was armed on this brief at "
                f"{ptr['base_rev']}.\nRe-stamping `base_rev` at a commit that already "
                "contains the work empties the diff this check exists to read.\nNo "
                f"verdict was produced. To check against the pinned base, re-run with "
                f"`--base {ptr['base_rev']}`.")
    return None


def corroborate(root, ptr, rel_brief, base):
    """Does anything outside the brief agree the work started at `base`? (source, why).

    source "pin" = the guard was armed on this brief at this base, and has not been
    disarmed since. "repin" = the same record, but written after a `--deactivate`, so it
    is only as old as the re-arm and corroborates nothing about where the work started.
    source None = nothing outside the brief speaks to it; `why` says so and the caller
    flags it for a human rather than passing it off as checked.

    Why this exists: `base_rev` is a field in a file the agent can edit. An agent that
    commits its work and re-stamps `base_rev` at the resulting commit hands this tool a
    base that already contains the work, and everything downstream then reads an empty
    diff as a compliant one — a valid SHA, so B16 sees nothing wrong.

    The brief's own committed copy at `base` is a second, weaker record: it can raise the
    question but it cannot settle it. A brief cannot honestly name, as the commit it
    started from, a commit whose tree already carried a *different* base — unless the
    brief is a reusable slot at a stable path, which is the normal shape for a tracked
    brief, and then a second honest task re-stamps that field exactly as tampering would.
    History cannot tell those apart, so it raises a REVIEW and the pin remains the only
    authority. An absent field is not agreement either: a brief committed without a
    `base_rev` says nothing about where any work started, and reporting that as
    corroboration is worse than reporting nothing, because it suppresses the flag that
    would otherwise fire.

    Every record here is a file on disk. None survives an agent that rewrites it with a
    shell command, and nothing local can: the guarantee is not that evasion is
    impossible, it is that evasion stops being a silent one-field edit and becomes an act
    with a name.
    """
    if ptr["brief"] == rel_brief and ptr["base_rev"] == base:
        # Not `ptr["repin"]` alone: that flag is written INTO the pointer by
        # `--activate`, and the pointer is exactly the file a forged Write can recreate
        # from scratch — three lines, no `repin` line, and this would read it as a clean
        # first arm. The tombstone log is the independent record: if it says a disarm
        # ever happened anywhere in this repo, this pin is a repin whether or not it
        # says so about itself.
        if ptr["repin"] or any_disarm(root):
            tomb = digest_of(tombstone_path(root))
            ack = (f" Read the log and, if you accept it, re-run with "
                    f"`--ack-disarms {tomb[:12]}`." if tomb else "")
            return "repin", (
                f"`base_rev: {base}` is pinned in .prompire/ACTIVE, but that pin was "
                "written after a `--deactivate` (see .prompire/ACTIVE.tombstones). It "
                "records what the brief claimed at the re-arm, not where the work "
                "started, so it corroborates the base no better than the brief does."
                + ack)
        return "pin", None
    blob = git_show(root, base, rel_brief)
    was = None
    if blob is not None:
        m = re.search(r"^base_rev:\s*(\S+)", blob, re.M)
        was = m.group(1).strip() if m else None
    if was and was != base:
        return None, (
            f"`base_rev` says {base}, but the copy of this brief committed at {base} says "
            f"{was}. Either the field was re-stamped after the work — which moves the base "
            "past it and empties this diff — or this brief is a reusable slot and a second "
            "task honestly re-stamped it. Nothing in git can tell those two apart; read "
            "the brief's history and decide. Do not simply re-run against " + was +
            ", which folds the earlier task's work into this diff")
    return None, (
        f"nothing outside the brief corroborates `base_rev: {base}` — the guard is not "
        "armed on this brief, so the only record of where the work started is the field "
        "the agent could edit")


def same_commit(root, a, b):
    """Do these two revision spellings name the same commit?

    Not a string compare. `baseline.py` stamps a 12-character short SHA, so the obvious
    thing a reviewer types — `--base $(git rev-parse HEAD)` naming the very commit that is
    pinned — used to be reported as "the two disagree", and under `--strict` that REVIEW is
    exit 1. A spurious disagreement is worse than a missing one here: it teaches the
    operator that the flag is noise, and the flag's whole job is to be believed on the day
    the two really do differ.

    Falls back to comparing the strings when a side will not resolve — a pin naming a
    commit that no longer exists is a genuine disagreement, not an equality.
    """
    if a == b:
        return True

    def resolve(rev):
        try:
            return git(root, ["rev-parse", "--verify", "--quiet", f"{rev}^{{commit}}"]).strip()
        except RepoError:
            return None

    ra = resolve(a)
    return ra is not None and ra == resolve(b)


def changed(root, base):
    """[(status, path, origin)] for everything that differs from `base`, plus untracked.

    `git diff <rev>` compares the working tree to the revision, so staged, unstaged and
    already-committed work all show up. Untracked files come from status.
    """
    out = []
    raw = git(root, ["diff", "--name-status", "-z", base])
    toks = [t for t in raw.split("\0") if t != ""]
    i = 0
    while i < len(toks):
        st = toks[i]
        if st[:1] in ("R", "C") and i + 2 < len(toks):
            out.append((st[:1], toks[i + 2], toks[i + 1]))
            i += 3
        elif i + 1 < len(toks):
            out.append((st[:1], toks[i + 1], None))
            i += 2
        else:
            break
    for line in git(root, ["status", "--porcelain=v1", "-z", "--untracked-files=all"]).split("\0"):
        if line.startswith("?? "):
            out.append(("A", line[3:], None))
    seen, uniq = set(), []
    for st, p, o in out:
        if (p, o) in seen:
            continue
        seen.add((p, o))
        uniq.append((st, p, o))
    return uniq


def added_lines(root, base, path):
    """Lines the diff adds to `path`. Untracked files count as entirely added."""
    full = root / path
    tracked = subprocess.run(["git", "-C", str(root), "ls-files", "--error-unmatch", path],
                             capture_output=True, text=True).returncode == 0
    if not tracked:
        try:
            return full.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            return []
    diff = git(root, ["diff", "-U0", base, "--", path], check=False)
    return [ln[1:] for ln in diff.splitlines()
            if ln.startswith("+") and not ln.startswith("+++")]


def check(brief, root, base, brief_path):
    # The actual filesystem's fold behaviour, probed once for the whole run — not
    # assumed from the OS, and not re-probed per path below. See `fs_fold`'s docstring:
    # without this, `forbidden: [src/golden/**]` is defeated on a case-folding volume by
    # a diff entry spelled `src/GOLDEN/x.txt`.
    fold = fs_fold(root)
    editable = [str(t) for t in as_list(brief.get("tests_editable"))]
    ignored = [norm_path(p, fold) for p in as_list(brief.get("dirty_baseline"))]
    policy = tests_policy_of(brief)
    findings = []

    def add(kind, path, msg, fix=""):
        findings.append({"kind": kind, "path": path, "message": msg, "fix": fix})

    for status, path, origin in changed(root, base):
        for p in filter(None, (path, origin)):
            np = norm_path(p, fold)
            if _fold_in(np, [norm_path(brief_path, fold)], fold):
                # Only visible when the brief is tracked; `.prompire/` is normally
                # gitignored, which is exactly why the PreToolUse hook also protects it.
                if status in ("M", "R"):
                    add("REVIEW", np, "the brief itself changed since the base revision — "
                        "re-read it before trusting the acceptance block",
                        "confirm the revision was deliberate, then re-run baseline.py")
                elif status == "D":
                    add("REVIEW", np, "the brief itself was deleted since the base revision "
                        "— there is nothing left to re-read before trusting the acceptance "
                        "block", "confirm the deletion was deliberate; a missing brief is "
                        "not consent to skip the guard")
                continue
            if _fold_in(np, ignored, fold) or matches_any(ALWAYS_ALLOWED, np, fold):
                continue
            v = boundary_verdict(brief, np, policy, fold=fold)
            if v:
                add("VIOLATION", np, v[1], v[2])
                continue
            if (root / np).is_symlink():
                add("REVIEW", np, "is a symlink; the guard checks the link, not its target")

        if (not is_test_path(path, editable, fold)
                and not (origin and is_test_path(origin, editable, fold))):
            continue

        # --- tests policy (B7). Everything below is about test files only. ---
        # is_test=True: the gate above already established test-ness from path or origin —
        # a rename out of the test tree must still be judged, even though `np` itself (the
        # destination) would no longer match `is_test_path` on its own.
        np = norm_path(path, fold)
        v = tests_verdict(brief, np, policy, status=status, is_test=True, fold=fold)
        if v:
            add("VIOLATION", np, v[1], v[2])
            continue
        marks = sorted({m.group(0) for ln in added_lines(root, base, np)
                        for m in [SKIP_MARKERS.search(ln)] if m})
        if marks and policy != "authoring":
            add("VIOLATION", np, "the diff adds a disabling marker to a test file: "
                + ", ".join(marks[:3]),
                "a skipped test is a deleted test with extra steps")
        elif marks:
            add("REVIEW", np, "adds a disabling marker (" + ", ".join(marks[:3])
                + ") under tests_policy `authoring`")

    if policy in ("authoring", "named"):
        findings.append({"kind": "REVIEW", "path": ", ".join(editable) or "(tests)",
                         "message": f"tests_policy `{policy}` lets test files change; no "
                                    "checker can tell a repaired assertion from a weakened "
                                    "one", "fix": "read the test diff yourself"})
    return findings


def main(argv):
    args = [a for a in argv[1:] if not a.startswith("--")]

    if "--deactivate" in argv:
        expected = None
        if "--expect-brief" in argv:
            idx = argv.index("--expect-brief")
            if idx + 1 >= len(argv) or argv[idx + 1].startswith("--"):
                print("`--expect-brief` requires the repo-relative active brief path")
                return 2
            expected = argv[idx + 1]
        return deactivate(args[0] if args else pathlib.Path.cwd(), expected)

    if not args:
        print(__doc__.strip())
        return 2
    brief_path = args[0]
    explicit_base = argv[argv.index("--base") + 1] if "--base" in argv else None
    # Digest either side of the parse, so the bytes the verdict is read from are the
    # bytes the digest attests to. A brief rewritten in the window between the two reads
    # would otherwise be judged as one file and vouched for as another; this cannot
    # reproduce the bytes it parsed while showing an unchanged digest, so it refuses
    # instead of quietly disagreeing with itself.
    digest_before = digest_of(brief_path)
    try:
        brief = load_brief(brief_path)
        root = repo_root(pathlib.Path(brief_path).resolve().parent)
    except (BriefError, RepoError) as e:
        print(str(e))
        return 2
    digest_now = digest_of(brief_path)
    if digest_before != digest_now:
        print("the brief changed while this check was reading it — the file parsed and "
              "the file measured are not the same bytes.\nNo verdict was produced. Nothing "
              "should be writing to a brief while its own guard runs; re-run once the tree "
              "is still.")
        return 2

    try:
        rel_brief = norm_path(pathlib.Path(brief_path).resolve().relative_to(root))
    except ValueError:
        rel_brief = None

    if "--activate" in argv:
        if rel_brief is None:
            print(f"refused: {brief_path} is outside the repository at {root}")
            return 2
        return activate(brief, rel_brief, brief_path, root)

    rel_brief = rel_brief or norm_path(brief_path)
    if any_disarm(root) == "unreadable":
        bad = _unreadable_tombstone_path(root) or tombstone_path(root)
        print(f"{bad} exists but cannot be read as a log.\nThat file is "
              "how a disarm stays visible after the fact, and nothing legitimate puts "
              "anything but a file there — a directory at that path is one allowed Write "
              "that stops every later `--deactivate` from recording anything.\nNo verdict "
              "was produced. Make that path a readable file (or remove it, which is itself "
              "worth saying out loud) and re-run.")
        return 2

    # `--ack-disarms DIGEST` — a reviewer accepting the tombstone log exactly as it reads
    # right now. Deliberately checked after the unreadable-log refusal above, never
    # before it: an obstructed log is tampering, not a clean slate, and this flag must
    # not be a way past that. DIGEST is matched against the log's current bytes, so it
    # binds to *this* set of disarms — one more `--deactivate` changes the digest and
    # the same flag stops matching. See the docstring above.
    ack_arg = None
    if "--ack-disarms" in argv:
        idx = argv.index("--ack-disarms")
        ack_arg = argv[idx + 1] if idx + 1 < len(argv) else ""
        if not ACK_DIGEST_RE.fullmatch(ack_arg):
            print("`--ack-disarms` takes 12-64 hex characters — a prefix of the sha256 of "
                  ".prompire/ACTIVE.tombstones, not typed from memory. Read it off the "
                  "`repin` REVIEW or the `--deactivate` output and pass that.")
            return 2
        # A leftover .agent-brief/ACTIVE.tombstones means this repo is mid-migration off
        # the pre-0.4.0 state directory: its disarm history is split across two files,
        # and no single digest can speak for a set that is not yet one log. Refuse
        # outright rather than digest two files or silently ignore the older one — the
        # fix is one append and one delete, named here so this refusal is also the
        # instruction that gets past it.
        legacy = legacy_tombstone_path(root)
        if legacy.is_file():
            print(f"--ack-disarms refused: {legacy} still exists, so this repo has not "
                  "finished migrating off the old state directory and its disarm history "
                  "is split across two files — no one digest can speak for that.\n"
                  f"Append its contents to {tombstone_path(root)}, then delete {legacy}. "
                  "Once the migration is done, a digest of the combined log covers the "
                  "whole history and --ack-disarms works normally.\nNo verdict was "
                  "produced.")
            return 2

    ack_bound = False   # the digest given matches the tombstone log as it reads right now
    if ack_arg is not None:
        tomb = digest_of(tombstone_path(root))
        if tomb is None:
            # A fresh checkout legitimately has no `.prompire/` at all — it is
            # gitignored — so this is not a reason to refuse a verdict, only to say the
            # flag did nothing. Skipped under --json: this line is not part of that
            # contract and would corrupt output meant to be parsed as one object.
            if "--json" not in argv:
                print(f"--ack-disarms {ack_arg}: no {tombstone_path(root)} exists in this "
                      "repo — nothing has been disarmed here, so there is nothing to "
                      "acknowledge. Continuing to a normal verdict.")
        elif tomb.startswith(ack_arg.lower()):
            # The whole promise of this digest is that one more `--deactivate` moves it —
            # that is what makes an acknowledgement stop binding once it no longer applies.
            # A log the process cannot append to can never make that move, so an
            # acknowledgement of it is a promise with no way to come due: refuse, the same
            # way an obstructed log refuses above, rather than bind to something that has
            # stopped being able to record the next disarm.
            if not os.access(tombstone_path(root), os.W_OK):
                print(f"--ack-disarms {ack_arg} matches {tombstone_path(root)}, but that "
                      "file is not writable. The acknowledgement's whole premise is that a "
                      "later `--deactivate` changes it — a log nothing can append to can "
                      "never make that move, so there is no way to tell a disarm this "
                      "acknowledgement has not seen from one it has.\nNo verdict was "
                      "produced. Restore write access to the log and re-run.")
                return 2
            ack_bound = True
        else:
            print(f"--ack-disarms {ack_arg} does not match the tombstone log as it reads "
                  f"now (sha256 {tomb}). A mismatch means there are disarms in "
                  ".prompire/ACTIVE.tombstones this acknowledgement has not seen — that "
                  "is the property the flag exists to enforce. Read the log, then re-run "
                  f"with `--ack-disarms {tomb[:12]}` once you accept it.\nNo verdict was "
                  "produced.")
            return 2

    ptr = read_pointer(root)
    # Runs whichever way `base` is about to be established: an explicit `--base` chooses
    # the comparison, it does not vouch for the boundary the comparison is read against.
    # The brief's own declared base, never `--base`: this compares the brief against
    # the record made of it, which an explicit revision has no bearing on.
    armed = armed_verdict(ptr, rel_brief, digest_now,
                          str(brief.get("base_rev") or "").strip())
    if armed:
        print(armed)
        return 2

    if explicit_base is not None:
        base, source, note = explicit_base, "--base", None
        if (ptr["base_rev"] and ptr["brief"] == rel_brief
                and not same_commit(root, ptr["base_rev"], base)):
            note = (f"`--base {base}` overrides the base pinned when the guard was armed "
                    f"({ptr['base_rev']}) — a human choosing the comparison wins, but the "
                    "two disagree")
    else:
        rev = str(brief.get("base_rev") or "").strip()
        if not SHA_RE.fullmatch(rev):
            print(f"no base to check against — `base_rev` is {rev or 'missing'} in the "
                  "brief and no `--base` was given. Defaulting to HEAD would let an agent "
                  "that commits its own work erase the diff this check exists to read. "
                  "Run `baseline.py <brief> --write` to pin the commit this brief started "
                  "from, or pass `--base <rev>` explicitly.")
            return 2
        base, source, note = rev, None, None

    try:
        git(root, ["rev-parse", "--verify", "--quiet", base + "^{commit}"])
    except RepoError as e:
        print(str(e))
        return 2

    if source is None:
        source, note = corroborate(root, ptr, rel_brief, base)

    findings = check(brief, root, base, rel_brief)
    # `ack_bound` only ever silences *this* finding — the repin note — and only when it
    # is the reason `source` reads "repin" right now. A digest that happens to match
    # while the guard is unarmed, or armed on a different base, has nothing to bind to:
    # base_source stays whatever corroborate() said, unpromoted, and the finding text
    # below is untouched.
    acked_finding = None
    if note:
        msg = note
        if source == "repin" and ack_bound:
            msg += (" Acknowledged: `--ack-disarms` matches the tombstone log as it reads "
                    "now, so this finding alone does not fail `--strict` — the next "
                    "`--deactivate` changes the digest and this acknowledgement stops "
                    "matching.")
        finding = {"kind": "REVIEW", "path": rel_brief, "message": msg,
                  "fix": "" if source == "--base" else
                         "arm the guard with `--activate` before the work starts — "
                         "then the base, and the rest of the brief with it, has a "
                         "record outside the one file the agent can edit"}
        findings.append(finding)
        if source == "repin" and ack_bound:
            acked_finding = finding
    violations = [f for f in findings if f["kind"] == "VIOLATION"]
    reviews = [f for f in findings if f["kind"] == "REVIEW"]
    strict = "--strict" in argv
    # Every review still prints and still counts in `reviews` above — the ack does not
    # suppress the finding, only this one finding's power to fail --strict on its own.
    strict_reviews = [f for f in reviews if f is not acked_finding]

    if "--json" in argv:
        print(json.dumps({"base": base, "base_source": source,
                          "violations": len(violations),
                          "reviews": len(reviews), "findings": findings,
                          "ack_disarms_bound": ack_bound},
                         ensure_ascii=False, indent=2))
    else:
        for f in violations + reviews:
            print(f"{f['kind']:9s} {f['path']}: {f['message']}")
            if f["fix"]:
                print(f"          → {f['fix']}")
        print(f"\n{len(violations)} violation(s), {len(reviews)} review flag(s) "
              f"— scope vs {base} ({BASE_SOURCE[source]})")
        if not violations:
            print("every change is inside the declared boundary"
                  + (" (review flags are for a human)" if reviews else ""))
    return 1 if violations or (strict and strict_reviews) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
