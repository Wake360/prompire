#!/usr/bin/env python3
"""The PreToolUse guard refuses the writes the brief does not allow — before they land.

Run: python3 tests/hook.py
Exit 0 = every case produced the expected exit code.

Each case builds a throwaway repo, activates a brief, feeds the hook one synthetic tool
call on stdin and checks the exit code. 2 = blocked, 0 = allowed.

The cases that must exit 0 matter as much as the ones that must exit 2. This hook runs on
every write in every project on the machine: one that blocks unrelated sessions gets
uninstalled, and an uninstalled guard protects nothing.
"""
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
import unicodedata

HERE = pathlib.Path(__file__).resolve().parent
SKILL = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(SKILL))

import brief_common  # noqa: E402
import fixtures  # noqa: E402

HOOK = str(SKILL / "hook_scope_guard.py")
GUARD = str(SKILL / "check_scope.py")

BRIEF = """goal: Fix the off-by-one in src/cart.total().
scope:
  - src/cart.py
  - docs/**
forbidden:
  - golden/**
  - docs/secret/**
tests_policy: {policy}
{editable}acceptance:
  - cmd: python3 -m unittest -q tests.test_total
    expect: exit 0
    transition: flip
autonomy: ask
"""

NAMED = "tests_editable:\n  - tests/test_cart.py\n"

# expect_exit for a case whose correct answer depends on whether this volume folds case
# or Unicode normalisation — resolved at runtime by _fs_folds(), see below.
FOLD_DEPENDENT = "fold-dependent"

# (name, policy, editable, tool, file_path, cwd_rel, expect_exit, expect_substr)
#
# file_path is normally a relative string, resolved against cwd exactly as target_of()
# does it. A ("abs", relpath) tuple instead sends `str(repo / relpath)` as an absolute
# path — the shape Claude Code's Write/Edit/NotebookEdit tools actually send in
# production; see abs-in-scope / abs-cwd-outside-repo below.
CASES = [
    ("in-scope",               "immutable", "",    "Write",     "src/cart.py",            ".",  0, ""),
    ("outside-scope",          "immutable", "",    "Write",     "src/other.py",           ".",  2, "outside `scope`"),
    ("forbidden-wins",         "immutable", "",    "Write",     "golden/report.txt",      ".",  2, "forbidden"),
    # docs/secret/** sits *inside* the docs/** scope entry — this is the case that
    # actually pins forbidden-beats-scope; forbidden-wins above is outside scope too, so
    # it would block either way and only the "forbidden" substring assertion matters.
    ("forbidden-inside-scope", "immutable", "",    "Write",     "docs/secret/report.txt", ".",  2, "forbidden"),
    ("test-immutable",         "immutable", "",    "Edit",      "tests/test_cart.py",     ".",  2, "tests_policy"),
    ("test-named-listed",      "named",     NAMED, "Edit",      "tests/test_cart.py",     ".",  0, ""),
    ("test-named-other",       "named",     NAMED, "Edit",      "tests/test_total.py",    ".",  2, "tests_editable"),
    ("prompire-notes",      "immutable", "",    "Write",     ".prompire/notes.md",  ".",  0, ""),
    # The pointer and its tombstone log are named exactly, not matched by prefix: an
    # ordinary note whose name merely starts with "active" is a working file like any
    # other, and blocking it would make the guard cost something it never meant to.
    ("prompire-active-note", "immutable", "",   "Write", ".prompire/active-notes.md", ".", 0, ""),
    ("self-edit-brief",        "immutable", "",    "Edit",      ".prompire/spec.yaml", ".",  2, "active brief"),
    ("self-edit-pointer",      "immutable", "",    "Write",     ".prompire/ACTIVE",    ".",  2, "guard pointer"),
    # The tombstone log is what makes `--deactivate && --activate` visible as a re-arm
    # rather than a fresh pin. A record of a disarm that the disarmed party can rewrite
    # is not a record, so it is protected exactly like the pointer it sits beside.
    ("self-edit-tombstones",   "immutable", "",    "Write", ".prompire/ACTIVE.tombstones", ".", 2, "guard pointer"),
    # …and BENEATH either of them. A last-two-components match let these through, and the
    # write lands a *directory* where a state file belongs: --deactivate then dies on
    # IsADirectoryError without disarming, and a log that cannot be written records
    # nothing. One allowed Write disabled the tombstone for good.
    ("under-tombstones",       "immutable", "",    "Write", ".prompire/ACTIVE.tombstones/x", ".", 2, "guard pointer"),
    ("under-pointer",          "immutable", "",    "Write", ".prompire/ACTIVE/x",  ".",  2, "guard pointer"),
    ("nested-under-tombstones", "immutable", "",   "Write", "src/.prompire/ACTIVE.tombstones/x", ".", 2, "guard pointer"),
    # C1 regression: a pointer planted anywhere below root must be refused exactly like
    # the root one — ALWAYS_ALLOWED lets .prompire/** through everywhere, so without
    # the nested check this write would be permitted and later shadow the real brief.
    ("nested-pointer-plant",   "immutable", "",    "Write",     "src/.prompire/ACTIVE", ".", 2, "guard pointer"),
    # C1'a/C1'b: APFS/HFS+ are case-insensitive, so a case-variant write lands on the
    # very same file as the canonical spelling. These must block exactly like the
    # exact-case forms above.
    ("case-variant-pointer",   "immutable", "",    "Write",     ".prompire/active",   ".",  2, "guard pointer"),
    # ...but the brief's own name is matched by OS-level identity, so on a case-sensitive
    # volume `Spec.yaml` is a genuinely different file and 0 is the right answer there.
    # The pointer case above is a shape match and blocks on every volume.
    ("case-variant-brief",     "immutable", "",    "Write",     ".prompire/Spec.yaml", ".",  FOLD_DEPENDENT, "active brief"),
    # C1'd: `..` through a missing directory (ENOENT) or through an existing *file*
    # (ENOTDIR) leaves the raw target unstat'able, while the write tool normalises `..`
    # lexically before it touches the filesystem and lands on the brief regardless. The
    # identity check has to run on the resolved path, not the spelling the agent chose.
    ("dotdot-brief-missing-dir", "immutable", "",  "Write",     ".prompire/nope/../spec.yaml", ".", 2, "active brief"),
    ("dotdot-brief-via-file",  "immutable", "",    "Write",     "src/cart.py/../../.prompire/spec.yaml", ".", 2, "active brief"),
    ("multi-edit-in-scope",    "immutable", "",    "MultiEdit", "src/cart.py",            ".",  0, ""),
    ("nested-cwd",             "immutable", "",    "Write",     "cart.py",               "src", 0, ""),
    ("unwatched-tool",         "immutable", "",    "Bash",      "src/other.py",           ".",  0, ""),
    ("notebook-path",          "immutable", "",    "NotebookEdit", "src/other.ipynb",     ".",  2, "outside `scope`"),
    ("abs-in-scope",           "immutable", "",    "Write",     ("abs", "src/cart.py"),   ".",  0, ""),
    # I1 regression: cwd is OUTSIDE the repo entirely (repo's own parent directory);
    # only an absolute target under the armed root can reveal whether root-derivation
    # falls back to cwd alone. Before the fix, find_root(cwd) finds nothing and the
    # write is allowed even though the target is outside `scope`.
    ("abs-cwd-outside-repo",   "immutable", "",    "Write",     ("abs", "other/random.py"), "..", 2, "outside `scope`"),
]


def run_hook(repo, tool, file_path, cwd_rel, raw=None):
    fp = str(repo / file_path[1]) if isinstance(file_path, tuple) else file_path
    payload = raw if raw is not None else json.dumps({
        "hook_event_name": "PreToolUse", "tool_name": tool, "cwd": str(repo / cwd_rel),
        "tool_input": ({"notebook_path": fp} if tool == "NotebookEdit"
                       else {"file_path": fp}),
    })
    r = subprocess.run([sys.executable, HOOK], input=payload,
                       capture_output=True, text=True)
    return r.returncode, r.stderr


def _fs_folds(where, canonical, variant):
    """Does this volume open `variant` and `canonical` as the same directory entry?

    APFS and HFS+ fold both case and Unicode normalisation; ext4 folds neither. On a
    folding volume a variant-spelled write lands on the active brief itself and must be
    blocked; on a preserving volume it is a genuinely different file inside
    `.prompire/`, which ALWAYS_ALLOWED permits, and 0 is correct. So the expected exit
    code is a property of the volume the suite runs on, not of the guard — hard-coding 2
    turns the first Linux run red on two security cases for a non-defect.
    """
    probe = pathlib.Path(where) / canonical
    probe.write_text("probe", encoding="utf-8")
    try:
        return (pathlib.Path(where) / variant).exists()
    finally:
        probe.unlink()


