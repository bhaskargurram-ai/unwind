"""ReversiBench live sandbox — the fidelity-validation harness (``PROJECT.md`` §6 Stage 5, §8).

This is what makes fidelity claims **real, not asserted** (golden rule /
benchmark hygiene): the harness (:mod:`bench.sandbox.harness`) executes
pre_read → forward → inverse against a real (or mock) server and diffs state to
grade fidelity. The mock comms/payments servers model the irreversible-ish tools
(``send_email`` R3 with a ~30s recall window; ``charge`` R4 post-settlement) that
public servers won't let a benchmark exercise safely.
"""

from __future__ import annotations

__all__ = ["harness", "mock_servers"]
