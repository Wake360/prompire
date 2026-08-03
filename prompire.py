#!/usr/bin/env python3
import argparse
import contextlib
import importlib.metadata
import json
import os
import pathlib
import re
import shlex
import shutil
import stat
import subprocess
import sys
import tempfile
import time

import yaml

from brief_common import (ACCEPTANCE_KEYS, DRAFT_LEDGER, DRAFT_MARKER, as_list,
                          glob_re, norm_path, utf8_stdio)
from check_scope import RepoError, active_brief, digest_of, read_pointer, repo_root

# After the siblings above: render_brief prepends its own directory to sys.path,
# so importing a stray installed copy first would make every later sibling import
# resolve beside *it* instead of beside this file.
import render_brief  # noqa: E402

HERE = pathlib.Path(__file__).resolve().parent
TOOLS = {
    "baseline": "baseline.py",
    "lint": "lint_brief.py",
    "render": "render_brief.py",
    "scope": "check_scope.py",
    "acceptance": "verify_acceptance.py",
}
PROMPT_TARGETS = ("generic", "claude", "codex", "copilot")
LOW_LEVEL_COMMANDS = ("baseline", "lint", "render", "scope")
DEFAULT_DRAFT_OUT = ".prompire/task.yaml"
DRAFT_AGENT_TIMEOUT = 600
# Host invocations this tree has actually run. claude is the shape bench/run.py
# uses, --setting-sources included, so one machine's personal instructions cannot
# leak into the draft. codex drafts under its read-only sandbox — drafting must
# never write — with the user config ignored and no session files left behind.
# antigravity (agy 1.1.8) can neither read the prompt from stdin nor treat an
# untrusted cwd as a workspace, so its entry carries the two placeholders
# `agent_argv` substitutes; headless agy has no read-only mode, which is what the
# repository snapshot in draft() is for. Any other host is spelled by the caller
# via --agent-cmd.
DRAFT_AGENTS = {
    "claude": ["claude", "-p", "--setting-sources", "project"],
    "codex": ["codex", "exec", "--sandbox", "read-only", "--ignore-user-config",
              "--ephemeral", "--color", "never", "-"],
    "antigravity": ["agy", "-p", "{prompt}", "--add-dir", "{root}",
                    "--print-timeout", "540s"],
}
# Everything the schema lets a task declare, minus what Prompire measures. A key
# missing here is a key no compiler frontend can propose — that asymmetry is how the
# pre-compiler drafts made `named`/`authoring`/refactor tasks structurally impossible.
DRAFT_KEYS = ("goal", "scope", "forbidden", "constraints", "tests_policy",
              "tests_editable", "oracle", "acceptance", "manual_checks",
              "context", "plan_first", "rollback", "autonomy")
DRAFT_MEASURED = ("baseline", "base_rev", "dirty_baseline")
DRAFT_PROMPT = """\
Compile the request below into a draft Prompire brief. Inspect this repository
first; every line must be grounded in what you find, never invented.

Request: {sentence}

Output only a YAML mapping with these keys and no others:
- goal: one imperative sentence, at most 30 words, sharpened from the request.
- scope: the exact files or narrow globs the work may edit, including files it
  must create. Never `.`.
- forbidden: paths that must not change; [] after considering it.
- constraints: observable facts that must stay true; omit if none.
- tests_policy: immutable, unless the request itself is about changing tests —
  then named, or authoring when the tests are the deliverable.
- tests_editable: only with named/authoring — the exact test paths that may change.
- oracle: only with authoring — what judges the work when the suite cannot.
- acceptance: commands this repository evidences (a package script, a configured
  test runner, an existing file). Each item carries cmd and expect; add
  `transition: flip` when it fails today and making it pass is the goal. If
  nothing runnable proves the work, write acceptance: [].
- manual_checks: what only a human can confirm; omit if none.
- context: at most three lines of repository fact the agent would otherwise
  rediscover the hard way; omit unless it changes the implementation.
- plan_first: true only when the request asks for a plan or approval step, or
  the task is a refactor/migration or wider than three paths (the linter
  demands a plan gate there). It stops the agent mid-run for a human to
  approve the plan, so an unattended run stalls on it; omit it otherwise.
- autonomy: ask
Never output baseline, base_rev or dirty_baseline; they are measured, not drafted.
No prose, no code fences.
"""
DEMO_PYTHON = "python" if os.name == "nt" else "python3"
# The demo's acceptance command must not import a module: the bytecode cache it would
# leave behind is itself a change outside `scope`, and the clean pass would not be clean.
DEMO_BRIEF = f"""\
goal: Change the greeting word in greeting.py.
scope:
  - greeting.py
autonomy: ask
acceptance:
  - cmd: {DEMO_PYTHON} check.py
    expect: exit 0
manual_checks:
  - done: greeting.py no longer says hello
"""
DEMO_CHECK = """\
import pathlib

text = pathlib.Path("greeting.py").read_text(encoding="utf-8")
raise SystemExit(0 if text.startswith('WORD = "') else 1)
"""
CHILD_JSON_KEYS = {
    "scope": {"violations", "reviews", "findings"},
    "acceptance": {"passed", "failed", "not_run", "results"},
}


def review_is_acceptance_safe(finding):
    """Is this REVIEW an evidence-only flag, safe to gather acceptance results under?

    check_scope.py exports no machine-readable review kind, so the message text is the
    only classifier this layer has — and matching fails closed: a message these
    predicates do not recognize, including one a future check_scope.py edit reworded,
    keeps acceptance blocked. The four recognized kinds are the ones adjudicated as
    evidence-only: the unconditional tests-policy flag, the authoring skip-marker flag,
    a tracked brief modified since base, and the repin flag (acknowledged or not).
    A symlink review, a brief-deleted review, and anything unrecognized keep blocking.
    """
    message = str(finding.get("message") or "")
    return (
        (message.startswith("tests_policy `")
         and "lets test files change" in message)
        or (message.startswith("adds a disabling marker (")
            and message.endswith("under tests_policy `authoring`"))
        or message.startswith("the brief itself changed since the base revision")
        or (message.startswith("`base_rev: ")
            and "written after a `--deactivate`" in message)
    )


def acceptance_evidence_safe(scope_data):
    """May acceptance run despite a failed strict preflight? Only when the failure is
    reviews-only, every review is an evidence-only kind, and the base has a record
    outside the agent-writable brief (pin or repin). base_source None is the unarmed
    state: there the brief — its acceptance commands included — is one Write away from
    being the agent's own, and those commands run through the shell on the reviewer's
    machine. Running them on nothing more than a zero violation count is the exact
    wrong implementation this gate exists to prevent."""
    if scope_data.get("violations") != 0:
        return False
    if scope_data.get("base_source") not in ("pin", "repin"):
        return False
    findings = scope_data.get("findings")
    if not isinstance(findings, list):
        return False
    for finding in findings:
        if not isinstance(finding, dict) or finding.get("kind") != "REVIEW":
            return False
        if not review_is_acceptance_safe(finding):
            return False
    return True


