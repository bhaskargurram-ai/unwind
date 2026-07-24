"""Live fidelity-validation harness (``PROJECT.md`` §6 Stage 5, §8 "Live validation").

Executes ``pre_read → forward → inverse`` against a server and **diffs state** to
grade rollback fidelity — this is what makes fidelity claims real rather than
asserted (benchmark hygiene). Fidelity is graded on the ordinal
:class:`~unwind.types.FidelityGrade` scale (never a boolean, golden rule #4), and
**residue** (side-effects undo cannot remove) is always reported.

The harness is transport-agnostic: it drives any object with a synchronous
``call(tool, **kwargs) -> dict`` method. The mock backends
(:class:`~bench.sandbox.mock_servers.comms_server.CommsBackend`,
:class:`~bench.sandbox.mock_servers.payments_server.PaymentsBackend`) are adapted
via :class:`BackendCaller` for dependency-light unit tests; a thin MCP client
adapter can implement the same protocol for the full Docker sandbox.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol

from unwind.types import FidelityGrade

__all__ = [
    "BackendCaller",
    "FidelityReport",
    "ToolCaller",
    "grade_fidelity",
    "run_forward_inverse",
]


class ToolCaller(Protocol):
    """Anything the harness can call a tool on."""

    def call(self, tool: str, /, **kwargs: Any) -> dict[str, Any]: ...


@dataclass
class BackendCaller:
    """Adapt a plain in-process backend (methods = tools) to :class:`ToolCaller`.

    Lets the harness drive :class:`CommsBackend` / :class:`PaymentsBackend`
    directly in unit tests without spawning an MCP subprocess. ``call("charge",
    account=..., amount_cents=...)`` dispatches to ``backend.charge(...)``.
    """

    backend: Any

    def call(self, tool: str, /, **kwargs: Any) -> dict[str, Any]:
        method = getattr(self.backend, tool)
        result = method(**kwargs)
        return dict(result) if isinstance(result, Mapping) else {"result": result}


def _key_field_diff(
    before: Mapping[str, Any],
    after: Mapping[str, Any],
    key_fields: Sequence[str],
) -> list[str]:
    """Return the list of key fields that differ between two state snapshots."""
    changed: list[str] = []
    for k in key_fields:
        if before.get(k) != after.get(k):
            changed.append(k)
    return changed


@dataclass
class FidelityReport:
    """Graded outcome of a forward+inverse round-trip (§6 Stage 5).

    Attributes
    ----------
    grade:
        The :class:`FidelityGrade` (failed / acceptable-approximation / semantic /
        exact).
    residue:
        Side-effects the inverse could not remove (notifications, fees, audit
        entries, version bumps).
    executed_ok:
        Whether the inverse call executed without error (feeds §8.B validity).
    changed_fields:
        Fields that still differ from pre-state after the inverse (empty ⇒ exact).
    prestate, poststate:
        The captured snapshots, for auditing.
    """

    grade: FidelityGrade
    residue: list[str] = field(default_factory=list)
    executed_ok: bool = True
    changed_fields: list[str] = field(default_factory=list)
    prestate: dict[str, Any] = field(default_factory=dict)
    poststate: dict[str, Any] = field(default_factory=dict)


def grade_fidelity(
    prestate: Mapping[str, Any],
    poststate: Mapping[str, Any],
    *,
    key_fields: Sequence[str],
    residue: Sequence[str],
    inverse_ok: bool,
    approx_fields: Sequence[str] = (),
) -> FidelityReport:
    """Grade a forward+inverse round-trip by diffing pre- vs post-state (§6 Stage 5).

    Grading ladder (ordinal, matching :class:`FidelityGrade`):

    * **failed** — the inverse errored (``inverse_ok`` is False), or a *key* field
      that is **not** an accepted approximation still differs.
    * **acceptable-approximation** — the only differing key fields are in
      ``approx_fields`` (e.g. a new ``updated_at``), or residue exists but the
      restored state is semantically right (per Garcia-Molina & Salem: "an
      acceptable approximation").
    * **semantic** — all key fields restored **and** no residue, but non-key
      fields may differ (identity/timestamps).
    * **exact** — every key field restored, no residue, no accepted-approximation
      drift.

    DECISION: "semantic" vs "exact" hinges on residue and non-key drift, not on a
    byte-for-byte compare of the whole record — matching §6's grade names, where
    "exact" means the observable prior state is fully restored with nothing left
    over, and "semantic" means the key fields match but the compensation left a
    benign trace (e.g. an id change). Residue always caps the grade at
    acceptable-approximation (there is a side-effect undo could not remove).
    """
    changed = _key_field_diff(prestate, poststate, key_fields)
    non_approx_changed = [c for c in changed if c not in set(approx_fields)]
    approx_changed = [c for c in changed if c in set(approx_fields)]
    has_residue = len(residue) > 0

    if not inverse_ok or non_approx_changed:
        grade = FidelityGrade.FAILED
    elif has_residue or approx_changed:
        grade = FidelityGrade.ACCEPTABLE_APPROXIMATION
    else:
        # All key fields restored, no residue. Distinguish exact vs semantic by
        # whether ANY field (beyond the key set) drifted.
        all_keys = set(prestate) | set(poststate)
        any_drift = any(prestate.get(k) != poststate.get(k) for k in all_keys)
        grade = FidelityGrade.SEMANTIC if any_drift else FidelityGrade.EXACT

    return FidelityReport(
        grade=grade,
        residue=list(residue),
        executed_ok=inverse_ok,
        changed_fields=changed,
        prestate=dict(prestate),
        poststate=dict(poststate),
    )


def run_forward_inverse(
    caller: ToolCaller,
    *,
    pre_read: str,
    pre_read_args: Mapping[str, Any],
    forward: str,
    forward_args: Mapping[str, Any],
    inverse: str,
    inverse_args_fn: Callable[[Mapping[str, Any], Mapping[str, Any]], Mapping[str, Any]],
    key_fields: Sequence[str],
    approx_fields: Sequence[str] = (),
    residue_key: str = "residue",
) -> FidelityReport:
    """Drive ``pre_read → forward → inverse → pre_read`` and grade fidelity (§6).

    Steps:
      1. ``pre_read`` snapshots pre-state.
      2. ``forward`` performs the mutating call.
      3. ``inverse_args_fn(prestate, forward_result)`` binds the inverse
         arguments from captured pre-state and the forward response (§6 Stage 4).
      4. ``inverse`` runs; its ``residue`` (if any) is collected.
      5. ``pre_read`` snapshots post-state; :func:`grade_fidelity` diffs.

    The inverse's return value contributing ``residue_key`` supplies the residue
    list; ``executed_ok`` is False iff the inverse reports a falsy success flag
    (``voided``/``retracted``/``refunded`` == False) or raises.
    """
    prestate = caller.call(pre_read, **dict(pre_read_args))
    forward_result = caller.call(forward, **dict(forward_args))
    inverse_args = dict(inverse_args_fn(prestate, forward_result))
    inverse_ok = True
    residue: list[str] = []
    try:
        inv_result = caller.call(inverse, **inverse_args)
    except Exception:
        inverse_ok = False
        inv_result = {}
    residue = list(inv_result.get(residue_key, []) or [])
    # A named success flag reporting False means the inverse did not take effect.
    for flag in ("voided", "retracted", "refunded", "restored", "ok"):
        if flag in inv_result and not inv_result[flag]:
            inverse_ok = False
    poststate = caller.call(pre_read, **dict(pre_read_args))
    return grade_fidelity(
        prestate,
        poststate,
        key_fields=key_fields,
        residue=residue,
        inverse_ok=inverse_ok,
        approx_fields=approx_fields,
    )
