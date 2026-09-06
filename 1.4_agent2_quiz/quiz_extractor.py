# 1.4_agent2_quiz/quiz_extractor.py
# ─────────────────────────────────────────────────────────────────────────
"""
PDF → (question, context, answer-rubric) extractor
↳ OCR fallback now uses unstructured.partition.pdf with strategy="ocr_only".

Returned list item:
{
  "id":       1,
  "question": "…?",
  "context":  "…all info learner needs…",
  "answer":   [ { "criterion": str, "marks": int }, … ]
}
"""

from __future__ import annotations
from pathlib import Path
from typing import List, Dict
import os, json, re, textwrap, shutil, warnings, copy
import streamlit as st
from llm_provider import get_llm

from unstructured.partition.pdf import partition_pdf          # single import

from middleware.input_sanitizer import InputSanitizer

# Lazy singleton so importing this module doesn't require a configured API key
# (e.g. under pytest) until a PDF is actually parsed.
_sanitizer = None


def _get_sanitizer() -> InputSanitizer:
    global _sanitizer
    if _sanitizer is None:
        _sanitizer = InputSanitizer()
    return _sanitizer

# ── Tunables ────────────────────────────────────────────────────────────
MAX_CHARS      = 24_000                # ≈ 7 200 tokens
OCR_LANGUAGES  = ["eng"]            # use only English for maximum compatibility
TEXT_THRESHOLD = 1_000                # chars – if fewer → trigger OCR

# ── Prompts (unchanged) ─────────────────────────────────────────────────
EXTRACT_PROMPT = """\
You are an expert teaching assistant.

TASK:
1. Read the PDF text (≤25 k characters) that follows.
2. Find every assessment question.
3. For each question, output its text and the minimal context required in the following plain text format:

Question: <question text>
Context: <minimal context>

Separate each question block with a blank line and do not output any extra text.
"""

# When the source has instructions/exercises but no explicit questions, synthesize clear questions.
FALLBACK_SYNTH_PROMPT = """\
You are an expert teaching assistant.

TASK:
1. If the source contains instructions, exercises, or teaching material without explicit question labels, synthesize 5–10 clear, self-contained quiz questions.
2. For each question, also provide the minimal context a student needs to answer (but NOT the answer).
3. Use exactly this plain-text format with a blank line between blocks:

Question: <question text>
Context: <minimal context>

Return only the blocks, with no extra commentary.
"""

# ENRICH_PROMPT = textwrap.dedent("""\
#     ROLE
#       • Subject-matter teaching assistant
#       • Excellent at building marking rubrics

#     TASK
#       1. *Verify & enrich* the context so the learner sees
#          **all variables / code / tables essential** to answer the question.
#       2. *Create an answer rubric* – JSON **array** of
#          {{"criterion": str, "marks": int}} items (total ≈ 10 marks).

#     RETURN STRICT JSON (no markdown):

#       {{
#         "context": "<<clean enriched context>>",
#         "answer":  [ {{ "criterion": "...", "marks": 2 }}, … ]
#       }}

#     ------------------------------------------------------------------
#     FULL PDF TEXT (truncated) ↓
#     {pdf_text}
#     ------------------------------------------------------------------

#     QUESTION
#     «{question}»

#     CURRENT CONTEXT
#     «{context}»
# """)

ENRICH_PROMPT = textwrap.dedent("""
    ROLE
      • Experienced university tutor & assessment designer

    TASK:
    Review the CURRENT CONTEXT and the FULL SOURCE TEXT below in relation to the QUESTION.
      • Only include code snippets that are necessary for understanding the question, such as function signatures, input/output format, or code templates that help the student get started.
      • Do NOT include full example solutions, worked code, or step-by-step answers unless the question explicitly asks for it.
    • If the source or context contains any sample output, expected output, or example results, ALWAYS extract and include them in the context, clearly labeled as "Sample Output:" or "Expected Output:" (use section headings).
      • Do NOT just summarize or restate the question—always include all code, variables, and all sample/expected output needed to answer, but avoid giving away the solution.
    • If details are missing but can be found in the FULL SOURCE TEXT, append those details.
      • Otherwise, return the CURRENT CONTEXT verbatim.
      • Format the output for a student: use clear section headings (e.g., "Instructions:", "Useful Functions:", "Sample Output:", "Expected Output:"), bullet points for steps, and triple backticks for code or output blocks.
      • Do NOT output or restate the answer itself, only the information needed to answer.
      • If the context includes "Expected Output" or "Sample Output", label it clearly, but do not provide the answer unless the question explicitly asks for it.

    CURRENT CONTEXT:
    «{context}»

    FULL SOURCE TEXT (truncated):
    {pdf_text}

    QUESTION:
    «{question}»

    RESPONSE:
    Return the enriched context as plain text, formatted for students, including only helpful code instructions (not full solutions) and ALL sample/expected output, but never the answer itself. If you find any sample or expected output, always include it as a clearly labeled section.
""")


