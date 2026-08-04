from dataclasses import dataclass

from task_ir import TaskIRError


STDLIB_VERSION = "1"


def _policy(identifier, guidance, target="watch_for"):
    return {"id": identifier, "guidance": guidance, "target": target}


FACETS = {
    "create": {"kind": "operation", "policies": ()},
    "add": {"kind": "operation", "policies": ()},
    "modify": {"kind": "operation", "policies": ()},
    "fix": {"kind": "operation", "policies": (
        _policy("bugfix.broader-invariant",
                "Inspect callers and sibling paths before special-casing the literal reported example."),
    )},
    "refactor": {"kind": "operation", "policies": (
        _policy("refactor.observable-behavior",
                "Preserve externally observable behavior and existing extension points unless the request changes them.",
                "preserve"),
    )},
    "migrate": {"kind": "operation", "policies": (
        _policy("migration.persisted-data",
                "Account for existing persisted data and dependent readers when representation changes."),
        _policy("migration.transition-compatibility",
                "Consider compatibility during the transition and reversibility only where deployment evidence makes it material."),
    )},
    "integrate": {"kind": "operation", "policies": (
        _policy("integration.existing-boundaries",
                "Reuse established integration boundaries, configuration sources, and failure conventions."),
    )},
    "optimize": {"kind": "operation", "policies": (
        _policy("optimize.measure-hot-path",
                "Identify the actual hot path and existing measurements before broad rewrites."),
    )},
    "test": {"kind": "operation", "policies": (
        _policy("testing.regression-surface",
                "Exercise the public behavior that would regress, including sibling paths sharing the same invariant.",
                "checks"),
    )},
    "document": {"kind": "operation", "policies": ()},
    "investigate": {"kind": "operation", "policies": ()},
    "remove": {"kind": "operation", "policies": (
        _policy("removal.dependent-callers",
                "Check dependent callers, configuration, and exported symbols before removing the implementation."),
    )},
    "upgrade": {"kind": "operation", "policies": (
        _policy("upgrade.compatibility",
                "Inspect version-specific APIs, generated artifacts, and downstream compatibility before changing the dependency."),
    )},
    "ui": {"kind": "surface", "policies": (
        _policy("ui.existing-primitives",
                "Reuse the repository's existing UI primitives and design conventions instead of replacing its stack.",
                "context"),
        _policy("ui.interaction-states",
                "Preserve existing loading, error, or empty behavior only when the affected interaction can enter that state."),
    )},
    "frontend": {"kind": "surface", "policies": (
        _policy("frontend.client-boundaries",
                "Respect existing client state, routing, and server-boundary conventions where the change crosses them."),
    )},
    "backend": {"kind": "surface", "policies": ()},
    "service": {"kind": "surface", "policies": (
        _policy("service.failure-contract",
                "Preserve the service's established timeout, retry, and failure-reporting contract.",
                "preserve"),
    )},
    "api": {"kind": "surface", "policies": (
        _policy("api.validation-error-shape",
                "Reuse existing endpoint validation and error-shape conventions.",
                "context"),
        _policy("api.serialization-compatibility",
                "Preserve established serialization and caller compatibility unless the request changes the contract.",
                "preserve"),
    )},
    "cli": {"kind": "surface", "policies": (
        _policy("cli.machine-readable-output",
                "Keep machine-readable output free of human diagnostics and preserve exit-code and stderr conventions.",
                "preserve"),
    )},
    "library": {"kind": "surface", "policies": (
        _policy("library.public-api",
                "Preserve public API and import behavior unless the task explicitly changes them.",
                "preserve"),
    )},
    "sdk": {"kind": "surface", "policies": (
        _policy("sdk.generated-contract",
                "Check generated surfaces and supported client compatibility before changing handwritten SDK behavior.",
                "preserve"),
    )},
    "database": {"kind": "surface", "policies": (
        _policy("database.data-transition",
                "Treat schema and stored-data transitions as part of the change, not only the final representation."),
    )},
    "data": {"kind": "surface", "policies": (
        _policy("data.schema-semantics",
                "Preserve null, ordering, encoding, and schema semantics relied on by downstream consumers.",
                "preserve"),
        _policy("data.structured-roundtrip",
                "For structured exports, check delimiter, quoting, newline, encoding, and null semantics through a conforming parser.",
                "checks"),
    )},
    "infrastructure": {"kind": "surface", "policies": (
        _policy("infrastructure.deployment-conventions",
                "Fit existing deployment, health, and configuration conventions rather than adding a parallel mechanism."),
    )},
    "automation": {"kind": "surface", "policies": (
        _policy("automation.idempotency",
                "Preserve rerun safety and existing failure signaling where automation can execute more than once."),
    )},
    "mobile": {"kind": "surface", "policies": (
        _policy("mobile.platform-lifecycle",
                "Account for the repository's platform lifecycle and background-state conventions when affected."),
    )},
    "desktop": {"kind": "surface", "policies": (
        _policy("desktop.platform-conventions",
                "Preserve platform integration, persistence, and window lifecycle conventions where affected."),
    )},
    "ml": {"kind": "surface", "policies": (
        _policy("ml.evaluation-contract",
                "Keep preprocessing, evaluation splits, and inference-time contracts aligned with the existing model path."),
    )},
    "systems": {"kind": "surface", "policies": (
        _policy("systems.resource-limits",
                "Respect existing memory, ownership, and platform-boundary assumptions before widening resource use."),
    )},
    "documentation": {"kind": "surface", "policies": (
        _policy("documentation.reference-consistency",
                "Update linked references or generated documentation only where the repository shows the same name is shared.",
                "checks"),
    )},
    "general": {"kind": "surface", "policies": ()},
    "compatibility": {"kind": "quality", "policies": (
        _policy("compatibility.observable-behavior",
                "Preserve observable caller behavior unless the request explicitly changes it.",
                "preserve"),
    )},
    "data_integrity": {"kind": "quality", "policies": (
        _policy("integrity.partial-transition",
                "Avoid states where only part of the data or its dependent representation has transitioned."),
    )},
    "security": {"kind": "quality", "policies": (
        _policy("security.trust-boundaries",
                "Reuse existing trust boundaries and validation points; do not broaden authority as an incidental fix."),
    )},
    "privacy": {"kind": "quality", "policies": (
        _policy("privacy.data-exposure",
                "Check whether the change alters stored, logged, or returned sensitive data."),
    )},
    "performance": {"kind": "quality", "policies": (
        _policy("performance.measure-baseline",
                "Use existing benchmarks or a focused before/after measurement and preserve correctness.",
                "checks"),
    )},
    "reliability": {"kind": "quality", "policies": (
        _policy("reliability.failure-policy",
                "Match established retry, timeout, cancellation, and failure-reporting behavior where applicable."),
        _policy("reliability.bounded-retries",
                "For retry behavior, distinguish transient from permanent failures, bound total attempts, and preserve the final failure."),
    )},
    "concurrency": {"kind": "quality", "policies": (
        _policy("concurrency.atomicity",
                "Inspect ownership and atomicity boundaries before changing shared state or retry behavior."),
    )},
    "accessibility": {"kind": "quality", "policies": (
        _policy("accessibility.interaction",
                "Preserve keyboard, focus, labels, and assistive semantics for affected interactive behavior.",
                "preserve"),
    )},
    "ux": {"kind": "quality", "policies": (
        _policy("ux.existing-flows",
                "Keep affected user flows consistent with neighboring interactions and feedback patterns.",
                "context"),
    )},
    "observability": {"kind": "quality", "policies": (
        _policy("observability.existing-signals",
                "Extend existing health, logging, or metrics conventions rather than inventing an unrelated signal.",
                "context"),
    )},
    "deployment": {"kind": "quality", "policies": (
        _policy("deployment.rollout-when-implied",
                "Include rollout compatibility or rollback only when repository deployment evidence makes it relevant."),
    )},
    "resource_usage": {"kind": "quality", "policies": (
        _policy("resource-usage.bounds",
                "Preserve existing CPU, memory, connection, and file-descriptor bounds where the change can affect them.",
                "preserve"),
    )},
    "backwards_compatibility": {"kind": "quality", "policies": (
        _policy("backwards-compatibility.dependent-callers",
                "Inspect dependent callers and serialized forms before changing a public or persisted contract.",
                "preserve"),
    )},
    "existing_system": {"kind": "project_state", "policies": ()},
    "partial_system": {"kind": "project_state", "policies": (
        _policy("partial.complete-seam",
                "Identify the incomplete seam already present before introducing a second path."),
    )},
    "greenfield": {"kind": "project_state", "policies": (
        _policy("greenfield.minimum-structure",
                "Choose the smallest conventional structure that supports the requested behavior without inventing product scope.",
                "context"),
    )},
}

