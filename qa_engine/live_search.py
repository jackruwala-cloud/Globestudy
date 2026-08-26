"""Live official-source fallback via the Perplexity API.

Used ONLY when the curated knowledge base would otherwise refuse (confidence
"none"). Perplexity is hard-restricted to official domains via
`search_domain_filter`, and — belt and suspenders — every citation it returns is
re-validated against the official allowlist here, so an informal source can never
reach the user. If no official citation survives, we return None and the engine
falls back to the honest "no verified source" response.

The API key is read from config (env PERPLEXITY_API_KEY) and lives server-side
only. This module never runs unless a key is configured.
"""
from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from sources.source_policy import ALLOWED_GOV_DOMAINS

PERPLEXITY_URL = "https://api.perplexity.ai/chat/completions"

_SYSTEM = (
    "You are a careful assistant for international students (F-1/J-1) in the "
    "United States. Answer ONLY using official U.S. government sources (IRS, "
    "USCIS, DHS/SEVP, Department of Labor, Department of State, SSA) and the "
    "student's own university website. Be concise (3-6 sentences) and specific, "
    "including figures, form numbers, and deadlines when the official sources "
    "give them. If the official sources do not clearly answer, say you don't "
    "have a verified official answer. Do NOT give personalized legal or tax "
    "advice — frame everything as general information and tell the student to "
    "confirm with their DSO / international student office and a licensed "
    "professional. Never use or cite non-government, non-university sources."
)


def _registrable(host: str) -> str:
    host = (host or "").lower()
    if host.startswith("www."):
        host = host[4:]
    return host


def _is_official(url: str) -> bool:
    host = _registrable(urlparse(url).hostname or "")
    if not host:
        return False
    if host.endswith(".edu"):
        return True
    return any(host == d or host.endswith("." + d) for d in ALLOWED_GOV_DOMAINS)


def _official_domains(university_domain: Optional[str]) -> List[str]:
    domains = list(ALLOWED_GOV_DOMAINS)
    if university_domain and university_domain.endswith(".edu"):
        domains.append(university_domain)
    # Perplexity caps the filter length; keep the most relevant, deduped.
    seen: List[str] = []
    for d in domains:
        if d not in seen:
            seen.append(d)
    return seen[:10]


def live_official_answer(
    question: str,
    cfg: Dict[str, Any],
    university_domain: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Return {answer, citations:[{title,url}]} from official sources, or None."""
    key = (cfg.get("perplexity", {}) or {}).get("api_key", "")
    if not key:
        return None

    import urllib.request  # stdlib — no third-party dependency

    payload = {
        "model": (cfg.get("perplexity", {}) or {}).get("model", "sonar"),
        "messages": [
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": question},
        ],
        "search_domain_filter": _official_domains(university_domain),
        "temperature": 0.1,
        "max_tokens": 600,
    }
    try:
        req = urllib.request.Request(
            PERPLEXITY_URL,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.load(resp)
    except Exception:
        return None

    try:
        content = data["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError):
        return None
    if not content:
        return None

    # Collect citation URLs (Perplexity returns "search_results" and/or "citations").
    results: List[Dict[str, str]] = []
    for sr in data.get("search_results") or []:
        url = sr.get("url")
        if url:
            results.append({"title": sr.get("title") or "", "url": url})
    for url in data.get("citations") or []:
        if isinstance(url, str) and not any(r["url"] == url for r in results):
            results.append({"title": "", "url": url})

    # Belt-and-suspenders: keep only OFFICIAL citations.
    official = [r for r in results if _is_official(r["url"])]
    if not official:
        return None

    # Drop any bracketed [n] markers that reference now-filtered citations; keep prose.
    answer = re.sub(r"\s*\[\d+\]", "", content).strip()
    return {"answer": answer, "citations": official}
