"""Chat-style web UI for the International Student Advisor.

Run from the repo root:
    streamlit run web_ui/app.py
"""
from __future__ import annotations

import os
import sys

# Make the project importable when launched via `streamlit run web_ui/app.py`.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st

from common import logging_store
from qa_engine.engine import answer as engine_answer
from qa_engine.prompts import DISCLAIMER

st.set_page_config(page_title="International Student Advisor", page_icon="🎓", layout="centered")

CONF_STYLE = {
    "high": ("#166534", "#dcfce7", "High confidence", "Strong match to a primary source."),
    "medium": ("#92400e", "#fef3c7", "Medium confidence", "Partial match — read the cited sources carefully."),
    "none": ("#991b1b", "#fee2e2", "No verified source", "No official source confidently covers this."),
}


def _badge(text: str, fg: str, bg: str) -> str:
    return (
        "<span style='background:{bg};color:{fg};padding:2px 10px;border-radius:12px;"
        "font-size:0.78rem;font-weight:600;margin-right:6px;white-space:nowrap;'>{t}</span>"
    ).format(bg=bg, fg=fg, t=text)


def render_answer(ans: dict) -> None:
    conf = ans["confidence"]
    fg, bg, label, sub = CONF_STYLE.get(conf, CONF_STYLE["none"])

    # Badges row: risk + confidence.
    if ans["risk_level"] == "HIGH":
        risk_badge = _badge("⚠ High-stakes question", "#991b1b", "#fee2e2")
    else:
        risk_badge = _badge("General info", "#1e3a8a", "#dbeafe")
    conf_badge = _badge(label, fg, bg)
    st.markdown(risk_badge + conf_badge, unsafe_allow_html=True)
    st.caption("{}  ·  {}".format(sub, ans["coverage"]))

    # High-stakes verification notice (before the answer, so it can't be missed).
    if ans.get("high_stakes_notice"):
        st.warning(ans["high_stakes_notice"])

    # The answer body.
    st.markdown(ans["answer_markdown"])

    # Citations.
    if ans.get("citations"):
        st.markdown("**Sources** (click to verify at the official page):")
        for c in ans["citations"]:
            st.markdown(
                "- **[{n}]** [{title} — _{section}_]({url})  \n"
                "  <span style='color:#6b7280;font-size:0.8rem;'>{pub} · retrieved {date} · match {score:.2f}</span>".format(
                    n=c["n"], title=c["source_title"], section=c["section"], url=c["url"],
                    pub=c["publisher"], date=c["retrieved_date"], score=c["score"],
                ),
                unsafe_allow_html=True,
            )

    # Referrals (shown when we have no confident source).
    if ans.get("referrals"):
        st.markdown("**Who to ask instead:**")
        for r in ans["referrals"]:
            st.markdown("- {}".format(r))

    # Feedback buttons.
    _render_feedback(ans)


def _render_feedback(ans: dict) -> None:
    key = "fb_" + ans["id"]
    existing = st.session_state.get(key)
    st.markdown("<div style='margin-top:6px;'></div>", unsafe_allow_html=True)
    cols = st.columns([1, 1, 6])
    if existing:
        cols[2].caption("Thanks — feedback recorded ({}).".format("👍" if existing == "up" else "👎"))
        return
    if cols[0].button("👍 Helpful", key="up_" + ans["id"]):
        _log_fb(ans, "up")
        st.session_state[key] = "up"
        st.rerun()
    if cols[1].button("👎 Not helpful", key="down_" + ans["id"]):
        _log_fb(ans, "down")
        st.session_state[key] = "down"
        st.rerun()


def _log_fb(ans: dict, vote: str) -> None:
    logging_store.log_feedback(
        {
            "answer_id": ans["id"],
            "question": ans["question"],
            "vote": vote,
            "confidence": ans["confidence"],
            "risk_level": ans["risk_level"],
            "answered": ans["answered"],
        }
    )


# ----------------------------- Sidebar -----------------------------
with st.sidebar:
    st.header("About this tool")
    st.markdown(
        "Answers questions from international students in the U.S. about **visa, "
        "tax, and financial** topics — and shows the **primary source** behind "
        "every answer.\n\n"
        "**How it works**\n"
        "1. Your question is matched against a small, curated set of official "
        "IRS / USCIS / CFPB documents.\n"
        "2. The answer is composed **only** from those sources, with citations.\n"
        "3. If nothing official matches, it says so instead of guessing."
    )
    st.divider()
    st.subheader("Scope")
    st.markdown(
        "- ✅ F-1/J-1 tax basics, FICA, Forms 8843 / 1042-S, residency\n"
        "- ✅ On-campus work, CPT, OPT, STEM OPT\n"
        "- ✅ Sending money abroad (consumer protections)\n"
        "- ❌ Personalized tax/legal/immigration advice\n"
        "- ❌ Investment advice · bank linking · moving money"
    )
    st.divider()
    st.caption(DISCLAIMER)


# ----------------------------- Main -----------------------------
st.title("🎓 International Student Advisor")
st.caption("Traceable answers on U.S. visa, tax & money questions — every answer cites an official source.")

# Permanent, always-visible disclaimer.
st.info("ℹ️ **Informational only — not licensed tax, legal, or immigration advice.** "
        "Always confirm with your school's international student office (DSO) and a licensed professional.")

if "history" not in st.session_state:
    st.session_state.history = []

# Example prompts.
with st.expander("Try an example question"):
    st.markdown(
        "- does my F-1 OPT income get FICA taxed?\n"
        "- how many hours can I work on campus?\n"
        "- do I need to file taxes if I had no income?\n"
        "- how do I get the STEM OPT extension?\n"
        "- how do I send money home to my family?"
    )

# Replay history.
for item in st.session_state.history:
    with st.chat_message("user"):
        st.markdown(item["question"])
    with st.chat_message("assistant"):
        render_answer(item["answer"])

# Input.
prompt = st.chat_input("Ask a visa, tax, or money question…")
if prompt:
    with st.chat_message("user"):
        st.markdown(prompt)
    with st.chat_message("assistant"):
        with st.spinner("Searching primary sources…"):
            ans = engine_answer(prompt).to_dict()
        render_answer(ans)
    st.session_state.history.append({"question": prompt, "answer": ans})
