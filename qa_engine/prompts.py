"""Prompt templates and fixed copy for the QA engine.

The LLM prompt is intentionally strict: answer ONLY from the numbered context,
cite every claim, and refuse when the context is insufficient. The default
engine mode is extractive (no LLM) so citation discipline holds even with no
API key configured.
"""
from __future__ import annotations

from typing import List

DISCLAIMER = (
    "This tool is informational and educational only. It is NOT licensed tax, "
    "legal, or immigration advice. Rules change and individual situations vary. "
    "Always confirm with your school's international student office (DSO) and a "
    "licensed professional before acting."
)

HIGH_STAKES_NOTICE = (
    "This is a high-stakes question (it can affect your visa status, tax filing, "
    "or work authorization). Treat the answer below as a starting point, not the "
    "final word — verify it with your Designated School Official (DSO) / "
    "international student office and a licensed professional (a tax professional "
    "experienced with nonresident returns, or an immigration attorney)."
)

# Who to contact when we have no confident source, by topic.
REFERRALS = {
    "tax": [
        "Your school's international student / tax office (many offer free access to tax-prep software such as Sprintax for nonresident students).",
        "A licensed tax professional (CPA or Enrolled Agent) experienced with nonresident alien returns.",
        "IRS International Taxpayers resources: https://www.irs.gov/individuals/international-taxpayers",
    ],
    "visa": [
        "Your school's Designated School Official (DSO) / international student office — they manage your SEVIS record.",
        "A licensed immigration attorney (e.g., via the American Immigration Lawyers Association, aila.org).",
        "USCIS students and employment resources: https://www.uscis.gov/working-in-the-united-states/students-and-exchange-visitors",
    ],
    "finance": [
        "Your bank or credit union for account-specific questions.",
        "Consumer Financial Protection Bureau (CFPB): https://www.consumerfinance.gov/",
        "Your school's financial aid or student services office.",
    ],
    "general": [
        "Your school's international student office (DSO) — the best first stop for visa, work, and tax-orientation questions.",
        "A licensed professional in the relevant area (tax professional or immigration attorney).",
    ],
}


def build_llm_messages(question: str, numbered_context: List[str]) -> dict:
    context_block = "\n\n".join(numbered_context)
    system = (
        "You are a careful assistant for international students in the U.S. "
        "Answer ONLY using the numbered SOURCES provided. Do not use any outside "
        "knowledge about tax, visa, or immigration rules. Cite every factual "
        "sentence with the matching source number in square brackets, e.g. [1]. "
        "If the sources do not clearly answer the question, reply exactly with: "
        "INSUFFICIENT_CONTEXT and nothing else. Never invent citations, URLs, "
        "numbers, or deadlines that are not in the sources."
    )
    user = (
        "SOURCES:\n{context}\n\nQUESTION: {q}\n\n"
        "Write a concise answer (2-5 sentences) using only the sources above, "
        "with a [n] citation after each claim.".format(context=context_block, q=question)
    )
    return {"system": system, "user": user}
