"""ReversiBench catalog — tool-spec extraction from live MCP servers (§8 "Corpus").

Only the crawler and content hashes are committed; crawled data lands under the
gitignored ``bench/catalog/data/`` (``PROJECT.md`` §12, ``CLAUDE.md`` git
conventions).
"""

from __future__ import annotations

__all__ = ["crawler"]
