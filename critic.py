import json

from task_ir import TaskIRError


MAX_ISSUE_CHARS = 240

CRITIC_SCHEMA = {
    "type": "object",
    "properties": {
        "issues": {
            "type": "array",
            "items": {"type": "string", "maxLength": MAX_ISSUE_CHARS},
            "maxItems": 3,
        },
    },
    "required": ["issues"],
    "additionalProperties": False,
}

CRITIC_QUESTION = (
    "What is the most likely way a competent coding agent could follow this task "
    "and still produce a superficially acceptable but materially wrong result?"
)


class Critic:
    def __init__(self, model):
        self.model = model

    def review(self, request, evidence, task_ir, selection=None):
        semantic = selection.to_dict() if selection is not None else {}
        adopted = selection.adopted_policies() if selection is not None else []
        prompt = f"""{CRITIC_QUESTION}
Return at most three material findings. Attack repository-derived and stdlib-derived enrichment.
Look for an important omission, incorrect assumption, irrelevant stdlib policy, generic advice,
over-constraint, or prompt bloat. A useful finding may require removing information.
Do not demand fixes for unrelated repository problems or expand the user's objective.
Keep each finding under 180 characters and make it a complete sentence.
Do not critique writing, propose an architecture, brainstorm, plan, or generate code.

ORIGINAL REQUEST
{request}

SELECTED REPOSITORY EVIDENCE
{json.dumps(evidence, ensure_ascii=False)}

TASK IR V1
{json.dumps(task_ir.to_dict(), ensure_ascii=False)}

SEMANTIC SELECTION V1
{json.dumps(semantic, ensure_ascii=False)}

ADOPTED STDLIB POLICIES
{json.dumps(adopted, ensure_ascii=False)}
"""
        response = self.model.complete(prompt, CRITIC_SCHEMA)
        data = response.data
        if not isinstance(data, dict) or not isinstance(data.get("issues"), list):
            raise TaskIRError("critic reply must contain `issues`")
        issues = []
        for issue in data["issues"]:
            if not isinstance(issue, str):
                raise TaskIRError("critic issues must be strings")
            if len(issue) > MAX_ISSUE_CHARS:
                raise TaskIRError("critic issue exceeds its prompt budget")
            if issue.strip():
                issues.append(issue.strip())
        return tuple(issues[:3]), response
