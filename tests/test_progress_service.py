# Regression test: the My Progress summary cards (Quizzes Completed, Average
# Score, Improvement Rate) used to find a student's records with a plain
# doc_id.startswith(student_id + "_") check, which also matches a different
# student whose username happens to be a prefix of this one followed by "_"
# (e.g. "alice" matching "alice_smith"'s records). The history section on the
# same page was already fixed to use student_records.belongs_to_student;
# this test checks the card calculations use the same safe check.

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
INTERFACE_DIR = PROJECT_ROOT / "1.1_interface"

sys.path.insert(0, str(INTERFACE_DIR))

import progress_service


def _fake_doc(doc_id: str, data: dict) -> SimpleNamespace:
    return SimpleNamespace(id=doc_id, to_dict=lambda: data)


def _records() -> list[SimpleNamespace]:
    # "alice" and "alice_smith" collide under naive prefix matching.
    return [
        _fake_doc(
            "alice_CSIT302_Week1",
            {
                "student_id": "alice",
                "answers": {"q1": [{"score": 1.0}]},
            },
        ),
        _fake_doc(
            "alice_smith_CSIT302_Week1",
            {
                "student_id": "alice_smith",
                "answers": {"q1": [{"score": 0.0}, {"score": 1.0}]},
            },
        ),
    ]


def _patched_db():
    fake_db = MagicMock()
    fake_db.collection.return_value.stream.return_value = _records()
    return patch.object(progress_service.firestore, "client", return_value=fake_db)


def test_quizzes_completed_only_counts_own_records():
    with _patched_db():
        assert progress_service.get_quizzes_completed("alice") == 1
        assert progress_service.get_quizzes_completed("alice_smith") == 1


def test_average_score_only_uses_own_records():
    with _patched_db():
        assert progress_service.get_average_score("alice") == 100
        assert progress_service.get_average_score("alice_smith") == 100


def test_improvement_rate_only_uses_own_records():
    with _patched_db():
        assert progress_service.get_improvement_rate("alice") == 0
        assert progress_service.get_improvement_rate("alice_smith") == 100
