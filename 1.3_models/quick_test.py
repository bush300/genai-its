"""Manual smoke test for the configured CyberNexa LLM provider.

Run manually from the project root:

    python 1.3_models/quick_test.py

The test is protected by a main guard so pytest can import this file
without sending a real LLM request.
"""

from __future__ import annotations

import pathlib
import sys
from typing import Any


MODELS_DIR = pathlib.Path(__file__).resolve().parent

if str(MODELS_DIR) not in sys.path:
    sys.path.insert(0, str(MODELS_DIR))

from llm_provider import get_llm


def _unwrap_llm(llm: Any) -> Any:
    """Return the underlying provider when governance wraps the model."""
    return getattr(llm, "_llm", llm)


def _detect_backend(llm: Any) -> str:
    """Return a readable provider name."""
    raw_llm = _unwrap_llm(llm)
    class_name = raw_llm.__class__.__name__.lower()

    if "groq" in class_name:
        return "groq"

    if "ollama" in class_name:
        return "ollama"

    if "openai" in class_name:
        return "openai"

    return class_name


def _response_text(response: Any) -> str:
    """Extract text from either a LangChain AIMessage or a plain string."""
    content = getattr(response, "content", response)
    return str(content)


def main() -> int:
    llm = get_llm()
    provider = _detect_backend(llm)

    print(
        f"[OK] Provider resolved -> {provider} "
        f"({llm.__class__.__name__})"
    )
    print("[INFO] Sending test prompt...")

    response = llm.invoke("Reply with: CyberNexa provider test passed.")
    text = _response_text(response)

    if not text.strip():
        print("[ERROR] The provider returned an empty response.")
        return 1

    print(text[:200])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())