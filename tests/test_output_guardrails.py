
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
QUIZ_AGENT_DIR = PROJECT_ROOT / "1.4_agent2_quiz"

# Allow imports from the project root and quiz agent directory.
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(QUIZ_AGENT_DIR))

from output_guardrails import check_output


def test_valid_numeric_score():
    result = check_output("Correct: Well done.\nSCORE: 1.0")
    assert "missing_or_invalid_score" not in result["flags"]
    assert "score_out_of_range" not in result["flags"]


def test_exploration_score_x_is_allowed():
    result = check_output("Here is an explanation.\nSCORE: X")
    assert "missing_or_invalid_score" not in result["flags"]
    assert "score_out_of_range" not in result["flags"]


def test_score_above_range_is_flagged():
    result = check_output("Correct: Well done.\nSCORE: 1.5")
    assert "score_out_of_range" in result["flags"]


def test_missing_score_is_flagged():
    result = check_output("Correct: Well done.")
    assert "missing_or_invalid_score" in result["flags"]


def test_contradictory_incorrect_feedback_and_positive_score():
    result = check_output("Incorrect: Your answer is wrong.\nSCORE: 1.0")
    assert "score_feedback_contradiction" in result["flags"]
    assert result["needs_review"] is True


def test_consistent_correct_feedback_and_positive_score():
    result = check_output("Correct: Well done!\nSCORE: 1.0")
    assert "score_feedback_contradiction" not in result["flags"]
    assert result["needs_review"] is False


def test_possible_rubric_leak_is_flagged():
    result = check_output(
        "The expected answer is to implement access control.\nSCORE: 1.0"
    )
    assert "possible_rubric_leak" in result["flags"]


def test_harmless_mention_of_expected_answer_is_not_flagged():
    result = check_output(
        "I won't reveal the expected answer yet. Try explaining your reasoning.\n"
        "SCORE: X"
    )
    assert "possible_rubric_leak" not in result["flags"]

def test_rubric_overlap_is_flagged():
    rubric = (
        "Implement access control to restrict unauthorised users "
        "from accessing sensitive resources in the system."
    )
    response = (
        "Implement access control to restrict unauthorised users "
        "from accessing sensitive resources in the system.\n"
        "SCORE: 1.0"
    )

    result = check_output(response, rubric=rubric)

    assert "possible_rubric_leak" in result["flags"]


def test_no_rubric_overlap_is_not_flagged():
    rubric = (
        "Implement access control to restrict unauthorised users "
        "from accessing sensitive resources in the system."
    )
    response = (
        "You should explain how permissions protect private information.\n"
        "SCORE: X"
    )

    result = check_output(response, rubric=rubric)

    assert "possible_rubric_leak" not in result["flags"]