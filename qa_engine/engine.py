"""Retrieval-augmented answer engine with enforced citation discipline.

Guarantees:
  * No answer is produced without at least one retrieved primary source above
    the confidence floor. Below the floor, the engine explicitly says it has no
    verified source and refers the student to the right human/office.
  * Every answer ships with numbered, clickable citations back to the exact
    source URL and section, plus a confidence/coverage indicator.
  * On tax/visa specifics the engine never answers from general model knowledge:
    the default "extractive" mode composes the answer only from retrieved text.
"""
from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

from common import config, logging_store
from ingestion.chunker import load_manifest
from ingestion.vector_store import Retrieved, get_retriever
from qa_engine import guides, prompts
from risk_classifier.classifier import classify


@dataclass
class Citation:
    n: int
    source_title: str
    publisher: str
    section: str
    url: str
    retrieved_date: str
    score: float


@dataclass
class Answer:
    id: str
    question: str
    answered: bool
    confidence: str  # "high" | "medium" | "none"
    coverage: str  # human-readable coverage note
    top_score: float
    mode: str
    answer_markdown: str
    citations: List[Citation] = field(default_factory=list)
    referrals: List[str] = field(default_factory=list)
    risk_level: str = "HIGH"
    risk_reasoning: str = ""
    high_stakes_notice: Optional[str] = None
    disclaimer: str = prompts.DISCLAIMER

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        return d


def _confidence_label(top_score: float, cfg: Dict[str, Any]) -> str:
    r = cfg["retrieval"]
    partial_floor = r.get("partial_floor", r["min_score"])
    if top_score < partial_floor:
        return "none"
    if top_score < r["min_score"]:
        return "low"  # near-miss: show closest source, flagged as partial
    if top_score >= r["high_conf_score"]:
        return "high"
    return "medium"


def _coverage_note(supporting: List[Retrieved], confidence: str) -> str:
    n = len(supporting)
    sources = len({r.chunk["source_id"] for r in supporting})
    if confidence == "none":
        return "No source in the knowledge base matched this question with enough confidence."
    if confidence == "low":
        return "Partial: no source squarely matched — showing the closest official source(s)."
    strength = {"high": "strong", "medium": "partial"}.get(confidence, "partial")
    return "{} match: {} passage(s) from {} primary source document(s).".format(
        strength.capitalize(), n, sources
    )


def _build_citations(supporting: List[Retrieved]) -> List[Citation]:
    citations: List[Citation] = []
    for i, r in enumerate(supporting, start=1):
        c = r.chunk
        citations.append(
            Citation(
                n=i,
                source_title=c["source_title"],
                publisher=c["publisher"],
                section=c["section"],
                url=c["source_url"],
                retrieved_date=c["retrieved_date"],
                score=r.score,
            )
        )
    return citations


def _extractive_answer(supporting: List[Retrieved]) -> str:
    """Compose the answer strictly from retrieved source text (public-domain gov)."""
    lines = [
        "Here is what the primary sources say (quoted/summarized directly from "
        "them — nothing added from outside knowledge):",
        "",
    ]
    for i, r in enumerate(supporting, start=1):
        c = r.chunk
        lines.append("**{}** [{}]".format(c["section"], i))
        lines.append(c["text"])
        lines.append("")
    return "\n".join(lines).strip()


def _llm_answer(question: str, supporting: List[Retrieved], cfg: Dict[str, Any]) -> Optional[str]:
    """Optional: answer via Claude, still constrained to the retrieved context."""
    api_key = (cfg.get("anthropic", {}) or {}).get("api_key", "")
    if not api_key:
        return None
    try:
        import anthropic  # type: ignore
    except ImportError:
        return None

    numbered = []
    for i, r in enumerate(supporting, start=1):
        c = r.chunk
        numbered.append("[{}] ({} — {}) {}".format(i, c["source_title"], c["section"], c["text"]))

    msg = prompts.build_llm_messages(question, numbered)
    try:
        client = anthropic.Anthropic(api_key=api_key)
        resp = client.messages.create(
            model=cfg["qa"]["llm_model"],
            max_tokens=600,
            system=msg["system"],
            messages=[{"role": "user", "content": msg["user"]}],
        )
        text = "".join(block.text for block in resp.content if getattr(block, "type", "") == "text").strip()
    except Exception as exc:  # network/key/model errors -> fall back to extractive
        return "__LLM_ERROR__:{}".format(exc)

    if not text or "INSUFFICIENT_CONTEXT" in text:
        return "__INSUFFICIENT__"
    return text


