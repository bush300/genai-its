# Decides whether a student_performance Firestore record belongs to a given
# student. Pulled out as its own function so it's testable without mocking
# Streamlit/Firestore - see tests/test_student_records.py.

from __future__ import annotations

from typing import Optional


def belongs_to_student(doc_id: str, record_data: dict, student_id: str) -> bool:
    """True if this student_performance record is this student's own.

    Doc IDs are f"{student_id}_{subject}_{week}" with no reserved separator,
    so a plain prefix check (doc_id.startswith(student_id + "_")) also
    matches a different student whose ID happens to start with this one
    followed by "_" (e.g. "alice" matching "alice_smith"'s records). Prefer
    the student_id field stored on the record itself; only fall back to the
    prefix check for older records saved before that field existed.
    """
    record_student_id: Optional[str] = record_data.get("student_id")
    if record_student_id is not None:
        return record_student_id == student_id
    return doc_id.startswith(f"{student_id}_")
