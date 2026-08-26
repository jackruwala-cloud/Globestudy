"""HTTP API around the citation engine — the shared 'brain' for every surface
(the Lovable web app, the browser extension, voice input all call these).

Run:
    uvicorn api.main:app --reload --port 8000
    # or: ./run.sh api

Design notes:
  * Every /ask response keeps the trust guarantees: citations, confidence, risk
    level, and an explicit "no verified source" when nothing matches.
  * /draft_email returns a DRAFT only. It never sends email. Sending is a
    front-end concern using the student's own Gmail OAuth, with their consent.
  * CORS is open for development. Restrict allow_origins before production.
"""
from __future__ import annotations

import json
import os
import time
from typing import Any, Dict, List, Optional
from urllib.parse import quote_plus

import requests
from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from api import security

from common import config, paths
from ingestion.chunker import load_manifest
from qa_engine import guides as guides_mod
from qa_engine.email_drafter import draft_email
from qa_engine.engine import answer as engine_answer
from qa_engine.prompts import DISCLAIMER
from qa_engine.status_calendar import compute_calendar


def _load_json(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


# Curated reference data (loaded once).
_UNIVERSITIES: List[Dict[str, Any]] = _load_json(paths.UNIVERSITIES_PATH)["universities"]
_UNI_BY_ID: Dict[str, Dict[str, Any]] = {u["id"]: u for u in _UNIVERSITIES}
_UNIS_WITH_SOURCE = {
    s.get("university_id")
    for s in load_manifest()["sources"]
    if s.get("scope") == "university" and s.get("university_id")
}

app = FastAPI(title="StatusCompass API", version="0.2.0")

# Restrict origins in production via the ALLOWED_ORIGINS env var
# (comma-separated), e.g. "https://your-app.lovable.app,https://yourdomain.com".
# Defaults to "*" for local development.
_origins_env = os.environ.get("ALLOWED_ORIGINS", "*").strip()
_allow_origins = ["*"] if _origins_env in ("", "*") else [o.strip() for o in _origins_env.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allow_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ------------------------------- models -------------------------------
class AskRequest(BaseModel):
    question: str
    university_id: Optional[str] = None  # non-PII; personalizes sources only


class DraftEmailRequest(BaseModel):
    prompt: str = ""
    request_type: str = ""
    fields: Dict[str, str] = {}
    use_llm: bool = False


class CalendarRequest(BaseModel):
    program_start_date: Optional[str] = None
    program_end_date: Optional[str] = None
    opt_ead_start_date: Optional[str] = None
    opt_ead_end_date: Optional[str] = None
    i94_end_date: Optional[str] = None
    visa_expiry_date: Optional[str] = None
    is_stem: bool = False
    as_of: Optional[str] = None


# ------------------------------- routes -------------------------------
@app.get("/health")
def health() -> Dict[str, Any]:
    cfg = config.get_config()
    manifest = load_manifest()
    all_guides = guides_mod._load_guides()
    return {
        "status": "ok",
        "qa_mode": cfg["qa"]["mode"],
        "retrieval_backend": cfg["retrieval"]["backend"],
        "num_sources": len(manifest["sources"]),
        "num_guides": len(all_guides),
        "num_universities": len(_UNIVERSITIES),
        "disclaimer": DISCLAIMER,
    }


def _office_link(u: Dict[str, Any]) -> Dict[str, Any]:
    """Best link to the school's INTERNATIONAL STUDENT office (not its homepage).

    Uses the curated office URL when we have one; otherwise a search scoped to the
    school's own domain, which reliably lands on the ISSS/international-office page
    rather than the university homepage.
    """
    curated = u.get("international_office_url")
    if curated:
        return {"url": curated, "is_search": False}
    domain = u.get("domain")
    if domain:
        query = "international student office site:" + domain
    else:
        query = (u.get("name", "") + " international student office").strip()
    return {"url": "https://www.google.com/search?q=" + quote_plus(query), "is_search": True}


def _school_context(university_id: Optional[str]) -> Optional[Dict[str, Any]]:
    if not university_id:
        return None
    u = _UNI_BY_ID.get(university_id)
    if not u:
        return None
    office = _office_link(u)
    return {
        "university_id": u["id"],
        "name": u["name"],
        "international_office_url": office["url"],
        "international_office_is_search": office["is_search"],
        "has_curated_source": university_id in _UNIS_WITH_SOURCE,
    }


def _require_user(authorization: Optional[str]) -> Optional[str]:
    """Auth-gate: return the user id, or raise 401. No-op when enforcement is off."""
    if not security.enforcement_enabled():
        return None
    user_id = security.verify_user(security.bearer_token(authorization))
    if not user_id:
        raise HTTPException(
            status_code=401,
            detail={"error": "auth_required", "message": "Please sign in to ask questions."},
        )
    return user_id


@app.get("/usage")
def usage(authorization: Optional[str] = Header(None)) -> Dict[str, Any]:
    if not security.enforcement_enabled():
        return {"enforced": False, "used": 0, "limit": None, "remaining": None}
    user_id = _require_user(authorization)
    used = security.usage_today(user_id)
    limit = security.FREE_DAILY_LIMIT
    return {"enforced": True, "used": used, "limit": limit, "remaining": max(0, limit - used)}


@app.post("/ask")
def ask(req: AskRequest, authorization: Optional[str] = Header(None)) -> Dict[str, Any]:
    user_id = _require_user(authorization)
    if user_id is not None:
        allowed, used, limit = security.check_and_consume(user_id)
        if not allowed:
            raise HTTPException(
                status_code=429,
                detail={
                    "error": "limit_reached",
                    "message": "You've used all {} of your free questions for today. Your limit resets tomorrow.".format(limit),
                    "used": used,
                    "limit": limit,
                },
            )
    _uni = _UNI_BY_ID.get(req.university_id) if req.university_id else None
    _uni_domain = _uni.get("domain") if _uni else None
    result = engine_answer(
        req.question, university_id=req.university_id, university_domain=_uni_domain
    ).to_dict()
    # Attach the student's school office as context so the app can always show a
    # DSO/office pointer, even when no school-specific source was curated yet.
    result["school_context"] = _school_context(req.university_id)
    return result


@app.get("/universities")
def universities(q: str = "", limit: int = 20) -> List[Dict[str, Any]]:
    ql = (q or "").strip().lower()
    matches = _UNIVERSITIES if not ql else [
        u for u in _UNIVERSITIES
        if ql in u["name"].lower() or ql in u.get("city", "").lower() or ql in u.get("state", "").lower()
    ]
    matches = sorted(matches, key=lambda u: u["name"])[: max(1, min(limit, 100))]
    return [
        {
            "id": u["id"], "name": u["name"], "city": u.get("city", ""), "state": u.get("state", ""),
            "international_office_url": _office_link(u)["url"],
            "has_curated_source": u["id"] in _UNIS_WITH_SOURCE,
        }
        for u in matches
    ]


@app.get("/tax_treaty_countries")
def tax_treaty_countries() -> Dict[str, Any]:
    return _load_json(paths.TAX_TREATY_PATH)


@app.post("/status_calendar")
def status_calendar(req: CalendarRequest) -> Dict[str, Any]:
    # Dates are used to compute cited milestones and are NOT stored or logged.
    return compute_calendar(req.dict())


# --- Official news feed (Federal Register API — free, official, no key) ---
_FR_API = "https://www.federalregister.gov/api/v1/documents.json"
_news_cache: Dict[str, Any] = {"ts": 0.0, "data": None}
_NEWS_TTL = 1800  # 30 minutes


def _fetch_news() -> Dict[str, Any]:
    params = {
        "per_page": 20,
        "order": "newest",
        "conditions[term]": "nonimmigrant students exchange visitors F-1",
        "conditions[agencies][]": "homeland-security-department",
        "fields[]": ["document_number", "title", "abstract", "publication_date",
                     "effective_on", "html_url", "type", "agencies"],
    }
    try:
        r = requests.get(_FR_API, params=params, timeout=15,
                         headers={"User-Agent": "statuscompass-news/1.0"})
        r.raise_for_status()
        raw = r.json()
        items = []
        for d in raw.get("results", []):
            items.append({
                "title": d.get("title"),
                "abstract": d.get("abstract"),
                "type": d.get("type"),  # Rule, Proposed Rule, Notice
                "publication_date": d.get("publication_date"),
                "effective_on": d.get("effective_on"),
                "url": d.get("html_url"),
                "agencies": [a.get("name") for a in (d.get("agencies") or []) if a.get("name")],
                "publisher": "Federal Register (U.S. government)",
            })
        return {"source": "Federal Register", "source_url": "https://www.federalregister.gov/",
                "official": True, "items": items, "error": None}
    except Exception as exc:
        return {"source": "Federal Register", "official": True, "items": [], "error": str(exc)}


@app.get("/news")
def news() -> Dict[str, Any]:
    now = time.time()
    if _news_cache["data"] is None or (now - _news_cache["ts"]) > _NEWS_TTL:
        _news_cache["data"] = _fetch_news()
        _news_cache["ts"] = now
    return _news_cache["data"]


@app.get("/guides")
def list_guides() -> List[Dict[str, Any]]:
    out = []
    for g in guides_mod._load_guides().values():
        out.append(
            {
                "id": g["id"],
                "stage": g.get("stage", ""),
                "title": g["title"],
                "intro": g.get("intro", ""),
                "num_sections": len(g.get("sections", [])),
            }
        )
    # Stable lifecycle order.
    order = {"new_student": 0, "mid_year": 1, "graduating": 2}
    out.sort(key=lambda x: order.get(x["id"], 99))
    return out


@app.get("/guides/{guide_id}")
def get_guide(guide_id: str) -> Dict[str, Any]:
    all_guides = guides_mod._load_guides()
    g = all_guides.get(guide_id)
    if not g:
        return {"error": "guide not found", "available": list(all_guides.keys())}
    body, source_ids = guides_mod.render_guide(g)
    manifest = {s["id"]: s for s in load_manifest()["sources"]}
    citations = [
        {
            "n": i,
            "source_title": manifest.get(sid, {}).get("title", sid),
            "publisher": manifest.get(sid, {}).get("publisher", ""),
            "url": manifest.get(sid, {}).get("url", ""),
            "retrieved_date": manifest.get(sid, {}).get("retrieved_date", ""),
        }
        for i, sid in enumerate(source_ids, start=1)
    ]
    return {
        "id": g["id"],
        "stage": g.get("stage", ""),
        "title": g["title"],
        "intro": g.get("intro", ""),
        "sections": g["sections"],
        "answer_markdown": body,
        "citations": citations,
    }


@app.post("/draft_email")
def draft(req: DraftEmailRequest) -> Dict[str, Any]:
    d = draft_email(
        prompt=req.prompt, request_type=req.request_type, fields=req.fields, use_llm=req.use_llm
    )
    return d.to_dict()


@app.get("/sources")
def sources() -> List[Dict[str, Any]]:
    return [
        {
            "id": s["id"],
            "title": s["title"],
            "publisher": s["publisher"],
            "category": s["category"],
            "url": s["url"],
            "retrieved_date": s["retrieved_date"],
            "summary": s["summary"],
        }
        for s in load_manifest()["sources"]
    ]
