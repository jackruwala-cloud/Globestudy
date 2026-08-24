"""Build the retrievable knowledge base from the curated primary sources.

Usage:
    python -m ingestion.build_index

This (1) chunks every source document by section, (2) writes an inspectable
data/chunks.json, and (3) if the configured backend is Chroma, populates a
local Chroma collection. The default tfidf backend needs no extra build step
beyond chunks.json.
"""
from __future__ import annotations

import sys

from common import config
from ingestion import chunker


def build_chroma(chunks) -> None:
    try:
        import chromadb  # type: ignore
    except ImportError:
        print("[build_index] chromadb not installed; skipping Chroma build.")
        print("               Install with `pip install chromadb` or use backend: tfidf.")
        return

    from common import paths

    client = chromadb.PersistentClient(path=paths.CHROMA_DIR)
    # Rebuild cleanly each time.
    try:
        client.delete_collection("primary_sources")
    except Exception:
        pass
    collection = client.get_or_create_collection("primary_sources")
    collection.add(
        ids=[c["id"] for c in chunks],
        documents=[c["text"] for c in chunks],
        metadatas=[
            {
                "source_id": c["source_id"],
                "source_title": c["source_title"],
                "source_url": c["source_url"],
                "section": c["section"],
                "category": c["category"],
                "retrieved_date": c["retrieved_date"],
            }
            for c in chunks
        ],
    )
    print("[build_index] Chroma collection 'primary_sources' built with {} chunks.".format(len(chunks)))


def main() -> int:
    cfg = config.get_config()

    # ENFORCE the official-source policy before building anything.
    from sources.source_policy import validate_sources, ALLOWED_GOV_DOMAINS, ALLOWED_TLDS

    manifest = chunker.load_manifest()
    ok, violations = validate_sources(manifest["sources"])
    if violations:
        print("[build_index] REFUSING TO BUILD — non-official source(s) found:")
        for s in violations:
            print("   ✗ {}  ->  {}".format(s.get("id"), s.get("url")))
        print("   Allowed: {} domains + {} (universities).".format(
            ", ".join(ALLOWED_GOV_DOMAINS), ", ".join(ALLOWED_TLDS)))
        print("   Fix or remove these sources in sources/manifest.json, or update")
        print("   sources/source_policy.py if a new official domain is intended.")
        return 1
    print("[build_index] Source policy OK — all {} sources are official (.gov/.edu).".format(len(ok)))

    chunks = chunker.build_chunks()
    chunker.write_chunks(chunks)
    print("[build_index] Wrote {} chunks to data/chunks.json".format(len(chunks)))

    by_source: dict = {}
    for c in chunks:
        by_source[c["source_id"]] = by_source.get(c["source_id"], 0) + 1
    for sid, count in by_source.items():
        print("             {:<32} {} chunks".format(sid, count))

    backend = cfg["retrieval"]["backend"]
    if backend == "chroma":
        build_chroma(chunks)
    else:
        print("[build_index] Backend = tfidf (pure Python). No further build needed.")

    print("[build_index] Done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