def main():
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="prompire-hook-"))
    case_folds = _fs_folds(tmp, "FoldProbe.tmp", "foldprobe.tmp")
    norm_folds = _fs_folds(tmp, unicodedata.normalize("NFC", "nfold-probe-é.tmp"),
                           unicodedata.normalize("NFD", "nfold-probe-é.tmp"))
    # `brief_common.fs_fold()` is the ONE probe check_scope.py and this hook both call
    # in production (Task 14). This checks it against ground truth computed
    # independently right above, so a bug in the shared probe itself would show up here
    # instead of every FOLD_DEPENDENT case below quietly trusting the same function
    # they are meant to be testing.
    assert brief_common.fs_fold(tmp) == (case_folds, norm_folds), (
        f"brief_common.fs_fold(tmp) = {brief_common.fs_fold(tmp)}, expected "
        f"{(case_folds, norm_folds)} from the independent probe above")
    bad = []
    for name, policy, editable, tool, fp, cwd_rel, want_rc, want_sub in CASES:
        if want_rc == FOLD_DEPENDENT:
            want_rc, want_sub = (2, want_sub) if case_folds else (0, "")
        repo = fixtures.build(tmp / name)
        fixtures.write(repo, ".prompire/spec.yaml",
                       BRIEF.format(policy=policy, editable=editable))
        subprocess.run([sys.executable, GUARD, ".prompire/spec.yaml", "--activate"],
                       cwd=str(repo), capture_output=True, text=True)
        rc, err = run_hook(repo, tool, fp, cwd_rel)
        why = ""
        if rc != want_rc:
            why = f"exit {rc}, wanted {want_rc} — {err.strip()[:160]}"
        elif want_sub and want_sub not in err:
            why = f"stderr missing {want_sub!r} — {err.strip()[:160]}"
        if why:
            bad.append(f"{name}: {why}")
        print(f"{'FAIL' if why else 'pass'}  {name}")

    # --- fail-open cases: infrastructure trouble must never block an unrelated write ---
    repo = fixtures.build(tmp / "failopen")
    fixtures.write(repo, ".prompire/spec.yaml", BRIEF.format(policy="immutable", editable=""))
    subprocess.run([sys.executable, GUARD, ".prompire/spec.yaml", "--activate"],
                   cwd=str(repo), capture_output=True, text=True)
    open_cases = [
        ("malformed-stdin", lambda: run_hook(repo, "Write", "src/other.py", ".", raw="not json")),
        ("no-active-brief", lambda: (_deactivate(repo),
                                     run_hook(repo, "Write", "src/other.py", "."))[1]),
        ("unreadable-brief", lambda: (_point_at_nothing(repo),
                                      run_hook(repo, "Write", "src/other.py", "."))[1]),
        ("no-repo-anywhere", lambda: run_hook(tmp, "Write", str(tmp / "x.txt"), ".")),
    ]
    for name, fn in open_cases:
        rc, err = fn()
        ok = rc == 0
        if not ok:
            bad.append(f"{name}: exit {rc}, wanted 0 — the guard failed closed\n        {err[:160]}")
        print(f"{'pass' if ok else 'FAIL'}  {name}")

    # --- cases needing a bespoke setup the (name, ..., cwd_rel) tuple can't express ---
    extra_cases = []

    # m-new1: cwd is armed, but the absolute target sits under no armed root at all —
    # the only thing that still lets a cwd-only brief matter now that root-derivation
    # is target-first. Without this fallback, an absolute write anywhere outside any
    # armed repo would have nothing to enforce `outside-repo` with.
    unarmed = pathlib.Path(tempfile.mkdtemp(prefix="prompire-hook-unarmed-"))
    repo = fixtures.build(tmp / "cwd-armed-target-unarmed")
    fixtures.write(repo, ".prompire/spec.yaml", BRIEF.format(policy="immutable", editable=""))
    subprocess.run([sys.executable, GUARD, ".prompire/spec.yaml", "--activate"],
                   cwd=str(repo), capture_output=True, text=True)
    extra_cases.append(("cwd-armed-target-unarmed",
                        run_hook(repo, "Write", str(unarmed / "x.txt"), "."),
                        2, "outside the repository"))
    shutil.rmtree(unarmed, ignore_errors=True)

    # I-new1: cwd is repo A, armed with the narrow brief above; the absolute target is
    # inside a SEPARATE armed repo B whose own brief is wide open. B's brief correctly
    # speaks for B's own files, but A's own boundary must still apply — an agent bound
    # by A must not escape into any other armed repo just because that repo's brief
    # happens to permit the path.
    repo_a = fixtures.build(tmp / "cross-repo-a")
    fixtures.write(repo_a, ".prompire/spec.yaml", BRIEF.format(policy="immutable", editable=""))
    subprocess.run([sys.executable, GUARD, ".prompire/spec.yaml", "--activate"],
                   cwd=str(repo_a), capture_output=True, text=True)
    repo_b = fixtures.build(tmp / "cross-repo-b")
    fixtures.write(repo_b, ".prompire/spec.yaml",
                   "goal: wide open\nscope:\n  - '**'\ntests_policy: immutable\nacceptance:\n"
                   "  - cmd: \"true\"\n    expect: exit 0\nautonomy: auto\n")
    subprocess.run([sys.executable, GUARD, ".prompire/spec.yaml", "--activate"],
                   cwd=str(repo_b), capture_output=True, text=True)
    extra_cases.append(("cross-repo-escape",
                        run_hook(repo_a, "Write", str(repo_b / "anything.md"), "."),
                        2, "outside the repository"))

    # A pointer whose brief declares a `base_rev` carries a second line — the base pinned
    # by --activate, which check_scope.py keeps out here where a write tool cannot reach
    # it. The hook must go on reading line 1 and nothing else: parsing the whole file
    # would resolve to no brief at all and silently disarm the guard for every armed
    # repo whose brief has been through baseline.py, which is all of them.
    repo = fixtures.build(tmp / "pinned-pointer")
    head = fixtures.git(repo, "rev-parse", "HEAD").strip()
    fixtures.write(repo, ".prompire/spec.yaml",
                   BRIEF.format(policy="immutable", editable="") + f"base_rev: {head}\n")
    subprocess.run([sys.executable, GUARD, ".prompire/spec.yaml", "--activate"],
                   cwd=str(repo), capture_output=True, text=True)
    assert f"base_rev {head}" in (repo / ".prompire" / "ACTIVE").read_text(
        encoding="utf-8"), "sanity: --activate wrote no pin, so this case proves nothing"
    extra_cases.append(("pinned-pointer-still-blocks",
                        run_hook(repo, "Write", "src/other.py", "."),
                        2, "outside `scope`"))
    extra_cases.append(("pinned-pointer-still-allows",
                        run_hook(repo, "Write", "src/cart.py", "."), 0, ""))

    # I-new3 (walk on): a broken pointer nested below the real root must not shadow it.
    # This simulates a pre-existing or Bash-planted garbage pointer — something the hook
    # itself cannot prevent from being created, since it only gates Write/Edit/
    # MultiEdit/NotebookEdit. What matters is that its mere existence does not disarm the
    # subtree beneath it: the real root brief above must still govern a write inside it.
    repo = fixtures.build(tmp / "walk-on-shadow")
    fixtures.write(repo, ".prompire/spec.yaml", BRIEF.format(policy="immutable", editable=""))
    subprocess.run([sys.executable, GUARD, ".prompire/spec.yaml", "--activate"],
                   cwd=str(repo), capture_output=True, text=True)
    fixtures.write(repo, "src/.prompire/ACTIVE", "nope/missing.yaml\n")
    # cwd is INSIDE src/ too, not just the target — matching the actual adversarial
    # shape (a session cd'ed into the shadowed subtree). With cwd left at repo root, the
    # cwd-side root-derivation alone would already find the real brief directly and mask
    # a disabled walk-on; the target must sit inside src/ so its own walk actually passes
    # the planted pointer before reaching the real root above it.
    extra_cases.append(("walk-on-past-broken-nested-pointer",
                        run_hook(repo, "Write", "other.py", "src"),
                        2, "outside `scope`"))

    # I-new4: "broken" isn't only unloadable YAML — an unreadable or non-UTF-8 nested
    # pointer must ALSO be walked past. read_text()/load_brief() failing with OSError or
    # UnicodeDecodeError instead of the brief-parsing error must not escape the walk and
    # fail the WHOLE call open (both roots), which would re-open exactly the shadow
    # walk-on was added to close.
    repo = fixtures.build(tmp / "walk-on-non-utf8-pointer")
    fixtures.write(repo, ".prompire/spec.yaml", BRIEF.format(policy="immutable", editable=""))
    subprocess.run([sys.executable, GUARD, ".prompire/spec.yaml", "--activate"],
                   cwd=str(repo), capture_output=True, text=True)
    nested_dir = repo / "src" / ".prompire"
    nested_dir.mkdir(parents=True, exist_ok=True)
    (nested_dir / "ACTIVE").write_bytes(b"\xff\xfe\x00garbage")
    extra_cases.append(("walk-on-past-non-utf8-nested-pointer",
                        run_hook(repo, "Write", "other.py", "src"),
                        2, "outside `scope`"))

    repo = fixtures.build(tmp / "walk-on-chmod000-pointer")
    fixtures.write(repo, ".prompire/spec.yaml", BRIEF.format(policy="immutable", editable=""))
    subprocess.run([sys.executable, GUARD, ".prompire/spec.yaml", "--activate"],
                   cwd=str(repo), capture_output=True, text=True)
    nested_dir = repo / "src" / ".prompire"
    nested_dir.mkdir(parents=True, exist_ok=True)
    nested_pointer = nested_dir / "ACTIVE"
    nested_pointer.write_text("spec.yaml\n", encoding="utf-8")
    nested_pointer.chmod(0o000)
    extra_cases.append(("walk-on-past-chmod000-nested-pointer",
                        run_hook(repo, "Write", "other.py", "src"),
                        2, "outside `scope`"))
    nested_pointer.chmod(0o644)  # restore so cleanup can remove it

    # C1'e: the hook has to model the WRITE TOOL's path semantics, not the OS's. The tool
    # collapses `..` lexically and only then lets the kernel resolve symlinks, so
    # `flink/..` is the link's OWN parent; realpath alone follows the link first and calls
    # it the target's parent. Judge one directory, write in another — and with the brief
    # one `..` away that is a total disarm. Every `node_modules/.bin/*` entry npm writes
    # has this exact shape, so the pivot costs an adversary nothing.
    repo = fixtures.build(tmp / "symlink-dotdot-brief")
    fixtures.write(repo, ".prompire/spec.yaml", BRIEF.format(policy="immutable", editable=""))
    subprocess.run([sys.executable, GUARD, ".prompire/spec.yaml", "--activate"],
                   cwd=str(repo), capture_output=True, text=True)
    (repo / "flink").symlink_to(repo / "src" / "cart.py")
    extra_cases.append(("symlink-dotdot-onto-brief",
                        run_hook(repo, "Write", "flink/../.prompire/spec.yaml", "."),
                        2, "active brief"))

    # The same divergence moves the boundary without touching the brief: judged inside
    # `docs/**`, lands in `golden/**`.
    repo = fixtures.build(tmp / "symlink-dotdot-forbidden")
    fixtures.write(repo, ".prompire/spec.yaml", BRIEF.format(policy="immutable", editable=""))
    subprocess.run([sys.executable, GUARD, ".prompire/spec.yaml", "--activate"],
                   cwd=str(repo), capture_output=True, text=True)
    (repo / "docs" / "sub").mkdir(parents=True, exist_ok=True)
    (repo / "dclink").symlink_to(repo / "docs" / "sub")
    extra_cases.append(("symlink-dotdot-into-forbidden",
                        run_hook(repo, "Write", "dclink/../golden/report.txt", "."),
                        2, "forbidden"))

    # The root walk starts from the RESOLVED target's parent, not the lexical one. A
    # symlink whose final component points into an armed repo lands the write inside that
    # repo, so that repo's brief has to judge it — with the lexical parent, neither the
    # target side nor an unarmed cwd finds any root and the write sails through. Creating
    # the symlink needs Bash (the documented gap); the write that follows is a Write, and
    # this is what it meets.
    repo = fixtures.build(tmp / "symlink-target")
    fixtures.write(repo, ".prompire/spec.yaml", BRIEF.format(policy="immutable", editable=""))
    subprocess.run([sys.executable, GUARD, ".prompire/spec.yaml", "--activate"],
                   cwd=str(repo), capture_output=True, text=True)
    outside = pathlib.Path(tempfile.mkdtemp(prefix="prompire-hook-outside-"))
    (outside / "link.py").symlink_to(repo / "src" / "other.py")
    extra_cases.append(("symlink-target-into-armed-repo",
                        run_hook(outside, "Write", str(outside / "link.py"), "."),
                        2, "outside `scope`"))
    shutil.rmtree(outside, ignore_errors=True)

    # C1'c: a Unicode-normalisation variant of the active brief's own (user-chosen,
    # non-ASCII) filename must not clobber it. `spec.yaml` has no decomposable
    # character, so this needs a distinct brief filename to actually exercise the bug —
    # APFS is normalisation-insensitive: writing the NFD spelling of an NFC name opens
    # the same directory entry.
    repo = fixtures.build(tmp / "unicode-brief")
    nfc_name = unicodedata.normalize("NFC", "spéc.yaml")  # "spéc.yaml", precomposed
    nfd_name = unicodedata.normalize("NFD", "spéc.yaml")  # combining accent, decomposed
    assert nfc_name != nfd_name, "sanity: these must be different byte spellings"
    fixtures.write(repo, f".prompire/{nfc_name}", BRIEF.format(policy="immutable", editable=""))
    subprocess.run([sys.executable, GUARD, f".prompire/{nfc_name}", "--activate"],
                   cwd=str(repo), capture_output=True, text=True)
    # Same platform caveat as case-variant-brief: on a normalisation-preserving volume
    # the NFD spelling is a different file and 0 is correct.
    nfd_want = 2 if _fs_folds(tmp, nfc_name, nfd_name) else 0
    extra_cases.append(("unicode-normalization-variant-brief",
                        run_hook(repo, "Write", f".prompire/{nfd_name}", "."),
                        nfd_want, "active brief" if nfd_want else ""))

    # m-new13: a NUL byte in a *directory* component made `Path.resolve()` raise
    # ValueError before any root was found, and main()'s catch-all turned that into a
    # fail-open on a string the agent chose. Both positions must fail closed; nothing
    # legitimate is lost, since no write tool can create either path.
    repo = fixtures.build(tmp / "nul-path")
    fixtures.write(repo, ".prompire/spec.yaml", BRIEF.format(policy="immutable", editable=""))
    subprocess.run([sys.executable, GUARD, ".prompire/spec.yaml", "--activate"],
                   cwd=str(repo), capture_output=True, text=True)
    extra_cases.append(("nul-in-dirname",
                        run_hook(repo, "Write", "no\x00pe/x.py", "."), 2, "unnameable-path"))
    extra_cases.append(("nul-in-filename",
                        run_hook(repo, "Write", "src/x\x00.py", "."), 2, "unnameable-path"))

    # I2: `matches_any`/`glob_re` compared pattern to path as plain strings, and
    # `Path.resolve()` does not canonicalise case on macOS — APFS/HFS+ fold case by
    # default. `scope: [src/**]` covers `src/GOLDEN/x.txt` because `**` matches any
    # spelling of a directory name; `forbidden: [src/golden/**]` used to miss it,
    # because the literal segment `golden` was compared case-sensitively. On a folding
    # volume the two paths are the SAME directory, so this used to let a write land
    # straight inside a directory the brief names as forbidden, just by pressing shift.
    # FOLD_DEPENDENT because on a genuinely case-sensitive volume `src/GOLDEN/` really
    # is a different, unforbidden directory, and 0 is the correct answer there.
    fold_brief = ("goal: Refactor helpers under src/.\n"
                  "scope:\n  - src/**\n"
                  "forbidden:\n  - src/golden/**\n"
                  "tests_policy: immutable\n"
                  "acceptance:\n  - cmd: \"true\"\n    expect: exit 0\n"
                  "autonomy: auto\n")
    repo = fixtures.build(tmp / "forbidden-case-variant")
    fixtures.write(repo, ".prompire/spec.yaml", fold_brief)
    subprocess.run([sys.executable, GUARD, ".prompire/spec.yaml", "--activate"],
                   cwd=str(repo), capture_output=True, text=True)
    case_want = (2, "forbidden") if case_folds else (0, "")
    extra_cases.append(("forbidden-case-variant",
                        run_hook(repo, "Write", "src/GOLDEN/x.txt", "."), *case_want))

    # I2, normalisation half: same shape, an NFD-spelled write against an NFC-spelled
    # `forbidden` entry. APFS folds Unicode normalisation independently of its
    # case-sensitivity setting (see unicode-normalization-variant-brief above), so this
    # can disagree with the case probe even on the very same volume.
    nfc_dir = unicodedata.normalize("NFC", "café")
    nfd_dir = unicodedata.normalize("NFD", "café")
    assert nfc_dir != nfd_dir, "sanity: these must be different byte spellings"
    norm_fold_brief = ("goal: Update docs under docs/.\n"
                       "scope:\n  - docs/**\n"
                       f"forbidden:\n  - docs/{nfc_dir}/**\n"
                       "tests_policy: immutable\n"
                       "acceptance:\n  - cmd: \"true\"\n    expect: exit 0\n"
                       "autonomy: auto\n")
    repo = fixtures.build(tmp / "forbidden-norm-variant")
    fixtures.write(repo, ".prompire/spec.yaml", norm_fold_brief)
    subprocess.run([sys.executable, GUARD, ".prompire/spec.yaml", "--activate"],
                   cwd=str(repo), capture_output=True, text=True)
    norm_want = (2, "forbidden") if norm_folds else (0, "")
    extra_cases.append(("forbidden-normalization-variant",
                        run_hook(repo, "Write", f"docs/{nfd_dir}/x.txt", "."), *norm_want))

    for name, (rc, err), want_rc, want_sub in extra_cases:
        why = ""
        if rc != want_rc:
            why = f"exit {rc}, wanted {want_rc} — {err.strip()[:160]}"
        elif want_sub and want_sub not in err:
            why = f"stderr missing {want_sub!r} — {err.strip()[:160]}"
        if why:
            bad.append(f"{name}: {why}")
        print(f"{'FAIL' if why else 'pass'}  {name}")

    # --- Task 19 (C1/C2): the guard pointer and its disarm log are refused even where
    # NO guard has EVER been armed — the exact fail-open window C1 and C2 exploited.
    # Every repo below is `fixtures.build`-only: no `.prompire/spec.yaml` is ever
    # written and `check_scope.py --activate` is never run, so `_find_governing` finds
    # nothing on either side. Before the fix, `decide()` fell through the
    # not-governing `return 0` before this write was ever judged; a Write to
    # `.prompire/ACTIVE` forged a `pin` from nothing, and one to
    # `.prompire/ACTIVE.tombstones` erased a disarm history that was never armed
    # against in the first place.
    UNARMED_CASES = [
        # (name, tool, file_path, cwd_rel, want_rc, want_sub)
        ("unarmed-pointer-refused", "Write", ".prompire/ACTIVE", ".", 2, "guard pointer"),
        ("unarmed-tombstones-refused", "Write", ".prompire/ACTIVE.tombstones", ".",
         2, "guard pointer"),
        ("unarmed-nested-pointer-refused", "Write", "src/.prompire/ACTIVE", ".",
         2, "guard pointer"),
        # C1's own literal case-fold spellings: an uppercase directory and an
        # uppercase-first tombstones filename.
        ("unarmed-case-fold-pointer-refused", "Write", ".PROMPIRE/active", ".",
         2, "guard pointer"),
        ("unarmed-case-fold-tombstones-refused", "Write", ".prompire/Active.Tombstones",
         ".", 2, "guard pointer"),
        # Lexical `..` traversal: the write tool collapses this to `.prompire/ACTIVE`
        # before it ever touches the filesystem, and `_as_written` has to model that.
        ("unarmed-dotdot-refused", "Write", "x/../.prompire/ACTIVE", ".",
         2, "guard pointer"),
        # The ACTIVE.tombstones-as-a-directory shape: a write *beneath* the log must be
        # refused too, or the write lands a directory where the log file belongs.
        ("unarmed-under-tombstones-refused", "Write", ".prompire/ACTIVE.tombstones/x",
         ".", 2, "guard pointer"),
        # NFD spelling: `_looks_like_active_pointer` NFC-normalises every path segment
        # before comparing. None of ".prompire", "ACTIVE" or "active.tombstones" has
        # a decomposable character, so an NFD-normalised copy of this literal path is
        # BYTE-IDENTICAL to the NFC one — this case cannot tell "normalises" from "is a
        # no-op" for these three names, and removing the `unicodedata.normalize` call
        # would not make it fail. It is here because the fix must not regress that call
        # at all, not because this literal can exercise it; a real NFC/NFD divergence
        # (the brief's own filename) is pinned separately, in the armed-state
        # `unicode-normalization-variant-brief` case above.
        ("unarmed-nfd-spelling-refused",
         "Write", unicodedata.normalize("NFD", ".prompire/ACTIVE"), ".",
         2, "guard pointer"),
        # The narrowness pin: an ordinary note that merely starts with "active" stays
        # writable in a repo that has never armed a guard, exactly as it does in one
        # that has — `.prompire/` is where working notes and renders live.
        ("unarmed-active-notes-allowed", "Write", ".prompire/active-notes.md", ".",
         0, ""),
        # The no-collateral pin: this fix must not turn the hook into something that
        # refuses writes in a repo that never opted into any of this.
        ("unarmed-ordinary-file-allowed", "Write", "src/other.py", ".", 0, ""),

        # Task 20: the SAME protection, under the pre-0.4.0 state-directory name.
        # `~/LifeOS/.agent-brief/ACTIVE.tombstones` is real, live disarm history from
        # before the rename — once `any_disarm()` reads it (check_scope.py), a bare
        # Write emptying it is exactly the C2 hole `0.3.1` closed for `.prompire/`, just
        # under the old name. No `--activate` is ever run in any of these repos either.
        ("unarmed-legacy-pointer-refused", "Write", ".agent-brief/ACTIVE", ".",
         2, "guard pointer"),
        ("unarmed-legacy-tombstones-refused", "Write", ".agent-brief/ACTIVE.tombstones",
         ".", 2, "guard pointer"),
        ("unarmed-legacy-nested-pointer-refused", "Write",
         "src/.agent-brief/ACTIVE", ".", 2, "guard pointer"),
        ("unarmed-legacy-case-fold-pointer-refused", "Write", ".AGENT-BRIEF/active", ".",
         2, "guard pointer"),
        # The narrowness pin under the legacy name too: an ordinary note in
        # `.agent-brief/` stays writable — that directory is not wholesale off-limits,
        # only the two record files (and paths beneath them) are.
        ("unarmed-legacy-active-notes-allowed", "Write",
         ".agent-brief/active-notes.md", ".", 0, ""),
    ]
    for name, tool_, fp, cwd_rel, want_rc, want_sub in UNARMED_CASES:
        repo = fixtures.build(tmp / name)
        rc, err = run_hook(repo, tool_, fp, cwd_rel)
        why = ""
        if rc != want_rc:
            why = f"exit {rc}, wanted {want_rc} — {err.strip()[:160]}"
        elif want_sub and want_sub not in err:
            why = f"stderr missing {want_sub!r} — {err.strip()[:160]}"
        if why:
            bad.append(f"{name}: {why}")
        print(f"{'FAIL' if why else 'pass'}  {name}")

    # Task 14 fix round 1 (C1): `_fs_probe`'s canonical file vanishing between
    # `write_text()` and its own `exists()` check must be read as inconclusive — never
    # as "does not fold". That window is exactly what a concurrent probe's `unlink()`
    # used to land in when two callers shared a fixed filename; a real race is
    # timing-dependent and this suite must not become flaky pinning one, so the vanish
    # is forced deterministically instead, by making `write_text` remove the file the
    # instant it lands. The property under test is the fallback itself, not the odds of
    # hitting it.
    _orig_write_text = pathlib.Path.write_text

    def _vanishing_write_text(self, *a, **kw):
        result = _orig_write_text(self, *a, **kw)
        self.unlink()
        return result

    pathlib.Path.write_text = _vanishing_write_text
    try:
        probe_result = brief_common._fs_probe(
            tmp, "vanish-probe.tmp", "this-name-never-exists-either.tmp")
    finally:
        pathlib.Path.write_text = _orig_write_text
    vanish_ok = probe_result is True

    # Task 14 fix round 2 (S1): the mutation table above shows fixed probe names PLUS
    # the vanish-fallback above still lose the concurrency race — unique naming is the
    # part that actually removes the shared resource, and it was the one half of the
    # fix with no deterministic test pinning it (only the flaky-judged concurrency
    # repro exercised it). This spies on the actual filenames `_fs_probe` writes across
    # two cache-cleared `fs_fold()` calls and asserts all four (case-probe + norm-probe,
    # x2 calls) are distinct — no timing, no threads, no concurrency.
    seen_names = []
    _orig_write_text2 = pathlib.Path.write_text

    def _recording_write_text(self, *a, **kw):
        seen_names.append(self.name)
        return _orig_write_text2(self, *a, **kw)

    pathlib.Path.write_text = _recording_write_text
    try:
        brief_common.fs_fold.cache_clear()
        brief_common.fs_fold(tmp)
        brief_common.fs_fold.cache_clear()
        brief_common.fs_fold(tmp)
    finally:
        pathlib.Path.write_text = _orig_write_text2
    names_ok = len(seen_names) == 4 and len(set(seen_names)) == 4

    probe_cases = [
        ("probe-vanished-mid-check-assumes-folding", vanish_ok,
         f"expected True (assume folding), got {probe_result!r}"),
        ("probe-names-unique-per-call", names_ok,
         f"expected 4 distinct probe filenames, got {seen_names}"),
    ]
    for name, ok, msg in probe_cases:
        if not ok:
            bad.append(f"{name}: {msg}")
        print(f"{'pass' if ok else 'FAIL'}  {name}")

    # --- m-new7: pin the new observability itself, not just that it doesn't crash ---
    log_cases = []

    repo = fixtures.build(tmp / "log-disarmed")
    fixtures.write(repo, ".prompire/spec.yaml", BRIEF.format(policy="immutable", editable=""))
    subprocess.run([sys.executable, GUARD, ".prompire/spec.yaml", "--activate"],
                   cwd=str(repo), capture_output=True, text=True)
    (repo / ".prompire" / "ACTIVE").write_text("nope/missing.yaml\n", encoding="utf-8")
    run_hook(repo, "Write", "golden/x.txt", ".")
    disarmed_log = repo / ".prompire" / "hook-errors.log"
    log_cases.append(("log-disarmed-writes-trace",
                      disarmed_log.is_file()
                      and "disarmed" in disarmed_log.read_text(encoding="utf-8")))

    # m-new10: with a broken pointer at the root AND a planted broken one below it, the
    # trace belongs at the OUTERMOST pointer-holding directory. The nearest one is where
    # a planted pointer sits by construction, and a trace written inside the plant is a
    # trace the operator never finds.
    repo = fixtures.build(tmp / "log-disarmed-farthest")
    fixtures.write(repo, ".prompire/spec.yaml", BRIEF.format(policy="immutable", editable=""))
    subprocess.run([sys.executable, GUARD, ".prompire/spec.yaml", "--activate"],
                   cwd=str(repo), capture_output=True, text=True)
    (repo / ".prompire" / "ACTIVE").write_text("nope/missing.yaml\n", encoding="utf-8")
    fixtures.write(repo, "src/.prompire/ACTIVE", "nope/missing.yaml\n")
    run_hook(repo, "Write", "other.py", "src")
    log_cases.append(("log-disarmed-at-farthest-pointer",
                      (repo / ".prompire" / "hook-errors.log").is_file()
                      and not (repo / "src" / ".prompire" / "hook-errors.log").exists()))

    repo = fixtures.build(tmp / "log-cap")
    fixtures.write(repo, ".prompire/spec.yaml", BRIEF.format(policy="immutable", editable=""))
    subprocess.run([sys.executable, GUARD, ".prompire/spec.yaml", "--activate"],
                   cwd=str(repo), capture_output=True, text=True)
    (repo / ".prompire" / "ACTIVE").write_text("nope/missing.yaml\n", encoding="utf-8")
    big_log = repo / ".prompire" / "hook-errors.log"
    big_log.write_text("X" * 1_100_000, encoding="utf-8")
    run_hook(repo, "Write", "golden/x.txt", ".")
    log_cases.append(("log-size-cap-resets",
                      big_log.is_file() and big_log.stat().st_size < 1_100_000
                      and "disarmed" in big_log.read_text(encoding="utf-8")))

    for name, ok in log_cases:
        if not ok:
            bad.append(f"{name}: expected log condition not met")
        print(f"{'pass' if ok else 'FAIL'}  {name}")

    copilot_total = copilot_cases(tmp, bad, case_folds, norm_folds)

    shutil.rmtree(tmp, ignore_errors=True)
    total = (len(CASES) + len(open_cases) + len(extra_cases) + len(UNARMED_CASES)
             + len(probe_cases) + len(log_cases) + copilot_total)
    for b in bad:
        print(f"        {b}")
    print(f"\n{total - len(bad)}/{total} hook cases")
    return 1 if bad else 0


