"""Rebuild reference/universities.json from the official U.S. Dept. of Education
College Scorecard API (the complete Title-IV institution list, ~6k schools).

Reads the API key from the SCORECARD_API_KEY environment variable (never commit
a key). Preserves curated seed entries (their stable ids + international_office_url)
by de-duplicating on domain.

Usage:
    SCORECARD_API_KEY=your_key python -m scripts.fetch_scorecard
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
import urllib.request
from urllib.parse import urlparse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "reference", "universities.json")
API = "https://api.data.gov/ed/collegescorecard/v1/schools.json"
FIELDS = "id,school.name,school.city,school.state,school.school_url"


def slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:70] or "school"


def domain_of(url: str) -> str:
    if not url:
        return ""
    host = (urlparse(url if "//" in url else "//" + url).hostname or "").lower()
    return host[4:] if host.startswith("www.") else host


def fetch_page(key: str, page: int):
    qs = (
        "?fields={f}&school.operating=1&per_page=100&page={p}&api_key={k}"
    ).format(f=FIELDS, p=page, k=key)
    with urllib.request.urlopen(API + qs, timeout=60) as resp:
        return json.load(resp)


def main() -> int:
    key = os.environ.get("SCORECARD_API_KEY", "").strip()
    if not key:
        print("Set SCORECARD_API_KEY in the environment.")
        return 1

    with open(OUT, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    seed = data["universities"]
    by_domain = {u["domain"]: u for u in seed if u.get("domain")}
    used_ids = {u["id"] for u in seed}
    curated = [u for u in seed if u.get("international_office_url")]

    result = fetch_page(key, 0)
    total = result["metadata"]["total"]
    pages = (total // 100) + 1
    print("College Scorecard total operating institutions:", total, "(", pages, "pages )")

    merged = {u["domain"] or u["name"]: u for u in seed}
    added = 0
    for page in range(pages):
        res = result if page == 0 else fetch_page(key, page)
        for r in res.get("results", []):
            name = (r.get("school.name") or "").strip()
            if not name:
                continue
            dom = domain_of(r.get("school.school_url") or "")
            dedupe_key = dom or name.lower()
            if dedupe_key in merged:
                continue  # keep curated / first-seen
            sid = slug(name)
            while sid in used_ids:
                sid = sid + "-" + (r.get("school.state") or str(r.get("id") or "x")).lower()
            used_ids.add(sid)
            entry = {
                "id": sid,
                "name": name,
                "city": (r.get("school.city") or "").strip(),
                "state": (r.get("school.state") or "").strip(),
                "domain": dom,
                "main_url": ("https://" + dom) if dom else None,
                "international_office_url": None,
            }
            merged[dedupe_key] = entry
            added += 1
        if page % 10 == 0:
            print("  page {}/{} … {} total".format(page, pages - 1, len(merged)))
        time.sleep(0.1)

    universities = sorted(merged.values(), key=lambda u: u["name"].lower())
    data["universities"] = universities
    data["note"] = (
        "U.S. universities for the onboarding picker, rebuilt from the official "
        "U.S. Dept. of Education College Scorecard (operating Title-IV institutions). "
        "Curated entries (with international_office_url) are preserved. "
        "international_office_url is set only for schools whose office guidance is "
        "curated into the knowledge base (manifest 'scope: university')."
    )
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
    print("Done. {} total schools ({} newly added, {} curated preserved).".format(
        len(universities), added, len(curated)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
