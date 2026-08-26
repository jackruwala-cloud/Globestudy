"""Auth gate + per-user free-question cap for the expensive endpoints.

Enforced at the API (not just the app) so hitting the API directly can't bypass
it and run up Perplexity/compute costs.

  * Auth: the app sends the caller's Supabase access token as a Bearer token.
    We validate it against Supabase's /auth/v1/user endpoint (works regardless of
    the project's JWT signing config) and get the user id. No valid token -> 401.
  * Daily cap: we count today's questions for that user in a Supabase table
    (question_usage) and refuse past the free limit -> 429.

All Supabase calls use the caller's OWN token under Row-Level Security (users can
select + insert their own usage rows, but not update/delete), so no service-role
key is needed. Config comes from environment variables (set on Render):
  SUPABASE_URL, SUPABASE_ANON_KEY (publishable), FREE_DAILY_LIMIT.
If SUPABASE_URL/ANON are not both present, enforcement is OFF (local dev /
backward compatible).
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
FREE_DAILY_LIMIT = int(os.environ.get("FREE_DAILY_LIMIT", "15"))


def enforcement_enabled() -> bool:
    return bool(SUPABASE_URL and SUPABASE_ANON_KEY)


def bearer_token(authorization: Optional[str]) -> Optional[str]:
    if authorization and authorization.lower().startswith("bearer "):
        return authorization.split(" ", 1)[1].strip()
    return None


def _user_headers(token: str, extra: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    headers = {"apikey": SUPABASE_ANON_KEY, "Authorization": "Bearer " + token}
    if extra:
        headers.update(extra)
    return headers


# --- token validation (short in-memory cache so we don't call Supabase every ask) ---
_token_cache: Dict[str, Tuple[str, float]] = {}


def verify_user(token: Optional[str]) -> Optional[str]:
    """Return the Supabase user id for a valid access token, else None."""
    if not token:
        return None
    now = time.time()
    cached = _token_cache.get(token)
    if cached and cached[1] > now:
        return cached[0]
    req = urllib.request.Request(SUPABASE_URL + "/auth/v1/user", headers=_user_headers(token))
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


def usage_today(token: str) -> int:
    url = (
        SUPABASE_URL
        + "/rest/v1/question_usage?select=id&created_at=gte."
        + urllib.parse.quote(_today_start_iso())
    )
    req = urllib.request.Request(url, headers=_user_headers(token, {"Prefer": "count=exact", "Range": "0-0"}))
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            content_range = resp.headers.get("Content-Range", "")  # e.g. "0-0/12" or "*/12"
        total = content_range.split("/")[-1]
        return int(total) if total.isdigit() else 0
    except Exception:
        return 0  # fail-open on transient counter errors (auth gate still applies)


def _record_question(user_id: str, token: str) -> None:
    req = urllib.request.Request(
        SUPABASE_URL + "/rest/v1/question_usage",
        data=json.dumps({"user_id": user_id}).encode("utf-8"),
        method="POST",
        headers=_user_headers(token, {"Content-Type": "application/json", "Prefer": "return=minimal"}),
    )
    try:
        urllib.request.urlopen(req, timeout=10).read()
    except Exception:
        pass


def check_and_consume(user_id: str, token: str) -> Tuple[bool, int, int]:
    """(allowed, used_after, limit). Records the question when allowed."""
    used = usage_today(token)
    if used >= FREE_DAILY_LIMIT:
        return (False, used, FREE_DAILY_LIMIT)
    _record_question(user_id, token)
    return (True, used + 1, FREE_DAILY_LIMIT)