COPILOT_HOOK = str(SKILL / "hook_copilot_guard.py")

FOLD_CASE = "fold-case"    # correct answer depends on whether this volume folds case
FOLD_NORM = "fold-norm"    # …or Unicode normalisation

WIDE_BRIEF = ("goal: wide open\nscope:\n  - '**'\ntests_policy: immutable\n"
              "acceptance:\n  - cmd: \"true\"\n    expect: exit 0\nautonomy: auto\n")


def _armed(tmp, name, policy="immutable", editable="", body=None):
    """A throwaway repo with a brief armed the ordinary way — `check_scope.py
    --activate`, never a hand-written pointer."""
    repo = fixtures.build(tmp / name)
    fixtures.write(repo, ".prompire/spec.yaml",
                   body if body is not None else BRIEF.format(policy=policy,
                                                              editable=editable))
    subprocess.run([sys.executable, GUARD, ".prompire/spec.yaml", "--activate"],
                   cwd=str(repo), capture_output=True, text=True)
    return repo


def camel(tool, args, cwd, **extra):
    """The native camelCase `preToolUse` payload: sessionId, timestamp, cwd, toolName,
    toolArgs — no event-name field."""
    payload = {"sessionId": "0f9c", "timestamp": 0, "cwd": str(cwd),
               "toolName": tool, "toolArgs": args}
    payload.update(extra)
    return json.dumps(payload)


