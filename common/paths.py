"""Central path definitions for the app. Everything resolves off the repo root."""
from __future__ import annotations

import os

# common/ -> repo root
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

SOURCES_DIR = os.path.join(ROOT, "sources")
DOCUMENTS_DIR = os.path.join(SOURCES_DIR, "documents")
MANIFEST_PATH = os.path.join(SOURCES_DIR, "manifest.json")
FRESHNESS_STATE_PATH = os.path.join(SOURCES_DIR, "freshness_state.json")

# Committed, curated reference data (not runtime-generated).
REFERENCE_DIR = os.path.join(ROOT, "reference")
UNIVERSITIES_PATH = os.path.join(REFERENCE_DIR, "universities.json")
TAX_TREATY_PATH = os.path.join(REFERENCE_DIR, "tax_treaty_countries.json")

DATA_DIR = os.path.join(ROOT, "data")
CHUNKS_PATH = os.path.join(DATA_DIR, "chunks.json")
CHROMA_DIR = os.path.join(DATA_DIR, "chroma")

QA_LOG_PATH = os.path.join(DATA_DIR, "qa_log.jsonl")
FEEDBACK_LOG_PATH = os.path.join(DATA_DIR, "feedback.jsonl")

CONFIG_PATH = os.path.join(ROOT, "config.yaml")
CONFIG_EXAMPLE_PATH = os.path.join(ROOT, "config.example.yaml")


def ensure_data_dir() -> None:
    os.makedirs(DATA_DIR, exist_ok=True)