def run_tool(name, *args):
    # The child's own stdout, which it already wrote as UTF-8 — decoding it with the
    # locale's encoding instead is how a Czech path in a verdict became mojibake, or a
    # traceback, on the way through this wrapper. `replace` because this layer only
    # reprints and re-parses that text: it cannot preserve a byte it also has to encode
    # back out, and a forwarded exit code must not depend on one.
    return subprocess.run(
        [sys.executable, str(HERE / TOOLS[name]), *map(str, args)],
        capture_output=True,
        encoding="utf-8",
        errors="replace",
    )


def emit_process(result):
    if result.stdout:
        print(result.stdout, end="")
    if result.stderr:
        print(result.stderr, end="", file=sys.stderr)
    return result.returncode


def replace_artifact(path, text):
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=path.parent,
                prefix=f".{path.name}.", suffix=".tmp", delete=False) as handle:
            temp_path = pathlib.Path(handle.name)
            handle.write(text)
        os.replace(temp_path, path)
        temp_path = None
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)


def _restore_brief(brief, original):
    """Put the pre-`prepare` bytes back after a failed stage. Byte-level on
    purpose: the brief is the user's file — comments, ordering, newline style —
    and a reserialized equivalent is exactly the partial state this exists to
    prevent. A restore that itself fails only warns: the stage error being
    reported is the primary signal and must not be masked."""
    if original is None:
        return
    try:
        if brief.read_bytes() == original:
            return
        temp_path = None
        try:
            with tempfile.NamedTemporaryFile(
                    mode="wb", dir=brief.parent,
                    prefix=f".{brief.name}.", suffix=".tmp", delete=False) as handle:
                temp_path = pathlib.Path(handle.name)
                handle.write(original)
            os.replace(temp_path, brief)
            temp_path = None
        finally:
            if temp_path is not None:
                temp_path.unlink(missing_ok=True)
    except OSError as exc:
        print(f"WARNING: could not restore {brief} to its pre-prepare bytes: {exc}",
              file=sys.stderr)


def _activation_committed(root, brief):
    """Did `--activate` write a pointer attesting to this brief's current bytes?

    `digest_of` returns None on a brief it cannot read and `read_pointer` returns
    sha256 None when there is no pointer, so the None case has to be answered before
    the comparison: `None == None` would claim a commit precisely when there is none
    and skip the restore that is owed."""
    digest = digest_of(brief)
    if digest is None:
        return False
    return read_pointer(root)["sha256"] == digest


def report_refusal(message, json_mode=False):
    if json_mode:
        print(json.dumps({"status": "refused", "message": message}, ensure_ascii=False))
    else:
        print(f"refused: {message}")
    return 2


def report_stage(stage, result, json_mode):
    code = result.returncode if result.returncode in (1, 2) else 2
    status = "failed" if code == 1 else "indeterminate"
    if json_mode:
        print(json.dumps({"status": status, "stage": stage,
                          "exit_code": result.returncode,
                          "stdout": result.stdout, "stderr": result.stderr},
                         ensure_ascii=False))
    else:
        print(f"{stage} {status}:", file=sys.stderr)
        emit_process(result)
    return code


def display_command(argv):
    parts = [str(part) for part in argv]
    return (subprocess.list2cmdline(parts) if os.name == "nt"
            else shlex.join(parts))


def report_prepared(brief, prompt, checklist, target, json_mode):
    next_command = display_command(["prompire", "verify", brief])
    if json_mode:
        print(json.dumps({"status": "prepared", "brief": str(brief),
                          "prompt": str(prompt), "checklist": str(checklist),
                          "target": target, "next": next_command}, ensure_ascii=False))
    else:
        print(f"prepared {brief}")
        print(f"prompt: {prompt}")
        print(f"checklist: {checklist}")
        print(next_command)
    return 0


def parse_child_json(stage, result):
    if result.returncode not in (0, 1, 2):
        if result.returncode < 0:
            return None, f"child terminated by signal {-result.returncode}"
        return None, f"unexpected child exit code {result.returncode}"
    try:
        data = json.loads(result.stdout)
    except (json.JSONDecodeError, TypeError) as exc:
        return None, f"child did not emit valid JSON: {exc}"
    if not isinstance(data, dict):
        return None, "child JSON is not an object"
    if result.returncode in (0, 1):
        missing = CHILD_JSON_KEYS[stage] - data.keys()
        if missing:
            return None, "child JSON is missing: " + ", ".join(sorted(missing))
    return data, None


def report_indeterminate(stage, result, message, json_mode, data=None):
    payload = {
        "status": "indeterminate",
        "stage": stage,
        "message": message,
        "exit_code": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
    }
    if json_mode:
        print(json.dumps(payload, ensure_ascii=False))
    else:
        # An exit-2 acceptance child speaks JSON ({"status": "indeterminate",
        # "error": ...}); an exit-2 scope child speaks prose. Print the error, or
        # the prose — never the raw JSON.
        error = data.get("error") if isinstance(data, dict) else None
        if error:
            print(f"no verdict: {error}")
            if result.stderr:
                print(result.stderr, end="", file=sys.stderr)
        else:
            print(f"no verdict: {stage} produced no trustworthy result")
            emit_process(result)
    return 2


def _counted(n, noun):
    return f"{n} {noun}" + ("" if n == 1 else "s")


ACK_REMEDY = re.compile(r"`--ack-disarms ([0-9a-f]{12,64})`")


def render_human_verdict(brief, scope_data, acceptance_data, code):
    """The verify result, retold for a human. This layer holds no authority: `code`
    arrives already computed from the children's exit codes, every finding and
    acceptance row is echoed from their JSON, and the one remedy line it can add
    quotes a digest check_scope itself printed — absent that phrasing, no remedy.
    The `caught: acceptance did not pass` wording is deliberate: `violation` is
    reserved for scope findings, and a not_runnable row exits 1 without failing."""
    findings = [f for f in (scope_data.get("findings") or []) if isinstance(f, dict)]
    results = acceptance_data.get("results")
    results = ([r for r in results if isinstance(r, dict)]
               if isinstance(results, list) else [])
    ran = acceptance_data.get("status") != "not_run"
    if code == 0:
        verdict = "clean"
    elif scope_data.get("violations"):
        verdict = "caught: " + _counted(scope_data["violations"], "violation")
    elif ran and (not results or any(not r.get("ok") for r in results)):
        verdict = "caught: acceptance did not pass"
    else:
        verdict = ("review: " + _counted(scope_data.get("reviews") or 0, "flag")
                   + " — needs a human")
    lines = [verdict]
    for finding in findings:
        lines.append(f"{str(finding.get('kind') or ''):9s} "
                     f"{finding.get('path') or ''}: {finding.get('message') or ''}")
        if finding.get("fix"):
            lines.append(f"          → {finding['fix']}")
    if not ran:
        lines.append(f"acceptance: not run — {acceptance_data.get('reason') or ''}")
    elif not results:
        lines.append("acceptance: no commands ran")
    else:
        for row in results:
            mark = ("PASS" if row.get("ok")
                    else "NOT RUN" if row.get("status") == "not_runnable" else "FAIL")
            lines.append(f"acceptance: {mark} {row.get('cmd') or ''}")
    if (scope_data.get("base_source") == "repin"
            and not scope_data.get("ack_disarms_bound")):
        for finding in findings:
            match = ACK_REMEDY.search(str(finding.get("message") or ""))
            if match:
                lines.append("acknowledge with: " + display_command(
                    ["prompire", "verify", str(brief),
                     "--ack-disarms", match.group(1)]))
                break
    return lines


