"""Unit tests for the lexical classifier (``unwind/classify/lexical.py``)."""

from __future__ import annotations

import pytest

from unwind.classify.lexical import classify_lexical, guess_entity, tokenize
from unwind.types import EffectVerb, Externality, ReversibilityClass, ToolSpec


def _spec(name: str, description: str = "") -> ToolSpec:
    return ToolSpec(server="s", name=name, description=description)


class TestTokenize:
    def test_snake_case(self) -> None:
        assert tokenize("delete_user_account") == ["delete", "user", "account"]

    def test_camel_case(self) -> None:
        assert tokenize("deleteUserAccount") == ["delete", "user", "account"]

    def test_kebab_case(self) -> None:
        assert tokenize("delete-user-account") == ["delete", "user", "account"]

    def test_mixed_with_digits(self) -> None:
        assert tokenize("getUser2Profile") == ["get", "user2", "profile"]


class TestClassifyLexicalVerbTable:
    @pytest.mark.parametrize(
        "name,expected_class,expected_verb",
        [
            ("get_file", ReversibilityClass.R0, EffectVerb.READ),
            ("list_pages", ReversibilityClass.R0, EffectVerb.READ),
            ("search_docs", ReversibilityClass.R0, EffectVerb.READ),
            ("write_file", ReversibilityClass.R1, EffectVerb.UPDATE),
            ("update_record", ReversibilityClass.R1, EffectVerb.UPDATE),
            ("set_config", ReversibilityClass.R1, EffectVerb.UPDATE),
            ("create_page", ReversibilityClass.R2, EffectVerb.CREATE),
            ("add_member", ReversibilityClass.R2, EffectVerb.CREATE),
            ("send_email", ReversibilityClass.R3, EffectVerb.SEND),
            ("post_message", ReversibilityClass.R3, EffectVerb.SEND),
            ("delete_page", ReversibilityClass.R4, EffectVerb.DELETE),
            ("drop_table", ReversibilityClass.R4, EffectVerb.DELETE),
            ("charge_card", ReversibilityClass.R4, EffectVerb.EXECUTE),
        ],
    )
    def test_verb_to_class(
        self, name: str, expected_class: ReversibilityClass, expected_verb: EffectVerb
    ) -> None:
        cls = classify_lexical(_spec(name))
        assert cls.rev_class == expected_class
        assert cls.effect_verb == expected_verb

    def test_unknown_fails_safe_to_r4_low_confidence(self) -> None:
        cls = classify_lexical(_spec("frobnicate_widget"))
        assert cls.rev_class == ReversibilityClass.R4
        assert cls.effect_verb == EffectVerb.UNKNOWN
        assert cls.confidence < 0.2

    def test_description_fallback_when_name_has_no_verb(self) -> None:
        cls = classify_lexical(_spec("widget_op", description="delete the widget"))
        assert cls.rev_class == ReversibilityClass.R4
        assert cls.effect_verb == EffectVerb.DELETE


class TestExternalityHints:
    def test_send_verb_is_external(self) -> None:
        cls = classify_lexical(_spec("send_email"))
        assert cls.externality == Externality.EXTERNAL

    def test_slack_notify_external(self) -> None:
        cls = classify_lexical(_spec("notify_slack"))
        assert cls.externality == Externality.EXTERNAL

    def test_internal_write_not_external(self) -> None:
        cls = classify_lexical(_spec("write_file"))
        assert cls.externality == Externality.INTERNAL


class TestGuessEntity:
    def test_entity_is_last_noun(self) -> None:
        assert guess_entity(["delete", "user"], EffectVerb.DELETE) == "user"

    def test_entity_none_when_only_verb(self) -> None:
        # "delete" is a verb word and filtered out; nothing left.
        assert guess_entity(["delete"], EffectVerb.DELETE) is None

    def test_classify_populates_entity(self) -> None:
        assert classify_lexical(_spec("create_page")).entity == "page"


class TestConfidenceMonotonicity:
    def test_read_high_confidence(self) -> None:
        assert classify_lexical(_spec("get_file")).confidence == pytest.approx(0.9)

    def test_middle_ambiguous_lower(self) -> None:
        # create/update are genuinely ambiguous -> lower confidence than reads.
        assert classify_lexical(_spec("update_record")).confidence < 0.9
