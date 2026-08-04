import math
import re


WORD_BUDGET = 250
MEDIUM_WORD_BUDGET = 180
HIGH_ENRICHMENT_WORDS = 30


def _section(lines, heading, items):
    if items:
        lines.extend(["", heading, *[f"- {value}" for value in items]])


def _render(task_ir, items, omitted):
    lines = ["TASK", task_ir.objective]
    if any(items.values()) or omitted:
        lines.extend([
            "",
            "INFERRED REPOSITORY GUIDANCE (ADVISORY)",
            "Treat these as leads, not requirements or edit boundaries.",
        ])
        if omitted:
            lines.append("Lower-priority inferred guidance was omitted to fit the prompt budget.")
    _section(lines, "LIKELY RELEVANT", items["likely_relevant"])
    _section(lines, "LIKELY CONTEXT", items["context"])
    _section(lines, "LIKELY BEHAVIOR TO PRESERVE", items["preserve"])
    _section(lines, "POTENTIAL PITFALLS", items["watch_for"])
    _section(lines, "USEFUL CHECKS", items["checks"])
    lines.extend([
        "",
        "Inspect or change additional implementation files if needed.",
        "Implementation details are yours. Keep the change focused.",
        "Make reasonable assumptions from repository evidence; ask only if product semantics remain materially ambiguous.",
    ])
    return "\n".join(lines).strip() + "\n"


def _render_high(task_ir, items):
    lines = ["TASK", task_ir.objective]
    _section(lines, "LIKELY RELEVANT", items["likely_relevant"])
    _section(lines, "LIKELY CONTEXT", items["context"])
    _section(lines, "PRESERVE", items["preserve"])
    _section(lines, "WATCH FOR", items["watch_for"])
    _section(lines, "CHECK", items["checks"])
    if items["likely_relevant"]:
        lines.extend(["", "Treat likely paths as inspection leads, not edit boundaries."])
    lines.extend(["", "Implementation details are yours. Keep the change focused."])
    return "\n".join(lines).strip() + "\n"


def render_task(task_ir, specificity="MEDIUM"):
    if specificity == "HIGH":
        items = {
            "likely_relevant": list(task_ir.likely_relevant[:1]),
            "context": list(task_ir.context[:1]),
            "preserve": list(task_ir.preserve[:1]),
            "watch_for": list(task_ir.watch_for[:1]),
            "checks": list(task_ir.checks[:1]),
        }
        limit = word_count(task_ir.objective) + HIGH_ENRICHMENT_WORDS
        while True:
            prompt = _render_high(task_ir, items)
            if word_count(prompt) <= min(WORD_BUDGET, limit):
                return prompt
            key = next((key for key in (
                "likely_relevant", "checks", "context", "watch_for", "preserve")
                        if items[key]), None)
            if key is None:
                raise ValueError(f"user request exceeds the {WORD_BUDGET}-word prompt budget")
            items[key].pop()
    if specificity not in {"LOW", "MEDIUM"}:
        raise ValueError("specificity must be LOW, MEDIUM, or HIGH")
    budget = WORD_BUDGET if specificity == "LOW" else MEDIUM_WORD_BUDGET
    items = {
        "likely_relevant": list(task_ir.likely_relevant),
        "context": list(task_ir.context),
        "preserve": list(task_ir.preserve),
        "watch_for": list(task_ir.watch_for),
        "checks": list(task_ir.checks),
    }
    drop_order = ("likely_relevant", "context", "watch_for", "checks", "preserve")
    omitted = 0
    while True:
        prompt = _render(task_ir, items, omitted)
        if word_count(prompt) <= budget:
            return prompt
        key = next((name for name in drop_order if len(items[name]) > 1), None)
        if key is None:
            key = next((name for name in drop_order if items[name]), None)
        if key is None:
            raise ValueError(f"user request exceeds the {WORD_BUDGET}-word prompt budget")
        items[key].pop()
        omitted += 1


def word_count(text):
    return len(re.findall(r"\S+", text))


def token_estimate(text):
    return math.ceil(len(text.encode("utf-8")) / 4)
