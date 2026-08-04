from dataclasses import dataclass
import json
import pathlib
import subprocess
import tempfile
import time

from critic import Critic
from repo_context import RepoContext
from task_ir import TaskIR
from task_renderer import render_task, token_estimate, word_count
from task_resolver import TaskResolver


class ModelExecutionError(RuntimeError):
    pass


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
    def __init__(self, executable="codex", runner=subprocess.run, timeout=180):
        self.executable = executable
        self.runner = runner
        self.timeout = timeout

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


class TaskContextCompiler:
    def __init__(self, root, resolver_model, critic_model):
        self.repo = RepoContext(root)
        self.resolver = TaskResolver(resolver_model)
        self.critic = Critic(critic_model)

    def compile(self, request):
        started = time.monotonic()
        responses = []
        requested = TaskIR.from_dict({"objective": request}).objective

        overview = self.repo.overview(requested)
        queries, response = self.resolver.select_queries(requested, overview)
        responses.append(response)
        evidence = self.repo.retrieve(queries)

        first_ir, response = self.resolver.resolve(requested, evidence)
        responses.append(response)
        first_ir = TaskIR.from_dict({
            **first_ir.to_dict(),
            "objective": requested,
            "likely_relevant": list(self.repo.tracked_subset(first_ir.likely_relevant)),
        })
        issues, response = self.critic.review(requested, evidence, first_ir)
        responses.append(response)
        task_ir, adopted, response = self.resolver.revise(
            requested, evidence, first_ir, issues)
        responses.append(response)
        task_ir = TaskIR.from_dict({
            **task_ir.to_dict(),
            "objective": requested,
            "likely_relevant": list(self.repo.tracked_subset(task_ir.likely_relevant)),
        })

        prompt = render_task(task_ir)
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
            "human_questions": 0,
            "prompt_words": word_count(prompt),
            "prompt_tokens": token_estimate(prompt),
            "prompt_tokens_estimated": True,
        }
        return CompilationResult(task_ir, prompt, tuple(evidence), metrics)
