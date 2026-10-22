# instructor release gate (draft/published quiz status), kept out of
# streamlit_app.py so it can be unit tested without mocking Streamlit or
# Firestore.

from __future__ import annotations

from typing import Optional


def is_quiz_published(quiz_doc: Optional[dict]) -> bool:
    # A quiz is visible to students unless it's explicitly marked draft.
    # No status field = quiz predates this feature, treat it as published.
    if not quiz_doc:
        return False
    return quiz_doc.get("status", "published") != "draft"


def resolve_save_status(
    existing_doc: Optional[dict],
    requested_status: Optional[str] = None,
) -> str:
    # requested_status wins (e.g. the Approve button). Otherwise editing a
    # quiz keeps whatever status it already had, and a brand new one starts
    # as a draft until a teacher approves it.
    if requested_status is not None:
        return requested_status
    if existing_doc and "status" in existing_doc:
        return existing_doc["status"]
    return "draft"
