#!/usr/bin/env python3
import argparse
import concurrent.futures
import hashlib
import json
import os
import pathlib
import random
import shutil
import statistics
import subprocess
import sys
import tempfile
import threading
import time

import yaml

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from task_compiler import CodexModel, TaskContextCompiler
from universal_fixtures import PROJECTS, TASKS, build_repository, task_by_id
from universal_grading import grade_repository


PREREG = ROOT / "bench/universal_prereg.yaml"
DEFAULT_OUTPUT = ROOT / "bench/results/universal-2026-08-04"
FROZEN_PATHS = (
    "bench/universal_fixtures.py", "bench/universal_grading.py",
    "README.md", "critic.py", "prompire.py", "prompt_stdlib.py",
    "pyproject.toml", "repo_context.py", "task_compiler.py", "task_ir.py",
    "task_renderer.py", "task_resolver.py",
)
EXECUTOR_DISABLED_FEATURES = (
    "apps", "auth_elicitation", "browser_use", "browser_use_external",
    "browser_use_full_cdp_access", "computer_use", "hooks",
    "image_generation", "in_app_browser", "multi_agent", "plugins",
    "remote_plugin", "skill_mcp_dependency_install", "skill_search",
    "tool_call_mcp_elicitation", "tool_suggest",
)
WRITE_LOCK = threading.Lock()


def sha256_text(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def run(command, cwd=None, **kwargs):
    return subprocess.run(command, cwd=cwd, check=True, **kwargs)


def git(root, *args):
    return run(
        ["git", "-C", str(root), *args], capture_output=True,
        text=True, encoding="utf-8").stdout.strip()


def read_jsonl(path):
    path = pathlib.Path(path)
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()]


def append_jsonl(path, row):
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with WRITE_LOCK, path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def write_json(path, value):
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8")
    os.replace(temporary, path)


def load_prereg(path=PREREG):
    return yaml.safe_load(pathlib.Path(path).read_text(encoding="utf-8"))


def validate_freeze(prereg):
    frozen = prereg["final_prompt_compiler_revision"]
    resolved = git(ROOT, "rev-parse", frozen)
    if resolved != frozen:
        raise RuntimeError("frozen compiler revision does not resolve exactly")
    changed = subprocess.run(
        ["git", "-C", str(ROOT), "diff", "--quiet", frozen, "--", *FROZEN_PATHS])
    if changed.returncode:
        raise RuntimeError("frozen compiler files changed after preregistration")


def validate_population(prereg):
    population = prereg["population"]
    if len(TASKS) != population["tasks"]:
        raise RuntimeError("task count differs from preregistration")
    counts = {level: sum(task["specificity"] == level for task in TASKS)
              for level in ("LOW", "MEDIUM", "HIGH")}
    if counts != population["specificity"]:
        raise RuntimeError("specificity population differs from preregistration")
    projects = {task["project"] for task in TASKS}
    surfaces = {task["surface"] for task in TASKS}
    if len(projects) < population["minimum_projects"]:
        raise RuntimeError("too few benchmark projects")
    if len(surfaces) < population["minimum_surfaces"]:
        raise RuntimeError("too few benchmark surfaces")
    if max(sum(item["surface"] == surface for item in TASKS)
           for surface in surfaces) > population["maximum_tasks_per_surface"]:
        raise RuntimeError("one surface exceeds its task cap")
    existing = sum(task["project"] != "image-cli" for task in TASKS)
    if existing < population["minimum_existing_repository_tasks"]:
        raise RuntimeError("too few existing-repository tasks")


def representative_task(project):
    return next(task["id"] for task in TASKS if task["project"] == project)


def prepare_repositories(output):
    repositories = {}
    for project in sorted(PROJECTS):
        root = output / "repositories" / project
        if not (root / ".git").exists():
            if root.exists():
                shutil.rmtree(root)
            root.mkdir(parents=True)
            build_repository(root, representative_task(project))
        repositories[project] = {
            "path": str(root.resolve()),
            "revision": git(root, "rev-parse", "HEAD"),
        }
    return repositories


