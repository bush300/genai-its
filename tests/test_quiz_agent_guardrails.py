
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
QUIZ_AGENT_DIR = PROJECT_ROOT / "1.4_agent2_quiz"

sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(QUIZ_AGENT_DIR))

from quiz_agent import QuizAgent


def make_agent():
    """Create a QuizAgent without initializing Firebase or the LLM."""
    agent = QuizAgent.__new__(QuizAgent)
    agent.subject = "cybersecurity"
    agent.week = 1
    agent.current_q = 0
    agent.performance = {"answers": {}}
    agent.load_knowledgebase = MagicMock(return_value="")
    return agent


def run_evaluation(response, guardrail_action="allow", flags=None):
    """Run evaluate_answer with mocked LLM and output guardrails."""
    agent = make_agent()

    mock_llm = MagicMock()
    mock_llm.invoke.return_value.content = response

    mock_guardrails = MagicMock()
    mock_guardrails.return_value = {
        "response": response,
        "flags": flags or [],
        "needs_review": bool(flags),
        "action": guardrail_action,
    }

    question = {
        "id": 1,
        "question": "What is access control?",
        "context": "",
        "answer": "Access control restricts access to resources.",
    }

    with patch(
        "quiz_agent.get_groq_llm",
        return_value=mock_llm,
    ), patch(
        "output_guardrails.check_output",
        mock_guardrails,
    ):
        result = agent.evaluate_answer(
            "Access control protects resources.",
            question,
        )

    return result, mock_guardrails


def test_canary_leak_is_blocked():
    result, mock_guardrails = run_evaluation(
        "Correct: Good work.\nSCORE: 1.0",
        guardrail_action="block",
        flags=["canary_leak"],
    )

    assert result[0] is True
    assert result[1] is None
    assert "couldn't safely validate the feedback" in result[2]
    mock_guardrails.assert_called_once()


def test_rubric_leak_is_blocked():
    result, mock_guardrails = run_evaluation(
        "Correct: Good work.\nSCORE: 1.0",
        guardrail_action="block",
        flags=["possible_rubric_leak"],
    )

    assert result[0] is True
    assert result[1] is None
    assert "couldn't safely validate the feedback" in result[2]
    mock_guardrails.assert_called_once()


def test_valid_feedback_is_returned():
    result, mock_guardrails = run_evaluation(
        "Correct: Access control limits access to resources.\nSCORE: 1.0"
    )

    assert result[0] is True
    assert result[1] == 1.0
    assert result[2] == (
        "Correct: Access control limits access to resources."
    )
    mock_guardrails.assert_called_once()


def test_multiple_score_lines_are_rejected():
    result, _ = run_evaluation(
        "Correct: Good work.\nSCORE: 1.0\nSCORE: 0.0",
        guardrail_action="block",
        flags=["multiple_score_lines"],
    )

    assert result[1] is None
    assert "couldn't safely validate the feedback" in result[2]


def test_missing_score_is_rejected():
    result, _ = run_evaluation(
        "Correct: Good work.",
        guardrail_action="block",
        flags=["missing_or_invalid_score"],
    )

    assert result[1] is None
    assert "couldn't safely validate the feedback" in result[2]


def test_out_of_range_score_is_blocked():
    result, _ = run_evaluation(
        "Correct: Good work.\nSCORE: 2.0",
        guardrail_action="block",
        flags=["score_out_of_range"],
    )

    assert result[1] is None
    assert "couldn't safely validate the feedback" in result[2]


def test_multiple_score_lines_rejected_even_if_guardrail_allows():
    result, _ = run_evaluation(
        "Correct: Good work.\nSCORE: 1.0\nSCORE: 0.0",
        guardrail_action="allow",
    )

    assert result[1] is None
    assert "validate the evaluation format" in result[2]


def test_missing_score_rejected_even_if_guardrail_allows():
    result, _ = run_evaluation(
        "Correct: Good work.",
        guardrail_action="allow",
    )

    assert result[1] is None
    assert "validate the evaluation format" in result[2]


def test_score_x_without_previous_score_is_rejected():
    result, _ = run_evaluation(
        "That is an interesting question.\nSCORE: X",
        guardrail_action="allow",
    )

    assert result[1] is None
    assert "previous score" in result[2]


def test_score_x_uses_previous_score_for_same_question():
    agent = make_agent()
    agent.performance["answers"]["1"] = [
        {
            "attempt": 1,
            "answer": "Access control protects resources.",
            "feedback": "Correct.",
            "score": 1.0,
        }
    ]

    response = "That is an interesting question.\nSCORE: X"
    mock_llm = MagicMock()
    mock_llm.invoke.return_value.content = response

    mock_guardrails = MagicMock()
    mock_guardrails.return_value = {
        "response": response,
        "flags": [],
        "needs_review": False,
        "action": "allow",
    }

    question = {
        "id": 1,
        "question": "What is access control?",
        "context": "",
        "answer": "Access control restricts access to resources.",
    }

    with patch(
        "quiz_agent.get_groq_llm",
        return_value=mock_llm,
    ), patch(
        "output_guardrails.check_output",
        mock_guardrails,
    ):
        result = agent.evaluate_answer(
            "Why is access control important?",
            question,
        )

    assert result[1] == 1.0
    assert result[2] == "That is an interesting question."


def test_feedback_request_does_not_call_llm():
    agent = make_agent()

    with patch("quiz_agent.get_groq_llm") as mock_get_llm:
        result = agent.evaluate_answer(
            "Can you give me some feedback?",
            {
                "id": 1,
                "question": "What is access control?",
                "context": "",
                "answer": "Access control restricts access to resources.",
            },
        )

    assert result[1] is None
    assert "try answering the question" in result[2]
    mock_get_llm.assert_not_called()
