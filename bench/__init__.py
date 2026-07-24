"""ReversiBench — the labelled reversibility corpus and live sandbox (``PROJECT.md`` §5, §8).

Benchmark hygiene is paramount (``CLAUDE.md``):

* **Server-disjoint splits** (never tool-disjoint within a server — sibling tools
  share lexical patterns and leak). See :mod:`bench.card` and the dataset card.
* **Calibration thresholds fit only on the calibration split, never test.**
* **≥2 annotators** on a stratified sample; report ordinal IAA
  (Krippendorff's alpha / Fleiss' κ) via :mod:`bench.labeling.iaa`.
* **Fidelity claims come from the live sandbox** (:mod:`bench.sandbox.harness`) —
  actual forward+inverse execution and state diff — never from model assertion.

Never commit crawled server data — only the crawler and content hashes
(:mod:`bench.catalog.crawler`); crawl outputs land under the gitignored
``bench/catalog/data/``.
"""

from __future__ import annotations

__all__ = ["catalog", "labeling", "sandbox", "scenarios"]
