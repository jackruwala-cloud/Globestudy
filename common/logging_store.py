"""Append-only JSONL logs for Q&A activity and user feedback.

Kept deliberately simple and inspectable (plain JSONL, one record per line) so
the admin view and any later analysis can read them without a database.
"""
from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from typing import Any, Dict, List

from common import paths

_lock = threading.Lock()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _append(path: str, record: Dict[str, Any]) -> None:
    paths.ensure_data_dir()
    line = json.dumps(record, ensure_ascii=False)
    with _lock:
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")


def _read(path: str) -> List[Dict[str, Any]]:
    records: List[Dict[str, Any]] = []
    try:
        with open(path, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    except FileNotFoundError:
        return []
    return records


def log_qa(record: Dict[str, Any]) -> None:
    record.setdefault("ts", _now_iso())
    _append(paths.QA_LOG_PATH, record)


def log_feedback(record: Dict[str, Any]) -> None:
    record.setdefault("ts", _now_iso())
    _append(paths.FEEDBACK_LOG_PATH, record)


def read_qa_log() -> List[Dict[str, Any]]:
    return _read(paths.QA_LOG_PATH)


def read_feedback() -> List[Dict[str, Any]]:
    return _read(paths.FEEDBACK_LOG_PATH)
