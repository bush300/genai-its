# quick_test.py   ── place in project root (genai_its/)
"""
One‑shot smoke‑test for whichever LLM provider is active.

• Relies on   1.3_models/llm_provider.py
• Works with either provider ('groq' or 'hf') without edits.
"""

import os, sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent / "1.3_models"))
# --- ensure 1.3_models is importable -----------------------------
ROOT = pathlib.Path(__file__).resolve().parent
MODELS_DIR = ROOT / "1.3_models"
if str(MODELS_DIR) not in sys.path:
    sys.path.insert(0, str(MODELS_DIR))

from llm_provider import get_llm  # your file – unchanged

# -----------------------------------------------------------------
# Helper: figure out which backend we actually got
def _detect_backend(llm) -> str:
    cls = llm.__class__.__name__.lower()
    if "groq" in cls:
        return "groq"
    if "huggingface" in cls or "hf" in cls:
        return "huggingface‑inference‑api"
    return cls

# -----------------------------------------------------------------
llm   = get_llm()                 # uses $LLM_PROVIDER env‑var (falls back to groq)
prov  = _detect_backend(llm)

print(f"✅ Provider resolved → {prov}  ({llm.__class__.__name__})")
print("🔹 Sending test prompt…")

reply = get_llm().invoke("Quick test via quick_test.py")
print(reply[:120])                 # reply is already a string
