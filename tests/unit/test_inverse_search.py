"""Unit tests for inverse-candidate retrieval (``unwind/synthesize/inverse_search.py``)."""

from __future__ import annotations

from unwind.synthesize.inverse_search import find_inverse, score_candidate
from unwind.types import ToolSpec

_ID_IN = {"properties": {"id": {"type": "string"}}}
_ID_OUT = {"properties": {"id": {"type": "string"}}}


def _tool(
    name: str, input_schema: dict | None = None, output_schema: dict | None = None
) -> ToolSpec:
    return ToolSpec(
        server="s", name=name, input_schema=input_schema or {}, output_schema=output_schema
    )


class TestFindInverse:
    def test_create_matches_delete_same_entity(self) -> None:
        create = _tool("create_page", _ID_IN, _ID_OUT)
        delete = _tool("delete_page", _ID_IN)
        cand = find_inverse(create, [create, delete])
        assert cand is not None
        assert cand.tool.name == "delete_page"

    def test_delete_matches_create(self) -> None:
        create = _tool("create_page", _ID_IN, _ID_OUT)
        delete = _tool("delete_page", _ID_IN, _ID_OUT)
        cand = find_inverse(delete, [create, delete])
        assert cand is not None
        assert cand.tool.name == "create_page"

    def test_send_email_has_no_inverse_against_delete_page(self) -> None:
        # Regression: an antonym verb alone (delete "undoes" send) must NOT match
        # without entity or schema agreement.
        send = _tool("send_email", {"properties": {"to": {"type": "string"}}})
        delete_page = _tool("delete_page", _ID_IN)
        assert find_inverse(send, [send, delete_page]) is None

    def test_self_reversible_update_returns_same_tool(self) -> None:
        update = _tool("update_record", _ID_IN, _ID_OUT)
        cand = find_inverse(update, [update])
        assert cand is not None
        assert cand.tool.name == "update_record"

    def test_no_candidates_returns_none(self) -> None:
        create = _tool("create_page", _ID_IN, _ID_OUT)
        unrelated = _tool("get_weather", {"properties": {"city": {"type": "string"}}})
        assert find_inverse(create, [create, unrelated]) is None


class TestScoreCandidate:
    def test_self_only_for_update(self) -> None:
        create = _tool("create_page", _ID_IN, _ID_OUT)
        # A create is not self-reversible: scoring itself against itself is None.
        assert score_candidate(create, create) is None

    def test_entity_agreement_boosts_score(self) -> None:
        create = _tool("create_page", _ID_IN, _ID_OUT)
        delete = _tool("delete_page", _ID_IN)
        cand = score_candidate(create, delete)
        assert cand is not None
        # base 0.4 + entity 0.3 + schema 0.3 (returns id, accepts id) = 1.0.
        assert cand.score == 1.0

    def test_antonym_without_entity_or_schema_is_none(self) -> None:
        # create_page vs delete_user: antonym verb but different entity and the
        # target returns no id -> not a valid inverse.
        create = _tool("create_page", _ID_IN)  # no output schema -> no returned id
        delete_user = _tool("delete_user", {"properties": {"handle": {"type": "string"}}})
        assert score_candidate(create, delete_user) is None