def clone_repository(source, destination):
    run(["git", "clone", "-q", "--no-hardlinks", str(source), str(destination)])
    return destination


def compilation_id(task, repeat):
    return f"{task['id']}-PROMPIRE-R{repeat}"


def all_cell_specs(prereg):
    repeats = prereg["population"]["repeats_per_task_per_arm"]
    cells = []
    for task in TASKS:
        for arm in prereg["population"]["arms"]:
            for repeat in range(1, repeats + 1):
                cells.append({
                    "cell_id": f"{task['id']}-{arm}-R{repeat}",
                    "task_id": task["id"],
                    "arm": arm,
                    "repeat": repeat,
                })
    random.Random(prereg["execution"]["seed"]).shuffle(cells)
    return cells


def compile_once(task, repeat, repository, prereg):
    cell_id = compilation_id(task, repeat)
    started = time.monotonic()
    attempts = 0
    last_error = None
    while attempts < 1:
        attempts += 1
        try:
            with tempfile.TemporaryDirectory(prefix=f"universal-compile-{cell_id}-") as tmp:
                target = clone_repository(repository["path"], pathlib.Path(tmp) / "repo")
                model = CodexModel(
                    timeout=prereg["execution"]["compiler_timeout_seconds"],
                    model=prereg["execution"]["compiler_model"],
                    effort=prereg["execution"]["compiler_reasoning_effort"],
                )
                result = TaskContextCompiler(
                    target, model, model,
                    target_model=prereg["execution"]["executor_model"],
                ).compile(task["request"])
            return {
                "cell_id": cell_id,
                "task_id": task["id"],
                "repeat": repeat,
                "repository_revision": repository["revision"],
                "prompt": result.prompt,
                "task_ir": result.task_ir.to_dict(),
                "metrics": result.metrics,
                "record": result.record,
                "attempts": attempts,
                "infrastructure_error": None,
            }
        except Exception as exc:
            last_error = f"{type(exc).__name__}: {exc}"
    return {
        "cell_id": cell_id,
        "task_id": task["id"],
        "repeat": repeat,
        "repository_revision": repository["revision"],
        "prompt": None,
        "task_ir": None,
        "metrics": {"wall_time_seconds": round(time.monotonic() - started, 3)},
        "record": None,
        "attempts": attempts,
        "infrastructure_error": last_error,
    }


def compile_prompts(output, repositories, prereg):
    path = output / "compilations.jsonl"
    existing = {row["cell_id"] for row in read_jsonl(path)}
    jobs = []
    repeats = prereg["population"]["repeats_per_task_per_arm"]
    for task in TASKS:
        for repeat in range(1, repeats + 1):
            if compilation_id(task, repeat) not in existing:
                jobs.append((task, repeat, repositories[task["project"]]))
    with concurrent.futures.ThreadPoolExecutor(
            max_workers=prereg["execution"]["compiler_workers"]) as pool:
        futures = [pool.submit(compile_once, *job, prereg) for job in jobs]
        for future in concurrent.futures.as_completed(futures):
            row = future.result()
            append_jsonl(path, row)
            print(
                f"compiled {row['cell_id']} "
                f"{row['metrics'].get('wall_time_seconds', 0):.3f}s",
                flush=True)
    return read_jsonl(path)


def executor_argv(root, prereg):
    execution = prereg["execution"]
    argv = [
        "codex", "exec", "--strict-config", "--ignore-user-config",
        "--ignore-rules", "--sandbox", execution["sandbox"], "--ephemeral",
        "--color", "never", "--json",
    ]
    for feature in EXECUTOR_DISABLED_FEATURES:
        argv.extend(["--disable", feature])
    argv.extend([
        "-c", 'web_search="disabled"',
        "-m", execution["executor_model"],
        "-c", f'model_reasoning_effort="{execution["executor_reasoning_effort"]}"',
        "-C", str(root), "-",
    ])
    return argv


