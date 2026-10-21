"""
Vector‑store query helper that uses Groq‑hosted Llama‑3 (or any other Groq
model) for answer generation.

Requirements:
    • GROQ_API_KEY set in the env (see .env)
    • data/vectorstore/  generated via document_loader.load_and_embed_pdf()
"""

from langchain.vectorstores import FAISS
from langchain.chains import RetrievalQA

from groq_llm import get_groq_llm
from document_loader import LocalHuggingFaceEmbeddings


def run_agent_query(query: str, model: str = "llama3-70b-8192") -> str:
    # --- open the vector‑store -------------------------------------------------
    embeddings = LocalHuggingFaceEmbeddings()
    vectordb = FAISS.load_local(
        "data/vectorstore/",
        embeddings,
        allow_dangerous_deserialization=True,
    )

    retriever = vectordb.as_retriever(search_type="similarity", k=3)

    # --- Groq LLM --------------------------------------------------------------
    qa_chain = RetrievalQA.from_chain_type(
        llm=get_groq_llm(model=model),   # ← Groq everywhere
        chain_type="stuff",
        retriever=retriever,
    )
    return qa_chain.run(query)
