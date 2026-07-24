"""Hand-computed regression tests for the IAA coefficients (§8 "Labelling")."""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np
import pytest

from bench.labeling.iaa import (
    fleiss_kappa,
    krippendorff_alpha,
)


def test_fleiss_kappa_perfect_agreement() -> None:
    # 3 items, 4 raters each, all raters agree per item -> kappa = 1.0.
    # categories = 3 (R0,R1,R2 columns). Each item all 4 in one column.
    ratings = [
        [4, 0, 0],
        [0, 4, 0],
        [0, 0, 4],
    ]
    assert fleiss_kappa(ratings) == pytest.approx(1.0)


def test_fleiss_kappa_hand_computed() -> None:
    # 2 items, 4 raters, 2 categories.
    # item0: 3 in cat0, 1 in cat1 ; item1: 1 in cat0, 3 in cat1.
    # n=4. P_i = (Σ n_ic^2 - n)/(n(n-1)) = (9+1-4)/(12) = 6/12 = 0.5 each.
    # P_bar = 0.5.
    # marginals: cat0 = (3+1)/(2*4)=0.5 ; cat1 = (1+3)/8 = 0.5. P_e = 0.25+0.25=0.5
    # kappa = (0.5 - 0.5)/(1 - 0.5) = 0.0
    ratings = [
        [3, 1],
        [1, 3],
    ]
    assert fleiss_kappa(ratings) == pytest.approx(0.0)


def test_fleiss_kappa_partial_agreement_hand_computed() -> None:
    # 2 items, 4 raters, 2 cats.
    # item0: 4/0 ; item1: 3/1.
    # P0 = (16-4)/12 = 1.0 ; P1 = (9+1-4)/12 = 0.5 -> P_bar = 0.75
    # marginals: cat0=(4+3)/8=0.875 ; cat1=(0+1)/8=0.125 -> P_e=0.765625+0.015625=0.78125
    # kappa = (0.75-0.78125)/(1-0.78125) = (-0.03125)/(0.21875) = -0.142857...
    ratings = [
        [4, 0],
        [3, 1],
    ]
    assert fleiss_kappa(ratings) == pytest.approx(-0.03125 / 0.21875)


def test_fleiss_kappa_requires_equal_raters() -> None:
    with pytest.raises(ValueError):
        fleiss_kappa([[3, 1], [2, 0]])  # 4 vs 2 raters


def test_krippendorff_alpha_perfect_agreement() -> None:
    # Two annotators agree on every item -> alpha = 1.0 (ordinal).
    data = [
        [0, 1, 2, 4, 3],
        [0, 1, 2, 4, 3],
    ]
    assert krippendorff_alpha(data, level="ordinal", categories=[0, 1, 2, 3, 4]) == pytest.approx(
        1.0
    )


def test_krippendorff_alpha_nominal_matches_reference() -> None:
    # 2 coders with missing data. Only mostly-agreeing items -> high nominal
    # alpha. Pinned against an independent recomputation (_reference_nominal_alpha)
    # so the exact number is auditable, not asserted.
    data = [
        [1, 2, 3, 3, 2, 1, 4, 1, 2, None, None, None],
        [1, 2, 3, 3, 2, 2, 4, 1, 2, 5, None, 3],
    ]
    cats = [1, 2, 3, 4, 5]
    alpha = krippendorff_alpha(data, level="nominal", categories=cats)
    ref = _reference_nominal_alpha(data, cats)
    assert alpha == pytest.approx(ref, abs=1e-12)
    assert alpha == pytest.approx(0.8521739130434782, abs=1e-9)


def test_krippendorff_alpha_ordinal_lenient_on_adjacent() -> None:
    # Ordinal alpha should exceed nominal alpha when disagreements are adjacent
    # on the scale (R3 vs R4), because ordinal distance penalises them less.
    data = [
        [0, 1, 2, 3, 4],
        [0, 1, 2, 4, 3],  # last two swapped: adjacent-ish disagreements
    ]
    cats = [0, 1, 2, 3, 4]
    a_ord = krippendorff_alpha(data, level="ordinal", categories=cats)
    a_nom = krippendorff_alpha(data, level="nominal", categories=cats)
    assert a_ord > a_nom


def test_krippendorff_alpha_ordinal_hand_pinned() -> None:
    # Small ordinal fixture we can recompute independently in-test.
    data = [
        [0, 2, 4, 4],
        [0, 2, 3, 4],  # one disagreement: item2 is 4 vs 3 (adjacent)
    ]
    cats = [0, 1, 2, 3, 4]
    alpha = krippendorff_alpha(data, level="ordinal", categories=cats)
    # Independent reference recomputation of the same ordinal-alpha definition.
    ref = _reference_ordinal_alpha(data, cats)
    assert alpha == pytest.approx(ref, abs=1e-12)
    assert 0.0 < alpha < 1.0


def _reference_coincidence(data: Sequence[Sequence[int | None]], cats: list[int]) -> np.ndarray:
    m = len(cats)
    ci = {c: i for i, c in enumerate(cats)}
    n_items = len(data[0])
    coincidence = np.zeros((m, m))
    for i in range(n_items):
        col: list[int] = [v for row in data if (v := row[i]) is not None]
        mu = len(col)
        if mu < 2:
            continue
        for a in range(mu):
            for b in range(mu):
                if a == b:
                    continue
                coincidence[ci[col[a]], ci[col[b]]] += 1.0 / (mu - 1)
    return coincidence


def _reference_ordinal_alpha(data: Sequence[Sequence[int | None]], cats: list[int]) -> float:
    """Independent, deliberately naive reimplementation used only to pin tests."""
    m = len(cats)
    coincidence = _reference_coincidence(data, cats)
    n_c = coincidence.sum(axis=1)
    total = float(n_c.sum())
    cum = np.cumsum(n_c)
    dist = np.zeros((m, m))
    for a in range(m):
        for b in range(m):
            lo, hi = (a, b) if a <= b else (b, a)
            seg = cum[hi] - (cum[lo - 1] if lo > 0 else 0.0)
            v = seg - (n_c[lo] + n_c[hi]) / 2.0
            dist[a, b] = v * v
    d_o = float(np.sum(coincidence * dist)) / total
    d_e = 0.0
    for a in range(m):
        for b in range(m):
            d_e += float(n_c[a] * n_c[b] * dist[a, b])
    d_e /= total * (total - 1)
    return float(1.0 - d_o / d_e)


def _reference_nominal_alpha(data: Sequence[Sequence[int | None]], cats: list[int]) -> float:
    """Independent nominal-alpha recomputation used only to pin tests."""
    m = len(cats)
    coincidence = _reference_coincidence(data, cats)
    n_c = coincidence.sum(axis=1)
    total = float(n_c.sum())
    dist = np.array([[0.0 if a == b else 1.0 for b in range(m)] for a in range(m)])
    d_o = float(np.sum(coincidence * dist)) / total
    d_e = 0.0
    for a in range(m):
        for b in range(m):
            d_e += float(n_c[a] * n_c[b] * dist[a, b])
    d_e /= total * (total - 1)
    return float(1.0 - d_o / d_e)
