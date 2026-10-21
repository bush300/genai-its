# Regression test for the "My Progress" data leak: a student whose username
# is a prefix of another student's username (e.g. "alice" / "alice_smith")
# could see the other student's quiz records, because student_performance
# doc IDs (f"{student_id}_{subject}_{week}") have no reserved separator and
# the page used to filter with a plain doc_id.startswith(student_id + "_").

from __future__ import annotations

from student_records import belongs_to_student


def _records() -> dict[str, dict]:
    """A small fake student_performance collection: two students whose
    usernames collide under naive prefix matching."""
    return {
        "alice_CSIT302_Week1": {"student_id": "alice", "last_score": 1.0},
        "alice_smith_CSIT302_Week1": {"student_id": "alice_smith", "last_score": 0.5},
    }


def test_alice_only_sees_her_own_record() -> None:
    records = _records()
    visible = {
        doc_id: data
        for doc_id, data in records.items()
        if belongs_to_student(doc_id, data, "alice")
    }

    assert visible == {"alice_CSIT302_Week1": records["alice_CSIT302_Week1"]}


def test_alice_smith_only_sees_her_own_record() -> None:
    records = _records()
    visible = {
        doc_id: data
        for doc_id, data in records.items()
        if belongs_to_student(doc_id, data, "alice_smith")
    }

    assert visible == {"alice_smith_CSIT302_Week1": records["alice_smith_CSIT302_Week1"]}


def test_legacy_record_without_student_id_field_falls_back_to_prefix() -> None:
    # Pre-existing records saved before student_id was stored on the document.
    # Still vulnerable to the prefix collision - documented, not hidden.
    legacy_alice_smith = {"last_score": 0.5}  # no "student_id" key

    assert belongs_to_student("alice_smith_CSIT302_Week1", legacy_alice_smith, "alice_smith") is True
    assert belongs_to_student("alice_smith_CSIT302_Week1", legacy_alice_smith, "alice") is True  # the known gap
