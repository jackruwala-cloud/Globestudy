"""Auth gate + per-user free-question cap for the expensive endpoints.

Enforced at the API (not just the app) so hitting the API directly can't bypass
it and run up Perplexity/compute costs.

  * Auth: the app sends the caller's Supabase access token as a Bearer token.
    We validate it against Supabase's /auth/v1/user endpoint (works regardless of
    the project's JWT signing config) and get the user id. No valid token -> 401.
  * Daily cap: we count today's questions for that user in a Supabase table
    (question_usage) and refuse past the free limit -> 429.

Config comes from environment variables (set on Render):
  SUPABASE_URL, SUPABASE_ANON_KEY, SUPABASE_SERVICE_ROLE_KEY, FREE_DAILY_LIMIT.
If they are not all present, enforcement is OFF (local dev / backward compatible).
"""
from __future__ import annotations

import json
import os
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Dict, Optional, Tuple

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_ANON_KEY = os.environ.get("SUPABASE_ANON_KEY", "")
SERVICE_ROLE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
FREE_DAILY_LIMIT = int(os.environ.get("FREE_DAILY_LIMIT", "15"))


def enforcement_enabled() -> bool:
    return bool(SUPABASE_URL and SUPABASE_ANON_KEY and SERVICE_ROLE_KEY)


def _service_headers(extra: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    """Headers for service-role PostgREST calls.

    Works with BOTH key formats: legacy service_role keys are JWTs (start with
    'eyJ') and go in the Authorization bearer; new opaque keys ('sb_secret_...')
    grant service access via the apikey header alone (a non-JWT bearer would be
    rejected by PostgREST).
    """
    headers = {"apikey": SERVICE_ROLE_KEY}
    if SERVICE_ROLE_KEY.startswith("eyJ"):
        headers["Authorization"] = "Bearer " + SERVICE_ROLE_KEY
    if extra:
        headers.update(extra)
    return headers


# --- token validation (short in-memory cache so we don't call Supabase every ask) ---
_token_cache: Dict[str, Tuple[str, float]] = {}


def bearer_token(authorization: Optional[str]) -> Optional[str]:
    if authorization and authorization.lower().startswith("bearer "):
        return authorization.split(" ", 1)[1].strip()
    return None


def verify_user(token: Optional[str]) -> Optional[str]:
    """Return the Supabase user id for a valid access token, else None."""
    if not token:
        return None
    now = time.time()
    cached = _token_cache.get(token)
    if cached and cached[1] > now:
        return cached[0]
    req = urllib.request.Request(
        SUPABASE_URL + "/auth/v1/user",
        headers={"Authorization": "Bearer " + token, "apikey": SUPABASE_ANON_KEY},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.load(resp)
        uid = data.get("id")
    except Exception:
        return None
    if uid:
        _token_cache[token] = (uid, now + 300)  # cache 5 minutes
        return uid
    return None


# --- daily usage counter (Supabase table `question_usage`, one row per question) ---
def _today_start_iso() -> str:
    now = datetime.now(timezone.utc)
    return now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()


def usage_today(user_id: str) -> int:
    url = (
        SUPABASE_URL
        + "/rest/v1/question_usage?select=id&user_id=eq."
        + urllib.parse.quote(user_id)
        + "&created_at=gte."
        + urllib.parse.quote(_today_start_iso())
    )
    req = urllib.request.Request(
        url,
        headers=_service_headers({"Prefer": "count=exact", "Range": "0-0"}),
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            content_range = resp.headers.get("Content-Range", "")  # e.g. "0-0/12" or "*/12"
        total = content_range.split("/")[-1]
        return int(total) if total.isdigit() else 0
    except Exception:
        return 0  # fail-open on transient counter errors (auth gate still applies)


def _record_question(user_id: str) -> None:
    req = urllib.request.Request(
        SUPABASE_URL + "/rest/v1/question_usage",
        data=json.dumps({"user_id": user_id}).encode("utf-8"),
        method="POST",
        headers=_service_headers({"Content-Type": "application/json", "Prefer": "return=minimal"}),
    )
    try:
        urllib.request.urlopen(req, timeout=10).read()
    except Exception:
        pass


def check_and_consume(user_id: str) -> Tuple[bool, int, int]:
    """(allowed, used_after, limit). Records the question when allowed."""
    used = usage_today(user_id)
    if used >= FREE_DAILY_LIMIT:
        return (False, used, FREE_DAILY_LIMIT)
    _record_question(user_id)
    return (True, used + 1, FREE_DAILY_LIMIT)