def report_verification(brief, scope, scope_data, acceptance, acceptance_data,
                        json_mode):
    code = 1 if scope.returncode == 1 or acceptance.returncode == 1 else 0
    if json_mode:
        print(json.dumps({"scope": scope_data, "acceptance": acceptance_data},
                         ensure_ascii=False))
    else:
        for line in render_human_verdict(brief, scope_data, acceptance_data, code):
            print(line)
        if scope.stderr:
            print(scope.stderr, end="", file=sys.stderr)
        if acceptance.stderr:
            print(acceptance.stderr, end="", file=sys.stderr)
    return code


def report_scope_preflight(brief, scope, scope_data, json_mode):
    acceptance_data = {
        "status": "not_run",
        "reason": "strict scope preflight did not pass",
    }
    if json_mode:
        print(json.dumps({"scope": scope_data, "acceptance": acceptance_data},
                         ensure_ascii=False))
    else:
        for line in render_human_verdict(brief, scope_data, acceptance_data, 1):
            print(line)
        if scope.stderr:
            print(scope.stderr, end="", file=sys.stderr)
    return 1


def detect_acceptance(root):
    """Deterministic candidates only — never a command the repo gives no evidence for."""
    found = []
    pkg = root / "package.json"
    if pkg.is_file():
        try:
            scripts = json.loads(pkg.read_text(encoding="utf-8")).get("scripts") or {}
        except ValueError:
            scripts = {}
        if "test" in scripts:
            found.append(("npm test", "package.json scripts.test"))
    py = root / "pyproject.toml"
    if (root / "pytest.ini").is_file() or (
            py.is_file()
            and "[tool.pytest" in py.read_text(encoding="utf-8", errors="ignore")):
        found.append(("python3 -m pytest", "pytest configuration"))
    mk = root / "Makefile"
    if mk.is_file() and re.search(
            r"^test:", mk.read_text(encoding="utf-8", errors="ignore"), re.M):
        found.append(("make test", "Makefile test target"))
    if (root / "Cargo.toml").is_file():
        found.append(("cargo test", "Cargo.toml"))
    if (root / "go.mod").is_file():
        found.append(("go test ./...", "go.mod"))
    return found


def _yaml_scalar(value):
    # A scalar dumped as its own document ends with a `...` end marker on the
    # next line; only the scalar itself belongs on the line being built.
    text = yaml.safe_dump(value, default_flow_style=True, allow_unicode=True,
                          width=2 ** 20).strip()
    return text[:-4].strip() if text.endswith("\n...") else text


def strip_fences(text):
    lines = text.strip().splitlines()
    if lines and lines[0].startswith("```"):
        lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
    return "\n".join(lines)


def parse_agent_brief(text):
    """The agent's reply is data, not a brief: whatever survives this parse is
    re-serialized by agent_draft_text, so the agent's own comments — including a
    marker it pretends to have confirmed — never reach the file."""
    try:
        data = yaml.safe_load(strip_fences(text))
    except yaml.YAMLError:
        return None, "the reply is not YAML"
    if not isinstance(data, dict):
        return None, "the reply is not a YAML mapping"
    for key in DRAFT_MEASURED:
        if key in data:
            return None, f"`{key}` is measured, never drafted"
    unknown = sorted(str(k) for k in set(data) - set(DRAFT_KEYS))
    if unknown:
        return None, "keys a draft does not carry: " + ", ".join(unknown)
    # `plan_first` gates execution, so a YAML accident must not set it: the string
    # "false" is truthy, and rendering it would stop an unattended run for approval.
    if "plan_first" in data and not isinstance(data.get("plan_first"), bool):
        return None, (f"`plan_first: {data.get('plan_first')}` is not a boolean — "
                      "write true or false")
    # The `done:` spelling of a manual check declares that a human judgment is the
    # task's completion condition (B17). That declaration is the human's own act —
    # a compiler that could propose it could also rubber-stamp vacuity back in.
    for item in as_list(data.get("manual_checks")):
        if not isinstance(item, str):
            return None, ("a manual_checks entry in a proposal must be a plain "
                          "string — the `done:` completion-condition spelling is "
                          "the human's to write, never the compiler's")
    entries = []
    for item in as_list(data.get("acceptance")):
        if isinstance(item, str):
            item = {"cmd": item}
        if not isinstance(item, dict) or "cmd" not in item:
            return None, "an acceptance item without a cmd cannot be checked"
        stray = sorted(str(k) for k in set(item) - ACCEPTANCE_KEYS)
        if stray:
            return None, "acceptance keys a draft does not carry: " + ", ".join(stray)
        # A compiler writes the current spelling; the legacy one would only make the
        # linter warn the human about a line the model chose.
        if item.pop("must_flip", None) and not item.get("transition"):
            item["transition"] = "flip"
        entries.append(item)
    data["acceptance"] = entries
    return data, None


def tracked_paths(root):
    listed = subprocess.run(["git", "-C", str(root), "ls-files"],
                            capture_output=True, encoding="utf-8", errors="replace")
    if listed.returncode:
        return []
    return [norm_path(line) for line in listed.stdout.splitlines() if line]


def matches_tracked(pattern, tracked):
    try:
        rx = glob_re(pattern)
    except re.error:
        return False
    return any(rx.match(path) for path in tracked)


def _marked(line, note, ledger=None, label=None):
    if ledger is not None and label is not None:
        ledger.append(label)
    return f"{line}  # {DRAFT_MARKER} — {note}"