def parse_events(text):
    final_message = ""
    usage = {"input": 0, "cached_input": 0, "output": 0}
    turns = 0
    turn_started = False
    tool_events = 0
    invalid_events = 0
    for line in (text or "").splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            invalid_events += 1
            continue
        event_type = event.get("type")
        if event_type == "turn.started":
            turn_started = True
        if event_type == "turn.completed":
            turns += 1
            values = event.get("usage") or {}
            usage["input"] += int(values.get("input_tokens") or 0)
            usage["cached_input"] += int(values.get("cached_input_tokens") or 0)
            usage["output"] += int(values.get("output_tokens") or 0)
        if event_type == "item.completed":
            item = event.get("item") or {}
            item_type = item.get("type")
            if item_type == "agent_message":
                final_message = item.get("text") or final_message
            elif item_type != "reasoning":
                tool_events += 1
    usage["total"] = usage["input"] + usage["output"]
    return {
        "final_message": final_message,
        "usage": usage,
        "turns": turns,
        "turn_started": turn_started,
        "tool_events": tool_events,
        "invalid_events": invalid_events,
    }


def execute_process(prompt, root, prereg):
    argv = executor_argv(root, prereg)
    started = time.monotonic()
    try:
        result = subprocess.run(
            argv, input=prompt, cwd=root, capture_output=True,
            text=True, encoding="utf-8", errors="replace",
            timeout=prereg["execution"]["executor_timeout_seconds"],
        )
        parsed = parse_events(result.stdout)
        return {
            **parsed,
            "exit_code": result.returncode,
            "timed_out": False,
            "stderr_tail": "\n".join(result.stderr.splitlines()[-5:]),
            "wall_time_seconds": round(time.monotonic() - started, 3),
        }
    except subprocess.TimeoutExpired as exc:
        parsed = parse_events(exc.stdout or "")
        return {
            **parsed,
            "exit_code": 124,
            "timed_out": True,
            "stderr_tail": "executor timed out",
            "wall_time_seconds": round(time.monotonic() - started, 3),
        }
    except OSError as exc:
        return {
            **parse_events(""),
            "exit_code": 127,
            "timed_out": False,
            "stderr_tail": f"{type(exc).__name__}: {exc}",
            "wall_time_seconds": round(time.monotonic() - started, 3),
        }


def changed_paths(root):
    output = git(root, "status", "--short", "--untracked-files=all")
    paths = []
    for line in output.splitlines():
        value = line[3:]
        if " -> " in value:
            value = value.split(" -> ", 1)[1]
        paths.append(value.strip('"'))
    return sorted(dict.fromkeys(paths))


def save_changes(root, destination, paths):
    destination.mkdir(parents=True, exist_ok=True)
    patch = subprocess.run(
        ["git", "-C", str(root), "diff", "--binary", "HEAD"],
        capture_output=True).stdout
    (destination / "tracked.diff").write_bytes(patch)
    files = {}
    for relative in paths:
        source = root / relative
        if not source.is_file() or source.is_symlink():
            continue
        target = destination / "files" / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        try:
            files[relative] = source.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            files[relative] = None
    return files


def unnecessary_paths(task, paths):
    expected = set(task["expected_paths"])
    return [path for path in paths
            if path not in expected and not path.startswith("tests/")]


def synthetic_executor_failure(spec, task, repository, message):
    return ({
        **spec,
        "request": task["request"],
        "repository_revision": repository["revision"],
        "prompt_hash": None,
        "executor_model": None,
        "executor_reasoning_effort": None,
        "codex_cli_version": None,
        "agent_exit": 127,
        "timed_out": False,
        "turns": 0,
        "tool_events": 0,
        "usage": {"input": 0, "cached_input": 0, "output": 0, "total": 0},
        "executor_wall_time_seconds": 0,
        "attempts": 0,
        "final_message": "",
        "stderr_tail": message,
        "changed_paths": [],
        "unnecessary_changed_paths": [],
        "visible_tests_pass": False,
        "visible_test_output": "",
        "review_material": {},
        "infrastructure_failure": True,
        "human_intervention": 0,
    }, {
        "cell_id": spec["cell_id"], "task_id": task["id"],
        "success": False, "hidden_pass": False,
        "first_attempt_success": False,
        "hidden_output": message, "subjective_pending": False,
        "infrastructure_failure": True,
    })


