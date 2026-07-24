"""§8.D — System metrics: latency and compatibility (``PROJECT.md`` §8).

Latency is reported split R0 (must be ~free — golden rule #7) vs mutating, so a
regression on the read hot-path can never hide behind a mutating-call average.
Compatibility rate gates adoption (§8.D "Adoption depends on this being ~100%").
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

from unwind.types import ReversibilityClass

__all__ = [
    "EndToEndUndo",
    "LatencySplit",
    "LatencySummary",
    "compatibility_rate",
    "end_to_end_undo",
    "latency_summary",
]


@dataclass(frozen=True)
class LatencySplit:
    """p50/p95 (milliseconds) for one call category."""

    p50_ms: float
    p95_ms: float
    n: int


@dataclass(frozen=True)
class LatencySummary:
    """Added-latency summary, split R0 vs mutating (§8.D).

    ``overall`` is all calls pooled; ``r0`` is nullipotent reads (the hot path
    that must stay ~free); ``mutating`` is everything ``rev_class != R0``.
    """

    overall: LatencySplit
    r0: LatencySplit
    mutating: LatencySplit


def _split(latencies_ms: np.ndarray) -> LatencySplit:
    if latencies_ms.size == 0:
        return LatencySplit(p50_ms=0.0, p95_ms=0.0, n=0)
    return LatencySplit(
        p50_ms=float(np.percentile(latencies_ms, 50)),
        p95_ms=float(np.percentile(latencies_ms, 95)),
        n=int(latencies_ms.size),
    )


def latency_summary(
    added_latency_ms: Sequence[float],
    call_classes: Sequence[ReversibilityClass],
) -> LatencySummary:
    """Added latency per call, p50/p95, split R0 vs mutating (§8.D).

    ``added_latency_ms[i]`` is the proxy overhead (not upstream time) for a call
    whose reversibility class is ``call_classes[i]``. Percentiles are the
    standard linear-interpolated percentiles (numpy default). R0 must stay
    ~free; the split makes any hot-path regression visible.
    """
    if len(added_latency_ms) != len(call_classes):
        raise ValueError("added_latency_ms and call_classes must have equal length")
    if not added_latency_ms:
        raise ValueError("latency_summary requires a non-empty sample")
    lat = np.asarray(added_latency_ms, dtype=float)
    cls = np.array([int(c) for c in call_classes], dtype=int)
    r0 = lat[cls == int(ReversibilityClass.R0)]
    mut = lat[cls != int(ReversibilityClass.R0)]
    return LatencySummary(overall=_split(lat), r0=_split(r0), mutating=_split(mut))


@dataclass(frozen=True)
class EndToEndUndo:
    """End-to-end undo latency + success rate (§8.D)."""

    success_rate: float
    p50_ms: float
    p95_ms: float
    n: int


def end_to_end_undo(
    undo_latency_ms: Sequence[float],
    undo_success: Sequence[bool],
) -> EndToEndUndo:
    """End-to-end undo latency and success rate (§8.D "End-to-end undo latency and success rate").

    ``undo_success[i]`` marks whether the i-th ``unwind.undo`` restored (or
    approximately restored) state; ``undo_latency_ms[i]`` is its wall-clock
    latency. Latency percentiles are over *all* attempts (successful or not), so
    a fast-but-failing undo cannot flatter the number.
    """
    if len(undo_latency_ms) != len(undo_success):
        raise ValueError("undo_latency_ms and undo_success must have equal length")
    if not undo_latency_ms:
        raise ValueError("end_to_end_undo requires a non-empty sample")
    lat = np.asarray(undo_latency_ms, dtype=float)
    return EndToEndUndo(
        success_rate=sum(1 for ok in undo_success if ok) / len(undo_success),
        p50_ms=float(np.percentile(lat, 50)),
        p95_ms=float(np.percentile(lat, 95)),
        n=len(undo_latency_ms),
    )


def compatibility_rate(pair_ok: Sequence[bool]) -> float:
    """Compatibility rate — % of clientxserver pairs working unmodified (§8.D).

    ``pair_ok[i]`` is ``True`` iff the i-th (client, server) pairing behaved
    identically with Unwind in the path (passthrough fidelity + no broken
    method). Adoption depends on this being ~100% (§8.D), so it is reported as a
    plain fraction with no smoothing.
    """
    if not pair_ok:
        raise ValueError("compatibility_rate requires a non-empty sample")
    return sum(1 for ok in pair_ok if ok) / len(pair_ok)
