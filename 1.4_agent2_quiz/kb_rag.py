from pathlib import Path
from typing import List, Tuple
import json

from langchain_community.vectorstores import FAISS
from .document_loader import LocalHuggingFaceEmbeddings

BASE = Path(__file__).resolve().parents[2]
VECTORS_DIR = BASE / "data" / "knowledgebase_vectors"


def _ensure_vectors_dir():
    VECTORS_DIR.mkdir(parents=True, exist_ok=True)


def _chunk_text(text: str, chunk_size: int = 800, overlap: int = 200) -> List[str]:
    # naive whitespace-based chunking
    words = text.split()
    chunks = []
    i = 0
    while i < len(words):
        chunk = " ".join(words[i:i+chunk_size])
        chunks.append(chunk)
        i += chunk_size - overlap
    return chunks


def build_index_from_firestore_kb(subject: str, week: str) -> None:
    """Read KB entries from Firestore (same doc used by the app), chunk their content,
    compute embeddings using LocalHuggingFaceEmbeddings and store a FAISS index on disk
    at data/knowledgebase_vectors/{subject}_{week}.
    Also write metadata.json with per-chunk {id, source_name, uploaded_at}.
    """
    from firebase_admin import firestore, credentials, initialize_app
    import firebase_admin
    if not firebase_admin._apps:
        cred = credentials.Certificate(dict(__import__('streamlit').secrets['FIREBASE']))
        initialize_app(cred)
    db = firestore.client()

    doc_id = f"{subject}_{week}_kb"
    doc = db.collection('knowledgebase').document(doc_id).get()
    if not doc.exists:
        # Nothing to build
        return
    kb = doc.to_dict().get('knowledgebase', [])
    texts = []
    metadata = []
    for entry in (kb or []):
        if isinstance(entry, dict):
            name = entry.get('name', 'unknown')
            content = entry.get('content') or ''
            uploaded_at = entry.get('uploaded_at')
            if content and content.strip():
                chunks = _chunk_text(content)
                for idx, c in enumerate(chunks):
                    texts.append(c)
                    metadata.append({
                        'id': f"{name}#chunk{idx}",
                        'source': name,
                        'uploaded_at': uploaded_at,
                    })
    if not texts:
        return

    _ensure_vectors_dir()
    target = VECTORS_DIR / f"{subject}_{week}"
    target.mkdir(parents=True, exist_ok=True)

    embs = LocalHuggingFaceEmbeddings()
    faiss_index = FAISS.from_texts(texts, embs, metadatas=metadata)
    faiss_index.save_local(str(target))

    # Write metadata file separately for quick access
    with open(target / 'metadata.json', 'w', encoding='utf-8') as f:
        json.dump(metadata, f, ensure_ascii=False, indent=2)


def query_kb(subject: str, week: str, query: str, top_k: int = 3) -> List[Tuple[str, str]]:
    """Return top_k tuples (citation_tag, chunk_text) for the given query.
    Citation tag format: [KB:source#chunk_idx] where source is the filename.
    """
    target = VECTORS_DIR / f"{subject}_{week}"
    if not target.exists():
        return []
    embs = LocalHuggingFaceEmbeddings()
    faiss_index = FAISS.load_local(str(target), embs, allow_dangerous_deserialization=True)
    results = faiss_index.similarity_search_with_score(query, k=top_k)
    output = []
    for doc, score in results:
        # doc.metadata expected to contain 'id' and 'source'
        meta = doc.metadata or {}
        cid = meta.get('id') or meta.get('source', 'kb')
        tag = f"[KB:{cid}]"
        output.append((tag, doc.page_content))
    return output
