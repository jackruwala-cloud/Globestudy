"""Chunk primary-source documents by section (Markdown '## ' headers).

We deliberately chunk by topic/section rather than fixed character counts so
that every chunk is a self-contained, citable unit. Each chunk carries its
exact source URL, publisher, section title, and retrieval date so citations can
always be traced back to the authoritative primary source.
"""
from __future__ import annotations

import json
import os
import re
from typing import Any, Dict, List

from common import paths


def _slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug or "section"


def _split_sections(markdown: str) -> List[Dict[str, str]]:
    """Split on level-2 headers. Text before the first '## ' becomes 'Overview'."""
    lines = markdown.splitlines()
    sections: List[Dict[str, str]] = []
    current_title = "Overview"
    current_body: List[str] = []

    for line in lines:
        if line.startswith("# ") and not sections and not current_body:
            # Document H1 title — skip as a section header, it's the doc title.
            continue
        if line.startswith("## "):
            if current_body and "".join(current_body).strip():
                sections.append({"title": current_title, "body": "\n".join(current_body).strip()})
            current_title = line[3:].strip()
            current_body = []
        else:
            current_body.append(line)

    if current_body and "".join(current_body).strip():
        sections.append({"title": current_title, "body": "\n".join(current_body).strip()})
    return sections


def load_manifest() -> Dict[str, Any]:
    with open(paths.MANIFEST_PATH, "r", encoding="utf-8") as fh:
        return json.load(fh)


def build_chunks() -> List[Dict[str, Any]]:
    manifest = load_manifest()
    chunks: List[Dict[str, Any]] = []

    for src in manifest["sources"]:
        doc_path = os.path.join(paths.SOURCES_DIR, src["file"])
        with open(doc_path, "r", encoding="utf-8") as fh:
            markdown = fh.read()

        for section in _split_sections(markdown):
            chunk_id = "{}#{}".format(src["id"], _slugify(section["title"]))
            chunks.append(
                {
                    "id": chunk_id,
                    "source_id": src["id"],
                    "source_title": src["title"],
                    "source_url": src["url"],
                    "publisher": src["publisher"],
                    "category": src["category"],
                    "retrieved_date": src["retrieved_date"],
                    "section": section["title"],
                    "text": section["body"],
                }
            )
    return chunks


def write_chunks(chunks: List[Dict[str, Any]]) -> None:
    paths.ensure_data_dir()
    with open(paths.CHUNKS_PATH, "w", encoding="utf-8") as fh:
        json.dump(chunks, fh, ensure_ascii=False, indent=2)


def load_chunks() -> List[Dict[str, Any]]:
    with open(paths.CHUNKS_PATH, "r", encoding="utf-8") as fh:
        return json.load(fh)
