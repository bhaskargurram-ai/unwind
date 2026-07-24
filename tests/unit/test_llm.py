"""Unit tests for the offline LLM classifier (``unwind/classify/llm.py``)."""

from __future__ import annotations

from unwind.classify.llm import HeuristicLLM, classify_llm
from unwind.types import ReversibilityClass, ToolSpec


def _spec(name: str) -> ToolSpec:
    return ToolSpec(server="s", name=name)


class TestClassifyLlm:
    def test_confidence_in_unit_interval(self) -> None:
        cls = classify_llm(_spec("create_page"), k=5)
        assert 0.0 <= cls.confidence <= 1.0

    def test_k1_gives_confidence_one(self) -> None:
        cls = classify_llm(_spec("create_page"), k=1)
        assert cls.confidence == 1.0

    def test_read_is_stable_r0_full_agreement(self) -> None:
        # R0 is stable at the extremes -> unanimous -> confidence 1.0.
        cls = classify_llm(_spec("get_file"), k=5)
        assert cls.rev_class == ReversibilityClass.R0
        assert cls.confidence == 1.0

    def test_delete_is_stable_r4(self) -> None:
        cls = classify_llm(_spec("delete_page"), k=7)
        assert cls.rev_class == ReversibilityClass.R4
        assert cls.confidence == 1.0

    def test_modal_class_returned(self) -> None:
        # The modal (most common) vote is returned; for a middle verb it should
        # be the lexical base most of the time.
        cls = classify_llm(_spec("update_record"), k=9)
        assert cls.rev_class in (ReversibilityClass.R1, ReversibilityClass.R2)

    def test_deterministic(self) -> None:
        a = classify_llm(_spec("create_widget"), k=5)
        b = classify_llm(_spec("create_widget"), k=5)
        assert a.rev_class == b.rev_class
        assert a.confidence == b.confidence

    def test_signals_populated(self) -> None:
        cls = classify_llm(_spec("create_page"), k=5)
        assert cls.signals["llm_backend"] == "HeuristicLLM"
        assert cls.signals["llm_k"] == 5
        assert isinstance(cls.signals["llm_votes"], dict)

    def test_k_floor_at_one(self) -> None:
        # k <= 0 is clamped to at least one sample.
        cls = classify_llm(_spec("get_file"), k=0)
        assert cls.signals["llm_k"] == 1


class TestHeuristicLLMDirect:
    def test_judge_stable_for_reads(self) -> None:
        llm = HeuristicLLM()
        votes = {llm.judge(_spec("list_pages"), seed=i) for i in range(20)}
        assert votes == {ReversibilityClass.R0}

    def test_judge_never_below_base_for_middle(self) -> None:
        llm = HeuristicLLM()
        base = ReversibilityClass.R2
        for i in range(20):
            v = llm.judge(_spec("create_page"), seed=i)
            assert v >= base
