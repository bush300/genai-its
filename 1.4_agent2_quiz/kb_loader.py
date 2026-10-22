"""
kb_loader.py
────────────────────────────────────────────────────────────────────────
A tiny helper that gives the feedback / evaluator agent **one call** to
load ALL artefacts for a given (course, quiz) pair:

    • questions.json          (Q/C/A triples)
    • course content vectors  (optional)
    • quiz-specific vector DB (optional)

This keeps path logic **centralised** so every chain / agent shares the
same layout convention.

Directory layout recap
────────────────────────────────────────────────────────────────────────
data/
└── courses/
    └── <COURSE>/
        ├── course_kb/                 ← course-wide content
        │   └── vectorstore/…
        └── quiz_kb/
            └── <QUIZ>/
                ├── questions.json     ← Q / C / (A) pairs
                └── vectorstore/…      ← vectors for the quiz PDF
"""

from pathlib import Path
import json
from typing import Dict, Optional
from langchain_community.vectorstores import FAISS
from .document_loader import LocalHuggingFaceEmbeddings  # already defined

BASE_DIR = Path(__file__).resolve().parents[2]  # …/GENAI_ITS
COURSES_DIR = BASE_DIR / "data" / "courses"

def _load_vectorstore(path: Path) -> Optional[FAISS]:
    """Return FAISS store if folder exists, else None (caller handles)."""
    if path.exists():
        embs = LocalHuggingFaceEmbeddings()
        return FAISS.load_local(
            str(path),
            embs,
            allow_dangerous_deserialization=True,
        )
    return None


def load_quiz_kb(course: str, quiz: str) -> Dict:
    """
    Returns:
        {
          "questions": List[dict],          # Q/C/A triples
          "quiz_vectors": FAISS | None,     # vectors built from the quiz sample PDF
          "course_vectors": FAISS | None,   # wider course content
        }
    Raises:
        FileNotFoundError if questions.json is missing.
    """
    course_path = COURSES_DIR / course / "quiz_kb" / quiz
    questions_file = course_path / "questions.json"

    if not questions_file.exists():
        raise FileNotFoundError(f"Missing questions.json at {questions_file}")

    with open(questions_file, "r", encoding="utf-8") as f:
        questions = json.load(f)  # List[dict]

    return {
        "questions":      questions,
        "quiz_vectors":   _load_vectorstore(course_path / "vectorstore"),
        "course_vectors": _load_vectorstore(COURSES_DIR / course / "course_kb" / "vectorstore"),
    }

def load_knowledgebase():
    kb_path = Path("data/global_kb")
    return [str(file) for file in kb_path.glob("**/*") if file.is_file()]

def load_subject_material(subject):
    subject_path = Path("data/courses") / subject / "subject_material"
    if not subject_path.exists():
        raise FileNotFoundError(f"No subject material found for {subject}.")
    return [str(file) for file in subject_path.glob("**/*") if file.is_file()]
