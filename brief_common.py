#!/usr/bin/env python3
"""Shared schema helpers for the Prompire tools.

The authoritative field-by-field schema is `references/schema.md`. This module is the
single implementation of the parts the linter, the renderer, the scope guard and the
baseline runner must all agree on: how a brief is loaded, how an acceptance entry is
keyed, what a transition means, and how a scope pattern matches a path.
"""
import functools
import os
import pathlib
import re
import sys
import unicodedata
import uuid

import yaml

TOP_KEYS = {
    "goal", "scope", "forbidden", "constraints", "acceptance", "baseline", "autonomy",
    "plan_first", "rollback", "manual_checks", "notes", "context",
    "tests_policy", "tests_editable", "oracle", "dirty_baseline", "base_rev",
}
ACCEPTANCE_KEYS = {"cmd", "expect", "cwd", "timeout", "requires", "transition",
                   "before_after", "must_flip"}
BASELINE_KEYS = {"cmd", "cwd", "status", "reason", "evidence", "must_flip"}

# A draft is not a brief yet. Every line a compiler could not settle carries this
# marker, and deleting it is the confirmation. prompire.py writes it, prepare refuses
# while one remains, lint_brief.py reports a file carrying one as a draft (B18), and
# check_scope.py refuses to arm one — the marker is Prompire's serialization of
# "unconfirmed", never the model's to write or to clear.
DRAFT_MARKER = "prompire:unconfirmed"
# The same fact, in the data rather than in comments. A comment is the one part of a
# YAML file no round-trip preserves: `yq -y .`, a formatter, an editor plugin, or an
# agent asked to tidy the brief drops every marker above, and the file then reads as
# fully confirmed. Reproduced end to end — six unconfirmed decisions, a relaxed
# `tests_policy` among them, went from draft to armed with the pin's authority. So the
# ledger lists what is still unconfirmed as a key every gate also refuses, and a
# round-trip carries the refusal instead of erasing it.
DRAFT_LEDGER = "unconfirmed"

AUTONOMY = ("manual", "ask", "auto")
BASELINE_STATUS = ("pass", "fail", "not_runnable")
TRANSITIONS = ("green", "flip", "hold")
TESTS_POLICIES = ("immutable", "named", "authoring")
REQUIRES_VOCAB = ("network", "credentials", "services", "docker", "database",
                  "display", "interactive", "writes-repo", "manual")

DEFAULT_TIMEOUT = 300

# What counts as a test file when no `tests_editable` narrows it. Deliberately broad:
# the guard fails closed, and a false positive is fixed by naming the path.
TEST_GLOBS = (
    "**/tests/**", "**/test/**", "**/__tests__/**", "**/spec/**",
    "**/test_*.py", "**/*_test.py", "**/*_test.go", "**/*_test.rb",
    "**/*.test.js", "**/*.test.ts", "**/*.test.jsx", "**/*.test.tsx",
    "**/*.spec.js", "**/*.spec.ts", "**/*.spec.jsx", "**/*.spec.tsx",
    "**/*Test.java", "**/*Tests.cs",
)

# Text a diff can add to a test file that disables a check. Mechanical, not semantic:
# these are literal markers, not an attempt to judge whether an assertion got weaker.
SKIP_MARKERS = re.compile(
    r"@(?:unittest\.)?skip|@pytest\.mark\.(?:skip|xfail)|pytest\.skip\(|"
    r"\bskipTest\(|\bxfail\b|\bit\.skip\b|\bdescribe\.skip\b|\btest\.skip\b|"
    r"\bit\.only\b|\bdescribe\.only\b|\btest\.only\b|\bt\.Skip\(|\bxit\(|\bxdescribe\(|"
    r"#\s*nosec|#\s*type:\s*ignore\[.*\]\s*#\s*test|@Ignore\b|\[Ignore\]",
    re.I,
)