def _no_source_answer(question: str, risk, cfg: Dict[str, Any], top_score: float = 0.0) -> Answer:
    category = "general"
    # Bias referral category off the question wording. Campus-conduct/legal is
    # checked first (it's out of scope for tax/visa rules but needs real direction).
    q = question.lower()
    if any(t in q for t in ("title ix", "title 9", "disciplinary", "misconduct", "student conduct",
                            "expel", "suspend", "dismiss", "arrest", "police", "charged with",
                            "lawsuit", "hearing", "probation", "dean of students")):
        category = "campus_legal"
    elif any(t in q for t in ("tax", "fica", "1040", "8843", "1042", "withhold", "refund", "treaty", "resident", "w-2")):
        category = "tax"
    elif any(t in q for t in ("visa", "opt", "cpt", "stem", "sevis", "ead", "status", "work", "i-765", "i-20")):
        category = "visa"
    elif any(t in q for t in ("money", "remittance", "budget", "bank", "credit", "exchange", "save", "invest")):
        category = "finance"

    body = prompts.ORIENTATION.get(category, prompts.ORIENTATION["general"])
    referrals = prompts.REFERRALS.get(category, prompts.REFERRALS["general"])

    return Answer(
        id=str(uuid.uuid4()),
        question=question,
        answered=False,
        confidence="none",
        coverage=_coverage_note([], "none"),
        top_score=top_score,
        mode=cfg["qa"]["mode"],
        answer_markdown=body,
        citations=[],
        referrals=referrals,
        risk_level=risk.level,
        risk_reasoning=risk.reasoning,
        high_stakes_notice=prompts.HIGH_STAKES_NOTICE if risk.level == "HIGH" else None,
    )


_manifest_by_id: Optional[Dict[str, Any]] = None


def _source_meta(source_id: str) -> Dict[str, Any]:
    global _manifest_by_id
    if _manifest_by_id is None:
        _manifest_by_id = {s["id"]: s for s in load_manifest()["sources"]}
    return _manifest_by_id.get(source_id, {})


def _guide_answer(question: str, guide: Dict[str, Any], risk, cfg: Dict[str, Any]) -> Answer:
    body, source_ids = guides.render_guide(guide)
    citations: List[Citation] = []
    for i, sid in enumerate(source_ids, start=1):
        meta = _source_meta(sid)
        citations.append(
            Citation(
                n=i,
                source_title=meta.get("title", sid),
                publisher=meta.get("publisher", ""),
                section="Checklist reference",
                url=meta.get("url", ""),
                retrieved_date=meta.get("retrieved_date", ""),
                score=1.0,
            )
        )
    return Answer(
        id=str(uuid.uuid4()),
        question=question,
        answered=True,
        confidence="high",
        coverage="Curated checklist for the '{}' stage, with {} cited source(s).".format(
            guide.get("stage", ""), len(citations)
        ),
        top_score=1.0,
        mode="guide:{}".format(guide["id"]),
        answer_markdown=body,
        citations=citations,
        referrals=[],
        risk_level=risk.level,
        risk_reasoning=risk.reasoning,
        high_stakes_notice=prompts.HIGH_STAKES_NOTICE if risk.level == "HIGH" else None,
    )


def answer(question: str, university_id: Optional[str] = None) -> Answer:
    cfg = config.get_config()
    risk = classify(question)

    # Navigational / "what do I need" questions get a curated cited checklist,
    # not a single-fact lookup (which would wrongly refuse them).
    guide = guides.match_guide(question)
    if guide is not None:
        ans = _guide_answer(question, guide, risk, cfg)
        _log(ans)
        return ans

    retriever = get_retriever(cfg["retrieval"]["backend"])
    # university_id lets the student's own school sources (scope: university)
    # join the federal sources in retrieval; federal sources always apply.
    results = retriever.query(question, k=cfg["retrieval"]["top_k"], university_id=university_id)

    top_score = results[0].score if results else 0.0
    confidence = _confidence_label(top_score, cfg)

    if confidence == "none":
        ans = _no_source_answer(question, risk, cfg, top_score=top_score)
        _log(ans)
        return ans

    support_floor = cfg["retrieval"].get("support_floor", cfg["retrieval"]["min_score"])
    supporting = [r for r in results if r.score >= support_floor][: cfg["qa"]["max_context_chunks"]]
    citations = _build_citations(supporting)

    mode = cfg["qa"]["mode"]
    body = None
    if mode == "llm":
        llm_out = _llm_answer(question, supporting, cfg)
        if llm_out and not llm_out.startswith("__"):
            body = llm_out
        elif llm_out == "__INSUFFICIENT__":
            # Model itself judged context insufficient -> refuse rather than guess.
            ans = _no_source_answer(question, risk, cfg, top_score=top_score)
            _log(ans)
            return ans
        # __LLM_ERROR__ or no key -> fall through to extractive.
    if body is None:
        mode = "extractive" if mode == "extractive" else "extractive(fallback)"
        body = _extractive_answer(supporting)

    # Near-miss (partial) answers lead with an explicit partial-coverage notice.
    if confidence == "low":
        body = prompts.PARTIAL_NOTICE + "\n\n" + body

    ans = Answer(
        id=str(uuid.uuid4()),
        question=question,
        answered=True,
        confidence=confidence,
        coverage=_coverage_note(supporting, confidence),
        top_score=top_score,
        mode=mode,
        answer_markdown=body,
        citations=citations,
        referrals=[],
        risk_level=risk.level,
        risk_reasoning=risk.reasoning,
        high_stakes_notice=prompts.HIGH_STAKES_NOTICE if risk.level == "HIGH" else None,
    )
    _log(ans)
    return ans


def _log(ans: Answer) -> None:
    logging_store.log_qa(
        {
            "id": ans.id,
            "question": ans.question,
            "answered": ans.answered,
            "confidence": ans.confidence,
            "top_score": ans.top_score,
            "mode": ans.mode,
            "risk_level": ans.risk_level,
            "risk_reasoning": ans.risk_reasoning,
            "num_citations": len(ans.citations),
            "source_ids": [c.section for c in ans.citations],
            "citation_sources": [c.source_title for c in ans.citations],
        }
    )