def pascal(tool, args, cwd, **extra):
    """The PascalCase VS Code-compatible payload: hook_event_name, session_id, a STRING
    timestamp, cwd, tool_name, tool_input."""
    payload = {"hook_event_name": "PreToolUse", "session_id": "0f9c",
               "timestamp": "2026-07-29T09:00:00Z", "cwd": str(cwd),
               "tool_name": tool, "tool_input": args}
    payload.update(extra)
    return json.dumps(payload)


def run_copilot(payload, env=None):
    r = subprocess.run([sys.executable, COPILOT_HOOK], input=payload,
                       capture_output=True, text=True,
                       env=dict(os.environ, **env) if env else None)
    return r.returncode, r.stdout, r.stderr


def _copilot_problems(rc, out, err, want):
    """Every case asserts the whole protocol, not just the decision.

    `want` is None for a neutral outcome or a substring the denial reason must contain.
    Copilot CLI reads a crash, exit 2, or any other non-zero exit as a denial, so exit 0
    is not a detail here — it is the only exit status this adapter is ever allowed to
    produce, and a case that passes its decision check while exiting 1 would deny in
    production for a reason nobody chose. stderr must stay empty for the same reason: a
    traceback on stderr means the process took the fail-closed path.
    """
    problems = []
    if rc != 0:
        problems.append(f"exit {rc}, wanted 0 — a non-zero exit is a Copilot denial: "
                        f"{err.strip()[:200]}")
    if err.strip():
        problems.append(f"wrote to stderr: {err.strip()[:200]}")
    body = out.strip()
    if want is None:
        # Neutral is empty output or `{}` — never `permissionDecision: "allow"`, which
        # would skip the permission prompt Copilot would otherwise show the operator.
        if body not in ("", "{}"):
            problems.append(f"expected neutral output, got {body[:200]!r}")
        return problems
    if not body:
        problems.append(f"expected a denial containing {want!r}, got empty output")
        return problems
    try:
        decision = json.loads(body)
    except ValueError:
        problems.append(f"denial is not valid JSON: {body[:200]!r}")
        return problems
    if not isinstance(decision, dict):
        problems.append(f"denial is not a JSON object: {body[:200]!r}")
        return problems
    if decision.get("permissionDecision") != "deny":
        problems.append(f"permissionDecision is {decision.get('permissionDecision')!r}, "
                        "wanted 'deny'")
    reason = decision.get("permissionDecisionReason")
    if not isinstance(reason, str) or not reason:
        problems.append("denial carries no permissionDecisionReason")
    elif want not in reason:
        problems.append(f"reason missing {want!r} — {reason[:200]!r}")
    return problems