def _fs_probe(root, canonical_name, variant_name):
    """Does writing `canonical_name` under `root` make `variant_name` resolve to the
    same directory entry? The only reliable way to answer this is to ask the actual
    volume — there is no portable stat flag for it, and `sys.platform` does not decide
    it either (macOS ships case-insensitive by default but supports a case-sensitive
    APFS volume as a real, opt-in choice).

    `canonical_name`/`variant_name` must be unique to this one call (see `fs_fold`,
    which stamps a pid+uuid4 token into both) — a fixed name here raced across
    concurrent processes probing the same root: one process's `unlink()` between
    another's `write_text()` and `exists()` made the second process read "does not
    fold" off a file a THIRD party had already removed, which is the unsafe direction
    (Task 14 fix round 1, C1 — reproduced live: 40 concurrent `hook_scope_guard.py`
    invocations writing a `forbidden` case-variant path, 1-11 of them landing exit 0).
    Unique names per call make that collision structurally impossible rather than just
    less likely.

    Every failure mode here has to resolve toward "assume folding" — the direction
    that still catches a `forbidden` case/normalisation variant rather than missing
    one. That includes the canonical file no longer existing right after this call
    wrote it: if it's gone, checking whether the variant name still resolves proves
    nothing (the answer would be `False` on `every` filesystem once the entry itself
    is gone), so that state is inconclusive, not evidence of non-folding.
    """
    probe = pathlib.Path(root) / canonical_name
    try:
        probe.write_text("x", encoding="utf-8")
    except OSError:
        return True  # can't tell; assume folding
    try:
        if not probe.exists():
            return True  # canonical vanished mid-probe — inconclusive, assume folding
        return (pathlib.Path(root) / variant_name).exists()
    finally:
        try:
            probe.unlink()
        except OSError:
            pass


@functools.lru_cache(maxsize=None)
def fs_fold(root):
    """(case_folds, norm_folds) for the filesystem holding `root`.

    Two independent probes, not one flag derived from the other: APFS folds Unicode
    normalisation regardless of whether it is folding case, so a case-sensitive APFS
    volume is still normalisation-insensitive (verified against a real
    `hdiutil create -fs "Case-sensitive APFS"` volume — see tests/hook.py). ext4 folds
    neither. `scope`/`forbidden` matching (`matches_any`, `boundary_verdict`,
    `tests_verdict`) has to match whichever of these the checkout is actually running
    on, or `forbidden: [src/golden/**]` is defeated by writing `src/GOLDEN/**` on a
    folding volume, and a scope entry can be missed by an honest case variant on one
    that doesn't fold.

    Cached per resolved root for the life of the process. `check_scope.py` calls this
    once per run; the PreToolUse hook calls it once per governing root (at most two)
    per invocation — every further glob match against the same root reuses the answer
    instead of re-probing the filesystem. The cache means only the FIRST call for a
    given (process, root) ever touches the filesystem, so the probe names below only
    need to be unique against every OTHER process's first call, not against repeats of
    this one — `os.getpid()` plus a `uuid4` makes a collision between two processes'
    probes astronomically unlikely rather than a fixed name any concurrent caller
    could step on (see `_fs_probe`).
    """
    root = pathlib.Path(root).resolve()
    token = f"{os.getpid()}-{uuid.uuid4().hex}"
    case_canonical = f".prompire-fold-probe-case-{token}.tmp"
    case_folds = _fs_probe(root, case_canonical, case_canonical.upper())
    norm_canonical = unicodedata.normalize("NFC", f".prompire-fold-probe-norm-é-{token}.tmp")
    norm_variant = unicodedata.normalize("NFD", f".prompire-fold-probe-norm-é-{token}.tmp")
    norm_folds = _fs_probe(root, norm_canonical, norm_variant)
    return case_folds, norm_folds


NO_FOLD = (False, False)


def utf8_stdio():
    """Make this tool's own output UTF-8, whatever the platform thinks the locale is.

    Every tool here is read by another program — the JSON is parsed by `prompire.py`, by
    the GitHub Action's runner, by the test suites — so the encoding of its stdout is a
    *wire format*, and a wire format that depends on the caller's console code page is
    the bug rather than a symptom of it. A redirected or piped stream on Windows is the
    ANSI code page, normally cp1252, and cp1252 cannot spell `č`; a Windows *console*
    stream has been UTF-8 through the console API since 3.6, so it is exactly the
    redirected case — which is how every caller actually runs these tools — that breaks.
    Hence UTF-8 is asserted here and not assumed.

    `backslashreplace` stays for a second, narrower reason: the tools decode git's output
    with `errors="surrogateescape"`, so a path git reported in bytes that are not valid
    UTF-8 arrives as lone surrogates, which *no* codec will encode back out.

    Both failures land at the moment of *reporting* a verdict already reached. Left alone
    they turn exit 0/1/2 into a traceback, and — worse in this repo, whose exit codes are
    load-bearing — a crash while printing exits 1, which is the code for "found a
    finding": a tool that died is then indistinguishable from a tool that decided. The
    escape spells what it cannot encode instead, and it cannot touch any character that
    already encoded, so no verdict and no golden snapshot moves.

    Best-effort by construction. A stream that cannot be reconfigured must never be a
    reason to fail — the two hooks call this and both must keep degrading toward not
    enforcing.
    """
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="backslashreplace")
        except Exception:
            pass


