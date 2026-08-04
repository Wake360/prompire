#!/usr/bin/env python3
import contextlib
import io
import json
import os
import pathlib
import shlex
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from repo_context import RepoContext, RepoContextError
from task_compiler import (
    append_experiment_record,
    CodexModel,
    CompilationResult,
    ModelExecutionError,
    ModelResponse,
    TaskContextCompiler,
)
from task_ir import TaskIR, TaskIRError
from task_renderer import render_task
from task_resolver import RETRIEVAL_SCHEMA, resolve_facets, resolve_specificity
from prompt_stdlib import SemanticSelection, policy_catalog

import prompire
from critic import Critic


def git(root, *args):
    return subprocess.run(
        ["git", "-C", str(root), *args],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


def build_repo(root):
    (root / "src" / "export").mkdir(parents=True)
    (root / "tests" / "export").mkdir(parents=True)
    (root / "src" / "export" / "csv.py").write_text(
        "def export_csv(rows):\n    return '\\n'.join(rows)\n",
        encoding="utf-8",
    )
    (root / "src" / "export" / "serializer.py").write_text(
        "from .csv import export_csv\n\ndef export_rows(rows):\n    return export_csv(rows)\n",
        encoding="utf-8",
    )
    (root / "tests" / "export" / "test_csv.py").write_text(
        "from src.export.csv import export_csv\n",
        encoding="utf-8",
    )
    (root / "pyproject.toml").write_text(
        "[tool.pytest.ini_options]\ntestpaths = ['tests']\n",
        encoding="utf-8",
    )
    (root / "src" / "large.txt").write_text("x" * 50_000, encoding="utf-8")
    git(root, "init", "-q")
    git(root, "add", ".")
    git(root, "-c", "user.email=test@prompire", "-c", "user.name=Prompire",
        "commit", "-qm", "seed CSV export")


def test_task_ir_is_small_and_typed():
    ir = TaskIR.from_dict({
        "objective": "Preserve embedded newlines inside quoted CSV fields.",
        "likely_relevant": ["src/export/csv.py", "tests/export/test_csv.py"],
        "context": ["The exporter preprocesses values before joining rows."],
        "preserve": ["Delimiter behavior stays unchanged."],
        "watch_for": ["Do not remove newlines before quoting."],
        "checks": ["Run python3 -m pytest tests/export/test_csv.py."],
    })
    assert ir.objective.startswith("Preserve embedded")
    assert ir.likely_relevant == (
        "src/export/csv.py", "tests/export/test_csv.py")
    assert ir.to_dict()["watch_for"] == ["Do not remove newlines before quoting."]

    try:
        TaskIR.from_dict({"objective": "x", "implementation_plan": ["edit csv.py"]})
    except TaskIRError as exc:
        assert "implementation_plan" in str(exc)
    else:
        raise AssertionError("Task IR accepted a planning field")

    for invalid in (
        task_ir(context=["x"] * 3),
        task_ir(watch_for=["x" * 1_000]),
    ):
        try:
            TaskIR.from_dict(invalid)
        except TaskIRError:
            pass
        else:
            raise AssertionError("Task IR accepted content outside its prompt budget")

    try:
        Critic(ScriptedModel([{"issues": ["x" * 241]}])).review(
            "fix CSV", (), ir)
    except TaskIRError:
        pass
    else:
        raise AssertionError("critic accepted an issue outside its prompt budget")


def test_repo_context_exposes_only_bounded_read_operations():
    with tempfile.TemporaryDirectory(prefix="prompire-context-") as tmp:
        root = pathlib.Path(tmp)
        build_repo(root)
        untracked = root / "secret.txt"
        untracked.write_text("not compiler evidence\n", encoding="utf-8")
        before = git(root, "status", "--short").stdout

        repo = RepoContext(root)
        overview = repo.overview("fix CSV export with quoted newlines")
        assert overview["tracked_file_count"] == 5
        assert "src/export/csv.py" in overview["candidate_paths"]
        assert "tests/export/test_csv.py" in overview["candidate_paths"]

        evidence = repo.retrieve([
            {"op": "search_text", "query": "export_csv"},
            {"op": "read_file", "path": "src/export/csv.py", "start": 1, "end": 20},
            {"op": "history", "path": "src/export/csv.py", "limit": 3},
            {"op": "list_files", "pattern": "*test*csv*"},
        ])
        assert len(evidence) == 4
        assert "src/export/csv.py:1:def export_csv" in evidence[0]["content"]
        assert "return '\\n'.join(rows)" in evidence[1]["content"]
        assert "seed CSV export" in evidence[2]["content"]
        assert "tests/export/test_csv.py" in evidence[3]["content"]
        assert repo.metrics["retrieval_calls"] == 5
        assert repo.metrics["by_operation"] == {
            "overview": 1,
            "search_text": 1,
            "read_file": 1,
            "history": 1,
            "list_files": 1,
        }
        assert len(repo._retrieve_read_file({
            "path": "src/large.txt", "start": 1, "end": 1,
        })) <= repo.MAX_RESULT_CHARS
        try:
            repo._retrieve_read_file({
                "path": "src/large.txt", "start": 2, "end": 2,
            })
        except RepoContextError as exc:
            assert "physical line" in str(exc)
        else:
            raise AssertionError("file reader drained an oversized physical line")
        try:
            repo._retrieve_read_file({
                "path": "src/export/csv.py", "start": 100_000, "end": 100_001,
            })
        except RepoContextError as exc:
            assert "start" in str(exc)
        else:
            raise AssertionError("file reader accepted unbounded line scanning")
        assert git(root, "status", "--short").stdout == before

        partial = repo.retrieve([
            {"op": "read_file", "path": "missing.py", "start": 1, "end": 10},
            {"op": "read_file", "path": "src/export/csv.py", "start": 1, "end": 10},
        ])
        assert "error" in partial[0]
        assert "def export_csv" in partial[1]["content"]

        if os.name != "nt":
            external_ran = root / "external-diff-ran"
            external = root / "external-diff"
            external.write_text(
                f"#!/bin/sh\ntouch {str(external_ran)!r}\n",
                encoding="utf-8",
            )
            external.chmod(0o700)
            git(root, "config", "diff.external", str(external))
            (root / "src" / "export" / "csv.py").write_text(
                "def export_csv(rows):\n    return 'changed'\n",
                encoding="utf-8",
            )
            git(root, "add", "src/export/csv.py")
            diff = repo.retrieve([{"op": "diff", "path": "src/export/csv.py"}])
            assert not external_ran.exists(), "repository config executed an external diff"
            assert "changed" in diff[0]["content"]

            (root / "src" / "export" / "serializer.py").unlink()
            deleted = repo.retrieve([
                {"op": "history", "path": "src/export/serializer.py", "limit": 2},
                {"op": "diff", "path": "src/export/serializer.py"},
            ])
            assert "seed CSV export" in deleted[0]["content"]
            assert "deleted file mode" in deleted[1]["content"]

        for query in ({"op": "shell", "command": "touch owned"},):
            try:
                repo.retrieve([query])
            except RepoContextError:
                pass
            else:
                raise AssertionError(f"unsafe retrieval query accepted: {query}")
        assert not (root / "owned").exists()

        other = root / "nested-repo"
        other.mkdir()
        (other / "other.py").write_text("OTHER = True\n", encoding="utf-8")
        git(other, "init", "-q")
        git(other, "add", ".")
        git(other, "-c", "user.email=test@prompire", "-c", "user.name=Prompire",
            "commit", "-qm", "other")
        old_git_dir = os.environ.get("GIT_DIR")
        old_git_tree = os.environ.get("GIT_WORK_TREE")
        try:
            os.environ["GIT_DIR"] = str(other / ".git")
            os.environ["GIT_WORK_TREE"] = str(other)
            isolated = RepoContext(root)
        finally:
            if old_git_dir is None:
                os.environ.pop("GIT_DIR", None)
            else:
                os.environ["GIT_DIR"] = old_git_dir
            if old_git_tree is None:
                os.environ.pop("GIT_WORK_TREE", None)
            else:
                os.environ["GIT_WORK_TREE"] = old_git_tree
        assert isolated.overview("CSV export")["tracked_file_count"] == 5

        if os.name != "nt":
            fake_bin = root / "fake-bin"
            fake_bin.mkdir()
            fake_git = fake_bin / "git"
            fake_git.write_text(
                "#!/bin/sh\n"
                f"{shlex.quote(sys.executable)} -c 'print(\"x\" * 3000000)'\n",
                encoding="utf-8",
            )
            fake_git.chmod(0o700)
            old_path = os.environ["PATH"]
            os.environ["PATH"] = str(fake_bin) + os.pathsep + old_path
            try:
                try:
                    RepoContext(root)
                except RepoContextError as exc:
                    assert "output limit" in str(exc)
                else:
                    raise AssertionError("repository command output was not bounded")
            finally:
                os.environ["PATH"] = old_path


class ScriptedModel:
    def __init__(self, responses):
        self.responses = list(responses)
        self.prompts = []

    def complete(self, prompt, schema):
        self.prompts.append((prompt, schema))
        if not self.responses:
            raise AssertionError("model received an unexpected extra call")
        return ModelResponse(self.responses.pop(0), input_tokens=100, output_tokens=20)


def task_ir(**changes):
    data = {
        "objective": "Preserve embedded newlines inside quoted CSV fields.",
        "likely_relevant": ["src/export/csv.py", "tests/export/test_csv.py"],
        "context": ["The exporter joins preprocessed row values."],
        "preserve": ["Existing delimiter behavior stays unchanged."],
        "watch_for": ["Do not strip newlines before serialization."],
        "checks": ["Run python3 -m pytest tests/export/test_csv.py."],
    }
    data.update(changes)
    return data


def guidance(**changes):
    data = task_ir(**changes)
    data.pop("objective")
    return data


def resolution(*, facets=None, specificity="LOW", policies=None, **changes):
    return {
        "task_ir": guidance(**changes),
        "semantic_facets": facets or ["fix", "data", "existing_system"],
        "specificity": specificity,
        "adopted_policy_ids": policies or [],
    }


def revised_resolution(*, adopted_issues=None, **changes):
    return {
        **resolution(**changes),
        "adopted_issue_numbers": adopted_issues or [],
    }


def test_semantic_facets_compose_and_filter_candidate_policies():
    selected = SemanticSelection.from_reply(
        ["migrate", "backend", "data", "compatibility", "reliability",
         "existing_system"],
        "LOW",
        ["migration.persisted-data", "compatibility.observable-behavior"],
    )
    assert selected.facets == (
        "migrate", "backend", "data", "compatibility", "reliability",
        "existing_system",
    )
    assert "migration.persisted-data" in selected.candidate_policy_ids
    assert "reliability.failure-policy" in selected.candidate_policy_ids
    assert "compatibility.observable-behavior" in selected.adopted_policy_ids
    assert "reliability.failure-policy" in selected.rejected_policy_ids

    unknown = SemanticSelection.from_reply(
        ["general", "existing_system"], "LOW", [])
    assert unknown.facets == ("general", "existing_system")
    assert unknown.specificity == "LOW"

    try:
        SemanticSelection.from_reply(
            ["ui", "existing_system"], "MEDIUM", ["api.validation-error-shape"])
    except TaskIRError as exc:
        assert "selected facets" in str(exc)
    else:
        raise AssertionError("a policy outside the selected facets was adopted")

    catalog = policy_catalog()
    assert catalog["ui"]["kind"] == "surface"
    assert catalog["performance"]["kind"] == "quality"
    assert catalog["greenfield"]["kind"] == "project_state"
    assert any(item["id"] == "reliability.bounded-retries"
               for item in catalog["reliability"]["policies"])
    assert any(item["id"] == "data.structured-roundtrip"
               for item in catalog["data"]["policies"])
    assert all("best practice" not in item["guidance"].lower()
               for facet in catalog.values() for item in facet["policies"])


def test_cross_domain_tasks_have_compositional_candidate_knowledge():
    cases = (
        ("add retries", ["add", "service", "reliability", "existing_system"],
         "service.failure-contract"),
        ("migrate users to UUIDs",
         ["migrate", "database", "data_integrity", "compatibility",
          "existing_system"], "migration.persisted-data"),
        ("add JSON output", ["add", "cli", "compatibility", "existing_system"],
         "cli.machine-readable-output"),
        ("speed up startup",
         ["optimize", "library", "performance", "compatibility",
          "existing_system"], "optimize.measure-hot-path"),
        ("clean up this module", ["refactor", "general", "existing_system"],
         "refactor.observable-behavior"),
        ("add deployment health checks",
         ["add", "infrastructure", "observability", "reliability",
          "existing_system"], "observability.existing-signals"),
        ("fix CSV export", ["fix", "data", "compatibility", "existing_system"],
         "bugfix.broader-invariant"),
        ("make dashboard better on mobile",
         ["modify", "ui", "ux", "accessibility", "existing_system"],
         "ui.existing-primitives"),
        ("build a small CLI for converting images",
         ["create", "cli", "greenfield"], "greenfield.minimum-structure"),
        ("rename Foo to Bar in README.md",
         ["modify", "documentation", "existing_system"],
         "documentation.reference-consistency"),
    )
    for request, facets, expected in cases:
        selection = SemanticSelection.from_reply(facets, "LOW", [])
        assert expected in selection.candidate_policy_ids, request


def test_compiler_retrieves_then_uses_one_material_critic_pass():
    with tempfile.TemporaryDirectory(prefix="prompire-compiler-") as tmp:
        root = pathlib.Path(tmp)
        build_repo(root)
        sentinel = root / "model-output-ran"
        dangerous_check = (
            f"python3 -c \"open({str(sentinel)!r}, 'w').write('bad')\"")
        resolver = ScriptedModel([
            {"queries": [
                {"op": "search_text", "query": "export_csv"},
                {"op": "read_file", "path": "src/export/csv.py", "start": 1, "end": 40},
                {"op": "read_file", "path": "src/export/serializer.py", "start": 1, "end": 40},
                {"op": "read_file", "path": "tests/export/test_csv.py", "start": 1, "end": 60},
            ]},
            resolution(
                facets=["fix", "data", "compatibility", "existing_system"],
                policies=["bugfix.broader-invariant"],
                checks=[dangerous_check],
            ),
            revised_resolution(
                facets=["fix", "data", "compatibility", "existing_system"],
                policies=[],
                adopted_issues=[1],
                likely_relevant=[
                    "src/export/csv.py",
                    "src/export/serializer.py",
                    "tests/export/test_csv.py",
                ],
                watch_for=[
                    "Direct export and wrapper export may use separate paths.",
                ],
                checks=[dangerous_check],
            ),
        ])
        critic = ScriptedModel([{
            "issues": [
                "The wrapper may use a separate serializer path.",
                "A quoted field at the exact row boundary may still fail.",
                "Re-import may normalize the embedded newline.",
                "This fourth issue must be discarded.",
            ],
        }])

        request = (
            "fix CSV export with quoted newlines; do not change delimiter behavior")
        result = TaskContextCompiler(root, resolver, critic).compile(request)

        assert len(resolver.prompts) == 3
        assert len(critic.prompts) == 1
        assert "objective" not in resolver.prompts[1][1]["properties"]["task_ir"]["properties"]
        assert "semantic_facets" in resolver.prompts[1][1]["properties"]
        assert "specificity" in resolver.prompts[1][1]["properties"]
        assert "src/export/csv.py" in resolver.prompts[0][0]
        assert "join(rows)" not in resolver.prompts[0][0]
        assert "join(rows)" in resolver.prompts[1][0]
        assert "What is the most likely way a competent coding agent could follow this task and still produce a superficially acceptable but materially wrong result?" in critic.prompts[0][0]
        assert "Inspect callers and sibling paths" in critic.prompts[0][0]
        assert "src/export/serializer.py" in result.task_ir.likely_relevant
        assert result.task_ir.objective == request
        assert request in result.prompt
        assert "join(rows)" not in result.prompt
        assert "INFERRED REPOSITORY GUIDANCE (ADVISORY)" in result.prompt
        assert result.metrics["critic_found"] == 3
        assert result.metrics["critic_adopted"] == 1
        assert result.metrics["critic_rejected"] == 2
        assert result.metrics["model_calls"] == 4
        assert result.metrics["model_input_tokens"] == 400
        assert result.metrics["model_output_tokens"] == 80
        assert result.metrics["model_total_tokens"] == 480
        assert result.metrics["model_cached_input_tokens"] == 0
        assert result.metrics["retrieval_calls"] == 5
        assert result.metrics["retrieved_chars"] > 0
        assert result.metrics["human_questions"] == 0
        assert result.metrics["prompt_words"] <= 250
        assert result.metrics["prompt_tokens"] > 0
        assert result.metrics["prompt_tokens_estimated"] is True
        assert result.record["raw_request"] == request
        assert result.record["selected_semantic_facets"] == [
            "fix", "data", "compatibility", "existing_system"]
        assert result.record["specificity"] == "LOW"
        assert result.record["stdlib_version"] == "1"
        assert result.record["candidate_stdlib_policies"]
        assert result.record["adopted_stdlib_policies"] == []
        assert "bugfix.broader-invariant" in result.record["rejected_stdlib_policies"]
        assert len(result.record["critic_findings"]["issues_rejected"]) == 2
        assert result.record["final_task_ir"]["objective"] == request
        assert result.record["final_rendered_prompt"] == result.prompt
        assert result.record["prompt_hash"]
        assert result.record["repository_evidence_identifiers"]
        assert "reasoning" not in json.dumps(result.record).lower()
        assert not sentinel.exists(), "compiler executed a check suggested by model output"


def test_specificity_scales_enrichment_and_high_is_near_identity():
    assert resolve_facets("add retries", ["add", "test", "reliability"]) == [
        "add", "reliability"]
    assert resolve_facets("add retry tests", ["add", "test", "reliability"]) == [
        "add", "test", "reliability"]
    assert resolve_specificity(
        "build a small CLI for converting images", "HIGH") == "LOW"
    assert resolve_specificity(
        "rename Foo to Bar in README.md", "MEDIUM") == "HIGH"
    assert resolve_specificity(
        "rename Foo to Bar in README.md and update every API reference",
        "HIGH") == "MEDIUM"
    assert resolve_specificity(
        "Please build a small CLI for converting images", "HIGH") == "LOW"
    assert resolve_specificity(
        "Can you build a small CLI for converting images?", "HIGH") == "LOW"
    with tempfile.TemporaryDirectory(prefix="prompire-specificity-") as tmp:
        root = pathlib.Path(tmp)
        build_repo(root)
        request = "rename Foo to Bar in README.md"
        bloated = {
            "likely_relevant": ["pyproject.toml", "src/export/csv.py"],
            "context": ["The repository has several unrelated modules."],
            "preserve": ["Preserve all public behavior."],
            "watch_for": ["Avoid broad architectural changes."],
            "checks": ["Inspect the renamed documentation reference.",
                       "Run the full test suite."],
        }
        resolver = ScriptedModel([
            {"queries": []},
            resolution(
                facets=["modify", "documentation", "existing_system"],
                specificity="HIGH",
                policies=["documentation.reference-consistency"],
                **bloated,
            ),
            revised_resolution(
                facets=["modify", "documentation", "existing_system"],
                specificity="HIGH",
                policies=["documentation.reference-consistency"],
                **bloated,
            ),
        ])
        critic = ScriptedModel([{"issues": []}])

        result = TaskContextCompiler(root, resolver, critic).compile(request)

        assert "The repository has several unrelated modules." in critic.prompts[0][0]
        assert result.task_ir.objective == request
        assert len(result.task_ir.likely_relevant) <= 1
        guidance_items = (
            len(result.task_ir.context) + len(result.task_ir.preserve)
            + len(result.task_ir.watch_for) + len(result.task_ir.checks))
        assert guidance_items <= 1
        assert result.task_ir.checks == (
            "Inspect the renamed documentation reference.",)
        assert result.metrics["specificity"] == "HIGH"
        assert result.metrics["prompt_words"] <= len(request.split()) + 30
        assert result.prompt.startswith(f"TASK\n{request}\n")
        low_prompt = render_task(TaskIR.from_dict({"objective": request, **bloated}), "LOW")
        assert len(result.prompt.split()) < len(low_prompt.split())


def test_adopted_stdlib_policy_survives_into_the_rendered_prompt():
    with tempfile.TemporaryDirectory(prefix="prompire-policy-render-") as tmp:
        root = pathlib.Path(tmp)
        build_repo(root)
        empty = {
            "likely_relevant": [], "context": [], "preserve": [],
            "watch_for": [], "checks": [],
        }
        resolver = ScriptedModel([
            {"queries": []},
            resolution(
                facets=["add", "cli", "existing_system"],
                policies=["cli.machine-readable-output"],
                **empty,
            ),
            revised_resolution(
                facets=["add", "cli", "existing_system"],
                policies=["cli.machine-readable-output"],
                **empty,
            ),
        ])
        critic = ScriptedModel([{"issues": []}])

        result = TaskContextCompiler(root, resolver, critic).compile("add JSON output")

        assert "machine-readable output free of human diagnostics" in result.prompt
        assert result.record["adopted_stdlib_policies"] == [
            "cli.machine-readable-output"]


def test_critic_is_subtractive_and_receives_stdlib_provenance():
    ir = TaskIR.from_dict(task_ir())
    model = ScriptedModel([{"issues": [
        "Remove the API auth policy because this export path has no auth boundary.",
    ]}])
    selection = SemanticSelection.from_reply(
        ["fix", "api", "existing_system"],
        "MEDIUM",
        ["api.validation-error-shape"],
    )
    issues, _ = Critic(model).review("fix CSV export", (), ir, selection)
    assert len(issues) == 1
    prompt = model.prompts[0][0]
    assert "irrelevant stdlib policy" in prompt
    assert "generic advice" in prompt
    assert "over-constraint" in prompt
    assert "prompt bloat" in prompt
    assert "api.validation-error-shape" in prompt


def test_experiment_records_persist_outside_target_repo_without_reasoning():
    with tempfile.TemporaryDirectory(prefix="prompire-record-target-") as target_tmp, \
            tempfile.TemporaryDirectory(prefix="prompire-record-out-") as out_tmp:
        target = pathlib.Path(target_tmp)
        build_repo(target)
        before = git(target, "status", "--short").stdout
        record = {
            "raw_request": "add JSON output",
            "critic_findings": {"issues_found": [], "issues_adopted": [],
                                "issues_rejected": []},
        }
        out = pathlib.Path(out_tmp) / "compilations.jsonl"
        append_experiment_record(out, record, target)
        stored = json.loads(out.read_text(encoding="utf-8"))
        assert stored == record
        assert git(target, "status", "--short").stdout == before

        try:
            append_experiment_record(target / "record.jsonl", record, target)
        except ValueError as exc:
            assert "target repository" in str(exc)
        else:
            raise AssertionError("experiment metadata was written into the target repository")

        linked = pathlib.Path(out_tmp) / "linked"
        git(target, "worktree", "add", "-q", "-b", "metadata-test", str(linked))
        try:
            common_text = git(linked, "rev-parse", "--git-common-dir").stdout.strip()
            common = pathlib.Path(common_text)
            if not common.is_absolute():
                common = (linked / common).resolve()
            try:
                append_experiment_record(common / "record.jsonl", record, linked)
            except ValueError as exc:
                assert "Git administration" in str(exc)
            else:
                raise AssertionError("experiment metadata was written into Git administration")

            try:
                append_experiment_record(
                    out, {**record, "analysis": "private trace"}, linked)
            except ValueError as exc:
                assert "unknown experiment record fields" in str(exc)
            else:
                raise AssertionError("experiment metadata accepted an unknown trace field")
        finally:
            git(target, "worktree", "remove", "--force", str(linked))


def test_renderer_keeps_paths_advisory_and_implementation_open():
    ir = TaskIR.from_dict(task_ir())
    prompt = render_task(ir)
    assert "LIKELY RELEVANT" in prompt
    assert "INFERRED REPOSITORY GUIDANCE (ADVISORY)" in prompt
    assert "authorized to edit only" not in prompt.lower()
    assert "Inspect or change additional implementation files if needed." in prompt
    assert "Implementation details are yours." in prompt
    assert "Make reasonable assumptions from repository evidence" in prompt
    assert "IMPLEMENTATION PLAN" not in prompt
    assert len(prompt.split()) <= 250

    maximum = TaskIR.from_dict(task_ir(
        objective=" ".join(["task"] * 35),
        likely_relevant=[f"src/path-{index}.py" for index in range(6)],
        context=[" ".join(["context"] * 14)] * 2,
        preserve=[" ".join(["preserve"] * 12)] * 2,
        watch_for=[" ".join(["risk"] * 12)] * 3,
        checks=[" ".join(["check"] * 16)] * 3,
    ))
    assert len(render_task(maximum).split()) <= 250
    medium = render_task(maximum, "MEDIUM")
    low = render_task(maximum, "LOW")
    assert len(medium.split()) <= 180
    assert len(medium.split()) < len(low.split())

    dense = TaskIR.from_dict(task_ir(
        context=[" ".join(["x"] * 90)] * 2,
        preserve=[" ".join(["x"] * 80)] * 2,
        watch_for=[" ".join(["x"] * 80)] * 3,
        checks=[" ".join(["x"] * 100)] * 3,
    ))
    dense_prompt = render_task(dense)
    assert len(dense_prompt.split()) <= 250
    assert "Lower-priority inferred guidance was omitted" in dense_prompt


class RecordingRunner:
    def __init__(self, stdout, returncode=0, stderr=""):
        self.stdout = stdout
        self.returncode = returncode
        self.stderr = stderr
        self.calls = []
        self.schema = None

    def __call__(self, argv, **kwargs):
        self.calls.append((argv, kwargs))
        if "--output-schema" in argv:
            schema_path = pathlib.Path(argv[argv.index("--output-schema") + 1])
            self.schema = json.loads(schema_path.read_text(encoding="utf-8"))
        return subprocess.CompletedProcess(
            argv, self.returncode, stdout=self.stdout, stderr=self.stderr)


def jsonl_model_reply(data, item_type="agent_message"):
    return "\n".join([
        json.dumps({"type": "thread.started", "thread_id": "fixture"}),
        json.dumps({
            "type": "item.completed",
            "item": {"type": item_type, "text": json.dumps(data)},
        }),
        json.dumps({
            "type": "turn.completed",
            "usage": {"input_tokens": 11, "cached_input_tokens": 7,
                      "output_tokens": 4},
        }),
    ]) + "\n"


def test_codex_model_disables_tools_and_reads_only_structured_output():
    runner = RecordingRunner(jsonl_model_reply({"queries": []}))
    response = CodexModel(runner=runner).complete(
        "select evidence", RETRIEVAL_SCHEMA)
    argv, kwargs = runner.calls[0]
    assert response.data == {"queries": []}
    assert response.input_tokens == 11 and response.output_tokens == 4
    assert response.cached_input_tokens == 7
    assert "agents.enabled=false" in argv
    assert 'web_search="disabled"' in argv
    assert "--ignore-user-config" in argv and "--ignore-rules" in argv
    assert "--strict-config" in argv
    assert "--ephemeral" in argv and "--json" in argv
    for feature in ("shell_tool", "unified_exec", "multi_agent", "apps", "hooks"):
        assert ["--disable", feature] == argv[
            argv.index(feature) - 1:argv.index(feature) + 1]
    disabled = {
        argv[index + 1] for index, value in enumerate(argv[:-1])
        if value == "--disable"
    }
    assert {
        "apps", "artifact", "auth_elicitation", "browser_use",
        "browser_use_external", "browser_use_full_cdp_access", "code_mode",
        "code_mode_host", "computer_use", "deferred_executor", "goals", "hooks",
        "image_generation", "in_app_browser", "multi_agent", "plugins",
        "remote_plugin", "request_permissions_tool", "shell_tool",
        "skill_mcp_dependency_install", "skill_search", "tool_call_mcp_elicitation",
        "tool_suggest", "unified_exec", "workspace_dependencies",
    } <= disabled
    assert kwargs["input"] == "select evidence"
    query_schema = runner.schema["properties"]["queries"]["items"]
    variants = query_schema["anyOf"]
    assert {
        variant["properties"]["op"]["enum"][0] for variant in variants
    } == {"list_files", "search_text", "read_file", "history", "diff"}
    assert all(
        set(variant["required"]) == set(variant["properties"])
        for variant in variants)

    unsafe = RecordingRunner(jsonl_model_reply(
        {"queries": []}, item_type="command_execution"))
    try:
        CodexModel(runner=unsafe).complete("select evidence", {"type": "object"})
    except ModelExecutionError as exc:
        assert "command_execution" in str(exc)
    else:
        raise AssertionError("compiler accepted a model tool-execution event")

    unknown_events = "\n".join([
        json.dumps({"type": "thread.started", "thread_id": "fixture"}),
        json.dumps({"type": "unexpected.side_effect"}),
        json.dumps({
            "type": "item.completed",
            "item": {"type": "agent_message", "text": '{"queries": []}'},
        }),
        json.dumps({"type": "turn.completed", "usage": {}}),
    ]) + "\n"
    try:
        CodexModel(runner=RecordingRunner(unknown_events)).complete(
            "select evidence", RETRIEVAL_SCHEMA)
    except ModelExecutionError as exc:
        assert "unexpected.side_effect" in str(exc)
    else:
        raise AssertionError("compiler ignored an unknown Codex event")


def test_downstream_codex_reports_operating_system_errors():
    def denied(*args, **kwargs):
        raise PermissionError("blocked")

    errors = io.StringIO()
    with contextlib.redirect_stderr(errors):
        code = prompire.launch_codex("TASK\nDo it.\n", pathlib.Path.cwd(), denied)
    assert code == 2
    assert "could not launch Codex" in errors.getvalue()

    calls = []

    def recording(argv, **kwargs):
        calls.append((argv, kwargs))
        return subprocess.CompletedProcess(argv, 0)

    assert prompire.launch_codex(
        "TASK\nDo it.\n", pathlib.Path.cwd(), recording) == 0
    argv, _ = calls[0]
    assert "--ignore-user-config" in argv
    assert "--ignore-rules" in argv
    assert "--strict-config" in argv
    assert ["-m", "gpt-5.6-sol"] == argv[argv.index("-m"):argv.index("-m") + 2]
    assert 'model_reasoning_effort="medium"' in argv
    for feature in ("apps", "browser_use", "computer_use", "hooks", "plugins"):
        assert ["--disable", feature] == argv[
            argv.index(feature) - 1:argv.index(feature) + 1]


def test_compile_and_run_cli_share_the_compiled_prompt():
    with tempfile.TemporaryDirectory(prefix="prompire-cli-context-") as tmp:
        root = pathlib.Path(tmp)
        build_repo(root)
        redirected = root / "redirected"
        redirected.mkdir()
        build_repo(redirected)
        ir = TaskIR.from_dict(task_ir())
        prompt = render_task(ir)
        experiment = {"raw_request": "fix CSV export with quoted newlines"}
        result = CompilationResult(ir, prompt, (), {
            "retrieval_calls": 4,
            "critic_found": 2,
            "critic_adopted": 2,
            "prompt_words": len(prompt.split()),
        }, experiment)
        compiled = []
        launched = []
        original_compile = prompire.compile_context_request
        original_launch = prompire.launch_codex

        def fake_compile(sentence, repo):
            compiled.append((sentence, pathlib.Path(repo)))
            return result

        def fake_launch(value, repo):
            launched.append((value, pathlib.Path(repo)))
            return 0

        prompire.compile_context_request = fake_compile
        prompire.launch_codex = fake_launch
        previous = pathlib.Path.cwd()
        record_path = root.parent / f"{root.name}-compilations.jsonl"
        old_git_dir = os.environ.get("GIT_DIR")
        old_git_tree = os.environ.get("GIT_WORK_TREE")
        try:
            os.environ["GIT_DIR"] = str(redirected / ".git")
            os.environ["GIT_WORK_TREE"] = str(redirected)
            os.chdir(root)
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                code = prompire.main([
                    "compile", "fix CSV export with quoted newlines", "--json",
                    "--record", str(record_path)])
            payload = json.loads(output.getvalue())
            assert code == 0
            assert payload["task_ir"] == ir.to_dict()
            assert payload["prompt"] == prompt
            assert payload["record"] == experiment
            assert json.loads(record_path.read_text(encoding="utf-8")) == experiment

            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                code = prompire.main([
                    "run", "fix CSV export with quoted newlines", "--agent", "codex"])
            assert code == 0
            assert launched == [(prompt, root.resolve())]
            assert "Compiling task..." in output.getvalue()
            assert "critic found 2 likely omissions; resolver adopted 2" in output.getvalue()
            assert "Launching Codex..." in output.getvalue()
        finally:
            os.chdir(previous)
            if old_git_dir is None:
                os.environ.pop("GIT_DIR", None)
            else:
                os.environ["GIT_DIR"] = old_git_dir
            if old_git_tree is None:
                os.environ.pop("GIT_WORK_TREE", None)
            else:
                os.environ["GIT_WORK_TREE"] = old_git_tree
            prompire.compile_context_request = original_compile
            prompire.launch_codex = original_launch
            record_path.unlink(missing_ok=True)
        assert [item[0] for item in compiled] == [
            "fix CSV export with quoted newlines",
            "fix CSV export with quoted newlines",
        ]
        assert all(item[1] == root.resolve() for item in compiled)


def main():
    tests = (
        test_task_ir_is_small_and_typed,
        test_repo_context_exposes_only_bounded_read_operations,
        test_semantic_facets_compose_and_filter_candidate_policies,
        test_cross_domain_tasks_have_compositional_candidate_knowledge,
        test_compiler_retrieves_then_uses_one_material_critic_pass,
        test_specificity_scales_enrichment_and_high_is_near_identity,
        test_adopted_stdlib_policy_survives_into_the_rendered_prompt,
        test_critic_is_subtractive_and_receives_stdlib_provenance,
        test_experiment_records_persist_outside_target_repo_without_reasoning,
        test_renderer_keeps_paths_advisory_and_implementation_open,
        test_codex_model_disables_tools_and_reads_only_structured_output,
        test_downstream_codex_reports_operating_system_errors,
        test_compile_and_run_cli_share_the_compiled_prompt,
    )
    for test in tests:
        test()
    print(f"{len(tests)}/{len(tests)} task-context cases pass")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
