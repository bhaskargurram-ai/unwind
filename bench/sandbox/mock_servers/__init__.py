"""In-repo mock MCP servers for the ReversiBench sandbox (``PROJECT.md`` §8, §10).

Public comms/payments servers cannot be exercised destructively in a benchmark,
so we ship faithful mocks that reproduce the *reversibility structure* we need to
validate:

* :mod:`bench.sandbox.mock_servers.comms_server` — ``send_email`` / ``post_message``
  are R3/R4-ish with a "retract within 30s" half-life (§5.2).
* :mod:`bench.sandbox.mock_servers.payments_server` — ``charge`` is R4
  post-settlement (R2 inside a void window); ``refund`` is a *partial* compensation
  that leaves residue.

Both expose the same in-process backend the servers use, so :mod:`bench.sandbox.harness`
can drive them without a subprocess in unit tests, and via FastMCP stdio in the
full sandbox.
"""

from __future__ import annotations

__all__ = ["comms_server", "payments_server"]