class BriefError(Exception):
    """The brief could not be read as a brief at all (exit 2, not a lint finding)."""


def load_brief(path):
    try:
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except OSError as e:
        raise BriefError(f"cannot read {path}: {e}") from e
    except UnicodeError as e:
        raise BriefError(f"cannot decode {path} as UTF-8: {e}") from e
    except yaml.YAMLError as e:
        raise BriefError(f"cannot parse {path}: {e}") from e
    if not isinstance(data, dict):
        raise BriefError(f"{path}: expected a YAML mapping at the top level")
    return data


def as_list(v):
    if v is None:
        return []
    return v if isinstance(v, list) else [v]


def norm_cmd(s):
    return " ".join(str(s or "").split())


def norm_cwd(s):
    c = str(s or ".").strip().replace("\\", "/")
    while c.startswith("./"):
        c = c[2:]
    c = c.rstrip("/")
    return c or "."


def entry_key(entry):
    """Acceptance and baseline entries are matched on (command, working directory).

    Both are normalised for whitespace so a reflowed YAML string still matches.
    """
    if not isinstance(entry, dict):
        return None
    cmd = norm_cmd(entry.get("cmd"))
    if not cmd:
        return None
    return (cmd, norm_cwd(entry.get("cwd")))


def transition_of(entry):
    """green = passes now and must stay passing. flip = red now, green when done.
    hold = red now and must stay exactly as measured.

    `must_flip: true` is the pre-2026-07-27 spelling of `transition: flip`; it is
    accepted so old briefs keep working, and the linter points at the new field.
    """
    if not isinstance(entry, dict):
        return "green"
    t = str(entry.get("transition") or "").strip().lower()
    if t in TRANSITIONS:
        return t
    if entry.get("must_flip"):
        return "flip"
    return "green"


def effective_transition(acceptance_entry, baseline_entry=None):
    """The transition a criterion actually declares, across both spellings.

    Old briefs put `must_flip: true` on the *baseline* entry, so a brief written before
    2026-07-27 still resolves to `flip` instead of hard-failing B15. The linter warns
    and names the replacement; nothing silently changes meaning.
    """
    t = str((acceptance_entry or {}).get("transition") or "").strip().lower()
    if t in TRANSITIONS:
        return t
    if (acceptance_entry or {}).get("must_flip"):
        return "flip"
    if isinstance(baseline_entry, dict) and baseline_entry.get("must_flip"):
        return "flip"
    return "green"


def acceptance_entries(brief):
    """Well-formed acceptance entries only; the linter reports the malformed ones."""
    out = []
    for a in as_list(brief.get("acceptance")):
        if isinstance(a, dict) and norm_cmd(a.get("cmd")):
            out.append(a)
    return out


def manual_check_entries(brief):
    """(text, carries_done, well_formed) per `manual_checks` entry.

    A plain string is a review note. The mapping spelling `- done: <text>` is the
    human's own declaration that this judgment is the task's completion condition —
    the one shape B17 accepts as a carrier of done-ness when nothing mechanical
    (a flip, a hold, a before/after comparison) distinguishes untouched HEAD from
    done. E1 armed two contracts whose every criterion was green on HEAD because a
    manual check merely *existing* silenced B17; existing is not carrying. The
    spelling is deliberately not proposable: `prompire draft` rejects a proposal
    whose manual entries are not plain strings, so the declaration can only be
    written by the human editing the confirmed brief.

    Any other mapping shape is malformed (well_formed False): neither a note nor a
    declaration, and guessing which it meant to be would guess about authority.
    """
    out = []
    for m in as_list(brief.get("manual_checks")):
        if isinstance(m, dict):
            if set(m) == {"done"} and str(m.get("done") or "").strip():
                out.append((str(m["done"]).strip(), True, True))
            else:
                out.append((str(m), False, False))
        else:
            out.append((str(m), False, True))
    return out


def manual_check_texts(brief):
    """The displayable text of every manual check, whatever its spelling."""
    return [text for text, _, _ in manual_check_entries(brief)]


