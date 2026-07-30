#!/usr/bin/env python3
import argparse
import json
import os
import pathlib
import re
import subprocess
import sys
import tempfile

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
CHILD_JSON_KEYS = {
    "scope": {"violations", "reviews", "findings"},
    "acceptance": {"passed", "failed", "not_run", "results"},
}


def run_tool(name, *args):
    return subprocess.run(
        [sys.executable, str(HERE / TOOLS[name]), *map(str, args)],
        capture_output=True,
        text=True,
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
    out = pathlib.Path(args.out)
    if os.path.lexists(out):  # a dangling symlink counts — never write through one
        return report_refusal(f"`{out}` already exists; pick another --out")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(draft_text(args.sentence, detect_acceptance(root)), encoding="utf-8")
    print(f"drafted {out}")
    print(f"confirm every `# {DRAFT_MARKER}` line, then: prompire prepare {out}")
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
    drafted.add_argument("--out", default=".prompire/task.yaml")
    drafted.set_defaults(handler=draft)

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
