"""Source-governance policy: ONLY official sources may enter the knowledge base.

Every source in manifest.json is validated against an allowlist of official
domains before it can be built into the retrievable index. Anything else — blogs,
forums, law-firm marketing pages, "study abroad" aggregators, AI summaries — is
rejected. This is what makes "we only cite official sources" an enforced rule,
not just a promise.

Allowed:
  * U.S. federal government agencies (.gov): IRS, USCIS, DHS/SEVP (incl.
    studyinthestates.dhs.gov), ICE, Department of Labor, Department of State,
    Social Security Administration, CFPB.
  * Accredited U.S. universities and colleges (.edu) — a school's own official
    international-student-office pages, added per school.

To add a school's official page, add a manifest entry whose URL host ends in
".edu". To broaden/narrow the federal allowlist, edit ALLOWED_GOV_DOMAINS.
"""
from __future__ import annotations

from typing import Any, Dict, List, Tuple
from urllib.parse import urlparse

# Explicit federal agency domains we accept (host equals, or is a subdomain of).
ALLOWED_GOV_DOMAINS = [
    "irs.gov",
    "uscis.gov",
    "dhs.gov",            # includes studyinthestates.dhs.gov
    "ice.gov",            # SEVP / SEVIS
    "dol.gov",            # Department of Labor
    "state.gov",          # Dept. of State (travel.state.gov visas)
    "ssa.gov",            # Social Security (SSN)
    "federalregister.gov",  # official U.S. government publication of record (rules)
    "consumerfinance.gov",  # CFPB — federal agency (financial-literacy items)
]

# University sources are allowed by TLD (a school's own official site).
ALLOWED_TLDS = [".edu"]


def _host(url: str) -> str:
    return (urlparse(url).hostname or "").lower()


def is_official(url: str) -> bool:
    host = _host(url)
    if not host:
        return False
    if any(host == d or host.endswith("." + d) for d in ALLOWED_GOV_DOMAINS):
        return True
    if any(host.endswith(tld) for tld in ALLOWED_TLDS):
        return True
    return False


def validate_sources(sources: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Return (ok, violations). A violation is a source whose URL is not official."""
    ok, violations = [], []
    for s in sources:
        (ok if is_official(s.get("url", "")) else violations).append(s)
    return ok, violations
