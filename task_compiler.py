from dataclasses import dataclass, field
import hashlib
import json
import pathlib
import subprocess
import tempfile
import time

from critic import Critic
from prompt_stdlib import POLICIES, POLICY_TARGETS, STDLIB_VERSION
from repo_context import RepoContext, git_env
from task_ir import LIMITS, TaskIR
from task_renderer import render_task, token_estimate, word_count
from task_resolver import TaskResolver


class ModelExecutionError(RuntimeError):
    pass


DEFAULT_CODEX_MODEL = "gpt-5.6-sol"
DEFAULT_CODEX_EFFORT = "medium"


COMPILER_DISABLED_FEATURES = (
    "apps",
    "artifact",
    "auth_elicitation",
    "browser_use",
    "browser_use_external",
    "browser_use_full_cdp_access",
    "code_mode",
    "code_mode_buffered_exec",
    "code_mode_host",
    "code_mode_only",
    "computer_use",
    "default_mode_request_user_input",
    "deferred_executor",
    "deferred_tool_world_state",
    "enable_mcp_apps",
    "executor_capability_discovery",
    "goals",
    "hooks",
    "image_generation",
    "in_app_browser",
    "mcp_2026_07_28",
    "multi_agent",
    "multi_agent_v2",
    "network_proxy",
    "plugin_sharing",
    "plugins",
    "remote_plugin",
    "request_permissions_tool",
    "shell_tool",
    "skill_mcp_dependency_install",
    "skill_search",
    "standalone_web_search",
    "tool_call_mcp_elicitation",
    "tool_suggest",
    "unified_exec",
    "workspace_dependencies",
)


@dataclass(frozen=True)
class ModelResponse:
    data: dict
    input_tokens: int = 0
    cached_input_tokens: int = 0
    output_tokens: int = 0


class CodexModel:
    def __init__(self, executable="codex", runner=subprocess.run, timeout=180,
                 model=DEFAULT_CODEX_MODEL, effort=DEFAULT_CODEX_EFFORT):
        self.executable = executable
        self.runner = runner
        self.timeout = timeout
        self.model = model
        self.effort = effort

    def complete(self, prompt, schema):
        with tempfile.TemporaryDirectory(prefix="prompire-model-") as tmp:
            root = pathlib.Path(tmp)
            schema_path = root / "output-schema.json"
            schema_path.write_text(
                json.dumps(schema, ensure_ascii=False), encoding="utf-8")
            argv = [
                self.executable,
                "exec",
                "--strict-config",
                "--sandbox", "read-only",
                "--ignore-user-config",
                "--ignore-rules",
                "--ephemeral",
                "--skip-git-repo-check",
                "--json",
            ]
            for feature in COMPILER_DISABLED_FEATURES:
                argv.extend(["--disable", feature])
            argv.extend([
                "-c", "agents.enabled=false",
                "-c", 'web_search="disabled"',
                "-m", self.model,
                "-c", f'model_reasoning_effort="{self.effort}"',
                "-C", str(root),
                "--output-schema", str(schema_path),
                "-",
            ])
            try:
                result = self.runner(
                    argv,
                    input=prompt,
                    cwd=str(root),
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=self.timeout,
                )
            except FileNotFoundError as exc:
                raise ModelExecutionError(f"Codex executable not found: {self.executable}") from exc
            except subprocess.TimeoutExpired as exc:
                raise ModelExecutionError(
                    f"Codex model call exceeded {self.timeout} seconds") from exc
        if result.returncode:
            detail = (result.stderr or result.stdout).strip().splitlines()
            raise ModelExecutionError(
                f"Codex model call exited {result.returncode}"
                + (f": {detail[-1]}" if detail else ""))
        return self._parse_events(result.stdout)

    def configuration(self):
        return {
            "provider": "codex-cli",
            "model": self.model,
            "effort": self.effort,
            "timeout_seconds": self.timeout,
            "sandbox": "read-only",
            "tools": "disabled",
        }

    @staticmethod
    def _parse_events(text):
        allowed_events = {
            "thread.started", "turn.started", "item.started", "item.updated",
            "item.completed", "turn.completed", "turn.failed", "error",
        }
        final_message = None
        input_tokens = 0
        cached_input_tokens = 0
        output_tokens = 0
        for line in text.splitlines():
            try:
                event = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ModelExecutionError("Codex emitted invalid JSONL") from exc
            event_type = event.get("type")
            if event_type not in allowed_events:
                raise ModelExecutionError(f"Codex emitted unsupported event: {event_type}")
            if isinstance(event_type, str) and event_type.startswith("item."):
                item_type = (event.get("item") or {}).get("type")
                if item_type not in {"reasoning", "agent_message"}:
                    raise ModelExecutionError(
                        f"compiler model attempted unsupported tool event: {item_type}")
                if event_type == "item.completed" and item_type == "agent_message":
                    final_message = event["item"].get("text")
            if event_type == "turn.completed":
                usage = event.get("usage") or {}
                input_tokens += int(usage.get("input_tokens") or 0)
                cached_input_tokens += int(
                    usage.get("cached_input_tokens") or 0)
                output_tokens += int(usage.get("output_tokens") or 0)
            if event_type in {"turn.failed", "error"}:
                raise ModelExecutionError("Codex model call failed")
        if not isinstance(final_message, str):
            raise ModelExecutionError("Codex emitted no final structured message")
        try:
            data = json.loads(final_message)
        except json.JSONDecodeError as exc:
            raise ModelExecutionError("Codex final message was not JSON") from exc
        if not isinstance(data, dict):
            raise ModelExecutionError("Codex final message was not an object")
        return ModelResponse(data, input_tokens, cached_input_tokens, output_tokens)


