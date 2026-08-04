#!/usr/bin/env python3
import argparse
import concurrent.futures
import json
import pathlib
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "bench"))

from task_compiler import CodexModel, TaskContextCompiler
from task_renderer import word_count
from universal_fixtures import build_repository


SMOKE_CASES = (
    ("S01", "add retries", "U01"),
    ("S02", "migrate users to UUIDs", "U03"),
    ("S03", "add JSON output", "U05"),
    ("S04", "speed up startup", "U06"),
    ("S05", "clean up this module", "U06"),
    ("S06", "add deployment health checks", "U07"),
    ("S07", "fix CSV export", "U09"),
    ("S08", "make dashboard better on mobile", "U10"),
    ("S09", "build a small CLI for converting images", "U08"),
    ("S10", "rename Foo to Bar in README.md", "U11"),
)


def compile_case(case):
    case_id, request, fixture_id = case
    with tempfile.TemporaryDirectory(prefix=f"prompire-smoke-{case_id}-") as tmp:
        target = pathlib.Path(tmp)
        build_repository(target, fixture_id)
        model = CodexModel(timeout=240)
        result = TaskContextCompiler(target, model, model).compile(request)
        guidance = result.task_ir.to_dict()
        guidance_count = sum(len(guidance[key]) for key in (
            "likely_relevant", "context", "preserve", "watch_for", "checks"))
        assert result.task_ir.objective == request
        assert result.metrics["model_calls"] == 4
        assert result.metrics["human_questions"] == 0
        assert result.metrics["prompt_words"] <= 250
        if result.metrics["specificity"] == "HIGH":
            assert word_count(result.prompt) <= word_count(request) + 30
        else:
            assert guidance_count > 0
        return {
            "case_id": case_id,
            "fixture_id": fixture_id,
            "request": request,
            "task_ir": guidance,
            "prompt": result.prompt,
            "metrics": result.metrics,
            "record": result.record,
        }


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=pathlib.Path,
                        default=ROOT / "bench/results/universal-smoke.json")
    parser.add_argument("--workers", type=int, default=2)
    args = parser.parse_args(argv)
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        rows = list(pool.map(compile_case, SMOKE_CASES))
    rows.sort(key=lambda row: row["case_id"])
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for row in rows:
        facets = ",".join(row["record"]["selected_semantic_facets"])
        print(
            f"{row['case_id']} {row['metrics']['specificity']} "
            f"{row['metrics']['prompt_words']}w {row['metrics']['wall_time_seconds']:.3f}s "
            f"[{facets}]")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
