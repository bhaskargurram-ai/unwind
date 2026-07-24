"""Stage 5 — sandbox validation + fidelity grading (``PROJECT.md`` §6).

*This is what makes Unwind research rather than heuristics.* In an isolated
instance we actually execute ``pre_read → forward → inverse`` and diff the state,
grading the result on the Garcia-Molina scale — **exact / semantic /
acceptable-approximation / failed** — and recording **residue**: the side effects
undo cannot remove (notifications fired, audit entries, version bumps).

Fidelity is measured here, never asserted by the model (benchmark-hygiene rule).
The grader is executor-agnostic: it takes callables so it works against the live
docker sandbox, the in-repo mock servers, or the in-process demo upstream.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from unwind.types import CompensationPlan, FidelityGrade

Executor = Callable[[str, dict[str, Any]], dict[str, Any]]
Snapshot = Callable[[], dict[str, Any]]


@dataclass
class ValidationResult:
    fidelity_grade: FidelityGrade
    residue: list[str] = field(default_factory=list)
    error: str | None = None
    diff: dict[str, Any] = field(default_factory=dict)


def _normalize(state: dict[str, Any], volatile: frozenset[str]) -> dict[str, Any]:
    """Drop known-volatile keys (timestamps, versions) before an equality check."""
    return {k: v for k, v in sorted(state.items()) if k not in volatile}


def state_diff(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    """Structural diff of two flat state dicts → {key: (before, after)}."""
    keys = set(before) | set(after)
    return {k: (before.get(k), after.get(k)) for k in sorted(keys) if before.get(k) != after.get(k)}


# Keys that legitimately change and represent residue rather than restoration
# failure (version counters, audit trails, updated-at timestamps).
_RESIDUE_KEYS = frozenset(
    {
        "version",
        "updated_at",
        "modified",
        "revision",
        "etag",
        "audit",
        "seq",
        "last_modified",
        "notified",
        "read_receipt",
    }
)


def validate_plan(
    plan: CompensationPlan,
    forward_args: dict[str, Any],
    inverse_args: dict[str, Any],
    executor: Executor,
    snapshot: Snapshot,
) -> ValidationResult:
    """Run forward+inverse and grade how faithfully state was restored."""
    if plan.inverse_tool is None:
        return ValidationResult(
            FidelityGrade.FAILED, residue=list(plan.residue), error="no inverse tool in plan"
        )

    try:
        s0 = snapshot()
        executor(plan.forward, forward_args)
        executor(plan.inverse_tool, inverse_args)
        s2 = snapshot()
    except Exception as exc:
        return ValidationResult(
            FidelityGrade.FAILED, residue=list(plan.residue), error=f"{type(exc).__name__}: {exc}"
        )

    diff = state_diff(s0, s2)
    residue = list(plan.residue)
    residue_only = all(any(rk in k for rk in _RESIDUE_KEYS) for k in diff) if diff else False

    if not diff:
        grade = FidelityGrade.EXACT
    elif residue_only:
        grade = FidelityGrade.SEMANTIC
        residue += [f"residual change in '{k}'" for k in diff]
    else:
        # Some non-volatile state was not restored: acceptable approximation at
        # best, failed if the core entity is entirely absent/changed.
        core_restored = _normalize(s0, _RESIDUE_KEYS) == _normalize(s2, _RESIDUE_KEYS)
        grade = FidelityGrade.ACCEPTABLE_APPROXIMATION if core_restored else FidelityGrade.FAILED

    return ValidationResult(grade, residue=sorted(set(residue)), diff=diff)
