"""Person A — retrieval layer. Backs the two RAG-facing MCP tools (contract v1.0)."""
from __future__ import annotations

import json
import sys
from functools import lru_cache
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app import config  # noqa: E402


def index_ready() -> bool:
    return (config.INDEX_DIR / "sections.json").exists()


@lru_cache(maxsize=1)
def _collection():
    import chromadb

    client = chromadb.PersistentClient(path=str(config.INDEX_DIR))
    return client.get_collection(config.COLLECTION_NAME)


@lru_cache(maxsize=1)
def _store() -> dict:
    return json.loads((config.INDEX_DIR / "sections.json").read_text(encoding="utf-8"))


def index_size() -> int:
    try:
        return _collection().count()
    except Exception:
        return 0


def search(query: str, k: int | None = None, doc_filter: str | None = None,
           category_filter: str | None = None) -> list[dict]:
    """Top-k semantic search. Returns contract-shaped results (may be empty — that's a valid answer)."""
    k = max(1, min(int(k or config.RETRIEVAL_K), 10))
    where: dict | None = None
    clauses = []
    if doc_filter:
        clauses.append({"doc_id": doc_filter})
    if category_filter:
        clauses.append({"category": category_filter})
    if len(clauses) == 1:
        where = clauses[0]
    elif clauses:
        where = {"$and": clauses}

    res = _collection().query(query_texts=[query], n_results=k, where=where)
    out = []
    for doc, meta, dist in zip(res["documents"][0], res["metadatas"][0], res["distances"][0]):
        out.append(
            {
                "doc_id": meta["doc_id"],
                "title": meta["title"],
                "section": meta["section"],
                "section_title": meta["section_title"],
                "snippet": doc[:800],
                "score": round(max(0.0, 1.0 - dist), 4),  # cosine distance -> similarity
            }
        )
    return out


def get_section(doc_id: str, section: str) -> dict | None:
    """Exact section fetch; '3' also collects all 3.x subsections (contract §2)."""
    doc = _store().get(doc_id)
    if not doc:
        return None
    secs = doc["sections"]
    if section in secs:
        s = secs[section]
        text, title = s["text"], s["section_title"]
    else:
        parts = [(k, v) for k, v in secs.items() if k.startswith(section + ".")]
        if not parts:
            return None
        parts.sort(key=lambda kv: [int(x) for x in kv[0].split(".")])
        text = "\n\n".join(f"{k} {v['section_title']}\n{v['text']}" for k, v in parts)
        title = f"Sections {section}.x"
    return {
        "doc_id": doc_id,
        "title": doc["title"],
        "section": section,
        "section_title": title,
        "text": text,
        "version": doc.get("version", ""),
        "last_updated": doc.get("last_updated", ""),
    }