@dataclass(frozen=True)
class CompilationResult:
    task_ir: object
    prompt: str
    evidence: tuple[dict, ...]
    metrics: dict
    record: dict = field(default_factory=dict)


def _limit_enrichment(task_ir, specificity):
    if specificity == "HIGH":
        data = task_ir.to_dict()
        data["likely_relevant"] = data["likely_relevant"][:1]
        selected = None
        for key in ("checks", "preserve", "watch_for", "context"):
            if data[key]:
                selected = (key, data[key][0])
                break
        for key in ("context", "preserve", "watch_for", "checks"):
            data[key] = [selected[1]] if selected and selected[0] == key else []
        return TaskIR.from_dict(data)
    elif specificity == "MEDIUM":
        limits = {
            "likely_relevant": 3,
            "context": 1,
            "preserve": 1,
            "watch_for": 2,
            "checks": 2,
        }
    else:
        return task_ir
    data = task_ir.to_dict()
    for key, limit in limits.items():
        data[key] = data[key][:limit]
    return TaskIR.from_dict(data)


def _strip_stdlib_fragments(task_ir):
    policy_text = set(POLICIES.values())
    data = task_ir.to_dict()
    for key in ("context", "preserve", "watch_for", "checks"):
        data[key] = [item for item in data[key] if item not in policy_text]
    return TaskIR.from_dict(data)


def _inject_stdlib_fragments(task_ir, selection):
    data = _strip_stdlib_fragments(task_ir).to_dict()
    kept = []
    for identifier in selection.adopted_policy_ids:
        target = POLICY_TARGETS[identifier]
        guidance = POLICIES[identifier]
        if guidance in data[target]:
            kept.append(identifier)
        elif len(data[target]) < LIMITS[target][0]:
            data[target].append(guidance)
            kept.append(identifier)
    return TaskIR.from_dict(data), selection.with_adopted(kept)


def _selection_present_in_ir(selection, task_ir):
    values = {
        item
        for key in ("context", "preserve", "watch_for", "checks")
        for item in getattr(task_ir, key)
    }
    return selection.with_adopted(
        identifier for identifier in selection.adopted_policy_ids
        if POLICIES[identifier] in values)


def _model_configuration(model):
    configuration = getattr(model, "configuration", None)
    if callable(configuration):
        return configuration()
    return {"provider": type(model).__name__}