RUBRIC_PROMPT = textwrap.dedent("""\
    ROLE
      • Senior examiner creating detailed analytic marking rubrics.
      • Follows instructions *exactly*.

    INSTRUCTIONS
      • Include all the asks mentioned in the question and its related context.
      • Almost every sentence, except background and fluff, should be a criteria item.
      • Flesh out the "how" for each criterion, detailing what the response would look like if executed.
      • Be accurate and comprehensive. Only include criteria items that are explicitly asked for.
      • Group similar items together (e.g., character names, code variables) unless specificity is key.
      • Classify each item as:
        - Objective: Yes/No answer (e.g., "Is this present?")
        - Subjective: Requires interpretation (e.g., "Is this appropriate?")
        - Formatting: Relates to presentation or structure.
      • If the context includes a section labeled "Expected Output", include a criterion requiring the student's answer to match it exactly. If the context includes "Sample Output", do not require the student to reproduce it unless the question explicitly asks for it.
      • Do NOT output or restate the answer itself in the rubric, only the criteria for a correct answer.
    RULES
      • Provide ≥ 3 criteria unless the question is trivial; total marks 8-12.
      • Use integers for marks.
      • If a detailed rubric makes no sense, return **one** criterion that
        contains the full correct answer and set "marks": 1 or 2.
      • Never wrap the JSON in back-ticks!

    OUTPUT FORMAT
        {{
            "answer": [
          {{"criterion": "≈1 sentence describing what earns 3 marks", "marks": 3}},
          {{"criterion": "Another criterion",                         "marks": 4}},
          {{"criterion": "Yet another criterion",                     "marks": 3}}
        ]
        }}
      Provide the marking rubric as plain text, formatted as follows:

      - Criterion 1: [Classification: Objective/Subjective/Formatting]
        Description: [What the criterion is about]
        How: [Details on how to evaluate this criterion]

      - Criterion 2: [Classification: Objective/Subjective/Formatting]
        Description: [What the criterion is about]
        How: [Details on how to evaluate this criterion]

    SPECIAL INSTRUCTIONS FOR OUTPUT FORMATS
      • If the context contains code blocks or sample outputs, reference them as "expected format" or "expected output" in the criteria, but do NOT copy or restate their content.
      • If the question requires a specific output format, include a criterion for correct formatting, but do not reveal the output itself.

    QUESTION
    «{question}»

    CONTEXT
    «{context}»
""")



# ── Helpers ────────────────────────────────────────────────────────────
_MD_FENCE = re.compile(r"```.*?```", re.S)
_JSON_RE  = re.compile(r"(\[.*?\]|\{.*?\})", re.S)
_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".tif", ".tiff"}
_TEXT_EXTENSIONS = {
    ".txt", ".md", ".py", ".js", ".ts", ".java", ".c", ".cpp", ".cs",
    ".html", ".css", ".json", ".yaml", ".yml", ".sh", ".bat", ".ps1", ".sql",
}


def _pdf_to_text(path: str) -> str:
    """Return ASCII-safe text, auto-switching to OCR if needed."""
    # Pass-1: use embedded text if present
    pages = partition_pdf(filename=path,
                          strategy="fast",
                          infer_table_structure=False)

    embedded_txt = "\n".join(p.text for p in pages if p.text)

    # If text layer is tiny → re-run with OCR
    if len(embedded_txt) < TEXT_THRESHOLD:
        _warn_once(
            "No/low text layer – switching to OCR (Tesseract required).")
        pages = partition_pdf(
            filename=path,
            strategy="ocr_only",
            languages=OCR_LANGUAGES,  # updated from ocr_languages to languages, now always a list
            infer_table_structure=True,
        )
        embedded_txt = "\n".join(p.text for p in pages if p.text)

    # ASCII-clean + truncate
    embedded_txt = re.sub(r"[^\x00-\x7F]+", " ", embedded_txt)
    embedded_txt = embedded_txt[:MAX_CHARS]

    # Security gate: block injected/malicious PDF content before it reaches the RAG system.
    is_safe, reason = _get_sanitizer().check_secondary_gate(embedded_txt)
    if not is_safe:
        raise RuntimeError(f"Security check failed for PDF content: {reason}")

    return embedded_txt


