#!/usr/bin/env python3
import argparse
import json
import os
import pathlib
import re
import shutil
import stat
import subprocess
import sys
import tempfile

from brief_common import tolerant_stdio
from check_scope import RepoError, active_brief, read_pointer, repo_root

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
# A draft is not a brief yet. Every line the heuristic could not settle carries this
# marker, and `prepare` refuses while one remains — deleting it is the confirmation.
DRAFT_MARKER = "prompire:unconfirmed"
DEFAULT_DRAFT_OUT = ".prompire/task.yaml"
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


def report_prepared(brief, prompt, checklist, target, json_mode):
    next_command = f"prompire verify {brief}"
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


def report_indeterminate(stage, result, message, json_mode):
    data = {
        "status": "indeterminate",
        "stage": stage,
        "message": message,
        "exit_code": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
    }
    if json_mode:
        print(json.dumps(data, ensure_ascii=False))
    else:
        print(f"{stage} indeterminate: {message}")
        emit_process(result)
    return 2


def report_verification(scope, scope_data, acceptance, acceptance_data, json_mode):
    code = 1 if scope.returncode == 1 or acceptance.returncode == 1 else 0
    if json_mode:
        print(json.dumps({"scope": scope_data, "acceptance": acceptance_data},
                         ensure_ascii=False))
    else:
        print("scope:")
        print(scope.stdout, end="")
        print("acceptance:")
        print(acceptance.stdout, end="")
        if scope.stderr:
            print(scope.stderr, end="", file=sys.stderr)
        if acceptance.stderr:
            print(acceptance.stderr, end="", file=sys.stderr)
    return code


def report_scope_preflight(scope, scope_data, json_mode):
    acceptance_data = {
        "status": "not_run",
        "reason": "strict scope preflight did not pass",
    }
    if json_mode:
        print(json.dumps({"scope": scope_data, "acceptance": acceptance_data},
                         ensure_ascii=False))
    else:
        print("scope:")
        print(scope.stdout, end="")
        print("acceptance:")
        print("NOT RUN strict scope preflight did not pass")
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


def draft_text(sentence, detected):
    out = [f"# Draft — read every line marked {DRAFT_MARKER}, fix it, delete the marker.",
           "goal: |", f"  {sentence}",
           f"scope: []  # {DRAFT_MARKER} — list the exact files the agent may edit",
           "autonomy: ask"]
    if detected:
        out.append("acceptance:")
        for cmd, src in detected:
            out += [f"  - cmd: {cmd}  # {DRAFT_MARKER} — detected from {src}; confirm it",
                    "    expect: exit 0"]
    else:
        out.append(f"acceptance: []  # {DRAFT_MARKER} — no test command detected; "
                   "add one that exists in this repo")
    return "\n".join(out) + "\n"


def draft(args, extra):
    if extra:
        return report_refusal("unrecognized arguments: " + " ".join(extra))
    try:
        root = repo_root(pathlib.Path("."))
    except RepoError as exc:
        return report_refusal(str(exc))
    # The default lands at the repo root, because that is the only place the Action's
    # `find_brief` looks. A path the caller typed keeps its cwd-relative meaning.
    out = root / DEFAULT_DRAFT_OUT if args.out is None else pathlib.Path(args.out)
    if os.path.lexists(out):  # a dangling symlink counts — never write through one
        return report_refusal(f"`{out}` already exists; pick another --out")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(draft_text(args.sentence, detect_acceptance(root)), encoding="utf-8")
    print(f"drafted {out}")
    print(f"confirm every `# {DRAFT_MARKER}` line, then: prompire prepare {out}")
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

    measured = run_tool("baseline", brief, "--write")
    if measured.returncode:
        return report_stage("baseline", measured, args.json)

    linted = run_tool("lint", brief, "--json")
    if linted.returncode:
        return report_stage("lint", linted, args.json)

    prompt = run_tool("render", brief, "--target", args.target)
    if prompt.returncode:
        return report_stage("render", prompt, args.json)

    checklist = run_tool("render", brief, "--target", "_cli-checklist")
    if checklist.returncode:
        return report_stage("render", checklist, args.json)

    prompt_path = brief.with_name(f"{brief.stem}.{args.target}.md")
    checklist_path = brief.with_name(f"{brief.stem}.checklist.md")
    try:
        replace_artifact(prompt_path, prompt.stdout)
        replace_artifact(checklist_path, checklist.stdout)
    except OSError as exc:
        return report_refusal(f"could not write artifacts: {exc}", args.json)

    armed = run_tool("scope", brief, "--activate")
    if armed.returncode:
        return report_stage("activate", armed, args.json)

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
            "scope", preflight, "scope could not produce a trustworthy result", args.json)
    if preflight.returncode == 1:
        return report_scope_preflight(preflight, preflight_data, args.json)

    acceptance = run_tool("acceptance", args.brief, "--json")
    acceptance_data, issue = parse_child_json("acceptance", acceptance)
    if issue:
        return report_indeterminate("acceptance", acceptance, issue, args.json)
    if acceptance.returncode == 2:
        return report_indeterminate(
            "acceptance", acceptance,
            "acceptance could not produce a trustworthy result", args.json)

    scope = run_tool("scope", *scope_args)
    scope_data, issue = parse_child_json("scope", scope)
    if issue:
        return report_indeterminate("scope", scope, issue, args.json)
    if scope.returncode == 2:
        return report_indeterminate(
            "scope", scope, "scope could not produce a trustworthy result", args.json)
    return report_verification(
        scope, scope_data, acceptance, acceptance_data, args.json)


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
    try:
        root = repo_root(pathlib.Path(args.brief).resolve().parent)
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


def build_parser():
    parser = argparse.ArgumentParser(prog="prompire")
    commands = parser.add_subparsers(dest="command", required=True)

    drafted = commands.add_parser("draft")
    drafted.add_argument("sentence")
    drafted.add_argument("--out", default=None,
                         help=f"default: <repo root>/{DEFAULT_DRAFT_OUT}")
    drafted.set_defaults(handler=draft)

    demoed = commands.add_parser("demo")
    demoed.add_argument("--keep", action="store_true")
    demoed.set_defaults(handler=demo)

    prepared = commands.add_parser("prepare")
    prepared.add_argument("brief")
    prepared.add_argument("--target", choices=PROMPT_TARGETS, default="generic")
    prepared.add_argument("--json", action="store_true")
    prepared.set_defaults(handler=prepare)

    verified = commands.add_parser("verify")
    verified.add_argument("brief")
    verified.add_argument("--ack-disarms")
    verified.add_argument("--json", action="store_true")
    verified.set_defaults(handler=verify)

    closed = commands.add_parser("close")
    closed.add_argument("brief")
    closed.set_defaults(handler=close)

    stated = commands.add_parser("status")
    stated.add_argument("brief")
    stated.add_argument("--json", action="store_true")
    stated.set_defaults(handler=status)

    for name in LOW_LEVEL_COMMANDS:
        commands.add_parser(name)
    return parser


def main(argv=None):
    # This layer re-emits the children's JSON with `ensure_ascii=False`, so a path
    # check_scope.py escaped for its own stdout arrives back here as a real surrogate and
    # has to be printed again — see brief_common.tolerant_stdio.
    tolerant_stdio()
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
