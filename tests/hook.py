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
import pathlib
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

    shutil.rmtree(tmp, ignore_errors=True)
    total = (len(CASES) + len(open_cases) + len(extra_cases) + len(UNARMED_CASES)
             + len(probe_cases) + len(log_cases))
    for b in bad:
        print(f"        {b}")
    print(f"\n{total - len(bad)}/{total} hook cases")
    return 1 if bad else 0


def _deactivate(repo):
    subprocess.run([sys.executable, GUARD, "--deactivate"], cwd=str(repo),
                   capture_output=True, text=True)


def _point_at_nothing(repo):
    (repo / ".prompire" / "ACTIVE").write_text("nope/missing.yaml\n", encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