def execute_cell(spec, compilation, repository, output, prereg):
    task = task_by_id(spec["task_id"])
    if spec["arm"] == "PROMPIRE":
        if not compilation or compilation.get("infrastructure_error"):
            return synthetic_executor_failure(
                spec, task, repository, "compiler infrastructure failure")
        prompt = compilation["prompt"]
    else:
        prompt = task["request"]
    with tempfile.TemporaryDirectory(prefix=f"universal-cell-{spec['cell_id']}-") as tmp:
        target = clone_repository(repository["path"], pathlib.Path(tmp) / "repo")
        attempts = []
        result = execute_process(prompt, target, prereg)
        attempts.append(result)
        if not result["turn_started"] and result["exit_code"]:
            result = execute_process(prompt, target, prereg)
            attempts.append(result)
        paths = changed_paths(target)
        save_changes(target, output / "changes" / spec["cell_id"], paths)
        grade = grade_repository(target, task["grader"])
        review_material = {}
        if task["id"] == "U10":
            for relative in ("web/dashboard.html", "web/dashboard.css"):
                review_material[relative] = (target / relative).read_text(encoding="utf-8")
    total_wall = sum(item["wall_time_seconds"] for item in attempts)
    total_usage = {
        key: sum(item["usage"][key] for item in attempts)
        for key in ("input", "cached_input", "output", "total")
    }
    infrastructure = not any(item["turn_started"] for item in attempts)
    success = bool(
        grade["success"] and result["exit_code"] == 0 and not infrastructure)
    cell = {
        **spec,
        "request": task["request"],
        "repository_revision": repository["revision"],
        "prompt_hash": sha256_text(prompt),
        "executor_model": prereg["execution"]["executor_model"],
        "executor_reasoning_effort": prereg["execution"]["executor_reasoning_effort"],
        "codex_cli_version": prereg["execution"]["codex_cli_version"],
        "agent_exit": result["exit_code"],
        "timed_out": result["timed_out"],
        "turns": sum(item["turns"] for item in attempts),
        "tool_events": sum(item["tool_events"] for item in attempts),
        "usage": total_usage,
        "executor_wall_time_seconds": round(total_wall, 3),
        "attempts": len(attempts),
        "final_message": result["final_message"],
        "stderr_tail": result["stderr_tail"],
        "changed_paths": paths,
        "unnecessary_changed_paths": unnecessary_paths(task, paths),
        "visible_tests_pass": grade["visible_pass"],
        "visible_test_output": grade["visible_output"],
        "review_material": review_material,
        "infrastructure_failure": infrastructure,
        "human_intervention": 0,
    }
    hidden = {
        "cell_id": spec["cell_id"],
        "task_id": task["id"],
        "success": success if task["id"] != "U10" else None,
        "first_attempt_success": success if task["id"] != "U10" else None,
        "hidden_pass": grade["hidden_pass"],
        "hidden_output": grade["hidden_output"],
        "subjective_pending": task["id"] == "U10",
        "infrastructure_failure": infrastructure,
    }
    return cell, hidden


def execute_cells(output, repositories, prereg, compilations):
    cell_path = output / "cells.jsonl"
    grade_path = output / "grades.hidden.jsonl"
    completed = {row["cell_id"] for row in read_jsonl(cell_path)}
    compilation_by_id = {row["cell_id"]: row for row in compilations}
    jobs = []
    for spec in all_cell_specs(prereg):
        if spec["cell_id"] in completed:
            continue
        task = task_by_id(spec["task_id"])
        compilation = compilation_by_id.get(
            compilation_id(task, spec["repeat"])) if spec["arm"] == "PROMPIRE" else None
        jobs.append((spec, compilation, repositories[task["project"]]))
    with concurrent.futures.ThreadPoolExecutor(
            max_workers=prereg["execution"]["executor_workers"]) as pool:
        futures = [pool.submit(
            execute_cell, spec, compilation, repository, output, prereg)
            for spec, compilation, repository in jobs]
        for future in concurrent.futures.as_completed(futures):
            cell, grade = future.result()
            append_jsonl(cell_path, cell)
            append_jsonl(grade_path, grade)
            print(
                f"executed {cell['cell_id']} exit={cell['agent_exit']} "
                f"visible={cell['visible_tests_pass']}", flush=True)
    return read_jsonl(cell_path), read_jsonl(grade_path)


