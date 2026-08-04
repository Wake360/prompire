#!/usr/bin/env python3
import collections
import pathlib
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "bench"))

from universal_fixtures import TASKS, build_repository, run_visible_tests
from universal_grading import apply_gold_solution, grade_repository


def test_population_is_preregisterable():
    assert len(TASKS) == 12
    assert collections.Counter(task["specificity"] for task in TASKS) == {
        "LOW": 6, "MEDIUM": 4, "HIGH": 2,
    }
    assert len({task["project"] for task in TASKS}) >= 4
    surface_counts = collections.Counter(task["surface"] for task in TASKS)
    assert len(surface_counts) >= 6
    assert max(surface_counts.values()) <= 2
    assert sum(task["project"] != "image-cli" for task in TASKS) >= 8
    assert len({task["request"] for task in TASKS}) == len(TASKS)


def test_every_fixture_starts_clean_and_has_a_solvable_hidden_grade():
    for task in TASKS:
        with tempfile.TemporaryDirectory(prefix="prompire-benchmark-test-") as tmp:
            root = pathlib.Path(tmp)
            build_repository(root, task["id"])
            assert run_visible_tests(root).returncode == 0
            assert not grade_repository(root, task["grader"])["success"]
            apply_gold_solution(root, task["grader"])
            result = grade_repository(root, task["grader"])
            assert result["success"], (task["id"], result)


def main():
    tests = (
        test_population_is_preregisterable,
        test_every_fixture_starts_clean_and_has_a_solvable_hidden_grade,
    )
    for test in tests:
        test()
    print(f"{len(tests)}/{len(tests)} universal benchmark cases pass")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
