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

import os
from typing import Any, Dict, List, Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from common import config
from ingestion.chunker import load_manifest
from qa_engine import guides as guides_mod
from qa_engine.email_drafter import draft_email
from qa_engine.engine import answer as engine_answer
from qa_engine.prompts import DISCLAIMER

app = FastAPI(title="International Student Advisor API", version="0.2.0")

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


class DraftEmailRequest(BaseModel):
    prompt: str = ""
    request_type: str = ""
    fields: Dict[str, str] = {}
    use_llm: bool = False


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
        "disclaimer": DISCLAIMER,
    }


@app.post("/ask")
def ask(req: AskRequest) -> Dict[str, Any]:
    return engine_answer(req.question).to_dict()


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
