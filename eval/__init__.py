"""Unwind evaluation harness — the five metric families of ``PROJECT.md`` §8.

Every public metric here carries a docstring citing its §8 definition and is
backed by a hand-computed numeric regression test (golden rule #10). Metrics are
pure and deterministic wherever the definition permits; the only stochastic
routine (:func:`eval.stats.bootstrap_ci`) is explicitly seeded.

Module map (mirrors §8 A-E)
---------------------------
* :mod:`eval.classification` — §8.A reversibility classification.
* :mod:`eval.compensation`   — §8.B compensation synthesis.
* :mod:`eval.escalation`     — §8.C escalation policy (selective prediction).
* :mod:`eval.system`         — §8.D system (latency, compatibility).
* :mod:`eval.agent_level`    — §8.E end-to-end agent-level.
* :mod:`eval.stats`          — bootstrap CIs and paired tests (§8 protocol).
"""

from __future__ import annotations

__all__ = [
    "agent_level",
    "classification",
    "compensation",
    "escalation",
    "stats",
    "system",
]
