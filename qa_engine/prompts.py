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

PARTIAL_NOTICE = (
    "**I don't have a source that squarely answers this, so treat this as a "
    "partial answer.** Here's the closest official information I have — it may "
    "not fully cover your exact question. Verify the specifics with your DSO / "
    "international student office or a licensed professional."
)

HIGH_STAKES_NOTICE = (
    "Before you act on this — applying, filing, traveling, or changing your "
    "enrollment or status — confirm the specifics with your DSO / international "
    "student office (and a licensed professional where money or legal filings are "
    "involved). Timing and eligibility depend on your individual record."
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
    "campus_legal": [
        "Your school's Title IX Office / Office of Student Conduct / Dean of Students — they run the process and can explain your rights, the steps, and the timeline.",
        "Your campus Student Legal Services (many schools offer free, confidential legal help to students), or a licensed attorney for anything serious.",
        "Your DSO / international student office — to understand any effect on your enrollment and F-1 status. Keep them informed early and confidentially.",
    ],
    "general": [
        "Your school's international student office (DSO) — the best first stop for visa, work, and tax-orientation questions.",
        "A licensed professional in the relevant area (tax professional or immigration attorney).",
    ],
}

# Constructive, non-fabricated orientation shown when we have no verified source.
# It tells the student how to think about their problem and who owns it, WITHOUT
# asserting any specific tax/legal/immigration rule.
ORIENTATION = {
    "tax": (
        "This is a U.S. tax-filing question, and the answer usually turns on your "
        "income type (wages on a W-2, a scholarship/fellowship, or no income) and "
        "your residency status. I don't have an official source that squarely "
        "covers your exact situation, so rather than guess, here is who can look at "
        "your specifics:"
    ),
    "visa": (
        "This is an immigration/status question, and the exact rule usually depends "
        "on your SEVIS record and program dates — which your DSO can actually see. "
        "I don't have an official source that squarely covers it, so start here:"
    ),
    "finance": (
        "This is a personal-finance question — it depends on your income, expenses, "
        "and goals. I don't have an official source that covers your exact case, but "
        "these can help you work through it:"
    ),
    "campus_legal": (
        "This looks like a campus-conduct or legal matter (for example a Title IX "
        "case, a disciplinary hearing, or a police/legal issue). These are handled "
        "by specific campus offices and, where needed, an attorney — not by tax or "
        "immigration rules, and I won't guess at legal specifics. One important "
        "thing to know: because a disciplinary or legal outcome can affect your "
        "enrollment, and your F-1 status depends on staying enrolled, it's worth "
        "looping in your DSO early. Here's who handles this:"
    ),
    "general": (
        "I don't have a verified official source that squarely covers this, so I "
        "won't guess. Here's who can point you the right way:"
    ),
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
