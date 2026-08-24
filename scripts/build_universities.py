"""Build / expand reference/universities.json from official data.

The seed list in reference/universities.json is a curated set of U.S. schools
with large international enrollments. To expand it to the full universe of U.S.
institutions, use the official U.S. Department of Education College Scorecard
open data (a .gov source), which lists every Title-IV institution with its name,
city, state, and main website.

Two ways to get the source data (both official):
  1. Bulk CSV: https://collegescorecard.ed.gov/data/  (download "Most Recent
     Institution-Level Data"; the relevant columns are INSTNM, CITY, STABBR,
     INSTURL).
  2. API: https://api.data.gov/ed/collegescorecard/ (needs a free api.data.gov
     key; query fields school.name, school.city, school.state, school.school_url).

Usage (with a downloaded College Scorecard institution CSV):
    python -m scripts.build_universities --csv Most-Recent-Cohorts-Institution.csv

This MERGES rows into reference/universities.json, keeping any curated
international_office_url values already present (matched by domain). It never
overwrites a curated international-office URL. 'international_office_url' stays
null for newly added schools until their office guidance is curated into the
knowledge base (see manifest 'scope: university').
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
from urllib.parse import urlparse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "reference", "universities.json")


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:60]


def _domain(url: str) -> str:
    host = (urlparse(url if "//" in url else "//" + url).hostname or "").lower()
    return host[4:] if host.startswith("www.") else host


def load_current() -> dict:
    with open(OUT, "r", encoding="utf-8") as fh:
        return json.load(fh)


def main() -> int:
    parser = argparse.ArgumentParser(description="Expand universities.json from College Scorecard CSV.")
    parser.add_argument("--csv", required=True, help="College Scorecard institution CSV path")
    args = parser.parse_args()

    data = load_current()
    by_domain = {u["domain"]: u for u in data["universities"] if u.get("domain")}

    added = 0
    with open(args.csv, "r", encoding="utf-8", errors="replace") as fh:
        for row in csv.DictReader(fh):
            name = (row.get("INSTNM") or "").strip()
            url = (row.get("INSTURL") or "").strip()
            if not name or not url:
                continue
            dom = _domain(url)
            if not dom or dom in by_domain:
                continue  # keep curated entries untouched
            entry = {
                "id": _slug(name),
                "name": name,
                "city": (row.get("CITY") or "").strip(),
                "state": (row.get("STABBR") or "").strip(),
                "domain": dom,
                "main_url": "https://" + dom,
                "international_office_url": None,
            }
            data["universities"].append(entry)
            by_domain[dom] = entry
            added += 1

    data["universities"].sort(key=lambda u: u["name"])
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
    print("Added {} schools. Total: {}.".format(added, len(data["universities"])))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
