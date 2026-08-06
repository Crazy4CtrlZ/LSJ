"""Person A tests: all four corpus formats parse into sectioned, citation-ready chunks."""
from rag.ingest import parse_corpus


def test_all_four_formats_parse():
    chunks, store = parse_corpus()
    assert len(store) == 16, f"expected 16 documents, parsed {len(store)}"
    assert len(chunks) >= 100

    by_ext_probe = {
        "POL-001": "md", "POL-009": "html", "POL-011": "txt", "POL-007": "pdf",
    }
    for doc_id in by_ext_probe:
        assert doc_id in store, f"{doc_id} missing from store"
        assert len(store[doc_id]["sections"]) >= 4, f"{doc_id}: too few sections"


def test_citation_metadata_present():
    chunks, _ = parse_corpus()
    for c in chunks[:50]:
        m = c["metadata"]
        assert m["doc_id"].startswith("POL-")
        assert m["section"] and m["title"]


def test_known_facts_land_in_expected_sections():
    _, store = parse_corpus()
    pto = store["POL-001"]["sections"]
    joined = " ".join(s["text"] for s in pto.values())
    assert "10 business days" in joined  # the notice rule Demo A depends on
    remote = " ".join(s["text"] for s in store["POL-002"]["sections"].values())
    assert "20 business days" in remote  # the cap Demo B depends on


def test_chunk_ids_deterministic():
    a, _ = parse_corpus()
    b, _ = parse_corpus()
    assert [c["id"] for c in a] == [c["id"] for c in b]