def blind_mobile_grade(output, repositories, prereg, cells, grades):
    current = final_grades(grades)
    mobile_ids = {cell["cell_id"] for cell in cells if cell["task_id"] == "U10"}
    if ((output / "blind-review.json").exists()
            and len(mobile_ids) == 4
            and all(not current.get(cell_id, {}).get("subjective_pending", True)
                    for cell_id in mobile_ids)):
        return grades, True
    mobile = sorted(
        (cell for cell in cells if cell["task_id"] == "U10"),
        key=lambda cell: cell["cell_id"])
    if len(mobile) != 4:
        raise RuntimeError("subjective grading requires four U10 cells")
    labels = ["A", "B", "C", "D"]
    random.Random(prereg["execution"]["seed"] + 10).shuffle(labels)
    mapping = dict(zip(labels, mobile))
    baseline_root = pathlib.Path(repositories["reporting-ui"]["path"])
    payload = {
        "task": task_by_id("U10")["request"],
        "rubric": prereg["grading"]["subjective_rubric"],
        "pass_score": prereg["grading"]["subjective_pass_score"],
        "baseline": {
            path: (baseline_root / path).read_text(encoding="utf-8")
            for path in ("web/dashboard.html", "web/dashboard.css")
        },
        "candidates": [
            {"label": label, "files": mapping[label]["review_material"]}
            for label in labels
        ],
    }
    write_json(output / "blind-review-input.json", payload)
    write_json(output / "blind-key.hidden.json", {
        label: mapping[label]["cell_id"] for label in labels})
    schema = {
        "type": "object",
        "properties": {
            "results": {
                "type": "array", "minItems": 4, "maxItems": 4,
                "items": {
                    "type": "object",
                    "properties": {
                        "label": {"type": "string", "enum": labels},
                        "score": {"type": "integer", "minimum": 0, "maximum": 10},
                        "critical_regression": {"type": "boolean"},
                        "rationale": {"type": "string", "maxLength": 500},
                    },
                    "required": ["label", "score", "critical_regression", "rationale"],
                    "additionalProperties": False,
                },
            },
        },
        "required": ["results"],
        "additionalProperties": False,
    }
    prompt = """Blindly grade four implementations of the same mobile dashboard task.
Arm identity and prompts are hidden. Review only the baseline, candidate files, and preregistered rubric.
Award 0-2 points for each rubric dimension. A critical regression means desktop information/actions were removed or existing behavior was materially broken.
Return one independent score and concise observable rationale per label.

MATERIAL
""" + json.dumps(payload, ensure_ascii=False)
    response = None
    error = None
    for _ in range(prereg["grading"]["subjective_reviewer_attempts"]):
        try:
            model = CodexModel(
                timeout=prereg["execution"]["compiler_timeout_seconds"],
                model=prereg["grading"]["subjective_reviewer_model"],
                effort=prereg["grading"]["subjective_reviewer_reasoning_effort"],
            )
            response = model.complete(prompt, schema)
            break
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
    if response is None:
        write_json(output / "blind-review.json", {"error": error})
        return grades, False
    results = response.data["results"]
    if {item["label"] for item in results} != set(labels):
        write_json(output / "blind-review.json", {"error": "invalid labels"})
        return grades, False
    write_json(output / "blind-review.json", {
        "results": results,
        "tokens": {
            "input": response.input_tokens,
            "cached_input": response.cached_input_tokens,
            "output": response.output_tokens,
        },
    })
    cells_by_id = {cell["cell_id"]: cell for cell in cells}
    by_cell = {mapping[item["label"]]["cell_id"]: item for item in results}
    for cell_id, item in by_cell.items():
        cell = cells_by_id[cell_id]
        passed = (
            item["score"] >= prereg["grading"]["subjective_pass_score"]
            and not item["critical_regression"]
            and cell["visible_tests_pass"]
            and cell["agent_exit"] == 0
            and not cell["infrastructure_failure"]
        )
        override = {
            "cell_id": cell_id,
            "task_id": "U10",
            "success": passed,
            "first_attempt_success": passed,
            "hidden_pass": True,
            "hidden_output": "",
            "subjective_pending": False,
            "infrastructure_failure": cell["infrastructure_failure"],
            "blind_score": item["score"],
            "critical_regression": item["critical_regression"],
            "blind_rationale": item["rationale"],
        }
        append_jsonl(output / "grades.hidden.jsonl", override)
        grades.append(override)
    return grades, True


