"""Curated lifecycle checklists ("guides").

These answer broad, navigational questions ("I'm a new F-1 student, what do I
need to cover?") that retrieval-of-a-single-fact cannot. A guide is curated,
cited content — not model guesswork — so it upholds the same citation discipline
as the fact engine: every rule-based item links to a primary source, and general
logistics items are clearly labeled as guidance to confirm with a DSO.

Guides live as editable JSON in the guides/ directory.
"""
from __future__ import annotations

import glob
import json
import os
from typing import Any, Dict, List, Optional, Tuple

from common import paths

GUIDES_DIR = os.path.join(paths.ROOT, "guides")

# A question is treated as "navigational" only if it contains one of these.
# This keeps specific factual questions ("does OPT get FICA taxed") on the
# fact-retrieval path instead of returning a whole checklist.
_OVERVIEW_TRIGGERS = [
    "what do i need", "what all", "what should i do", "what do i have to",
    "getting started", "get started", "get settled", "settling", "settle in",
    "first steps", "first thing", "where do i start", "checklist", "orientation",
    "new student", "just arrived", "just got here", "next steps", "next step",
    "guide me", "help me get", "new to the us", "new to the u.s", "new here",
    "cover as a", "do i need to cover", "everything i need",
]

_STAGE_KEYWORDS = {
    "graduating": [
        "graduat", "final year", "last semester", "about to finish", "finishing",
        "next steps", "next step", "post-completion", "after i finish", "after graduation",
        "job after", "opt after", "leaving school", "done with school",
    ],
    "mid_year": [
        "major", "minor", "change major", "changing major", "add major", "drop major",
        "switch major", "transfer", "travel signature", "new i-20", "new i20",
        "mid-year", "midyear", "already here", "internship", "second major",
    ],
    "new_student": [
        "new student", "just arrived", "just got here", "getting started", "get settled",
        "settle", "orientation", "first weeks", "first semester", "new here", "new to",
    ],
}

_cache: Dict[str, Dict[str, Any]] = {}


def _load_guides() -> Dict[str, Dict[str, Any]]:
    if _cache:
        return _cache
    for path in sorted(glob.glob(os.path.join(GUIDES_DIR, "*.json"))):
        with open(path, "r", encoding="utf-8") as fh:
            g = json.load(fh)
        _cache[g["id"]] = g
    return _cache


def match_guide(question: str) -> Optional[Dict[str, Any]]:
    """Return the best-matching guide, or None if this isn't a navigational question."""
    text = (question or "").lower()
    if not any(trigger in text for trigger in _OVERVIEW_TRIGGERS):
        return None

    guides = _load_guides()
    # Pick the lifecycle stage by keyword; default to new_student.
    for stage in ("graduating", "mid_year", "new_student"):
        if any(kw in text for kw in _STAGE_KEYWORDS[stage]) and stage in guides:
            return guides[stage]
    return guides.get("new_student")


def render_guide(guide: Dict[str, Any]) -> Tuple[str, List[str]]:
    """Render a guide to (markdown, ordered_unique_source_ids)."""
    ordered_sources: List[str] = []

    def cite_num(source_id: str) -> int:
        if source_id not in ordered_sources:
            ordered_sources.append(source_id)
        return ordered_sources.index(source_id) + 1

    lines = ["## {}".format(guide["title"]), "", guide.get("intro", ""), ""]
    for section in guide["sections"]:
        lines.append("### {}".format(section["category"]))
        for item in section["items"]:
            sid = item.get("source_id")
            if sid:
                lines.append("- ✅ {} [{}]".format(item["text"], cite_num(sid)))
            else:
                lines.append("- ✅ {}  \n  _general guidance — confirm with your DSO_".format(item["text"]))
        lines.append("")
    return "\n".join(lines).strip(), ordered_sources


def reset_cache() -> None:
    _cache.clear()