def _image_to_text(path: str) -> str:
    """Return OCR text from an image upload."""
    try:
        from unstructured.partition.image import partition_image

        elements = partition_image(
            filename=path,
            strategy="ocr_only",
            languages=OCR_LANGUAGES,
            infer_table_structure=False,
        )
        text = "\n".join(el.text for el in elements if getattr(el, "text", None))
        if text.strip():
            return re.sub(r"[^\x00-\x7F]+", " ", text)[:MAX_CHARS]
    except Exception:
        pass

    try:
        from PIL import Image
        import pytesseract

        text = pytesseract.image_to_string(Image.open(path), lang=OCR_LANGUAGES[0])
        return re.sub(r"[^\x00-\x7F]+", " ", text)[:MAX_CHARS]
    except Exception as exc:
        raise RuntimeError(f"Image OCR failed: {exc}") from exc


def _text_file_to_text(path: str) -> str:
    """Return plain text from a text or code upload."""
    try:
        raw = Path(path).read_text(encoding="utf-8", errors="ignore")
    except Exception as exc:
        raise RuntimeError(f"Text file read failed: {exc}") from exc
    return re.sub(r"[^\x00-\x7F]+", " ", raw)[:MAX_CHARS]


def _source_to_text(path: str) -> str:
    ext = Path(path).suffix.lower()
    if ext == ".pdf":
        return _pdf_to_text(path)
    if ext in _IMAGE_EXTENSIONS:
        return _image_to_text(path)
    if ext in _TEXT_EXTENSIONS:
        return _text_file_to_text(path)
    raise ValueError(f"Unsupported file type: {ext or 'unknown'}")


def _clean_json(raw: str) -> str:
    # Remove backticks and markdown fences
    raw = raw.strip("`").strip()
    raw = _MD_FENCE.sub("", raw).strip()

    # Extract JSON-like content
    m = _JSON_RE.search(raw)
    if m:
        return m.group(1).strip()

    # Log a warning if no JSON is found
    _warn_once(f"⚠️ No JSON found – first 300 chars:\n{raw[:300]}")
    return ""


def _repair_json(raw: str) -> str:
    try:
        # Attempt to parse the JSON directly
        json.loads(raw)
        return raw  # If valid, return as is
    except json.JSONDecodeError as e:
        st.warning(f"⚠️ Attempting to repair JSON: {e}")
        # Try basic fixes (e.g., adding missing commas)
        repaired = raw.replace("}{", "},{")  # Fix missing commas between objects
        repaired = re.sub(r",\s*}", "}", repaired)  # Remove trailing commas
        repaired = re.sub(r",\s*\]", "]", repaired)  # Remove trailing commas in arrays
        try:
            json.loads(repaired)  # Validate repaired JSON
            return repaired
        except json.JSONDecodeError:
            return raw  # If still invalid, return original


def _loads(raw: str, fallback):
    try:
        return json.loads(raw)
    except Exception as e:
        st.error(f"❌ JSON parsing error: {e}")
        return fallback


_warned = False
def _warn_once(msg: str) -> None:
    global _warned
    if not _warned:
        warnings.warn(msg)
        _warned = True


# ── Public API ─────────────────────────────────────────────────────────
def parse_extracted_questions(text: str) -> list[dict]:
    """
    Parse plain text output from the LLM into a list of questions and contexts.
    Fixes numbering and ensures correct order. Removes any leading number/label from the question text itself.
    """
    questions = []
    # Split blocks on double newlines
    blocks = [block.strip() for block in text.strip().split("\n\n") if block.strip()]
    # Remove empty or duplicate blocks
    seen = set()
    filtered_blocks = []
    for block in blocks:
        if block not in seen and block:
            filtered_blocks.append(block)
            seen.add(block)
    for idx, block in enumerate(filtered_blocks):
        q_line = None
        c_line = None
        for line in block.splitlines():
            if line.strip().startswith("Question:"):
                q_line = line.split("Question:",1)[1].strip()
            elif line.strip().startswith("Context:"):
                c_line = line.split("Context:",1)[1].strip()
        # Remove any leading number/label from the question text
        if q_line is not None:
            # Fix regex: match optional leading number, then optional ) or . or - or space
            q_line = re.sub(r"^(\d+)[\)\.\-\s]*", "", q_line)
        if q_line is not None and c_line is not None:
            questions.append({
                "id": len(questions) + 1,  # Always sequential, no skipping
                "question": q_line,
                "context": c_line,
            })
    return questions


