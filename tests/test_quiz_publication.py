# tests for the draft/published quiz gate - no Firestore/Streamlit needed,
# it's all plain functions

from __future__ import annotations

from quiz_publication import is_quiz_published, resolve_save_status


def test_missing_document_is_not_published() -> None:
    assert is_quiz_published(None) is False


def test_missing_status_field_treated_as_published() -> None:
    assert is_quiz_published({"subject": "COMP801", "week": "Week 1"}) is True


def test_draft_status_is_not_published() -> None:
    assert is_quiz_published({"status": "draft"}) is False


def test_published_status_is_published() -> None:
    assert is_quiz_published({"status": "published"}) is True


def test_new_quiz_defaults_to_draft() -> None:
    assert resolve_save_status(existing_doc=None) == "draft"


def test_editing_existing_quiz_preserves_its_status() -> None:
    assert resolve_save_status(existing_doc={"status": "published"}) == "published"
    assert resolve_save_status(existing_doc={"status": "draft"}) == "draft"


def test_explicit_status_overrides_everything() -> None:
    assert resolve_save_status(
        existing_doc={"status": "draft"}, requested_status="published"
    ) == "published"
