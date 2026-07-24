"""ReversiBench destructive end-to-end scenarios (``PROJECT.md`` §8.E, §13).

Trace-level suites for agent-level evaluation (§8.E): the 20-second demo scenario
(delete page / drop table / send email / force-push) plus ClawsBench-style bulk
email deletion and a permission grant/revoke trace. Loaded via
:mod:`bench.scenarios.loader`, typed by :mod:`bench.scenarios.schema`.
"""

from __future__ import annotations

__all__ = ["loader", "schema"]