def agent_draft_text(sentence, data, root, source="agent"):
    """The one serializer every compiler frontend flows through — deterministic
    heuristic, `--agent`/`--agent-cmd`, and `--proposal` alike. The boundary and the
    judge stay unconfirmed until a human deletes each marker, however fluent the
    proposal; what the repository itself corroborates (a tracked path, a command a
    config file declares) is counted in `stats` but still shown for confirmation,
    because corroboration says the thing exists, not that it is the right boundary
    or the right judge. Every marked line is also listed in the `unconfirmed:` ledger,
    which is what survives a YAML round-trip. Returns (text, stats)."""
    detected = dict(detect_acceptance(root))
    tracked = tracked_paths(root)
    stats = {"tracked_scope": 0, "detected_acceptance": 0}
    ledger = []
    # The goal is line 1 of every rendered prompt and the compiler rewrites it
    # freely, which makes it an execution-control field in practice: adversarial
    # review put "…once a human has approved your written plan" there and walked
    # E1's stall straight past the plan_first gate. A comment is legal after a
    # block-scalar header, so the marker rides on `goal: |` itself. The user's own
    # sentence, carried through unchanged, is not the compiler's decision.
    goal_line = "goal: |"
    if str(data.get("goal") or "").strip():
        goal_line = _marked(goal_line,
                            "the compiler rewrote your request into this goal; it is "
                            "the first line the agent reads — confirm it says the task "
                            "and nothing about how the run is conducted",
                            ledger, "goal")
    body = [goal_line, f"  {' '.join(str(data.get('goal') or sentence).split())}"]
    out = body
    scope = [str(s) for s in as_list(data.get("scope"))]
    if scope:
        out.append("scope:")
        for index, entry in enumerate(scope):
            if matches_tracked(entry, tracked):
                stats["tracked_scope"] += 1
                note = "agent-proposed boundary; confirm it"
            else:
                note = "matches nothing tracked today — new file or typo? confirm it"
            out.append(_marked(f"  - {_yaml_scalar(entry)}", note,
                               ledger, f"scope[{index}]"))
    else:
        out.append(_marked("scope: []", "list the exact files the agent may edit",
                           ledger, "scope"))
    for key, note, empty_note in (
            ("forbidden", "agent-proposed deny-list; confirm it names what must not change",
             "the agent says nothing is off-limits; confirm that"),
            ("constraints", "agent-proposed invariants; confirm each is true and observable",
             None)):
        if key in data:
            values = [str(v) for v in as_list(data.get(key))]
            if values:
                out.append(_marked(f"{key}:", note, ledger, key))
                out += [f"  - {_yaml_scalar(v)}" for v in values]
            elif empty_note:
                out.append(_marked(f"{key}: []", empty_note, ledger, key))
            else:
                out.append(f"{key}: []")
    policy = data.get("tests_policy")
    if policy is not None:
        line = f"tests_policy: {_yaml_scalar(str(policy))}"
        if policy != "immutable":
            line = _marked(line, "agent proposed relaxing test protection; confirm it",
                           ledger, "tests_policy")
        out.append(line)
    editable = [str(t) for t in as_list(data.get("tests_editable"))]
    if editable:
        out.append(_marked("tests_editable:",
                           "only these test paths may change; confirm the list is exact",
                           ledger, "tests_editable"))
        out += [f"  - {_yaml_scalar(t)}" for t in editable]
    oracle = " ".join(str(data.get("oracle") or "").split())
    if oracle:
        out.append(_marked(f"oracle: {_yaml_scalar(oracle)}",
                           "agent-proposed judge for authored tests; confirm you trust it",
                           ledger, "oracle"))
    if data["acceptance"]:
        out.append("acceptance:")
        for index, item in enumerate(data["acceptance"]):
            cmd = str(item["cmd"])
            if cmd in detected:
                stats["detected_acceptance"] += 1
                note = f"detected from {detected[cmd]}; confirm it"
            else:
                note = "agent-proposed; run it yourself before trusting it"
            # Every sub-key that moves what the criterion decides is named on the
            # marked line, so deleting the marker is a decision about them too and
            # none of them rides in unread. `before_after` in particular is one of
            # the shapes B17 accepts as carrying done-ness.
            rest = {str(k): v for k, v in item.items() if k != "cmd"}
            rest.setdefault("expect", "exit 0")
            disclosures = [f"expects {rest['expect']}"]
            requires = [str(r) for r in as_list(item.get("requires"))]
            if requires:
                disclosures.append("declares requires: " + ", ".join(requires)
                                   + " — the baseline will never run it")
            transition = str(item.get("transition") or "").strip().lower()
            if transition == "flip":
                disclosures.append("claims it fails on HEAD and the work must flip it green")
            elif transition == "hold":
                disclosures.append("claims it must stay exactly as measured")
            if item.get("before_after"):
                disclosures.append("compares against the baseline digest, which is what "
                                   "says this task is done")
            if item.get("cwd") is not None:
                disclosures.append(f"runs in {norm_path(item['cwd']) or '.'}/")
            if item.get("timeout") is not None:
                disclosures.append(f"times out after {item['timeout']}s")
            out.append(_marked(f"  - cmd: {_yaml_scalar(cmd)}",
                               note + "; " + "; ".join(disclosures),
                               ledger, f"acceptance[{index}]"))
            out += [f"    {key}: {_yaml_scalar(rest[key])}" for key in sorted(rest)]
    else:
        out.append(_marked("acceptance: []",
                           "no test command detected; add one that exists in this repo"
                           if source == "deterministic" else
                           "the agent proposed no runnable check; add one that exists "
                           "in this repo", ledger, "acceptance"))
    manual = [str(m) for m in as_list(data.get("manual_checks"))]
    if manual:
        out.append(_marked("manual_checks:",
                           "only a human can check these; if one of them is what "
                           "decides the task is done, respell that line "
                           "`- done: <text>` yourself as you confirm — a note that "
                           "merely exists carries nothing (B17)",
                           ledger, "manual_checks"))
        out += [f"  - {_yaml_scalar(m)}" for m in manual]
    # A model told "at most three lines" plausibly answers with a YAML list; carry
    # the lines, not the list's repr.
    raw_context = data.get("context")
    if isinstance(raw_context, list):
        raw_context = "\n".join(str(item) for item in raw_context)
    context = str(raw_context or "").strip()
    if context:
        out.append(_marked("context: |",
                           "the prompt carries this as fact; confirm it is true and "
                           "worth its words", ledger, "context"))
        out += [f"  {line}".rstrip() for line in context.splitlines()]
    # E1: all eight compile agents copied `plan_first: true`, the field carried no
    # marker, and every delivered session stalled at "Get the plan approved". It is
    # an execution-mode decision, so it is the human's — marked like the boundary.
    if data.get("plan_first") is True:
        out.append(_marked(
            "plan_first: true",
            "stops the agent for plan approval before any edit — an unattended run "
            "stalls here; keep it only if someone will review the plan mid-run",
            ledger, "plan_first"))
    rollback = " ".join(str(data.get("rollback") or "").split())
    if rollback:
        # Inert at `ask`, but B8 requires a rollback before `autonomy: auto`, so
        # this string is what the operator raises autonomy on — and the renderer
        # interpolates it into the autonomy sentence itself.
        out.append(_marked(f"rollback: {_yaml_scalar(rollback)}",
                           "becomes part of the autonomy sentence if this brief is "
                           "ever raised to unattended autonomy; confirm it names an "
                           "undo and nothing else", ledger, "rollback"))
    out.append("autonomy: ask")
    head = [f"# Draft — read every line marked {DRAFT_MARKER}, fix it, delete the marker,",
            f"# then delete the `{DRAFT_LEDGER}:` block below. Prompire refuses to "
            "prepare or arm",
            "# while either remains: comments do not survive a YAML round-trip, the "
            "block does.",
            f"{DRAFT_LEDGER}:"]
    head += [f"  - {_yaml_scalar(label)}" for label in ledger]
    return "\n".join(head + body) + "\n", stats


