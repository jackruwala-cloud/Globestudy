"""Internal admin view.

Run from the repo root:
    streamlit run admin/app.py

Surfaces three things for review:
  1. Coverage gaps  — questions with no source or low confidence (KB to expand).
  2. Feedback       — negative/positive feedback to review.
  3. Source freshness — which primary sources are stale or have changed.

This is intentionally plain and internal-facing.
"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st

from common import logging_store, paths
from ingestion.chunker import load_manifest

st.set_page_config(page_title="Advisor Admin", page_icon="🛠️", layout="wide")
st.title("🛠️ Advisor Admin — Review & Gaps")
st.caption("Internal view. Where the knowledge base is thin, where users disagreed, and which sources need re-checking.")


def _load_freshness() -> dict:
    try:
        with open(paths.FRESHNESS_STATE_PATH, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"sources": {}}


qa_log = logging_store.read_qa_log()
feedback = logging_store.read_feedback()

# ----------------------------- Top metrics -----------------------------
total = len(qa_log)
answered = sum(1 for r in qa_log if r.get("answered"))
no_source = total - answered
low_conf = sum(1 for r in qa_log if r.get("confidence") in ("none", "medium"))
downs = sum(1 for f in feedback if f.get("vote") == "down")

c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Questions asked", total)
c2.metric("Answered", answered)
c3.metric("No source found", no_source)
c4.metric("Low/medium conf.", low_conf)
c5.metric("👎 feedback", downs)

tab_gaps, tab_feedback, tab_fresh = st.tabs(["🕳️ Coverage gaps", "💬 Feedback", "📅 Source freshness"])

# ----------------------------- Coverage gaps -----------------------------
with tab_gaps:
    st.subheader("No verified source found")
    st.caption("These are the clearest gaps — questions the knowledge base could not answer. "
               "The 'near top score' hints how close the best match was: higher = a stronger candidate for a new source.")
    gaps = [r for r in qa_log if not r.get("answered")]
    gaps.sort(key=lambda r: r.get("top_score", 0), reverse=True)
    if gaps:
        st.dataframe(
            [
                {
                    "when": r.get("ts", "")[:19],
                    "question": r.get("question", ""),
                    "near top score": round(r.get("top_score", 0), 3),
                    "risk": r.get("risk_level", ""),
                }
                for r in gaps
            ],
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.success("No unanswered questions logged yet.")

    st.subheader("Answered, but low/medium confidence")
    st.caption("Answered from a source, but only a partial match — worth reviewing whether coverage should be deepened.")
    weak = [r for r in qa_log if r.get("answered") and r.get("confidence") != "high"]
    weak.sort(key=lambda r: r.get("top_score", 0))
    if weak:
        st.dataframe(
            [
                {
                    "when": r.get("ts", "")[:19],
                    "question": r.get("question", ""),
                    "confidence": r.get("confidence", ""),
                    "top score": round(r.get("top_score", 0), 3),
                    "cited sources": ", ".join(r.get("citation_sources", []) or []),
                }
                for r in weak
            ],
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.info("No low/medium-confidence answers logged yet.")

# ----------------------------- Feedback -----------------------------
with tab_feedback:
    st.subheader("Negative feedback to review")
    downs_list = [f for f in feedback if f.get("vote") == "down"]
    downs_list.reverse()
    if downs_list:
        st.dataframe(
            [
                {
                    "when": f.get("ts", "")[:19],
                    "question": f.get("question", ""),
                    "confidence": f.get("confidence", ""),
                    "risk": f.get("risk_level", ""),
                    "answered": f.get("answered", ""),
                }
                for f in downs_list
            ],
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.success("No negative feedback logged yet.")

    st.subheader("All feedback")
    ups = sum(1 for f in feedback if f.get("vote") == "up")
    st.write("👍 {}  ·  👎 {}  ·  total {}".format(ups, downs, len(feedback)))

# ----------------------------- Freshness -----------------------------
with tab_fresh:
    st.subheader("Primary source freshness")
    st.caption("Run `python -m sources.check_freshness` (online) to refresh. Some government sites "
               "block automated requests (HTTP 403) — those need a manual review at the source URL.")

    state = _load_freshness()
    srcs = state.get("sources", {})
    manifest = {s["id"]: s for s in load_manifest()["sources"]}

    if state.get("last_run"):
        st.write("Last freshness run: **{}**".format(state["last_run"][:19]))

    rows = []
    for sid, meta in manifest.items():
        entry = srcs.get(sid, {})
        status = entry.get("status", "never checked")
        icon = {"unchanged": "✅", "baseline": "🆕", "changed": "🔴", "error": "⚠️"}.get(status, "❔")
        rows.append(
            {
                "": icon,
                "source": meta["title"],
                "status": status,
                "stale?": "STALE" if entry.get("is_stale", True) else "ok",
                "last checked": (entry.get("last_checked", "") or "")[:19],
                "http": entry.get("http_status", ""),
                "curated (retrieved)": meta["retrieved_date"],
                "url": meta["url"],
            }
        )
    st.dataframe(rows, use_container_width=True, hide_index=True)

    changed = [r for r in rows if r["status"] == "changed"]
    if changed:
        st.error("🔴 {} source(s) CHANGED since last curation — re-review and update the curated extract.".format(len(changed)))
    errored = [r for r in rows if r["status"] == "error"]
    if errored:
        st.warning("⚠️ {} source(s) could not be auto-checked (e.g. HTTP 403). Verify manually at the URL.".format(len(errored)))
