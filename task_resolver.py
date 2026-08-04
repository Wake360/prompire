import json
import re

from prompt_stdlib import FACETS, POLICIES, SPECIFICITIES, SemanticSelection, policy_catalog
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

SEMANTIC_PROPERTIES = {
    "task_ir": GUIDANCE_SCHEMA,
    "semantic_facets": {
        "type": "array",
        "minItems": 1,
        "maxItems": 8,
        "items": {"type": "string", "enum": list(FACETS)},
    },
    "specificity": {"type": "string", "enum": list(SPECIFICITIES)},
    "adopted_policy_ids": {
        "type": "array",
        "maxItems": 8,
        "items": {"type": "string", "enum": list(POLICIES)},
    },
}

RESOLUTION_SCHEMA = {
    "type": "object",
    "properties": SEMANTIC_PROPERTIES,
    "required": list(SEMANTIC_PROPERTIES),
    "additionalProperties": False,
}

REVISION_SCHEMA = {
    "type": "object",
    "properties": {
        **SEMANTIC_PROPERTIES,
        "adopted_issue_numbers": {
            "type": "array",
            "items": {"type": "integer"},
            "maxItems": 3,
        },
    },
    "required": [*SEMANTIC_PROPERTIES, "adopted_issue_numbers"],
    "additionalProperties": False,
}


def resolve_specificity(request, claimed):
    text = request.strip()
    lowered = text.lower()
    if re.fullmatch(
            r"rename\s+\S+\s+to\s+\S+\s+in\s+\S+\.[a-z0-9]+[.!]?",
            lowered):
        return "HIGH"
    if re.match(
            r"^(please\s+|can you\s+|could you\s+|would you\s+)?(build|create)\b",
            lowered):
        return "LOW"
    if claimed == "HIGH":
        return "MEDIUM"
    return claimed


def resolve_facets(request, facets):
    if not isinstance(facets, list):
        return facets
    lowered = request.lower()
    if not re.search(r"\b(test|tests|testing|coverage)\b", lowered):
        facets = [facet for facet in facets if facet != "test"]
    return facets


class TaskResolver:
    def __init__(self, model):
        self.model = model

    def select_queries(self, request, overview):
        prompt = f"""Select the smallest useful batch of repository reads for this task.
The compiler will execute only the typed read-only operations in the schema.
Do not infer the solution yet. For search_text, request one literal string with no regex
or alternatives. list_files uses Python fnmatch patterns and has no brace expansion.
Use null for an optional range or limit.
For vague requests, read compact project documentation when it may define the missing behavior.

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
Preserve the user's intent. Select compositional semantic facets, then treat policies under those facets as candidates.
Operation facets describe the requested operation; select `test` only when the request itself is about tests or coverage.
Adopt only policies that materially improve this task; a facet match alone is not enough. Never add generic advice.
Return adopted policy IDs without copying their exact guidance into Task IR; the compiler inserts adopted fragments.
If Task IR relies on a stdlib consideration, report its policy ID. Do not paraphrase a policy while omitting provenance.
Do not restate an adopted policy separately unless repository evidence makes the guidance more specific.
Classify specificity from the raw request alone, never from how thoroughly repository evidence answers it.
LOW covers underspecified intent and broad build/create requests. MEDIUM covers a targeted behavior.
HIGH is reserved for a precise edit with explicit targets, such as an old/new name and exact file.
LOW may receive substantial useful enrichment, MEDIUM targeted enrichment, and HIGH minimal near-identity guidance.
Ground repository claims in the selected evidence. Use stdlib knowledge only where clearly applicable.
Do not turn unrelated repository defects, aspirations, or conventions into work the user did not request.
Do not write an implementation plan, choose exact edits, invent commands, or restrict work to predicted paths.
Unknown task types must still compile by composing the closest facets, including `general` when needed.
Keep every list short.

REQUEST
{request}

SELECTED REPOSITORY EVIDENCE
{json.dumps(evidence, ensure_ascii=False)}

PROMPT COMPILER STANDARD LIBRARY
{json.dumps(policy_catalog(), ensure_ascii=False)}
"""
        response = self.model.complete(prompt, RESOLUTION_SCHEMA)
        data = response.data
        if not isinstance(data, dict):
            raise TaskIRError("resolver reply must be an object")
        unknown = sorted(str(key) for key in set(data) - set(SEMANTIC_PROPERTIES))
        if unknown:
            raise TaskIRError("unknown resolver fields: " + ", ".join(unknown))
        guidance = data.get("task_ir")
        if not isinstance(guidance, dict):
            raise TaskIRError("resolver Task IR guidance must be an object")
        selection = SemanticSelection.from_reply(
            resolve_facets(request, data.get("semantic_facets")),
            resolve_specificity(request, data.get("specificity")),
            data.get("adopted_policy_ids"))
        return TaskIR.from_dict({"objective": request, **guidance}), selection, response

    def revise(self, request, evidence, first_ir, first_selection, issues):
        numbered = [{"number": index + 1, "issue": issue}
                    for index, issue in enumerate(issues)]
        prompt = f"""Revise the Task IR and semantic selection once.
Adopt only critic issues supported by the request, repository evidence, or a clearly applicable stdlib policy.
Reject critic issues that require fixing unrelated repository behavior or otherwise expand the objective.
Operation facets describe the requested operation; keep `test` only when the request itself is about tests or coverage.
The revision may remove incorrect, irrelevant, generic, bloated, or over-constraining enrichment.
A selected facet only makes its policies candidates; keep only policy IDs whose guidance survives as useful context.
If an adopted critic issue calls a policy irrelevant, generic, bloated, or over-constraining, remove that policy ID.
Never report such an issue adopted while retaining the criticized policy.
Return adopted policy IDs without copying their exact guidance into Task IR; the compiler inserts adopted fragments.
If Task IR relies on a stdlib consideration, report its policy ID and avoid a redundant paraphrase.
Preserve specificity-sensitive intensity, especially near-identity output for HIGH specificity.
Keep it compact. Do not add an implementation plan or turn likely paths into edit restrictions.
Report which numbered critic issues you adopted.

REQUEST
{request}

SELECTED REPOSITORY EVIDENCE
{json.dumps(evidence, ensure_ascii=False)}

TASK IR V1
{json.dumps(first_ir.to_dict(), ensure_ascii=False)}

SEMANTIC SELECTION V1
{json.dumps(first_selection.to_dict(), ensure_ascii=False)}

PROMPT COMPILER STANDARD LIBRARY
{json.dumps(policy_catalog(), ensure_ascii=False)}

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
        selection = SemanticSelection.from_reply(
            resolve_facets(request, data.get("semantic_facets")),
            resolve_specificity(request, data.get("specificity")),
            data.get("adopted_policy_ids"))
        adopted = data.get("adopted_issue_numbers")
        if not isinstance(adopted, list) or any(
                not isinstance(number, int) or not 1 <= number <= len(issues)
                for number in adopted):
            raise TaskIRError("adopted critic issue numbers are invalid")
        return revised, selection, tuple(dict.fromkeys(adopted)), response