PATCH = """*** Begin Patch
*** Update File: {path}
@@
-old
+new
*** End Patch
"""


def copilot_cases(tmp, bad, case_folds, norm_folds):
    """The GitHub Copilot CLI adapter: same boundary, opposite failure convention.

    Every case here runs the hook as a real subprocess and asserts stdin -> stdout,
    stderr and exit status together. The cases that must be NEUTRAL matter more than the
    ones that must deny: Copilot fails closed on its own, so every shape this adapter
    cannot read has to leave the call to Copilot's normal permission flow rather than
    refusing it or — worse — approving it.
    """
    cases = []   # (name, payload, want_substring_or_None)

    # --- the two documented payload shapes, both directions ---------------------
    repo = _armed(tmp, "cp-shapes")
    cases += [
        ("cp-camel-create-in-scope",
         camel("create", {"path": "src/cart.py", "content": "x"}, repo), None),
        ("cp-camel-create-outside-scope",
         camel("create", {"path": "src/other.py", "content": "x"}, repo),
         "outside `scope`"),
        ("cp-pascal-write-outside-scope",
         pascal("Write", {"file_path": "src/other.py"}, repo), "outside `scope`"),
        ("cp-pascal-edit-in-scope",
         pascal("Edit", {"file_path": "src/cart.py"}, repo), None),
        # The runtime name can arrive under the PascalCase envelope too — the matcher
        # fires on either spelling, so the payload may carry either.
        ("cp-pascal-runtime-name",
         pascal("edit", {"path": "src/other.py"}, repo), "outside `scope`"),
        # GitHub's own worked example parses `toolArgs` with a second `jq` call because
        # it arrives as a JSON *string*. Reading only the object form would make this
        # adapter silently blind on whichever host version disagrees with it.
        ("cp-toolargs-as-json-string",
         camel("create", json.dumps({"path": "src/other.py"}), repo), "outside `scope`"),
        # sessionId and timestamp are metadata this adapter never reads; a payload
        # without them must decide exactly the same way.
        ("cp-missing-optional-metadata",
         json.dumps({"cwd": str(repo), "toolName": "create",
                     "toolArgs": {"path": "src/other.py"}}), "outside `scope`"),
    ]

    # --- malformed and uninterpretable payloads: neutral, never a verdict -------
    cases += [
        ("cp-malformed-json", "not json at all", None),
        ("cp-empty-stdin", "", None),
        ("cp-non-object-json-array", "[1, 2, 3]", None),
        ("cp-non-object-json-scalar", '"just a string"', None),
        ("cp-non-object-json-null", "null", None),
        ("cp-toolname-wrong-type",
         json.dumps({"cwd": str(repo), "toolName": 7, "toolArgs": {"path": "src/other.py"}}),
         None),
        ("cp-toolargs-wrong-type",
         camel("create", ["src/other.py"], repo), None),
        ("cp-toolargs-string-not-json",
         camel("create", "src/other.py", repo), None),
        ("cp-toolargs-missing",
         json.dumps({"cwd": str(repo), "toolName": "create"}), None),
        # No cwd, no verdict: a relative `path` cannot be resolved without it, and
        # resolving it against this process's own cwd would judge a file in a directory
        # nobody named.
        ("cp-missing-cwd",
         json.dumps({"toolName": "create", "toolArgs": {"path": "src/other.py"}}), None),
        ("cp-cwd-wrong-type",
         json.dumps({"cwd": 3, "toolName": "create",
                     "toolArgs": {"path": "src/other.py"}}), None),
        # Misconfigured onto another event, this hook must say nothing rather than
        # answer a question it was not asked.
        ("cp-wrong-event",
         pascal("Write", {"file_path": "src/other.py"}, repo,
                hook_event_name="PostToolUse"), None),
        ("cp-create-with-no-path-key",
         camel("create", {"contents": "x"}, repo), None),
        ("cp-unknown-tool",
         camel("mcp__something__write", {"path": "src/other.py"}, repo), None),
    ]

    # --- tools that do not write files ------------------------------------------
    # `bash`/`powershell` are the documented gap, and this pins that the gap is real
    # rather than quietly half-covered: an identical out-of-scope path is denied under
    # `create` and passes untouched under `bash`. check_scope.py on the git diff is what
    # catches the shell write afterwards.
    cases += [
        ("cp-irrelevant-tool-view", camel("view", {"path": "src/other.py"}, repo), None),
        ("cp-irrelevant-tool-grep", camel("grep", {"pattern": "x"}, repo), None),
        ("cp-shell-write-not-intercepted",
         camel("bash", {"command": "echo x > src/other.py"}, repo), None),
        ("cp-powershell-write-not-intercepted",
         camel("powershell", {"command": "'x' > src/other.py"}, repo), None),
    ]

    # --- str_replace_editor: the operation lives in `command` --------------------
    cases += [
        ("cp-editor-str-replace-outside-scope",
         camel("str_replace_editor",
               {"command": "str_replace", "path": "src/other.py",
                "old_str": "a", "new_str": "b"}, repo), "outside `scope`"),
        ("cp-editor-create-forbidden",
         camel("str_replace_editor",
               {"command": "create", "path": "golden/report.txt", "file_text": "x"},
               repo), "forbidden"),
        # `view` reads. Refusing a read would be a boundary this brief does not draw.
        ("cp-editor-view-is-neutral",
         camel("str_replace_editor", {"command": "view", "path": "src/other.py"}, repo),
         None),
        # `undo_edit` writes, and is not assumed harmless just because it restores.
        ("cp-editor-undo-edit-writes",
         camel("str_replace_editor", {"command": "undo_edit", "path": "src/other.py"},
               repo), "outside `scope`"),
        ("cp-editor-in-scope",
         camel("str_replace_editor",
               {"command": "str_replace", "path": "src/cart.py"}, repo), None),
    ]

    # --- apply_patch: every file in the envelope, not the first one --------------
    multi = ("*** Begin Patch\n"
             "*** Update File: src/cart.py\n@@\n-old\n+new\n"
             "*** Update File: golden/report.txt\n@@\n-old\n+new\n"
             "*** End Patch\n")
    quoting = ("*** Begin Patch\n"
               "*** Update File: src/cart.py\n@@\n"
               " *** Update File: golden/report.txt\n"
               "+*** Delete File: docs/secret/x.md\n"
               "*** End Patch\n")
    cases += [
        ("cp-patch-single-outside-scope",
         camel("apply_patch", {"input": PATCH.format(path="src/other.py")}, repo),
         "outside `scope`"),
        ("cp-patch-in-scope", camel("apply_patch",
                                    {"input": PATCH.format(path="src/cart.py")}, repo),
         None),
        # The one that matters: file 1 is allowed, file 2 is forbidden. A guard that
        # answered from the first path would approve this whole patch.
        ("cp-patch-second-file-forbidden",
         camel("apply_patch", {"input": multi}, repo), "forbidden"),
        ("cp-patch-add-file-outside-scope",
         camel("apply_patch", {"input": "*** Begin Patch\n*** Add File: src/new.py\n"
                                        "+x\n*** End Patch\n"}, repo),
         "outside `scope`"),
        ("cp-patch-delete-file-forbidden",
         camel("apply_patch", {"input": "*** Begin Patch\n"
                                        "*** Delete File: golden/report.txt\n"
                                        "*** End Patch\n"}, repo), "forbidden"),
        # A rename names two paths. The destination is the one that escapes here, and a
        # source-only reading would miss it.
        ("cp-patch-move-destination-forbidden",
         camel("apply_patch", {"input": "*** Begin Patch\n"
                                        "*** Update File: src/cart.py\n"
                                        "*** Move to: golden/cart.py\n"
                                        "@@\n-old\n+new\n*** End Patch\n"}, repo),
         "forbidden"),
        # Content lines are prefixed with a space, `+` or `-`. A context line that
        # quotes a header — a diff of this file's own docstring would — is content, not
        # a path to refuse.
        ("cp-patch-quoted-header-is-content",
         camel("apply_patch", {"input": quoting}, repo), None),
        # A patch we cannot read is a set of changes we cannot enumerate. Silence, not a
        # guess from whatever path happens to be nearby.
        ("cp-patch-unparseable",
         camel("apply_patch", {"input": "just some text"}, repo), None),
        ("cp-patch-envelope-with-no-files",
         camel("apply_patch", {"input": "*** Begin Patch\n*** End Patch\n"}, repo), None),
        ("cp-patch-unreadable-does-not-fall-back-to-path",
         camel("apply_patch", {"input": "not a patch", "path": "src/other.py"}, repo),
         None),
        ("cp-patch-under-the-patch-key",
         camel("apply_patch", {"patch": PATCH.format(path="src/other.py")}, repo),
         "outside `scope`"),
    ]

    # --- path shapes -------------------------------------------------------------
    cases += [
        ("cp-absolute-path-outside-scope",
         camel("create", {"path": str(repo / "src" / "other.py")}, repo),
         "outside `scope`"),
        ("cp-absolute-path-in-scope",
         camel("create", {"path": str(repo / "src" / "cart.py")}, repo), None),
        ("cp-dot-relative-outside-scope",
         camel("create", {"path": "./src/other.py"}, repo), "outside `scope`"),
        ("cp-dot-relative-in-scope",
         camel("create", {"path": "./src/cart.py"}, repo), None),
        ("cp-dotdot-escapes-the-repo",
         camel("create", {"path": "../escaped.py"}, repo), "outside the repository"),
        ("cp-cwd-is-a-subdirectory",
         camel("create", {"path": "cart.py"}, repo / "src"), None),
        ("cp-cwd-is-a-subdirectory-outside-scope",
         camel("create", {"path": "other.py"}, repo / "src"), "outside `scope`"),
        ("cp-nul-in-path",
         camel("create", {"path": "src/x\x00.py"}, repo), "unnameable-path"),
        # POSIX names a backslash as an ordinary character, so `src\other.py` is one
        # file at the repo root, and it is outside `scope`. Pinned so the answer is a
        # decision rather than an accident of whichever normalisation ran last.
        ("cp-backslash-separator",
         camel("create", {"path": "src\\other.py"}, repo), "outside `scope`"),
    ]

    # --- the state files, unconditionally ---------------------------------------
    cases += [
        ("cp-state-pointer", camel("create", {"path": ".prompire/ACTIVE"}, repo),
         "guard pointer"),
        ("cp-state-tombstones",
         camel("create", {"path": ".prompire/ACTIVE.tombstones"}, repo), "guard pointer"),
        ("cp-state-nested-pointer",
         camel("create", {"path": "src/.prompire/ACTIVE"}, repo), "guard pointer"),
        ("cp-state-under-tombstones",
         camel("create", {"path": "src/.prompire/ACTIVE.tombstones/x"}, repo),
         "guard pointer"),
        ("cp-state-case-fold",
         camel("create", {"path": ".PROMPIRE/active"}, repo), "guard pointer"),
        ("cp-state-nfd-spelling",
         camel("create", {"path": unicodedata.normalize("NFD", ".prompire/ACTIVE")},
               repo), "guard pointer"),
        ("cp-state-dotdot",
         camel("create", {"path": "x/../.prompire/ACTIVE"}, repo), "guard pointer"),
        ("cp-state-legacy-pointer",
         camel("create", {"path": ".agent-brief/ACTIVE"}, repo), "guard pointer"),
        ("cp-state-legacy-tombstones",
         camel("create", {"path": ".agent-brief/ACTIVE.tombstones"}, repo),
         "guard pointer"),
        ("cp-state-legacy-nested",
         camel("create", {"path": "src/.agent-brief/ACTIVE"}, repo), "guard pointer"),
        # The narrowness pin, on this host too: `.prompire/` is where notes and renders
        # live (`ALWAYS_ALLOWED`), and only the two record files are off limits. The
        # legacy directory has no such blanket allowance and never did, so an armed
        # brief judges a note in it by `scope` like any other path — the pin that the
        # *shape* match stays narrow is `cp-never-armed-legacy-notes-allowed` below,
        # where no brief governs and only the shape rule can speak.
        ("cp-state-notes-allowed",
         camel("create", {"path": ".prompire/active-notes.md"}, repo), None),
        # An armed patch that touches the pointer among ordinary files is still a
        # pointer write.
        ("cp-patch-touching-the-pointer",
         camel("apply_patch", {"input": "*** Begin Patch\n"
                                        "*** Update File: src/cart.py\n@@\n-a\n+b\n"
                                        "*** Update File: .prompire/ACTIVE\n@@\n-a\n+b\n"
                                        "*** End Patch\n"}, repo), "guard pointer"),
        ("cp-self-edit-the-brief",
         camel("edit", {"path": ".prompire/spec.yaml"}, repo), "active brief"),
    ]

    # --- tests_policy, through the same tests_verdict check_scope.py uses --------
    immutable = _armed(tmp, "cp-tests-immutable")
    named = _armed(tmp, "cp-tests-named", policy="named", editable=NAMED)
    cases += [
        ("cp-tests-immutable-refused",
         camel("edit", {"path": "tests/test_cart.py"}, immutable), "tests_policy"),
        ("cp-tests-named-listed-allowed",
         camel("edit", {"path": "tests/test_cart.py"}, named), None),
        ("cp-tests-named-other-refused",
         camel("edit", {"path": "tests/test_total.py"}, named), "tests_editable"),
        ("cp-patch-touching-an-immutable-test",
         camel("apply_patch", {"input": "*** Begin Patch\n"
                                        "*** Update File: src/cart.py\n@@\n-a\n+b\n"
                                        "*** Update File: tests/test_cart.py\n@@\n-a\n+b\n"
                                        "*** End Patch\n"}, immutable), "tests_policy"),
    ]

    # --- no repo / no brief / broken brief: neutral, every one of them -----------
    bare = pathlib.Path(tempfile.mkdtemp(prefix="prompire-cp-bare-"))
    disarmed = _armed(tmp, "cp-disarmed")
    subprocess.run([sys.executable, GUARD, "--deactivate"], cwd=str(disarmed),
                   capture_output=True, text=True)
    broken = _armed(tmp, "cp-broken-pointer")
    (broken / ".prompire" / "ACTIVE").write_text("nope/missing.yaml\n", encoding="utf-8")
    unreadable = _armed(tmp, "cp-unreadable-pointer")
    (unreadable / ".prompire" / "ACTIVE").write_bytes(b"\xff\xfe\x00garbage")
    invalid = _armed(tmp, "cp-invalid-brief")
    fixtures.write(invalid, ".prompire/spec.yaml", "- this is a list\n- not a mapping\n")
    unarmed = fixtures.build(tmp / "cp-never-armed")
    cases += [
        ("cp-no-repo-anywhere", camel("create", {"path": str(bare / "x.py")}, bare), None),
        ("cp-no-active-brief", camel("create", {"path": "src/other.py"}, disarmed), None),
        ("cp-unreadable-pointer",
         camel("create", {"path": "src/other.py"}, unreadable), None),
        ("cp-pointer-at-a-missing-brief",
         camel("create", {"path": "src/other.py"}, broken), None),
        ("cp-brief-is-not-a-mapping",
         camel("create", {"path": "src/other.py"}, invalid), None),
        ("cp-never-armed-ordinary-file",
         camel("create", {"path": "src/other.py"}, unarmed), None),
        # …but the two record files are refused in a repo that never armed anything,
        # which is the state each of them exists to describe.
        ("cp-never-armed-pointer-refused",
         camel("create", {"path": ".prompire/ACTIVE"}, unarmed), "guard pointer"),
        ("cp-never-armed-legacy-tombstones-refused",
         camel("create", {"path": ".agent-brief/ACTIVE.tombstones"}, unarmed),
         "guard pointer"),
        # …and the shape match stays narrow while it does so: an ordinary note whose
        # name merely starts with "active" is a working file, under either state
        # directory name.
        ("cp-never-armed-notes-allowed",
         camel("create", {"path": ".prompire/active-notes.md"}, unarmed), None),
        ("cp-never-armed-legacy-notes-allowed",
         camel("create", {"path": ".agent-brief/active-notes.md"}, unarmed), None),
    ]

    # --- symlinks: the same three shapes the Claude adapter is pinned against ----
    # Not a claim that symlinks are solved — README lists a symlinked `.prompire`
    # directory as a live limitation, and creating any of these needs Bash, which neither
    # adapter watches. What is pinned is narrower and is the part that must not differ by
    # host: `_as_written` collapses `..` lexically BEFORE resolving symlinks, matching the
    # write tool rather than the OS, so `<symlink>/../…` is judged where the write lands.
    # Both adapters call the same function; a Copilot-only regression here would be
    # invisible without these.
    sym = _armed(tmp, "cp-symlink")
    (sym / "flink").symlink_to(sym / "src" / "cart.py")
    (sym / "docs" / "sub").mkdir(parents=True, exist_ok=True)
    (sym / "dclink").symlink_to(sym / "docs" / "sub")
    outside = pathlib.Path(tempfile.mkdtemp(prefix="prompire-cp-outside-"))
    (outside / "link.py").symlink_to(sym / "src" / "other.py")
    cases += [
        # `flink/..` is the LINK's parent, not the target's — so this lands on the brief.
        ("cp-symlink-dotdot-onto-the-brief",
         camel("create", {"path": "flink/../.prompire/spec.yaml"}, sym), "active brief"),
        # Judged inside `docs/**`, lands in `golden/**`.
        ("cp-symlink-dotdot-into-forbidden",
         camel("create", {"path": "dclink/../golden/report.txt"}, sym), "forbidden"),
        # The root walk starts from the RESOLVED target's parent: a symlink whose final
        # component points into an armed repo puts the write inside that repo, so that
        # repo's brief judges it even though cwd is nowhere near it.
        ("cp-symlink-target-into-armed-repo",
         camel("create", {"path": str(outside / "link.py")}, outside), "outside `scope`"),
    ]

    # --- an agent bound by repo A must not escape into repo B --------------------
    a = _armed(tmp, "cp-cross-a")
    b = _armed(tmp, "cp-cross-b", body=WIDE_BRIEF)
    cases.append(("cp-cross-repo-escape",
                  camel("create", {"path": str(b / "anything.md")}, a),
                  "outside the repository"))

    # --- case and normalisation folding, through the same fs_fold probe ----------
    fold_repo = _armed(tmp, "cp-fold-case", body=(
        "goal: Refactor helpers under src/.\nscope:\n  - src/**\n"
        "forbidden:\n  - src/golden/**\ntests_policy: immutable\n"
        "acceptance:\n  - cmd: \"true\"\n    expect: exit 0\nautonomy: auto\n"))
    nfc_dir = unicodedata.normalize("NFC", "café")
    nfd_dir = unicodedata.normalize("NFD", "café")
    norm_repo = _armed(tmp, "cp-fold-norm", body=(
        "goal: Update docs under docs/.\nscope:\n  - docs/**\n"
        f"forbidden:\n  - docs/{nfc_dir}/**\ntests_policy: immutable\n"
        "acceptance:\n  - cmd: \"true\"\n    expect: exit 0\nautonomy: auto\n"))
    cases += [
        ("cp-forbidden-case-variant",
         camel("create", {"path": "src/GOLDEN/x.txt"}, fold_repo), FOLD_CASE),
        ("cp-forbidden-normalisation-variant",
         camel("create", {"path": f"docs/{nfd_dir}/x.txt"}, norm_repo), FOLD_NORM),
    ]

    for name, payload, want in cases:
        if want == FOLD_CASE:
            want = "forbidden" if case_folds else None
        elif want == FOLD_NORM:
            want = "forbidden" if norm_folds else None
        rc, out, err = run_copilot(payload)
        problems = _copilot_problems(rc, out, err, want)
        if problems:
            bad.append(f"{name}: " + "; ".join(problems))
        print(f"{'FAIL' if problems else 'pass'}  {name}")

    extra = []

    # --- the exact denial text, byte for byte ------------------------------------
    # The reason is what the agent reads and acts on, so it is pinned rather than
    # substring-matched once: a reason that drifts into "ask and you may" wording would
    # pass every `want`-substring case above.
    _, out, _ = run_copilot(camel("create", {"path": "src/other.py"}, repo))
    expected_reason = (
        "BLOCKED by Prompire scope guard [outside-scope]: src/other.py — changed "
        "outside `scope` -> revert it, or revise the brief and re-run the baseline — a "
        "scope change is an edit to the brief, not a confirmation in chat. The brief is "
        "the contract. Widening `scope` is an edit to the brief followed by a fresh "
        "baseline, not a decision to make mid-task.")
    got_reason = json.loads(out).get("permissionDecisionReason")
    extra.append(("cp-denial-reason-is-deterministic", got_reason == expected_reason,
                  f"reason drifted:\n  got  {got_reason!r}\n  want {expected_reason!r}"))

    # The decision object carries the decision and nothing else — no `allow`, no
    # `modifiedArgs` rewriting the agent's call behind its back.
    extra.append(("cp-denial-object-is-exactly-the-decision",
                  set(json.loads(out)) == {"permissionDecision",
                                           "permissionDecisionReason"},
                  f"unexpected keys in the decision object: {sorted(json.loads(out))}"))

    # --- one boundary, two hosts -------------------------------------------------
    # The point of the shared core: for the same repo and the same path, the Claude
    # adapter's exit code and the Copilot adapter's decision must agree. They disagree
    # only in protocol.
    agree = []
    for rel in ("src/cart.py", "src/other.py", "golden/report.txt", "tests/test_cart.py",
                ".prompire/ACTIVE", ".prompire/active-notes.md", "docs/secret/x.md"):
        claude_rc, _ = run_hook(repo, "Write", rel, ".")
        _, cp_out, _ = run_copilot(camel("create", {"path": rel}, repo))
        cp_denied = bool(cp_out.strip())
        if (claude_rc == 2) != cp_denied:
            agree.append(f"{rel}: claude exit {claude_rc}, copilot denied={cp_denied}")
    extra.append(("cp-both-hosts-read-one-boundary", not agree,
                  f"the two adapters disagree about: {agree}"))

    # --- PyYAML unimportable: which protections survive, on both hosts -----------
    #
    # Forced for real, at process level, with no test-only branch in the shipped code: a
    # `yaml.py` on PYTHONPATH that raises on import makes `brief_common` explode inside
    # `verdict_for`. That is neither OSError nor BriefError, so it reaches each
    # adapter's catch-all.
    #
    # The split this pins is the whole point. `.prompire/ACTIVE`,
    # `.prompire/ACTIVE.tombstones` and a NUL path are documented as refused
    # UNCONDITIONALLY — README's guarantee paragraph and CLAUDE.md's Architecture
    # section both say so without qualification — so they must survive an import that
    # cannot happen, which is why `verdict_for` runs them in a first pass ABOVE the
    # `from brief_common import …`. Everything brief-dependent below that import is
    # infrastructure trouble and correctly fails open.
    #
    # This regressed once, silently, when the import was hoisted to the top of
    # `verdict_for` during the two-host refactor: the unconditional pair started
    # depending on PyYAML being installed and importable, and a half-installed venv was
    # enough to let a forged-pointer write through. An ordinary-path case alone cannot
    # see that — fail-open is the correct answer there — so the state-file and NUL cases
    # below are the ones that actually hold the line.
    shim = tmp / "cp-import-boom"
    shim.mkdir(parents=True, exist_ok=True)
    (shim / "yaml.py").write_text("raise RuntimeError('forced import failure')\n",
                                  encoding="utf-8")
    boom = {"PYTHONPATH": str(shim)}

    # Sanity first: the shim really does break the import, so nothing below passes
    # merely because nothing went wrong.
    probe = subprocess.run([sys.executable, "-c", "import yaml"],
                           capture_output=True, text=True, env=dict(os.environ, **boom))
    extra.append(("broken-import-shim-actually-breaks-yaml", probe.returncode != 0,
                  "the PYTHONPATH shim did not break `import yaml`, so every case below "
                  "proves nothing"))

    def claude_broken(rel):
        return subprocess.run(
            [sys.executable, HOOK],
            input=json.dumps({"hook_event_name": "PreToolUse", "tool_name": "Write",
                              "cwd": str(repo), "tool_input": {"file_path": rel}}),
            capture_output=True, text=True, env=dict(os.environ, **boom)).returncode

    # (name, path, claude_exit, copilot_wants_denial)
    BROKEN_IMPORT = [
        ("pointer", ".prompire/ACTIVE", 2, True),
        ("tombstones", ".prompire/ACTIVE.tombstones", 2, True),
        ("nested-pointer", "src/.prompire/ACTIVE", 2, True),
        ("legacy-pointer", ".agent-brief/ACTIVE", 2, True),
        ("legacy-tombstones", ".agent-brief/ACTIVE.tombstones", 2, True),
        ("case-fold-pointer", ".PROMPIRE/active", 2, True),
        ("nul-path", "src/x\x00.py", 2, True),
        # The other half: a boundary question genuinely cannot be answered without the
        # brief, so this one must still fail open on both hosts. A guard that started
        # refusing ordinary writes whenever an unrelated import broke would be
        # uninstalled by lunchtime, and an uninstalled guard protects nothing.
        ("ordinary-file", "src/other.py", 0, False),
    ]
    for label, rel, want_claude, want_deny in BROKEN_IMPORT:
        got = claude_broken(rel)
        extra.append((f"broken-import-claude-{label}", got == want_claude,
                      f"exit {got}, wanted {want_claude} — with PyYAML unimportable the "
                      f"Claude adapter must behave exactly as it did before the "
                      f"two-host refactor for {rel!r}"))
        rc, out, err = run_copilot(camel("create", {"path": rel}, repo), env=boom)
        denied = bool(out.strip())
        ok = rc == 0 and not err.strip() and denied == want_deny
        extra.append((f"broken-import-copilot-{label}", ok,
                      f"exit {rc}, denied={denied} (wanted {want_deny}), stdout "
                      f"{out.strip()[:120]!r}, stderr {err.strip()[:160]!r}"))

    # --- a closed stdout must not become a denial --------------------------------
    # Copilot reads ANY non-zero exit as a denial. If it stops reading our stdout — a
    # killed session, a hook it abandoned — the write, or Python's own flush at
    # interpreter exit, raises BrokenPipeError; unhandled that prints to stderr and exits
    # 120, and the tool call is refused for a reason the brief never gave. Reproduced by
    # closing the read end before the hook writes its decision.
    proc = subprocess.Popen([sys.executable, COPILOT_HOOK], stdin=subprocess.PIPE,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    proc.stdout.close()
    try:
        proc.stdin.write(camel("create", {"path": "golden/report.txt"}, repo))
        proc.stdin.close()
    except OSError:
        pass
    pipe_rc = proc.wait()
    pipe_err = proc.stderr.read()
    proc.stderr.close()
    extra.append(("cp-closed-stdout-is-not-a-denial",
                  pipe_rc == 0 and not pipe_err.strip(),
                  f"exit {pipe_rc}, stderr {pipe_err.strip()[:160]!r} — a broken pipe "
                  "must not exit non-zero, which Copilot would read as a denial"))

    # …and the OTHER way stdout can be unusable, which raises something else entirely.
    # With fd 1 closed outright (`>&-`), Python sets `sys.stdout` to None and the write
    # raises AttributeError, not OSError — so an enumerated `except (BrokenPipeError,
    # OSError)` misses it and the process exits 1 with a traceback. Both branches are
    # covered: the deny branch writes, and the NEUTRAL branch still flushes, so an
    # ordinary in-scope write was refused by this too.
    for label, rel in (("deny-branch", "golden/report.txt"),
                       ("neutral-branch", "src/cart.py")):
        closed = subprocess.run(
            [sys.executable, COPILOT_HOOK],
            input=camel("create", {"path": rel}, repo),
            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True,
            preexec_fn=lambda: os.close(1))
        extra.append((f"cp-closed-stdout-fd-is-not-a-denial-{label}",
                      closed.returncode == 0 and not (closed.stderr or "").strip(),
                      f"exit {closed.returncode}, stderr "
                      f"{(closed.stderr or '').strip()[:200]!r} — a closed stdout "
                      "descriptor must not exit non-zero either"))

    # The decision object is only ever built with "deny". `allow` would skip the
    # permission prompt Copilot would otherwise show the operator, so it must not be
    # constructible at all — checked against the source, since no input can produce it.
    guard_src = pathlib.Path(COPILOT_HOOK).read_text(encoding="utf-8")
    decisions = re.findall(r'"permissionDecision":\s*"(\w+)"', guard_src)
    extra.append(("cp-only-deny-is-ever-constructed",
                  decisions == ["deny"],
                  f"the adapter constructs {decisions} — only ['deny'] is permitted"))

    for name, ok, msg in extra:
        if not ok:
            bad.append(f"{name}: {msg}")
        print(f"{'pass' if ok else 'FAIL'}  {name}")

    shutil.rmtree(bare, ignore_errors=True)
    return len(cases) + len(extra)


def _deactivate(repo):
    subprocess.run([sys.executable, GUARD, "--deactivate"], cwd=str(repo),
                   capture_output=True, text=True)


def _point_at_nothing(repo):
    (repo / ".prompire" / "ACTIVE").write_text("nope/missing.yaml\n", encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