def baseline_entries(brief):
    b = brief.get("baseline")
    if not isinstance(b, list):
        return []
    return [e for e in b if isinstance(e, dict) and norm_cmd(e.get("cmd"))]


def baseline_map(brief):
    return {entry_key(e): e for e in baseline_entries(brief)}


def glob_re(pattern, fold=NO_FOLD):
    """Translate a scope/forbidden pattern to a regex.

    `**` crosses directory separators, `*` does not. A pattern with no wildcard, or one
    ending in `/`, also covers everything beneath it: `src/render/` and `src/render`
    both match `src/render/pdf.py`.

    `fold` is `(case_folds, norm_folds)` from `fs_fold()` — the property of the actual
    filesystem the path is being matched on, not an assumption. `norm_folds` normalises
    the pattern text itself (the matched path must be normalised the same way by the
    caller, via `norm_path(path, fold)`); `case_folds` compiles the regex
    case-insensitively rather than lowercasing the pattern, so it still reads correctly
    in error messages.
    """
    case_folds, norm_folds = fold
    p = str(pattern).strip().replace("\\", "/")
    if norm_folds:
        p = unicodedata.normalize("NFC", p)
    while p.startswith("./"):
        p = p[2:]
    dir_prefix = p.endswith("/")
    p = p.rstrip("/")
    out, i = [], 0
    while i < len(p):
        if p[i] == "*":
            if p[i:i + 3] == "**/":
                out.append("(?:.*/)?")
                i += 3
                continue
            if p[i:i + 2] == "**":
                out.append(".*")
                i += 2
                continue
            out.append("[^/]*")
            i += 1
            continue
        if p[i] == "?":
            out.append("[^/]")
            i += 1
            continue
        out.append(re.escape(p[i]))
        i += 1
    body = "".join(out)
    flags = re.IGNORECASE if case_folds else 0
    if dir_prefix or not re.search(r"[*?]", p):
        return re.compile("^" + body + "(?:/.*)?$", flags)
    return re.compile("^" + body + "$", flags)


def norm_path(path, fold=NO_FOLD):
    p = str(path).strip().replace("\\", "/")
    while p.startswith("./"):
        p = p[2:]
    p = p.strip("/")
    if fold[1]:
        p = unicodedata.normalize("NFC", p)
    return p


def matches_any(patterns, path, fold=NO_FOLD):
    """Return the first pattern that matches, or None."""
    path = norm_path(path, fold)
    for pat in patterns:
        if not str(pat).strip():
            continue
        if glob_re(pat, fold).match(path):
            return str(pat)
    return None


def is_test_path(path, extra_globs=(), fold=NO_FOLD):
    return matches_any(tuple(TEST_GLOBS) + tuple(extra_globs), path, fold) is not None


def _fold_in(item, items, fold):
    """Is `item` equal to one of `items`, under `fold`'s case-folding?

    `norm_path(x, fold)` already applies NFC normalisation when asked, but never
    case-folds the string it returns — `glob_re` handles the case axis with
    `re.IGNORECASE` instead, precisely so the original casing survives into displayed
    paths and error messages. The two identity checks in `boundary_verdict`
    (`dirty_baseline`, the brief's own path) compare full paths for exact equality
    rather than matching a glob, so they need their own case-fold step rather than
    inheriting one from `norm_path` or `glob_re` (Task 14 fix round 1, N1 — this was
    previously NFC-folded but not case-folded, a fail-safe-direction gap: it produced
    one more finding than a folding filesystem's own identity says is warranted, never
    fewer).
    """
    if fold[0]:
        item = item.casefold()
        items = [i.casefold() for i in items]
    return item in items


ALWAYS_ALLOWED = ("**/.prompire/**", ".prompire/**")


def allowed_globs(brief, policy=None):
    """Every pattern a path may match and still be inside the boundary.

    A tests policy that permits test edits widens the boundary for test files only;
    those paths do not have to be repeated in `scope`.
    """
    if policy is None:
        policy = tests_policy_of(brief)
    allow = [str(s) for s in as_list(brief.get("scope"))] + list(ALWAYS_ALLOWED)
    editable = [str(t) for t in as_list(brief.get("tests_editable"))]
    if policy in ("named", "authoring"):
        allow += editable
    return allow


