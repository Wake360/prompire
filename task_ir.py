from dataclasses import dataclass


class TaskIRError(ValueError):
    pass


FIELDS = (
    "objective",
    "likely_relevant",
    "context",
    "preserve",
    "watch_for",
    "checks",
)

LIMITS = {
    "objective": (1, 400, 35),
    "likely_relevant": (6, 240, None),
    "context": (2, 200, None),
    "preserve": (2, 180, None),
    "watch_for": (3, 180, None),
    "checks": (3, 240, None),
}


def _text(value, key):
    text = value.strip()
    _, max_chars, max_words = LIMITS[key]
    if len(text) > max_chars or (max_words is not None and len(text.split()) > max_words):
        raise TaskIRError(
            f"`{key}` exceeds its prompt budget")
    return text


def _items(data, key):
    value = data.get(key, [])
    if value is None:
        return ()
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise TaskIRError(f"`{key}` must be a list of strings")
    max_items, _, _ = LIMITS[key]
    if len(value) > max_items:
        raise TaskIRError(f"`{key}` accepts at most {max_items} items")
    return tuple(_text(item, key) for item in value if item.strip())


@dataclass(frozen=True)
class TaskIR:
    objective: str
    likely_relevant: tuple[str, ...] = ()
    context: tuple[str, ...] = ()
    preserve: tuple[str, ...] = ()
    watch_for: tuple[str, ...] = ()
    checks: tuple[str, ...] = ()

    @classmethod
    def from_dict(cls, data):
        if not isinstance(data, dict):
            raise TaskIRError("Task IR must be an object")
        unknown = sorted(str(key) for key in set(data) - set(FIELDS))
        if unknown:
            raise TaskIRError("unknown Task IR fields: " + ", ".join(unknown))
        objective = data.get("objective")
        if not isinstance(objective, str) or not objective.strip():
            raise TaskIRError("`objective` must be a non-empty string")
        return cls(
            objective=_text(objective, "objective"),
            likely_relevant=_items(data, "likely_relevant"),
            context=_items(data, "context"),
            preserve=_items(data, "preserve"),
            watch_for=_items(data, "watch_for"),
            checks=_items(data, "checks"),
        )

    def to_dict(self):
        return {
            "objective": self.objective,
            "likely_relevant": list(self.likely_relevant),
            "context": list(self.context),
            "preserve": list(self.preserve),
            "watch_for": list(self.watch_for),
            "checks": list(self.checks),
        }