def _evidence_identifiers(evidence):
    identifiers = []
    for item in evidence:
        encoded = json.dumps(item, ensure_ascii=False, sort_keys=True).encode("utf-8")
        identifiers.append({
            "id": hashlib.sha256(encoded).hexdigest(),
            "op": item.get("op"),
            "query": item.get("query"),
        })
    return identifiers


def _contains_private_trace(value):
    if isinstance(value, dict):
        forbidden = {"reasoning", "private_reasoning", "chain_of_thought", "cot"}
        if any(str(key).lower() in forbidden for key in value):
            return True
        return any(_contains_private_trace(item) for item in value.values())
    if isinstance(value, (list, tuple)):
        return any(_contains_private_trace(item) for item in value)
    return False


EXPERIMENT_RECORD_KEYS = {
    "raw_request",
    "task_repository_identifier",
    "prompt_hash",
    "selected_semantic_facets",
    "specificity",
    "stdlib_version",
    "repository_evidence_identifiers",
    "candidate_stdlib_policies",
    "adopted_stdlib_policies",
    "rejected_stdlib_policies",
    "adopted_stdlib_policy_text",
    "critic_findings",
    "final_task_ir",
    "final_rendered_prompt",
    "compiler_model_config",
    "compiler_calls",
    "compiler_tokens",
    "compiler_latency_seconds",
    "target_agent",
    "target_model",
    "downstream_outcome",
    "downstream_tokens",
    "human_intervention",
}