def agent_argv(entry, prompt, root):
    """The argv to run and what to feed it on stdin. `{prompt}` and `{root}` are
    substituted only in DRAFT_AGENTS entries, never in an --agent-cmd — that contract
    is documented as prompt-on-stdin, and a caller's literal braces stay theirs. A
    host that takes the prompt as an argument gets an empty stdin: agy answers a
    piped stdin with its usage error instead of the draft."""
    embedded = any("{prompt}" in part for part in entry)
    argv = [part.replace("{prompt}", prompt).replace("{root}", str(root))
            for part in entry]
    return argv, ("" if embedded else prompt)


def _git_visible_paths(root):
    listed = subprocess.run(
        ["git", "-C", str(root), "ls-files", "--cached", "--others",
         "--exclude-standard", "-z"],
        capture_output=True,
    )
    if listed.returncode:
        message = listed.stderr.decode("utf-8", "replace").strip()
        raise OSError(message or "git could not list the repository files")
    # os.fsdecode, not decode(errors="replace"): an undecodable filesystem byte must
    # survive as a path that can be reopened, not as a replacement character.
    return [pathlib.Path(os.fsdecode(raw))
            for raw in listed.stdout.split(b"\0") if raw]


def _copy_snapshot_entry(source, target, real_root, snapshot):
    """Copy one Git-visible entry into the snapshot. A symlink recreated verbatim
    still aims where it always did, so an ordinary relative write by the agent would
    land through it in the caller's checkout; each one is re-aimed at the snapshot's
    own copy instead, or dropped when it resolves out of the tree. What the target
    resolves to decides, not whether it exists — a dangling link is carried when it
    would dangle inside the tree and dropped when it would dangle outside it."""
    if source.is_symlink():
        # realpath, not readlink: the whole chain has to be followed, or a link into
        # the tree that hops out again through a second link escapes the check.
        resolved = pathlib.Path(os.path.realpath(source))
        if not resolved.is_relative_to(real_root):
            return  # not this repository's to carry
        inside = snapshot / resolved.relative_to(real_root)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.symlink_to(os.path.relpath(inside, target.parent),
                          target_is_directory=source.is_dir())
    else:
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)


@contextlib.contextmanager
def draft_snapshot(root):
    """A throwaway git repo holding the tree's Git-visible files, for the agent to
    run in. A drafting agent only reads — claude -p denies writes by default and codex
    drafts read-only — but headless agy has no read-only mode and --agent-cmd can name
    anything, so the writes land here instead of in the caller's checkout."""
    snapshot = pathlib.Path(tempfile.mkdtemp(prefix="prompire-draft-"))
    try:
        # Resolved once: a checkout reached through a symlinked parent (/tmp on macOS)
        # would otherwise make every one of its own links look like an escape.
        real_root = pathlib.Path(os.path.realpath(root))
        for rel in _git_visible_paths(root):
            source = root / rel
            # git lists a submodule gitlink and an untracked nested checkout as single
            # directory entries. Their contents belong to their own repository, so the
            # snapshot carries neither — copying one as a file would refuse the draft.
            if source.is_dir() and not source.is_symlink():
                continue
            if os.path.lexists(source):
                _copy_snapshot_entry(source, snapshot / rel, real_root, snapshot)
        # The commit is prompire's machinery, not the caller's: `--template=` keeps a
        # global `init.templateDir` from seeding hooks, and the hooks path and
        # `--no-verify` keep the caller's own hooks from running against this tree.
        commands = (
            ["git", "init", "-q", "--template="],
            ["git", "add", "-A"],
            ["git", "-c", "user.email=draft@prompire",
             "-c", "user.name=prompire-draft", "-c", "commit.gpgsign=false",
             "-c", "core.hooksPath=", "commit", "--no-verify",
             "--allow-empty", "-qm", "draft snapshot"],
        )
        for command in commands:
            subprocess.run(command, cwd=str(snapshot), check=True,
                           capture_output=True)
        # The commit the agent starts from, so a write it commits away is still
        # visible to the audit afterwards — see `_snapshot_writes`.
        stamped = subprocess.run(["git", "-C", str(snapshot), "rev-parse", "HEAD"],
                                 capture_output=True, encoding="utf-8",
                                 errors="replace")
        yield snapshot, (stamped.stdout.strip() if stamped.returncode == 0 else None)
    finally:
        _rmtree(snapshot)


def run_draft_agent(argv, prompt, root):
    try:
        return subprocess.run(argv, input=prompt, cwd=str(root), capture_output=True,
                              encoding="utf-8", errors="replace",
                              timeout=DRAFT_AGENT_TIMEOUT), None
    except FileNotFoundError:
        return None, f"agent command not found: {argv[0]}"
    except subprocess.TimeoutExpired:
        return None, f"agent did not answer within {DRAFT_AGENT_TIMEOUT}s"


def draft_ledger(raw):
    """The still-unconfirmed decisions a draft's `unconfirmed:` block lists.

    Parsed from the text rather than taken from a loaded brief, so the three gates
    (prepare, lint B18, --activate) all read the same thing from the same bytes. An
    unparseable file has no ledger to report — the caller's own loader reports that.
    """
    try:
        data = yaml.safe_load(raw)
    except yaml.YAMLError:
        return []
    if not isinstance(data, dict) or DRAFT_LEDGER not in data:
        return []
    return [str(item) for item in as_list(data.get(DRAFT_LEDGER))] or [DRAFT_LEDGER]


def _snapshot_writes(agent_root, setup_rev):
    """What the drafting agent left changed in its snapshot, or None on an unreadable
    audit.

    Two questions, not one. `status --porcelain` compares the worktree to HEAD, which
    an agent that commits its own writes moves along with it — the same move the
    verifier's pinned base exists to refuse, and it hides a write here just as well.
    So the setup commit recorded before the agent ran is the second comparison, and a
    committed write shows up in it."""
    written = set()
    audited = subprocess.run(["git", "-C", str(agent_root), "status", "--porcelain"],
                             capture_output=True, encoding="utf-8", errors="replace")
    if audited.returncode:
        return None
    written.update(line[3:].strip() for line in audited.stdout.splitlines()
                   if line.strip())
    if setup_rev:
        moved = subprocess.run(
            ["git", "-C", str(agent_root), "diff", "--name-only", setup_rev],
            capture_output=True, encoding="utf-8", errors="replace")
        if moved.returncode:
            return None
        written.update(line.strip() for line in moved.stdout.splitlines()
                       if line.strip())
    return sorted(written)