def boundary_verdict(brief, path, policy=None, brief_path=None, fold=NO_FOLD):
    """Is this path inside `scope` and outside `forbidden`? None means yes.

    Path-level only, because it is shared by two callers that see different things:
    check_scope.py has a diff, the PreToolUse hook has one path that has not been
    written yet. Anything needing two revisions — deleted lines, added skip markers,
    renames — stays in check_scope.py.

    `fold` is `(case_folds, norm_folds)` from `fs_fold(root)` — a property of the
    filesystem the caller is actually running on, not assumed. Without it, `forbidden:
    [src/golden/**]` is defeated on a case-folding volume by writing `src/GOLDEN/x.txt`:
    same directory entry, non-matching string. The default `NO_FOLD` reproduces the
    exact-case behaviour this function had before `fold` existed, so a caller that
    hasn't been updated to pass it fails the same way it always did — never more
    permissively.
    """
    np = norm_path(path, fold)
    if brief_path and _fold_in(np, [norm_path(brief_path, fold)], fold):
        return None
    if _fold_in(np, [norm_path(p, fold) for p in as_list(brief.get("dirty_baseline"))], fold):
        return None
    if matches_any(ALWAYS_ALLOWED, np, fold):
        return None
    hit = matches_any([str(f) for f in as_list(brief.get("forbidden"))], np, fold)
    if hit:
        return ("forbidden", f"changed a forbidden path (matches `{hit}`)",
                "revert it; `forbidden` wins over `scope`")
    if policy is None:
        policy = tests_policy_of(brief)
    if not matches_any(allowed_globs(brief, policy), np, fold):
        return ("outside-scope", "changed outside `scope`",
                "revert it, or revise the brief and re-run the baseline — a scope "
                "change is an edit to the brief, not a confirmation in chat")
    return None


def tests_verdict(brief, path, policy=None, status=None, is_test=None, fold=NO_FOLD):
    """Does the tests policy let this test file change at all? None means yes.

    Whether what it did once inside was legitimate is check_scope.py's problem, and
    under `named`/`authoring` it is a human's — no checker can tell a repaired
    assertion from a weakened one.

    `is_test` lets a caller that has already established test-ness (e.g. a rename whose
    origin was a test path, even though the destination is not) skip the internal
    `is_test_path` re-gate. Left `None`, the gate re-checks `path` itself — the hook's
    single-path callers rely on that self-gating.

    `fold`: see `boundary_verdict` — same `(case_folds, norm_folds)` from `fs_fold(root)`,
    same default-preserves-old-behaviour reasoning. Without it, an `immutable` test file
    is rewritten by way of a case-variant path the guard doesn't recognise as a test at
    all.
    """
    editable = [str(t) for t in as_list(brief.get("tests_editable"))]
    np = norm_path(path, fold)
    if is_test is None:
        is_test = is_test_path(np, editable, fold)
    if not is_test:
        return None
    if policy is None:
        policy = tests_policy_of(brief)
    seen = f" ({status})" if status else ""
    if policy in (None, "immutable"):
        return ("tests-immutable",
                f"test file changed{seen} under tests_policy "
                f"`{policy or 'undeclared (defaults to immutable)'}`",
                "revert it; if the task legitimately touches tests, the brief must say "
                "so with tests_policy: named | authoring")
    if policy in ("named", "authoring") and not matches_any(editable, np, fold):
        return ("tests-unnamed", "test file changed but is not listed in `tests_editable`",
                "only the named test paths may change")
    return None


def tests_policy_of(brief):
    """The declared policy, or the policy implied by legacy pinning, or None.

    A brief that predates `tests_policy` but pins tests in `forbidden`/`constraints`
    means `immutable`; that is what pinning always meant.
    """
    p = str(brief.get("tests_policy") or "").strip().lower()
    if p in TESTS_POLICIES:
        return p
    if legacy_pinned(brief):
        return "immutable"
    return None


def legacy_pinned(brief):
    forbidden = as_list(brief.get("forbidden"))
    constraints = as_list(brief.get("constraints"))
    cmds = [norm_cmd(a.get("cmd")) for a in acceptance_entries(brief)]
    if any(re.search(r"test|spec|__tests__", str(f), re.I) for f in forbidden):
        return True
    if any(re.search(r"test|spec", str(c), re.I) and
           re.search(r"not? (modif|chang|edit)|unchanged|don'?t (touch|edit|modify)",
                     str(c), re.I) for c in constraints):
        return True
    return any(re.search(r"git (diff|status).*test", c, re.I) for c in cmds)
