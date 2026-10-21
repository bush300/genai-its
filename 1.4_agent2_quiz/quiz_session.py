import os
import json

class QuizSession:
    def __init__(self, subject, week, quiz_name):  # Fixed: Added 'self' as the first parameter
        self.subject = subject
        self.week = week
        self.quiz_name = quiz_name
        self.questions = self._load_quiz()
        self.current_index = 0
        self.attempts = []

    def _load_quiz(self):
        quiz_path = os.path.join("data", "finalised_quizzes", self.subject, self.week, f"{self.quiz_name}.json")
        print(f"Looking for quiz file at: {quiz_path}")  # Debug statement
        if not os.path.exists(quiz_path):
            raise FileNotFoundError(f"Quiz {self.quiz_name} not found for {self.subject}/{self.week}.")
        with open(quiz_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def current_question(self):
        return self.questions[self.current_index]

    def submit_answer(self, answer):
        q = self.current_question()
        self.attempts.append({
            "question": q["question"],
            "answer": answer,
            "correct": None  # TBD - integrate answer checking
        })
        self.current_index += 1

    def is_finished(self):
        return self.current_index >= len(self.questions)