def lower_is_better_improvement(raw, prompire):
    if raw <= 0:
        return None
    return (raw - prompire) / raw * 100


def final_grades(grades):
    by_cell = {}
    for grade in grades:
        by_cell[grade["cell_id"]] = grade
    return by_cell


def summarize(output, prereg, compilations, cells, grades, blind_available):
    grades_by_cell = final_grades(grades)
    task_rows = []
    for task in TASKS:
        row = {"task_id": task["id"], "surface": task["surface"],
               "specificity": task["specificity"]}
        for arm in ("RAW", "PROMPIRE"):
            outcomes = []
            for repeat in (1, 2):
                cell_id = f"{task['id']}-{arm}-R{repeat}"
                grade = grades_by_cell.get(cell_id, {})
                outcomes.append(bool(grade.get("success")))
            row[arm.lower() + "_repeats"] = outcomes
            row[arm.lower() + "_score"] = sum(outcomes) / 2
        row["delta"] = row["prompire_score"] - row["raw_score"]
        task_rows.append(row)
    raw_total = sum(row["raw_score"] for row in task_rows)
    prompire_total = sum(row["prompire_score"] for row in task_rows)
    levels = {}
    for level in ("LOW", "MEDIUM", "HIGH"):
        subset = [row for row in task_rows if row["specificity"] == level]
        raw = sum(row["raw_score"] for row in subset)
        prompire = sum(row["prompire_score"] for row in subset)
        levels[level] = {"raw": raw, "prompire": prompire,
                         "delta": prompire - raw}
    positive_surfaces = sorted({row["surface"] for row in task_rows if row["delta"] > 0})
    successful_compiles = [row for row in compilations if not row["infrastructure_error"]]
    compiler_latencies = [row["metrics"]["wall_time_seconds"]
                          for row in successful_compiles]
    compiler_tokens = [row["metrics"]["model_total_tokens"]
                       for row in successful_compiles]
    cells_by_arm = {
        arm: [cell for cell in cells if cell["arm"] == arm]
        for arm in ("RAW", "PROMPIRE")
    }
    executor_medians = {
        arm: statistics.median(cell["usage"]["total"] for cell in rows)
        for arm, rows in cells_by_arm.items()
    }
    executor_wall_medians = {
        arm: statistics.median(cell["executor_wall_time_seconds"] for cell in rows)
        for arm, rows in cells_by_arm.items()
    }
    executor_turn_medians = {
        arm: statistics.median(cell["turns"] for cell in rows)
        for arm, rows in cells_by_arm.items()
    }
    unnecessary_means = {
        arm: statistics.mean(len(cell["unnecessary_changed_paths"]) for cell in rows)
        for arm, rows in cells_by_arm.items()
    }
    executor_token_improvement = lower_is_better_improvement(
        executor_medians["RAW"], executor_medians["PROMPIRE"])
    unnecessary_improvement = lower_is_better_improvement(
        unnecessary_means["RAW"], unnecessary_means["PROMPIRE"])
    low_ids = {task["id"] for task in TASKS if task["specificity"] == "LOW"}
    low_cells = {
        arm: [cell for cell in rows if cell["task_id"] in low_ids]
        for arm, rows in cells_by_arm.items()
    }
    low_executor = {
        arm: statistics.median(cell["usage"]["total"] for cell in rows)
        for arm, rows in low_cells.items()
    }
    low_unnecessary = {
        arm: statistics.mean(len(cell["unnecessary_changed_paths"]) for cell in rows)
        for arm, rows in low_cells.items()
    }
    low_secondary = [
        lower_is_better_improvement(low_executor["RAW"], low_executor["PROMPIRE"]),
        lower_is_better_improvement(low_unnecessary["RAW"], low_unnecessary["PROMPIRE"]),
    ]
    low_secondary = [value for value in low_secondary if value is not None]
    overall_secondary = [executor_token_improvement, unnecessary_improvement]
    overall_secondary = [value for value in overall_secondary if value is not None]
    primary = prereg["primary_success"]
    median_compiler_latency = (
        statistics.median(compiler_latencies) if compiler_latencies else None)
    median_compiler_tokens = (
        statistics.median(compiler_tokens) if compiler_tokens else None)
    primary_pass = (
        median_compiler_latency is not None
        and prompire_total >= raw_total + primary["prompire_total_minimum_delta"]
        and levels["LOW"]["delta"] >= primary["low_specificity_minimum_delta"]
        and levels["HIGH"]["delta"] >= -primary["high_specificity_maximum_regression"]
        and len(positive_surfaces) >= primary["minimum_positive_delta_surfaces"]
        and median_compiler_latency <= primary["maximum_median_compiler_latency_seconds"]
        and sum(row["metrics"]["human_questions"] for row in successful_compiles)
            == primary["compiler_questions"]
    )
    ceiling = prereg["ceiling_rule"]
    ceiling_active = raw_total >= ceiling["activates_at_raw_total"]
    ceiling_pass = (
        ceiling_active
        and prompire_total >= raw_total - ceiling["maximum_success_regression"]
        and levels["LOW"]["delta"] >= 0
        and any(value >= ceiling["low_specificity_secondary_improvement_percent"]
                for value in low_secondary)
        and any(value >= ceiling["overall_secondary_improvement_percent"]
                for value in overall_secondary)
    )
    infrastructure_failures = sum(cell["infrastructure_failure"] for cell in cells)
    blocker = (
        infrastructure_failures
        > prereg["methodological_blocker"]["unresolved_infrastructure_cells_greater_than"]
        or not blind_available
        or len(cells) != 48
        or len(grades_by_cell) != 48
    )
    confirmed = not blocker and (ceiling_pass if ceiling_active else primary_pass)
    state = "INCONCLUSIVE" if blocker else ("CONFIRMED" if confirmed else "REJECTED")
    summary = {
        "state": state,
        "raw_total": raw_total,
        "prompire_total": prompire_total,
        "delta": prompire_total - raw_total,
        "specificity": levels,
        "positive_delta_surfaces": positive_surfaces,
        "median_compiler_latency_seconds": median_compiler_latency,
        "median_compiler_tokens": median_compiler_tokens,
        "median_compiler_calls": statistics.median(
            row["metrics"]["model_calls"] for row in successful_compiles)
            if successful_compiles else None,
        "median_prompt_words": statistics.median(
            row["metrics"]["prompt_words"] for row in successful_compiles)
            if successful_compiles else None,
        "compiler_questions": sum(
            row["metrics"]["human_questions"] for row in successful_compiles),
        "uniform_solved": {
            arm: sum(row[arm.lower() + "_score"] == 1 for row in task_rows)
            for arm in ("RAW", "PROMPIRE")
        },
        "executor_median_tokens": executor_medians,
        "executor_median_wall_time_seconds": executor_wall_medians,
        "executor_median_turns": executor_turn_medians,
        "mean_unnecessary_file_changes": unnecessary_means,
        "executor_token_improvement_percent": executor_token_improvement,
        "unnecessary_change_improvement_percent": unnecessary_improvement,
        "compiler_total_tokens": sum(compiler_tokens),
        "compiler_total_wall_time_seconds": sum(compiler_latencies),
        "executor_total_tokens": {
            arm: sum(cell["usage"]["total"] for cell in rows)
            for arm, rows in cells_by_arm.items()
        },
        "total_product_tokens": {
            "RAW": sum(cell["usage"]["total"] for cell in cells_by_arm["RAW"]),
            "PROMPIRE": sum(compiler_tokens)
                + sum(cell["usage"]["total"] for cell in cells_by_arm["PROMPIRE"]),
        },
        "total_product_wall_time_seconds": {
            "RAW": sum(cell["executor_wall_time_seconds"]
                       for cell in cells_by_arm["RAW"]),
            "PROMPIRE": sum(compiler_latencies)
                + sum(cell["executor_wall_time_seconds"]
                      for cell in cells_by_arm["PROMPIRE"]),
        },
        "first_attempt_successes": {
            arm: sum(bool(grades_by_cell.get(cell["cell_id"], {}).get(
                         "first_attempt_success"))
                     for cell in rows)
            for arm, rows in cells_by_arm.items()
        },
        "visible_regressions": {
            arm: sum(not cell["visible_tests_pass"] for cell in rows)
            for arm, rows in cells_by_arm.items()
        },
        "human_intervention": {
            arm: sum(cell["human_intervention"] for cell in rows)
            for arm, rows in cells_by_arm.items()
        },
        "infrastructure_failures": infrastructure_failures,
        "primary_pass": primary_pass,
        "ceiling_active": ceiling_active,
        "ceiling_pass": ceiling_pass,
        "task_results": task_rows,
    }
    write_json(output / "summary.json", summary)
    final_compilations = []
    for compilation in compilations:
        row = json.loads(json.dumps(compilation))
        cell_id = compilation["cell_id"]
        cell = next((item for item in cells if item["cell_id"] == cell_id), None)
        grade = grades_by_cell.get(cell_id)
        if row.get("record") and cell and grade:
            row["record"]["downstream_outcome"] = grade.get("success")
            row["record"]["downstream_tokens"] = cell["usage"]
            row["record"]["human_intervention"] = cell["human_intervention"]
        final_compilations.append(row)
    final_path = output / "compilations.final.jsonl"
    final_path.write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n"
                for row in final_compilations), encoding="utf-8")
    return summary


