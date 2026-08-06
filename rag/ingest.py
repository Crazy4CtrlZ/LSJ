"""Person A — ingestion pipeline.

Parses the policy corpus (4 source formats: Markdown, HTML, PDF, TXT — rubric requires >=2),
splits it into heading-aware chunks (content-aware chunking, per the Adopting AI course),
embeds them with all-MiniLM-L6-v2 (ONNX build shipped via ChromaDB — local + free), and
persists a ChromaDB index plus a sections.json store used for exact-section citations.

Deterministic by construction: stable chunk ids (doc_id#section#part), no randomness.
Run:  python -m rag.ingest
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app import config  # noqa: E402

WINDOW_WORDS = 350   # fallback token-window size (words) for oversized sections
OVERLAP_WORDS = 60   # overlap so ideas straddling a boundary appear in both chunks


# ---------------------------------------------------------------- parsers
def _front_matter(text: str) -> tuple[dict, str]:
    m = re.match(r"^---\n(.*?)\n---\n(.*)$", text, re.S)
    if not m:
        return {}, text
    meta = dict(re.findall(r"^(\w+):\s*(.+)$", m.group(1), re.M))
    return meta, m.group(2)


def parse_markdown(path: Path) -> tuple[dict, list[dict]]:
    meta, body = _front_matter(path.read_text(encoding="utf-8"))
    sections, current, buf = [], ("0", "Preamble"), []

    def flush():
        text = "\n".join(buf).strip()
        if text:
            sections.append({"section": current[0], "section_title": current[1], "text": text})

    for line in body.splitlines():
        m = re.match(r"^#{2,3}\s+(\d+(?:\.\d+)?)\.?\s+(.*)$", line)
        if m:
            flush(); buf = []
            current = (m.group(1), m.group(2).strip())
        elif line.startswith("# "):
            continue  # document title line
        else:
            buf.append(line)
    flush()
    return meta, sections


def parse_html(path: Path) -> tuple[dict, list[dict]]:
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(path.read_text(encoding="utf-8"), "html.parser")
    meta = {m.get("name"): m.get("content") for m in soup.find_all("meta") if m.get("name")}
    if soup.title and soup.title.string:
        t = re.sub(r"^POL-\d+\s+—\s+", "", soup.title.string.split("|")[0]).strip()
        meta.setdefault("title", t)
    sections = []
    for h in soup.find_all(["h2", "h3"]):
        m = re.match(r"^(\d+(?:\.\d+)?)\.?\s+(.*)$", h.get_text(strip=True))
        if not m:
            continue
        parts = []
        for sib in h.find_next_siblings():
            if sib.name in ("h2", "h3"):
                break
            parts.append(sib.get_text(" ", strip=True))
        text = "\n".join(p for p in parts if p).strip()
        if text:
            sections.append({"section": m.group(1), "section_title": m.group(2).strip(), "text": text})
    return meta, sections


def _numbered_sections(lines: list[str]) -> list[dict]:
    """Shared splitter for TXT and PDF text: sections start at lines like '3. TITLE' or '3.1 Title'."""
    sections, current, buf = [], None, []

    def flush():
        if current and buf:
            text = "\n".join(buf).strip()
            if text:
                sections.append({"section": current[0], "section_title": current[1], "text": text})

    for line in lines:
        m = re.match(r"^(\d+(?:\.\d+)?)\.?\s+([A-Z].{2,80})$", line.strip())
        # heading heuristic: short line, starts with a number then a capitalised title
        if m and len(line.strip()) < 90 and not line.strip().endswith((".", ";", ",")):
            flush(); buf = []
            current = (m.group(1), m.group(2).strip())
        elif current:
            buf.append(line)
    flush()
    return sections


def parse_txt(path: Path) -> tuple[dict, list[dict]]:
    lines = path.read_text(encoding="utf-8").splitlines()
    meta: dict = {}
    for line in lines[:6]:
        m = re.search(r"Doc ID:\s*(POL-\d+)", line)
        if m:
            meta["doc_id"] = m.group(1)
        m = re.search(r"Category:\s*([^|]+)", line)
        if m:
            meta["category"] = m.group(1).strip()
        m = re.search(r"Version\s*([\d.]+)", line)
        if m:
            meta["version"] = m.group(1)
    if lines:
        meta.setdefault("title", lines[0].split("—")[0].strip().title())
    return meta, _numbered_sections(lines)


def parse_pdf(path: Path) -> tuple[dict, list[dict]]:
    from pypdf import PdfReader

    text = "\n".join((page.extract_text() or "") for page in PdfReader(str(path)).pages)
    lines = text.splitlines()
    meta: dict = {}
    for line in lines[:8]:
        m = re.search(r"Doc ID:\s*(POL-\d+)", line)
        if m:
            meta["doc_id"] = m.group(1)
        m = re.search(r"Category:\s*(\w[\w ]*)", line)
        if m:
            meta.setdefault("category", m.group(1).strip())
    if lines:
        meta.setdefault("title", re.sub(r"^LSJ, Inc\.\s*—\s*", "", lines[0]).strip())
    return meta, _numbered_sections(lines)


PARSERS = {".md": parse_markdown, ".html": parse_html, ".txt": parse_txt, ".pdf": parse_pdf}


# ---------------------------------------------------------------- chunking
def chunk_sections(doc_id: str, title: str, category: str, sections: list[dict]) -> list[dict]:
    """Heading-aware chunks; token-window fallback with overlap for oversized sections."""
    chunks = []
    for sec in sections:
        words = sec["text"].split()
        if len(words) <= WINDOW_WORDS:
            windows = [sec["text"]]
        else:
            windows, start = [], 0
            while start < len(words):
                windows.append(" ".join(words[start : start + WINDOW_WORDS]))
                start += WINDOW_WORDS - OVERLAP_WORDS
        for i, w in enumerate(windows):
            chunks.append(
                {
                    "id": f"{doc_id}#{sec['section']}#{i}",
                    "text": w,
                    "metadata": {
                        "doc_id": doc_id,
                        "title": title,
                        "category": category,
                        "section": sec["section"],
                        "section_title": sec["section_title"],
                    },
                }
            )
    return chunks


def parse_corpus(corpus_dir: Path | None = None) -> tuple[list[dict], dict]:
    """Returns (all_chunks, sections_store). Pure parsing — no embedding, no network."""
    corpus_dir = corpus_dir or config.CORPUS_DIR
    all_chunks: list[dict] = []
    store: dict[str, dict] = {}
    for path in sorted(corpus_dir.iterdir()):
        if path.suffix not in PARSERS or path.name == "README.md":
            continue
        meta, sections = PARSERS[path.suffix](path)
        doc_id = meta.get("doc_id", path.stem)
        title = meta.get("title", path.stem)
        category = meta.get("category", "General")
        all_chunks += chunk_sections(doc_id, title, category, sections)
        store[doc_id] = {
            "title": title,
            "category": category,
            "version": meta.get("version", ""),
            "last_updated": meta.get("last_updated", ""),
            "source_file": path.name,
            "sections": {s["section"]: {"section_title": s["section_title"], "text": s["text"]} for s in sections},
        }
    return all_chunks, store


def build_index(corpus_dir: Path | None = None, index_dir: Path | None = None) -> int:
    import chromadb

    index_dir = index_dir or config.INDEX_DIR
    index_dir.mkdir(parents=True, exist_ok=True)
    chunks, store = parse_corpus(corpus_dir)
    (index_dir / "sections.json").write_text(json.dumps(store, ensure_ascii=False, indent=1), encoding="utf-8")

    client = chromadb.PersistentClient(path=str(index_dir))
    try:
        client.delete_collection(config.COLLECTION_NAME)
    except Exception:
        pass
    col = client.create_collection(config.COLLECTION_NAME, metadata={"hnsw:space": "cosine"})
    B = 64
    for i in range(0, len(chunks), B):
        batch = chunks[i : i + B]
        col.add(
            ids=[c["id"] for c in batch],
            documents=[f"{c['metadata']['title']} — {c['metadata']['section_title']}\n{c['text']}" for c in batch],
            metadatas=[c["metadata"] for c in batch],
        )
    n = col.count()
    # Lightweight index metadata so the runtime can report size without loading
    # chromadb (keeps the 512 MB Render instance memory-light — see design doc §2).
    (index_dir / "meta.json").write_text(json.dumps({"chunks": n}), encoding="utf-8")
    return n


if __name__ == "__main__":
    n = build_index()
    print(f"Indexed {n} chunks from {config.CORPUS_DIR} into {config.INDEX_DIR}")