def draft(args, extra):
    started = time.monotonic()
    if extra:
        return report_refusal("unrecognized arguments: " + " ".join(extra), args.json)
    backends = [flag for flag, value in (("--agent", args.agent),
                                         ("--agent-cmd", args.agent_cmd),
                                         ("--proposal", args.proposal)) if value]
    if len(backends) > 1:
        return report_refusal(" and ".join(backends)
                              + " name the same thing; pick one", args.json)
    if args.agent and args.agent not in DRAFT_AGENTS:
        known = ", ".join(sorted(DRAFT_AGENTS))
        return report_refusal(f"unknown agent `{args.agent}`; known: {known} — "
                              "or spell the whole command with --agent-cmd", args.json)
    try:
        root = repo_root(pathlib.Path("."))
    except RepoError as exc:
        return report_refusal(str(exc), args.json)
    # The default lands at the repo root, because that is the only place the Action's
    # `find_brief` looks. A path the caller typed keeps its cwd-relative meaning.
    out = root / DEFAULT_DRAFT_OUT if args.out is None else pathlib.Path(args.out)
    if os.path.lexists(out):  # a dangling symlink counts — never write through one
        return report_refusal(
            f"`{out}` already exists; if it is a draft you no longer want, delete it "
            "and re-run — or pick another --out", args.json)
    if args.proposal:
        backend = "proposal"
        try:
            proposed = (sys.stdin.read() if args.proposal == "-"
                        else pathlib.Path(args.proposal).read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError) as exc:
            return report_refusal(f"could not read the proposal: {exc}", args.json)
        data, trouble = parse_agent_brief(proposed)
        if trouble:
            return report_refusal(f"proposal rejected: {trouble}", args.json)
        text, stats = agent_draft_text(args.sentence, data, root)
    elif args.agent or args.agent_cmd:
        backend = f"agent:{args.agent}" if args.agent else "agent-cmd"
        prompt = DRAFT_PROMPT.format(sentence=args.sentence)
        try:
            # The host arguments are built inside the snapshot, so a `{root}` a host
            # takes as its workspace names the disposable repository too.
            with draft_snapshot(root) as (agent_root, setup_rev):
                if args.agent:
                    argv, feed = agent_argv(DRAFT_AGENTS[args.agent], prompt, agent_root)
                else:
                    argv, feed = shlex.split(args.agent_cmd), prompt
                if not argv:
                    return report_refusal("--agent-cmd is empty", args.json)
                answered, trouble = run_draft_agent(argv, feed, agent_root)
                if trouble is None:
                    # A drafting run only reads. A write is evidence the run broke
                    # its contract, not a mess to tidy: the snapshot absorbed it, and
                    # the refusal names it instead of repairing it.
                    written = _snapshot_writes(agent_root, setup_rev)
                    if written is None:
                        trouble = "could not audit the snapshot after the agent ran"
                    elif written:
                        shown = ", ".join(written[:5]) + (
                            f" (+{len(written) - 5} more)" if len(written) > 5 else "")
                        trouble = ("the drafting agent modified the repository "
                                   f"snapshot: {shown} — drafting is read-only; the "
                                   "writes were discarded with the snapshot")
        except (OSError, subprocess.CalledProcessError) as exc:
            return report_refusal(f"could not build the draft snapshot: {exc}",
                                  args.json)
        if trouble is None and answered.returncode:
            tail = (answered.stderr or answered.stdout).strip().splitlines()
            trouble = f"agent exited {answered.returncode}" + (
                f": {tail[-1]}" if tail else "")
        if trouble is None:
            data, trouble = parse_agent_brief(answered.stdout)
        if trouble:
            return report_refusal(f"agent draft rejected: {trouble}", args.json)
        text, stats = agent_draft_text(args.sentence, data, root)
    else:
        backend = "deterministic"
        data = {"acceptance": [{"cmd": cmd, "expect": "exit 0"}
                               for cmd, _ in detect_acceptance(root)]}
        text, stats = agent_draft_text(args.sentence, data, root,
                                       source="deterministic")
    # The budget preview runs at compile time, before any confirmation effort is
    # spent: E1's eight briefs all blew the 250-word render budget and learned it
    # only at handoff. Deterministic, measures nothing, executes nothing — it
    # reuses the renderer itself over a provisional baseline (see preview_counts).
    proposed = yaml.safe_load(text)
    counts = render_brief.preview_counts(proposed, str(out))
    preview = {"words": counts, "budget": render_brief.WORD_BUDGET,
               "over": sorted(t for t, n in counts.items()
                              if n > render_brief.WORD_BUDGET),
               "sections": dict(render_brief.budget_attribution(proposed))}
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")
    unconfirmed = text.count(f"# {DRAFT_MARKER}")
    corroborated = sum(stats.values())
    seconds = round(time.monotonic() - started, 2)
    next_command = display_command(["prompire", "prepare", out])
    if args.json:
        print(json.dumps({"status": "drafted", "out": str(out), "backend": backend,
                          "unconfirmed": unconfirmed, "corroborated": stats,
                          "render_preview": preview,
                          "seconds": seconds, "next": next_command},
                         ensure_ascii=False))
    else:
        print(f"drafted {out}")
        print(f"{_counted(unconfirmed, 'decision')} to confirm, "
              f"{_counted(corroborated, 'fact')} corroborated by the repository "
              f"(tracked scope: {stats['tracked_scope']}, detected acceptance: "
              f"{stats['detected_acceptance']})")
        if preview["over"]:
            worst_target = max(preview["words"], key=preview["words"].get)
            worst = preview["words"][worst_target]
            print(f"render preview: {worst_target} is {worst} words — "
                  f"{worst - preview['budget']} over the 250-word render budget "
                  "(prepare will refuse). Narrow the contract before confirming:")
            print("  " + ", ".join(f"{name} {words}"
                                   for name, words in preview["sections"].items()))
        print(f"confirm every `# {DRAFT_MARKER}` line, then: {next_command}")
    return 0


def demo_verdict(result):
    """Retell one `verify` run as prose — the child speaks JSON, the demo speaks English."""
    try:
        data = json.loads(result.stdout)
    except ValueError:
        data = None
    # Every key is read before a line is printed, so a JSON shape this retelling does not
    # know falls back to the raw run instead of half-narrating it and then raising. A
    # traceback here would turn `demo`'s refusal path (exit 2) into exit 1.
    try:
        scope = data["scope"]
        lines = [f"     {f['kind'].lower()}: {f['path']} — {f['message']}"
                 for f in scope["findings"]]
        lines.append(f"     scope: {scope['violations']} violation(s) "
                     f"against base {scope['base']}")
        acceptance = data["acceptance"]
        if acceptance.get("status") == "not_run":
            lines.append(f"     acceptance: not run — {acceptance['reason']}")
        else:
            lines += [f"     acceptance: {e['cmd']} — {e['status']}"
                      for e in acceptance["results"]]
    except (TypeError, KeyError, AttributeError, IndexError):
        emit_process(result)
        return
    for line in lines:
        print(line)
    print("     clean (exit 0)" if result.returncode == 0
          else f"     caught (exit {result.returncode})")


