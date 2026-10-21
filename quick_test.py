# quick smoke test for whichever LLM_PROVIDER is active - run from repo root
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "1.3_models"))

from llm_provider import get_llm

llm = get_llm()
print("Assistant:", llm.invoke("Say hello as JSON").content)