def build_manifest(output, prereg, repositories):
    cells = all_cell_specs(prereg)
    manifest = {
        "preregistration_sha256": sha256_text(
            PREREG.read_text(encoding="utf-8")),
        "final_prompt_compiler_revision": prereg["final_prompt_compiler_revision"],
        "tasks": list(TASKS),
        "repositories": repositories,
        "execution_order": [cell["cell_id"] for cell in cells],
        "compiler_model": prereg["execution"]["compiler_model"],
        "executor_model": prereg["execution"]["executor_model"],
        "codex_cli_version": prereg["execution"]["codex_cli_version"],
    }
    write_json(output / "manifest.json", manifest)
    return manifest


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=pathlib.Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--phase", choices=("validate", "compile", "execute", "all"), default="all")
    args = parser.parse_args(argv)
    prereg = load_prereg()
    validate_freeze(prereg)
    validate_population(prereg)
    if args.phase == "validate":
        print("benchmark preregistration valid")
        return 0
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    repositories = prepare_repositories(output)
    build_manifest(output, prereg, repositories)
    compilations = compile_prompts(output, repositories, prereg)
    if args.phase == "compile":
        return 0
    cells, grades = execute_cells(output, repositories, prereg, compilations)
    grades, blind_available = blind_mobile_grade(
        output, repositories, prereg, cells, grades)
    summary = summarize(
        output, prereg, compilations, cells, grades, blind_available)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
