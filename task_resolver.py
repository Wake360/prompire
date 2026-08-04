import json

from task_ir import FIELDS, LIMITS, TaskIR, TaskIRError


GUIDANCE_FIELDS = FIELDS[1:]
GUIDANCE_SCHEMA = {
    "type": "object",
    "properties": {
        "likely_relevant": {
            "type": "array",
            "maxItems": LIMITS["likely_relevant"][0],
            "items": {
                "type": "string",
                "maxLength": LIMITS["likely_relevant"][1],
                "description": "One exact tracked repository path; no explanation.",
            },
        },
        "context": {
            "type": "array",
            "maxItems": LIMITS["context"][0],
            "items": {"type": "string", "maxLength": LIMITS["context"][1]},
        },
        "preserve": {
            "type": "array",
            "maxItems": LIMITS["preserve"][0],
            "items": {"type": "string", "maxLength": LIMITS["preserve"][1]},
        },
        "watch_for": {
            "type": "array",
            "maxItems": LIMITS["watch_for"][0],
            "items": {"type": "string", "maxLength": LIMITS["watch_for"][1]},
        },
        "checks": {
            "type": "array",
            "maxItems": LIMITS["checks"][0],
            "items": {"type": "string", "maxLength": LIMITS["checks"][1]},
        },
    },
    "required": list(GUIDANCE_FIELDS),
    "additionalProperties": False,
}

def _query_schema(operation, properties):
    fields = {
        "op": {"type": "string", "enum": [operation]},
        **properties,
    }
    return {
        "type": "object",
        "properties": fields,
        "required": list(fields),
        "additionalProperties": False,
    }


RETRIEVAL_SCHEMA = {
    "type": "object",
    "properties": {
        "queries": {
            "type": "array",
            "maxItems": 8,
            "items": {
                "anyOf": [
                    _query_schema("list_files", {
                        "pattern": {
                            "type": "string",
                            "description": "One Python fnmatch pattern; no brace expansion.",
                        },
                    }),
                    _query_schema("search_text", {
                        "query": {
                            "type": "string",
                            "description": "One literal fixed string; no regex or alternatives.",
                        },
                    }),
                    _query_schema("read_file", {
                        "path": {"type": "string"},
                        "start": {"type": ["integer", "null"]},
                        "end": {"type": ["integer", "null"]},
                    }),
                    _query_schema("history", {
                        "path": {"type": "string"},
                        "limit": {"type": ["integer", "null"]},
                    }),
                    _query_schema("diff", {
                        "path": {"type": "string"},
                    }),
                ],
            },
        },
    },
    "required": ["queries"],
    "additionalProperties": False,
}

REVISION_SCHEMA = {
    "type": "object",
    "properties": {
        "task_ir": GUIDANCE_SCHEMA,
        "adopted_issue_numbers": {
            "type": "array",
            "items": {"type": "integer"},
            "maxItems": 3,
        },
    },
    "required": ["task_ir", "adopted_issue_numbers"],
    "additionalProperties": False,
}


class TaskResolver:
    def __init__(self, model):
        self.model = model

    def select_queries(self, request, overview):
        prompt = f"""Select the smallest useful batch of repository reads for this task.
The compiler will execute only the typed read-only operations in the schema.
Do not infer the solution yet. For search_text, request one literal string with no regex
or alternatives. list_files uses Python fnmatch patterns and has no brace expansion.
Use null for an optional range or limit.

REQUEST
{request}

REPOSITORY OVERVIEW
{json.dumps(overview, ensure_ascii=False)}
"""
        response = self.model.complete(prompt, RETRIEVAL_SCHEMA)
        data = response.data
        if not isinstance(data, dict) or not isinstance(data.get("queries"), list):
            raise TaskIRError("resolver retrieval reply must contain `queries`")
        queries = [
            {key: value for key, value in query.items() if value is not None}
            for query in data["queries"]
        ]
        return queries, response

    def resolve(self, request, evidence):
        prompt = f"""Infer only the context a capable coding agent would benefit from before starting.
Preserve the user's intent. Ground claims in the selected evidence. Identify traps and useful existing checks.
Do not write an implementation plan, choose exact edits, invent commands, or restrict work to predicted paths.
Keep every list short.

REQUEST
{request}

SELECTED REPOSITORY EVIDENCE
{json.dumps(evidence, ensure_ascii=False)}
"""
        response = self.model.complete(prompt, GUIDANCE_SCHEMA)
        data = response.data
        if not isinstance(data, dict):
            raise TaskIRError("resolver reply must be an object")
        unknown = sorted(str(key) for key in set(data) - set(GUIDANCE_FIELDS))
        if unknown:
            raise TaskIRError("unknown resolver fields: " + ", ".join(unknown))
        return TaskIR.from_dict({"objective": request, **data}), response

    def revise(self, request, evidence, first_ir, issues):
        numbered = [{"number": index + 1, "issue": issue}
                    for index, issue in enumerate(issues)]
        prompt = f"""Revise the Task IR once. Adopt only critic issues supported by the request and evidence.
Keep it compact. Do not add an implementation plan or turn likely paths into edit restrictions.
Report which numbered critic issues you adopted.

REQUEST
{request}

SELECTED REPOSITORY EVIDENCE
{json.dumps(evidence, ensure_ascii=False)}

TASK IR V1
{json.dumps(first_ir.to_dict(), ensure_ascii=False)}

CRITIC ISSUES
{json.dumps(numbered, ensure_ascii=False)}
"""
        response = self.model.complete(prompt, REVISION_SCHEMA)
        data = response.data
        if not isinstance(data, dict):
            raise TaskIRError("resolver revision reply must be an object")
        guidance = data.get("task_ir")
        if not isinstance(guidance, dict):
            raise TaskIRError("revised Task IR guidance must be an object")
        unknown = sorted(str(key) for key in set(guidance) - set(GUIDANCE_FIELDS))
        if unknown:
            raise TaskIRError("unknown revised fields: " + ", ".join(unknown))
        revised = TaskIR.from_dict({"objective": request, **guidance})
        adopted = data.get("adopted_issue_numbers")
        if not isinstance(adopted, list) or any(
                not isinstance(number, int) or not 1 <= number <= len(issues)
                for number in adopted):
            raise TaskIRError("adopted critic issue numbers are invalid")
        return revised, tuple(dict.fromkeys(adopted)), response