def _make_tree_writable(root):
    """Every object git writes under `.git/objects` is created read-only, and unlike
    POSIX (where deletion is a directory-permission question, so a file's own
    read-only bit doesn't matter), Windows refuses to unlink a read-only file. Clear
    the attribute on everything before removal is attempted, rather than reacting to
    the failure (`shutil.rmtree`'s `onerror=` hook is deprecated as of Python 3.12,
    and this repo supports 3.11 through 3.13)."""
    for dirpath, dirnames, filenames in os.walk(root):
        for name in dirnames + filenames:
            path = os.path.join(dirpath, name)
            try:
                os.chmod(path, os.stat(path).st_mode | stat.S_IWRITE)
            except OSError:
                pass
    try:
        os.chmod(root, os.stat(root).st_mode | stat.S_IWRITE)
    except OSError:
        pass


def _rmtree(root):
    _make_tree_writable(root)
    shutil.rmtree(root, ignore_errors=True)


def demo(args, extra):
    if extra:
        return report_refusal("unrecognized arguments: " + " ".join(extra))
    root = pathlib.Path(tempfile.mkdtemp(prefix="prompire-demo-")).resolve()

    def git(*command):
        # The seed commit must not depend on the caller's identity or signing config.
        subprocess.run(["git", "-C", str(root), "-c", "user.email=demo@prompire",
                        "-c", "user.name=demo", "-c", "commit.gpgsign=false",
                        *command], check=True, capture_output=True)

    def cli(*command):
        return subprocess.run([sys.executable, str(HERE / "prompire.py"), *command],
                              cwd=str(root), capture_output=True,
                              encoding="utf-8", errors="replace")

    try:
        (root / "greeting.py").write_text('WORD = "hello"\n', encoding="utf-8")
        (root / "check.py").write_text(DEMO_CHECK, encoding="utf-8")
        git("init", "-q")
        git("add", ".")
        git("commit", "-qm", "seed")
        (root / ".prompire").mkdir()
        (root / ".prompire" / "demo.yaml").write_text(DEMO_BRIEF, encoding="utf-8")
    except (OSError, subprocess.CalledProcessError) as exc:
        _rmtree(root)
        return report_refusal(f"could not build the demo repository: {exc}")

    print(f"demo repo: {root}")
    print("     greeting.py — the one file the brief lets the agent touch")
    print(f"     check.py — its test, run as `{DEMO_PYTHON} check.py`")
    print("the brief the agent is held to:")
    for line in DEMO_BRIEF.splitlines():
        print(f"     {line}")
    print("1. prepare: measure the acceptance command on untouched HEAD, lint the brief,")
    print("   render the prompt, pin the base commit.")
    prepared = cli("prepare", ".prompire/demo.yaml")
    if prepared.returncode == 0:
        print("     armed: prompt and checklist rendered, base commit pinned")
    else:
        emit_process(prepared)

    print('2. the agent does what it was asked: greeting.py now says "ahoj".')
    (root / "greeting.py").write_text('WORD = "ahoj"\n', encoding="utf-8")
    clean = cli("verify", ".prompire/demo.yaml", "--json")
    demo_verdict(clean)

    print("3. the same agent drifts and also writes secrets.cfg, which the brief")
    print("   never allowed.")
    (root / "secrets.cfg").write_text("token=oops\n", encoding="utf-8")
    caught = cli("verify", ".prompire/demo.yaml", "--json")
    demo_verdict(caught)

    if args.keep:
        print(f"kept: {root}")
    else:
        _rmtree(root)
    if not (prepared.returncode == 0 and clean.returncode == 0 and caught.returncode == 1):
        return report_refusal("the demo story did not play out; rerun with --keep")
    print("the violation above was read out of the real git diff against the pinned base —")
    print("the agent was never asked, so nothing it could claim would hide the extra file.")
    return 0


def prepare(args, extra):
    if extra:
        return report_refusal("unrecognized arguments: " + " ".join(extra), args.json)
    brief = pathlib.Path(args.brief)
    try:
        raw = brief.read_text(encoding="utf-8") if brief.is_file() else ""
    except (OSError, UnicodeDecodeError):
        raw = ""  # let baseline report an unreadable brief; the gate only reads markers
    if f"# {DRAFT_MARKER}" in raw:
        return report_refusal(
            f"draft not confirmed: fix and remove each `# {DRAFT_MARKER}` line first",
            args.json)
    if draft_ledger(raw):
        return report_refusal(
            f"draft not confirmed: the `{DRAFT_LEDGER}:` block still lists "
            + ", ".join(draft_ledger(raw))
            + ". Comments do not survive a YAML round-trip and this block does, so it "
              "is what says these decisions are still the compiler's. Read each one, "
              "then delete the block", args.json)
    try:
        root = repo_root(brief.resolve().parent)
    except RepoError as exc:
        return report_refusal(str(exc), args.json)
    live = active_brief(root)
    if live:
        return report_refusal(
            f"`{live}` is already active; run `prompire close {live}` first",
            json_mode=args.json,
        )

    try:
        original = brief.read_bytes()
    except OSError:
        original = None  # baseline reports the unreadable brief; nothing to restore

    def stage_failed(stage, result):
        _restore_brief(brief, original)
        return report_stage(stage, result, args.json)

    measured = run_tool("baseline", brief, "--write")
    if measured.returncode:
        return stage_failed("baseline", measured)

    linted = run_tool("lint", brief, "--json")
    if linted.returncode:
        return stage_failed("lint", linted)

    prompt = run_tool("render", brief, "--target", args.target)
    if prompt.returncode:
        return stage_failed("render", prompt)

    checklist = run_tool("render", brief, "--target", "_cli-checklist")
    if checklist.returncode:
        return stage_failed("render", checklist)

    prompt_path = brief.with_name(f"{brief.stem}.{args.target}.md")
    checklist_path = brief.with_name(f"{brief.stem}.checklist.md")
    try:
        replace_artifact(prompt_path, prompt.stdout)
        replace_artifact(checklist_path, checklist.stdout)
    except OSError as exc:
        _restore_brief(brief, original)
        return report_refusal(f"could not write artifacts: {exc}", args.json)

    armed = run_tool("scope", brief, "--activate")
    if armed.returncode:
        # The child's exit code is not a witness for the commit: check_scope writes the
        # pointer inside its guard-state lock, and a failure to release that lock (or any
        # death after the write) turns a committed activation into a nonzero exit.
        # Restoring then would break the digest the pointer already attests to and wedge
        # the repo at exit 2 until a tombstone-costing --deactivate. Ask the pointer.
        if not _activation_committed(root, brief):
            _restore_brief(brief, original)
        return report_stage("activate", armed, args.json)

    # Activation is the transaction's commit: the pointer's digest now attests to
    # the brief exactly as armed. No failure path below this line may restore the
    # pre-prepare bytes — that would break the digest and force exit 2 on every
    # later run until a --deactivate, which costs a tombstone.
    return report_prepared(
        brief=brief,
        prompt=prompt_path,
        checklist=checklist_path,
        target=args.target,
        json_mode=args.json,
    )


