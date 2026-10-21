# loads a small set of demo accounts + a published quiz into Firestore, so
# there's something to click through for a demo/walkthrough without having
# to create everything by hand first.
#
#   python 1.5_security/seed_demo_data.py
#
# DEMO ONLY. The passwords below are fixed and public (they're right here in
# the repo) - never run this against a real/production database, only a
# throwaway or demo one. Safe to run more than once - accounts are
# overwritten, the quiz doc is just re-set with the same content.

from __future__ import annotations

import firebase_admin
from firebase_admin import firestore

from create_account import create_account

# No underscores - usernames are matched by prefix elsewhere (student_performance
# doc IDs), so "demo_student" would prefix-match "demo_student_anything_else".
DEMO_TEACHER = ("demoteacher", "demo-teacher-pass1")
DEMO_STUDENT = ("demostudent", "demo-student-pass1")

DEMO_SUBJECT = "DemoSubject"
DEMO_WEEK = "Week1"

DEMO_QUESTIONS = [
    {
        "id": 1,
        "question": "What does the acronym CIA stand for in cybersecurity?",
        "context": (
            "The CIA triad is a foundational model in information security, "
            "covering confidentiality, integrity and availability."
        ),
        "answer": (
            "Award full marks for confidentiality, integrity and availability "
            "all being named. Partial marks if only one or two are given."
        ),
    },
    {
        "id": 2,
        "question": "Why is multi-factor authentication more secure than a password alone?",
        "context": (
            "MFA requires at least two independent proofs of identity, e.g. "
            "something you know (password) plus something you have (phone/token)."
        ),
        "answer": (
            "Full marks if the answer explains that a stolen password alone "
            "is not enough because a second, independent factor is required."
        ),
    },
]


def seed() -> None:
    if not firebase_admin._apps:
        firebase_admin.initialize_app()
    db = firestore.client()

    create_account(*DEMO_TEACHER, role="Teacher", overwrite=True)
    create_account(*DEMO_STUDENT, role="Student", overwrite=True)

    doc_id = f"{DEMO_SUBJECT}_{DEMO_WEEK}"
    db.collection("finalised_quizzes").document(doc_id).set({
        "subject": DEMO_SUBJECT,
        "week": DEMO_WEEK,
        "questions": DEMO_QUESTIONS,
        "status": "published",
    })

    print("Demo data loaded:")
    print(f"  Teacher login - username: {DEMO_TEACHER[0]}  password: {DEMO_TEACHER[1]}")
    print(f"  Student login - username: {DEMO_STUDENT[0]}  password: {DEMO_STUDENT[1]}")
    print(f"  Quiz          - {DEMO_SUBJECT} / {DEMO_WEEK} (published, {len(DEMO_QUESTIONS)} questions)")


if __name__ == "__main__":
    seed()
