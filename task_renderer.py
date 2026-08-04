import math
import re


WORD_BUDGET = 250


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


def render_task(task_ir):
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
        if word_count(prompt) <= WORD_BUDGET:
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