POLICIES = {
    policy["id"]: policy["guidance"]
    for facet in FACETS.values()
    for policy in facet["policies"]
}
POLICY_TARGETS = {
    policy["id"]: policy["target"]
    for facet in FACETS.values()
    for policy in facet["policies"]
}

SPECIFICITIES = ("LOW", "MEDIUM", "HIGH")
ADOPTION_LIMITS = {"LOW": 8, "MEDIUM": 4, "HIGH": 1}


def policy_catalog():
    return {
        name: {
            "kind": value["kind"],
            "policies": [dict(policy) for policy in value["policies"]],
        }
        for name, value in FACETS.items()
    }


def candidate_policy_ids(facets):
    return tuple(dict.fromkeys(
        policy["id"]
        for facet in facets
        for policy in FACETS[facet]["policies"]
    ))


@dataclass(frozen=True)
class SemanticSelection:
    facets: tuple[str, ...]
    specificity: str
    candidate_policy_ids: tuple[str, ...]
    adopted_policy_ids: tuple[str, ...]

    @classmethod
    def from_reply(cls, facets, specificity, adopted_policy_ids):
        if (not isinstance(facets, list) or not facets
                or any(not isinstance(facet, str) for facet in facets)):
            raise TaskIRError("semantic facets must be a non-empty list of strings")
        selected = tuple(dict.fromkeys(facets))
        unknown = [facet for facet in selected if facet not in FACETS]
        if unknown:
            raise TaskIRError("unknown semantic facets: " + ", ".join(unknown))
        if len(selected) > 8:
            raise TaskIRError("at most 8 semantic facets may be selected")
        if specificity not in SPECIFICITIES:
            raise TaskIRError("specificity must be LOW, MEDIUM, or HIGH")
        if (not isinstance(adopted_policy_ids, list)
                or any(not isinstance(item, str) for item in adopted_policy_ids)):
            raise TaskIRError("adopted stdlib policies must be a list of IDs")
        candidates = candidate_policy_ids(selected)
        adopted = tuple(dict.fromkeys(adopted_policy_ids))
        outside = [item for item in adopted if item not in candidates]
        if outside:
            raise TaskIRError(
                "stdlib policies are not candidates of the selected facets: "
                + ", ".join(outside))
        adopted = adopted[:ADOPTION_LIMITS[specificity]]
        return cls(selected, specificity, candidates, adopted)

    @property
    def rejected_policy_ids(self):
        adopted = set(self.adopted_policy_ids)
        return tuple(item for item in self.candidate_policy_ids if item not in adopted)

    def to_dict(self):
        return {
            "semantic_facets": list(self.facets),
            "specificity": self.specificity,
            "candidate_policy_ids": list(self.candidate_policy_ids),
            "adopted_policy_ids": list(self.adopted_policy_ids),
            "rejected_policy_ids": list(self.rejected_policy_ids),
        }

    def adopted_policies(self):
        return [
            {"id": identifier, "guidance": POLICIES[identifier]}
            for identifier in self.adopted_policy_ids
        ]

    def with_adopted(self, adopted_policy_ids):
        return SemanticSelection(
            self.facets, self.specificity, self.candidate_policy_ids,
            tuple(adopted_policy_ids))