# Add a function to clean up LLM output for context (remove preambles/conclusions)
def clean_enriched_context(text: str) -> str:
    # Remove common preambles and trailing sentences
    text = text.strip()
    # Remove 'Here is the enriched context:' and similar
    text = re.sub(r"^Here is the enriched context:.*?\n+", "", text, flags=re.I)
    text = re.sub(r"^The question is asking.*?\n+", "", text, flags=re.I)
    text = re.sub(r"^The code is.*?\n+", "", text, flags=re.I)
    # Remove trailing generic sentences
    text = re.sub(r"\n*The (output|answer|result) (is|will be):.*", "", text, flags=re.I)
    # Remove trailing 'This is question ...' or similar
    text = re.sub(r"\n*This is question.*", "", text, flags=re.I)
    # Remove 'The variables are:' etc. if not code
    text = re.sub(r"^The variables (are|used are):.*?\n+", "", text, flags=re.I)
    text = _tidy_context_markdown(text)
    return text.strip()


def _tidy_context_markdown(text: str) -> str:
    """Normalize whitespace, split inline statements, and wrap code blocks."""
    text = text.replace("\r\n", "\n").replace("\t", "    ")
    text = text.replace("\u00a0", " ")
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)

    # Break inline Python statements that often appear on one line after extraction
    text = re.sub(
        r"(?P<header>class\s+[A-Za-z_][\w]*(?:\([^\)]*\))?\s*:)\s*(?=def\s+)",
        lambda m: f"{m.group('header')}\n",
        text,
    )
    text = re.sub(r"(:|\))\s+(def\s+)", r"\1\n\2", text)
    text = re.sub(r"(\bself\.[^\n]+?)\s+(def\s+)", r"\1\n\2", text)
    text = re.sub(r"(;\s*)(def\s+)", r"\1\n\2", text)

    # Normalise numbered steps and bullets
    text = re.sub(r"^\s*(\d+)\)\s*", r"\1. ", text, flags=re.M)
    text = re.sub(r"^\s*[•‣]\s*", "- ", text, flags=re.M)

    # Wrap contiguous code-like lines in fenced code blocks if not already fenced
    text = _wrap_python_code_blocks(text)

    return text


def _wrap_python_code_blocks(text: str) -> str:
    lines = text.splitlines()
    result: list[str] = []
    in_code = False
    manual_fence = False

    def looks_like_code(line: str) -> bool:
        stripped = line.lstrip()
        if not stripped:
            return False
        if stripped.startswith(("```", "~~~")):
            return False
        code_starts = (
            "class ", "def ", "for ", "while ", "if ", "elif ", "else:",
            "try:", "except ", "with ", "return ", "import ", "from ",
        )
        return stripped.startswith(code_starts) or stripped.startswith("#") or line.startswith("    ")

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("```"):
            if in_code and manual_fence:
                result.append("```")
                in_code = False
                manual_fence = False
            else:
                in_code = True
            result.append(line)
            continue

        is_code_line = looks_like_code(line)

        if is_code_line and not in_code:
            result.append("```python")
            in_code = True
            manual_fence = True
        if not is_code_line and in_code and manual_fence:
            result.append("```")
            in_code = False
            manual_fence = False

        result.append(line)

    if in_code and manual_fence:
        result.append("```")

    return "\n".join(result)