def append_experiment_record(path, record, repository_root):
    if not isinstance(record, dict):
        raise ValueError("experiment record must be an object")
    unknown = sorted(str(key) for key in set(record) - EXPERIMENT_RECORD_KEYS)
    if unknown:
        raise ValueError("unknown experiment record fields: " + ", ".join(unknown))
    destination = pathlib.Path(path).expanduser().resolve()
    repository = pathlib.Path(repository_root).resolve()
    if destination.is_relative_to(repository):
        raise ValueError("experiment records must remain outside the target repository")
    admin = subprocess.run(
        ["git", "--no-pager", "-c", "core.fsmonitor=false",
         "-c", "core.hooksPath=", "-C", str(repository),
         "rev-parse", "--absolute-git-dir", "--git-common-dir"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        env=git_env(), timeout=10)
    if admin.returncode:
        raise ValueError("could not identify repository Git administration paths")
    for value in admin.stdout.splitlines():
        path = pathlib.Path(value)
        if not path.is_absolute():
            path = (repository / path).resolve()
        else:
            path = path.resolve()
        if destination == path or destination.is_relative_to(path):
            raise ValueError("experiment records must remain outside Git administration paths")
    if _contains_private_trace(record):
        raise ValueError("experiment records may not contain private reasoning traces")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


class TaskContextCompiler:
    def __init__(self, root, resolver_model, critic_model,
                 target_agent="codex", target_model=DEFAULT_CODEX_MODEL):
        self.repo = RepoContext(root)
        self.resolver = TaskResolver(resolver_model)
        self.critic = Critic(critic_model)
        self.resolver_model = resolver_model
        self.critic_model = critic_model
        self.target_agent = target_agent
        self.target_model = target_model

    def compile(self, request):
        started = time.monotonic()
        responses = []
        requested = TaskIR.from_dict({"objective": request}).objective

        overview = self.repo.overview(requested)
        queries, response = self.resolver.select_queries(requested, overview)
        responses.append(response)
        evidence = self.repo.retrieve(queries)

        first_ir, first_selection, response = self.resolver.resolve(requested, evidence)
        responses.append(response)
        first_ir = TaskIR.from_dict({
            **first_ir.to_dict(),
            "objective": requested,
            "likely_relevant": list(self.repo.tracked_subset(first_ir.likely_relevant)),
        })
        first_ir, first_selection = _inject_stdlib_fragments(
            first_ir, first_selection)
        issues, response = self.critic.review(
            requested, evidence, first_ir, first_selection)
        responses.append(response)
        task_ir, selection, adopted, response = self.resolver.revise(
            requested, evidence, first_ir, first_selection, issues)
        responses.append(response)
        task_ir = TaskIR.from_dict({
            **task_ir.to_dict(),
            "objective": requested,
            "likely_relevant": list(self.repo.tracked_subset(task_ir.likely_relevant)),
        })
        task_ir, selection = _inject_stdlib_fragments(task_ir, selection)
        task_ir = _limit_enrichment(task_ir, selection.specificity)
        selection = _selection_present_in_ir(selection, task_ir)

        prompt = render_task(task_ir, selection.specificity)
        retrieval = self.repo.metrics
        input_tokens = sum(item.input_tokens for item in responses)
        cached_input_tokens = sum(item.cached_input_tokens for item in responses)
        output_tokens = sum(item.output_tokens for item in responses)
        metrics = {
            "wall_time_seconds": round(time.monotonic() - started, 3),
            "model_calls": len(responses),
            "model_input_tokens": input_tokens,
            "model_cached_input_tokens": cached_input_tokens,
            "model_output_tokens": output_tokens,
            "model_total_tokens": input_tokens + output_tokens,
            "retrieval_calls": retrieval["retrieval_calls"],
            "retrieval_by_operation": retrieval["by_operation"],
            "retrieved_chars": sum(len(item["content"]) for item in evidence),
            "critic_found": len(issues),
            "critic_adopted": len(adopted),
            "critic_rejected": len(issues) - len(adopted),
            "specificity": selection.specificity,
            "stdlib_version": STDLIB_VERSION,
            "human_questions": 0,
            "prompt_words": word_count(prompt),
            "prompt_tokens": token_estimate(prompt),
            "prompt_tokens_estimated": True,
        }
        adopted_numbers = set(adopted)
        candidates = tuple(dict.fromkeys(
            first_selection.candidate_policy_ids + selection.candidate_policy_ids))
        adopted_policies = list(selection.adopted_policy_ids)
        rejected_policies = [
            identifier for identifier in candidates if identifier not in adopted_policies]
        try:
            head = self.repo._git("rev-parse", "HEAD").strip()[:12]
        except Exception:
            head = "unknown"
        prompt_hash = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
        record = {
            "raw_request": requested,
            "task_repository_identifier": f"{self.repo.root.name}@{head}",
            "prompt_hash": prompt_hash,
            "selected_semantic_facets": list(selection.facets),
            "specificity": selection.specificity,
            "stdlib_version": STDLIB_VERSION,
            "repository_evidence_identifiers": _evidence_identifiers(evidence),
            "candidate_stdlib_policies": list(candidates),
            "adopted_stdlib_policies": adopted_policies,
            "rejected_stdlib_policies": rejected_policies,
            "adopted_stdlib_policy_text": {
                identifier: POLICIES[identifier] for identifier in adopted_policies},
            "critic_findings": {
                "issues_found": list(issues),
                "issues_adopted": [
                    issue for number, issue in enumerate(issues, 1)
                    if number in adopted_numbers],
                "issues_rejected": [
                    issue for number, issue in enumerate(issues, 1)
                    if number not in adopted_numbers],
            },
            "final_task_ir": task_ir.to_dict(),
            "final_rendered_prompt": prompt,
            "compiler_model_config": {
                "resolver": _model_configuration(self.resolver_model),
                "critic": _model_configuration(self.critic_model),
            },
            "compiler_calls": len(responses),
            "compiler_tokens": {
                "input": input_tokens,
                "cached_input": cached_input_tokens,
                "output": output_tokens,
                "total": input_tokens + output_tokens,
            },
            "compiler_latency_seconds": metrics["wall_time_seconds"],
            "target_agent": self.target_agent,
            "target_model": self.target_model,
            "downstream_outcome": None,
            "downstream_tokens": None,
            "human_intervention": None,
        }
        return CompilationResult(task_ir, prompt, tuple(evidence), metrics, record)
