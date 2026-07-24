"""Inter-annotator agreement for ReversiBench (``PROJECT.md`` §8 "Labelling").

Two coefficients, per the protocol ("report **Krippendorff's alpha / Fleiss' κ**
(ordinal)"):

* :func:`fleiss_kappa` — nominal agreement among a *fixed* number of raters per
  item over categories.
* :func:`krippendorff_alpha` — a general agreement coefficient that (a) handles
  missing ratings and (b) supports an **ordinal** distance metric, which is the
  right choice for the R-scale where R4↔R3 disagreement is milder than R4↔R0.

Both are implemented from their definitions (no external IAA library) so the
numbers are auditable and pinned by hand-computed fixtures.
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np

__all__ = [
    "fleiss_kappa",
    "krippendorff_alpha",
    "nominal_distance",
    "ordinal_distance_fn",
]


def fleiss_kappa(ratings: Sequence[Sequence[int]]) -> float:
    """Fleiss' κ for a fixed number of raters per item (§8 "Fleiss' κ").

    ``ratings`` is an ``items x categories`` count matrix: ``ratings[i][c]`` is
    the number of raters that assigned item ``i`` to category ``c``. Every item
    must have the same total number of raters ``n`` (Fleiss' assumption).

    κ = (P̄ - P̄_e) / (1 - P̄_e), where P̄ is the mean per-item agreement and
    P̄_e is the agreement expected by chance from the marginal category
    proportions. Returns 1.0 for perfect agreement; 0.0 for chance-level.

    DECISION: when ``1 - P̄_e == 0`` (all raters always pick the same single
    category, so chance agreement is already perfect) κ is defined here as 1.0 —
    there is perfect, if degenerate, agreement.
    """
    mat = np.asarray(ratings, dtype=float)
    if mat.ndim != 2:
        raise ValueError("ratings must be a 2-D items x categories count matrix")
    n_items, _ = mat.shape
    if n_items == 0:
        raise ValueError("fleiss_kappa requires at least one item")
    n_raters = mat.sum(axis=1)
    if not np.allclose(n_raters, n_raters[0]) or n_raters[0] < 2:
        raise ValueError("Fleiss' kappa requires the same (>=2) number of raters per item")
    n = n_raters[0]
    # Per-item agreement P_i = (Σ_c n_ic^2 - n) / (n(n-1)).
    p_i = (np.sum(mat**2, axis=1) - n) / (n * (n - 1))
    p_bar = float(np.mean(p_i))
    # Marginal category proportions p_c = Σ_i n_ic / (N·n).
    p_c = mat.sum(axis=0) / (n_items * n)
    p_e = float(np.sum(p_c**2))
    denom = 1.0 - p_e
    if abs(denom) < 1e-15:
        return 1.0
    return (p_bar - p_e) / denom


def nominal_distance(a: float, b: float) -> float:
    """Nominal (categorical) distance: 0 if equal, 1 otherwise."""
    return 0.0 if a == b else 1.0


def ordinal_distance_fn(categories: Sequence[int]):  # type: ignore[no-untyped-def]
    """Build Krippendorff's **ordinal** distance function for given ranks.

    For the R-scale we pass ``[0, 1, 2, 3, 4]``. Krippendorff's ordinal metric is
    ``δ²(c, k) = ( Σ_{g=c..k} n_g - (n_c + n_k)/2 )²`` where ``n_g`` are the
    marginal counts of each rank. This weights disagreements by how many
    intervening categories they span, so R4↔R3 costs far less than R4↔R0 — the
    asymmetry the R-scale needs (§5.1).

    Returns a closure that, given the marginal count per category, yields the
    pairwise squared-ordinal distance matrix.
    """
    cats = list(categories)
    idx = {c: i for i, c in enumerate(cats)}

    def distance_matrix(marginals: np.ndarray) -> np.ndarray:
        cum = np.cumsum(marginals)
        m = len(cats)
        dist = np.zeros((m, m), dtype=float)
        for ci in range(m):
            for ki in range(m):
                lo, hi = (ci, ki) if ci <= ki else (ki, ci)
                # Σ_{g=lo..hi} n_g  minus half the endpoints.
                seg = cum[hi] - (cum[lo - 1] if lo > 0 else 0.0)
                val = seg - (marginals[lo] + marginals[hi]) / 2.0
                dist[ci, ki] = val * val
        return dist

    distance_matrix.category_index = idx  # type: ignore[attr-defined]
    distance_matrix.categories = cats  # type: ignore[attr-defined]
    return distance_matrix


def krippendorff_alpha(
    reliability_data: Sequence[Sequence[int | None]],
    *,
    level: str = "ordinal",
    categories: Sequence[int] | None = None,
) -> float:
    """Krippendorff's alpha over the R-scale (§8 "Krippendorff's alpha (ordinal)").

    ``reliability_data`` is an ``annotators x items`` matrix; ``[r][i]`` is
    annotator ``r``'s category for item ``i`` (rank on the R-scale), or ``None``
    for a missing rating. Items rated by fewer than two annotators are dropped
    (they carry no agreement information), per Krippendorff.

    alpha = 1 - D_o / D_e, where D_o is observed and D_e expected disagreement,
    computed from the coincidence matrix with the chosen ``level`` distance
    (``"ordinal"`` — the default and correct choice for R0..R4 — or
    ``"nominal"``). alpha = 1 is perfect agreement, 0 is chance, < 0 is systematic
    disagreement.
    """
    data = [[None if v is None else int(v) for v in row] for row in reliability_data]
    if not data or not data[0]:
        raise ValueError("krippendorff_alpha requires a non-empty annotators x items matrix")
    n_items = len(data[0])

    observed_values = {v for row in data for v in row if v is not None}
    cats = sorted(observed_values) if categories is None else sorted(categories)
    if len(cats) < 2:
        # Only one value ever used -> perfect (degenerate) agreement.
        return 1.0
    cat_index = {c: i for i, c in enumerate(cats)}
    m = len(cats)

    # Build the coincidence matrix over units with >= 2 raters. Each unit of
    # multiplicity mu contributes ordered rater-pairs weighted 1/(mu-1) (the
    # standard Krippendorff construction; self-pairs excluded).
    coincidence = np.zeros((m, m), dtype=float)
    for i in range(n_items):
        col: list[int] = [v for row in data if i < len(row) and (v := row[i]) is not None]
        mu = len(col)
        if mu < 2:
            continue
        for a_i in range(mu):
            for b_i in range(mu):
                if a_i == b_i:
                    continue
                ca = cat_index[col[a_i]]
                cb = cat_index[col[b_i]]
                coincidence[ca, cb] += 1.0 / (mu - 1)
    n_c = coincidence.sum(axis=1)
    total = n_c.sum()
    if total <= 0:
        raise ValueError("no item has >= 2 ratings; alpha is undefined")

    # Distance matrix.
    if level == "nominal":
        dist = np.array(
            [[nominal_distance(cats[i], cats[j]) for j in range(m)] for i in range(m)],
            dtype=float,
        )
    elif level == "ordinal":
        builder = ordinal_distance_fn(cats)
        dist = builder(n_c)
    else:
        raise ValueError(f"unknown level {level!r}; use 'ordinal' or 'nominal'")

    # Observed disagreement.
    d_o = float(np.sum(coincidence * dist)) / total
    # Expected disagreement.
    d_e = 0.0
    for c in range(m):
        for k in range(m):
            d_e += n_c[c] * n_c[k] * dist[c, k]
    d_e /= total * (total - 1)
    if abs(d_e) < 1e-15:
        return 1.0
    return float(1.0 - d_o / d_e)