def _extract_questions_from_text(source_text: str) -> list[dict]:
    """
    Extract questions, enrich context, and generate rubrics from a source text blob using the LLM.
    """
    llm = get_llm()

    pdf_text = source_text
    st.write(f"✂️ Characters sent to LLM (per call): {len(pdf_text):,}")

    # Pass-1: Extract questions
    try:
        response = llm.invoke(
            [
                {"role": "system", "content": EXTRACT_PROMPT},
                {"role": "user", "content": pdf_text},
            ]
        ).content
    except Exception as e:
        st.error(f"Error invoking LLM for question extraction: {e}")
        return []

    questions = parse_extracted_questions(response)
    if not questions:
        # Fallback: synthesize questions from instruction-only PDFs
        st.info("No explicit questions detected. Attempting to synthesize quiz questions from instructions…")
        try:
            fallback_resp = llm.invoke(
                [
                    {"role": "system", "content": FALLBACK_SYNTH_PROMPT},
                    {"role": "user", "content": pdf_text},
                ]
            ).content
            questions = parse_extracted_questions(fallback_resp)
        except Exception as e:
            st.error(f"Fallback synthesis failed: {e}")
            return []
        if not questions:
            st.warning("No questions could be synthesized from the PDF. Please verify the document contains assessable material.")
            return []

    st.success(f"✅ Pass-1: extracted {len(questions)} questions")

    # Pass-2: Enrich context
    enriched_questions = []
    for idx, q in enumerate(questions, start=1):
        q.setdefault("id", idx)  # Ensure every question has an ID
        try:
            enrich_prompt = ENRICH_PROMPT.format(
                pdf_text=pdf_text,
                question=q["question"],
                context=q["context"],
            )
            enriched_context = llm.invoke(
                [
                    {"role": "system", "content": "Return ONLY the enriched context as plain text. Do not add any preamble, conclusion, or any answer. Do NOT include any answer, solution, or worked example—just the context needed to answer the question. If the PDF contains an answer or solution, OMIT it from the context."},
                    {"role": "user", "content": enrich_prompt},
                ],
                temperature=0.2  # Slightly higher for more helpful completions
            ).content
            cleaned_context = clean_enriched_context(enriched_context)
            # Remove any lines that look like an answer (e.g., start with 'Answer:', 'Solution:', 'Worked Example:', or are long and not code)
            # BUT: Never remove lines labeled as 'Sample Output', 'Expected Output', or similar (these must be shown to students)
            # Improved: Avoid context repetition and always include the original context at the top if not present
            cleaned_context_lines = []
            seen_lines = set()
            # Always start with the original context if not empty
            orig_context = q.get("context", "").strip()
            if orig_context:
                for line in orig_context.splitlines():
                    l = line.strip()
                    if l and l not in seen_lines:
                        cleaned_context_lines.append(l)
                        seen_lines.add(l)
            # Now add enriched lines, skipping duplicates and unwanted lines
            for line in cleaned_context.splitlines():
                lstr = line.strip().lower()
                l = line.strip()
                if not l or l in seen_lines:
                    continue
                if lstr.startswith(("answer:", "solution:", "worked example:")):
                    continue  # skip these
                if lstr.startswith(("the answer is", "in summary", "to solve this", "therefore", "thus", "correct answer", "final answer")):
                    continue  # skip these
                if len(l.split()) > 8 and not any(x in l for x in ["=", ":", "print", "input", "for ", "while ", "if ", "def ", "class "]):
                    continue  # skip likely answer sentences
                cleaned_context_lines.append(line)
                seen_lines.add(l)
            cleaned_context = "\n".join(cleaned_context_lines)
            # If context is still too short, try to extract relevant lines from PDF
            if len(cleaned_context) < 40:
                q_text = q["question"][:40]
                pdf_lines = pdf_text.splitlines()
                relevant_lines = [line for line in pdf_lines if q_text.split()[0] in line or any(x in line for x in ["=", "print", ":", "+", "input", "output", "Sample Output", "Expected Output"])]
                for line in relevant_lines[:6]:
                    l = line.strip()
                    if l and l not in seen_lines:
                        cleaned_context += "\n" + line
                        seen_lines.add(l)
            q["context"] = cleaned_context.strip()
            enriched_questions.append(q)
        except Exception as e:
            st.warning(f"⚠️ Error enriching context for Q{idx}: {e}")
            enriched_questions.append(q)  # Add the question without enrichment
    st.success("✅ Pass-2: context enriched")

    # Pass-3: Generate rubrics
    for q in enriched_questions:
        try:
            rubric_prompt = RUBRIC_PROMPT.format(
                question=q["question"],
                context=q["context"],
            )
            rubric_response = llm.invoke(
                [
                    {"role": "system", "content": "Return the marking rubric as plain text."},
                    {"role": "user", "content": rubric_prompt},
                ]
            ).content
            q["answer"] = rubric_response.strip()
        except Exception as e:
            st.warning(f"⚠️ Error generating rubric for Q{q['id']}: {e}")
            q["answer"] = "Rubric generation failed."
    st.success("✅ Pass-3: rubrics generated")
    return enriched_questions


def extract_questions_from_pdf(pdf_path: str) -> list[dict]:
    """Backwards-compatible PDF entrypoint."""
    try:
        return _extract_questions_from_text(_pdf_to_text(pdf_path))
    except Exception as e:
        st.error(f"Error extracting text from PDF: {e}")
        return []


def extract_questions_from_source(source_path: str) -> list[dict]:
    """Dispatch PDF, image, text, and code uploads into the existing three-pass pipeline."""
    try:
        return _extract_questions_from_text(_source_to_text(source_path))
    except Exception as e:
        st.error(f"Error extracting text from file: {e}")
        return []