def verify(args, extra):
    if extra:
        return report_refusal("unrecognized arguments: " + " ".join(extra), args.json)
    scope_args = [args.brief, "--strict", "--json"]
    if args.ack_disarms:
        scope_args += ["--ack-disarms", args.ack_disarms]
    preflight = run_tool("scope", *scope_args)
    preflight_data, issue = parse_child_json("scope", preflight)
    if issue:
        return report_indeterminate("scope", preflight, issue, args.json)
    if preflight.returncode == 2:
        return report_indeterminate(
            "scope", preflight, "scope could not produce a trustworthy result",
            args.json, preflight_data)
    if preflight.returncode == 1 and not acceptance_evidence_safe(preflight_data):
        return report_scope_preflight(args.brief, preflight, preflight_data, args.json)

    acceptance = run_tool("acceptance", args.brief, "--json")
    acceptance_data, issue = parse_child_json("acceptance", acceptance)
    if issue:
        return report_indeterminate("acceptance", acceptance, issue, args.json)
    if acceptance.returncode == 2:
        return report_indeterminate(
            "acceptance", acceptance,
            "acceptance could not produce a trustworthy result", args.json,
            acceptance_data)

    scope = run_tool("scope", *scope_args)
    scope_data, issue = parse_child_json("scope", scope)
    if issue:
        return report_indeterminate("scope", scope, issue, args.json)
    if scope.returncode == 2:
        return report_indeterminate(
            "scope", scope, "scope could not produce a trustworthy result",
            args.json, scope_data)
    return report_verification(
        args.brief, scope, scope_data, acceptance, acceptance_data, args.json)


def close(args, extra):
    if extra:
        return report_refusal("unrecognized arguments: " + " ".join(extra))
    brief = pathlib.Path(args.brief)
    try:
        root = repo_root(brief.resolve().parent)
    except RepoError as exc:
        return report_refusal(str(exc))
    try:
        requested = brief.resolve().relative_to(root).as_posix()
    except ValueError:
        return report_refusal(f"`{brief}` is outside the repository at {root}")
    result = run_tool(
        "scope", args.brief, "--deactivate", "--expect-brief", requested)
    return emit_process(result) if result.returncode == 0 else report_stage(
        "close", result, False)


def status(args, extra):
    if extra:
        return report_refusal("unrecognized arguments: " + " ".join(extra), args.json)
    candidate = pathlib.Path(args.brief)
    start = candidate.resolve() if candidate.is_dir() else candidate.resolve().parent
    try:
        root = repo_root(start)
    except RepoError as exc:
        return report_refusal(str(exc), args.json)
    live = active_brief(root)
    if not live:
        data = {"status": "inactive"}
    else:
        pointer = read_pointer(root)
        data = {"status": "repin" if pointer["repin"] else "active",
                "brief": live, "base": pointer["base_rev"]}
    if args.json:
        print(json.dumps(data, ensure_ascii=False))
    elif data["status"] == "inactive":
        print("inactive")
    else:
        print(f"{data['status']} {data['brief']} {data['base'] or '-'}")
    return 0


def cli_version():
    """A checkout's VERSION file wins over installed metadata: `python3
    prompire.py --version` in a checkout must report the checkout, not
    whatever wheel is installed beside it. The wheel ships no VERSION, so an
    installed CLI reads its own package metadata instead."""
    version_file = HERE / "VERSION"
    if version_file.is_file():
        return version_file.read_text(encoding="utf-8").strip()
    return importlib.metadata.version("prompire")


class _VersionAction(argparse.Action):
    """The version is computed only when --version is asked for: a bare
    prompire.py copy with no VERSION beside it and no installed distribution
    must still run every other command."""

    def __call__(self, parser, namespace, values, option_string=None):
        print(cli_version())
        parser.exit()


def build_parser():
    parser = argparse.ArgumentParser(
        prog="prompire",
        description="Pin the contract before a coding agent works; "
                    "read the verdict from the real git diff after.")
    parser.add_argument("--version", action=_VersionAction, nargs=0)
    commands = parser.add_subparsers(dest="command", required=True,
                                     metavar="command")

    drafted = commands.add_parser(
        "draft", help="write a draft brief from one sentence")
    drafted.add_argument("sentence")
    drafted.add_argument("--out", default=None,
                         help=f"default: <repo root>/{DEFAULT_DRAFT_OUT}")
    drafted.add_argument("--agent", default=None,
                         help="delegate the drafting to a host CLI: "
                              + ", ".join(sorted(DRAFT_AGENTS)))
    drafted.add_argument("--agent-cmd", default=None,
                         help="any command that reads the drafting prompt on stdin "
                              "and prints the brief on stdout")
    drafted.add_argument("--proposal", default=None,
                         help="a YAML proposal to compile instead of invoking a "
                              "model; `-` reads stdin. Same validation and markers "
                              "as an agent reply")
    drafted.add_argument("--json", action="store_true")
    drafted.set_defaults(handler=draft)

    demoed = commands.add_parser(
        "demo", help="walk a clean run and a caught violation in a throwaway repo")
    demoed.add_argument("--keep", action="store_true")
    demoed.set_defaults(handler=demo)

    prepared = commands.add_parser(
        "prepare",
        help="measure the baseline, lint the brief, render the prompt, arm the guard")
    prepared.add_argument("brief")
    prepared.add_argument("--target", choices=PROMPT_TARGETS, default="generic")
    prepared.add_argument("--json", action="store_true")
    prepared.set_defaults(handler=prepare)

    verified = commands.add_parser(
        "verify", help="verdict from the real git diff plus the acceptance commands")
    verified.add_argument("brief")
    verified.add_argument("--ack-disarms")
    verified.add_argument("--json", action="store_true")
    verified.set_defaults(handler=verify)

    closed = commands.add_parser(
        "close", help="disarm the guard after review; the disarm is recorded")
    closed.add_argument("brief")
    closed.set_defaults(handler=close)

    stated = commands.add_parser(
        "status", help="which brief is armed in this repository")
    stated.add_argument("brief", nargs="?", default=".")
    stated.add_argument("--json", action="store_true")
    stated.set_defaults(handler=status)

    for name, description in (
            ("baseline", "diagnostic: run baseline.py directly"),
            ("lint", "diagnostic: run lint_brief.py directly"),
            ("render", "diagnostic: run render_brief.py directly"),
            ("scope", "diagnostic: run check_scope.py directly")):
        commands.add_parser(name, help=description)
    return parser


def main(argv=None):
    # This layer re-emits the children's JSON with `ensure_ascii=False`, so a path
    # check_scope.py escaped for its own stdout arrives back here as a real surrogate and
    # has to be printed again — see brief_common.utf8_stdio.
    utf8_stdio()
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] in LOW_LEVEL_COMMANDS:
        return emit_process(run_tool(argv[0], *argv[1:]))
    parser = build_parser()
    args, extra = parser.parse_known_args(argv)
    return args.handler(args, extra)


def entrypoint():
    raise SystemExit(main())


if __name__ == "__main__":
    entrypoint()
