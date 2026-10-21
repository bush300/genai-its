from llm_provider import get_llm

# Initialize the LLM
llm = get_llm()

def evaluate_response(question, student_response, expected_answer):
    """
    Evaluate the student's response using the LLM.
    
    Parameters:
        question (str): The question being asked.
        student_response (str): The student's answer.
        expected_answer (dict): The expected answer (from the quiz JSON).

    Returns:
        tuple: (feedback, is_correct)
            feedback (str): Feedback for the student.
            is_correct (bool): Whether the response is correct.
    """
    prompt = f"""
You are an intelligent tutor. Evaluate the student's response to the question below.

Question:
{question}

Expected Answer:
{expected_answer['answer']}

Student's Response:
{student_response}

Provide feedback in two parts:
1. Is the response correct? (Yes/No)
2. If not fully correct, provide up to 2 points of feedback to help the student improve.

Your response should be in this format:
Correct: <Yes/No>
Feedback: <Your feedback here>
    """

    try:
        response = llm.invoke(prompt).content.strip()
        correct = "Yes" in response.splitlines()[0]
        feedback = "\n".join(response.splitlines()[1:])
        return feedback, correct
    except Exception as e:
        return f"Error evaluating response: {e}", False