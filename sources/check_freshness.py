"""Primary-source freshness checker.

Fetches each source URL, reduces it to visible text, and hashes that text. If the
hash differs from the last recorded hash, the source is flagged CHANGED so stale
guidance can be reviewed and re-curated. Sources not re-checked in a while are
flagged STALE. Results are written to sources/freshness_state.json and read by
the admin view.

Usage:
    python -m sources.check_freshness            # check all sources
    python -m sources.check_freshness --offline  # only report staleness, no network
    python -m sources.check_freshness --stale-days 30

Uses only the Python standard library (urllib), so it needs no extra packages.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Any, Dict

from common import paths
from ingestion.chunker import load_manifest

_USER_AGENT = "intl-student-advisor-freshness-check/1.0 (+research tool)"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _visible_text(html: str) -> str:
    """Crude HTML -> text so the hash tracks content, not markup/whitespace noise."""
    html = re.sub(r"(?is)<(script|style|noscript).*?</\1>", " ", html)
    text = re.sub(r"(?s)<[^>]+>", " ", html)
    text = re.sub(r"&[a-z0-9#]+;", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"\s+", " ", text).strip().lower()
    return text


def _fetch(url: str, timeout: int = 20) -> Dict[str, Any]:
    req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            charset = resp.headers.get_content_charset() or "utf-8"
            html = raw.decode(charset, errors="replace")
            text = _visible_text(html)
            return {
                "ok": True,
                "http_status": resp.status,
                "content_hash": hashlib.sha256(text.encode("utf-8")).hexdigest(),
                "text_len": len(text),
            }
    except urllib.error.HTTPError as exc:
        return {"ok": False, "http_status": exc.code, "error": "HTTP {}".format(exc.code)}
    except Exception as exc:  # network, TLS, DNS, timeout...
        return {"ok": False, "http_status": None, "error": str(exc)}


def _load_state() -> Dict[str, Any]:
    try:
        with open(paths.FRESHNESS_STATE_PATH, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"sources": {}}


def _save_state(state: Dict[str, Any]) -> None:
    with open(paths.FRESHNESS_STATE_PATH, "w", encoding="utf-8") as fh:
        json.dump(state, fh, ensure_ascii=False, indent=2)


def _days_since(iso_ts: str) -> float:
    try:
        # Accept both date and full ISO timestamps.
        if len(iso_ts) == 10:
            dt = datetime.strptime(iso_ts, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        else:
            dt = datetime.fromisoformat(iso_ts)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - dt).total_seconds() / 86400.0
    except Exception:
        return float("inf")


def check(offline: bool = False, stale_days: int = 30) -> Dict[str, Any]:
    manifest = load_manifest()
    state = _load_state()
    state.setdefault("sources", {})
    state["last_run"] = _now_iso()

    summary = {"changed": [], "unchanged": [], "errors": [], "stale": []}

    for src in manifest["sources"]:
        sid = src["id"]
        prev = state["sources"].get(sid, {})
        entry: Dict[str, Any] = dict(prev)
        entry["url"] = src["url"]
        entry["title"] = src["title"]
        entry["retrieved_date"] = src["retrieved_date"]

        if not offline:
            result = _fetch(src["url"])
            entry["last_checked"] = _now_iso()
            entry["http_status"] = result.get("http_status")
            if result["ok"]:
                new_hash = result["content_hash"]
                old_hash = prev.get("content_hash")
                entry["content_hash"] = new_hash
                entry["text_len"] = result["text_len"]
                entry["last_error"] = None
                if old_hash is None:
                    entry["status"] = "baseline"  # first time we see it
                    summary["unchanged"].append(sid)
                elif old_hash != new_hash:
                    entry["status"] = "changed"
                    entry["changed_at"] = _now_iso()
                    summary["changed"].append(sid)
                else:
                    entry["status"] = "unchanged"
                    summary["unchanged"].append(sid)
            else:
                entry["status"] = "error"
                entry["last_error"] = result.get("error")
                summary["errors"].append(sid)

        # Staleness is independent of the fetch (based on last successful check).
        last_checked = entry.get("last_checked")
        if not last_checked or _days_since(last_checked) > stale_days:
            entry["is_stale"] = True
            summary["stale"].append(sid)
        else:
            entry["is_stale"] = False

        state["sources"][sid] = entry

    _save_state(state)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Check primary-source freshness.")
    parser.add_argument("--offline", action="store_true", help="skip network, only report staleness")
    parser.add_argument("--stale-days", type=int, default=30, help="flag sources not checked within N days")
    args = parser.parse_args()

    summary = check(offline=args.offline, stale_days=args.stale_days)

    print("Freshness check complete ({}).".format("offline" if args.offline else "online"))
    print("  changed  : {} {}".format(len(summary["changed"]), summary["changed"] or ""))
    print("  unchanged: {}".format(len(summary["unchanged"])))
    print("  errors   : {} {}".format(len(summary["errors"]), summary["errors"] or ""))
    print("  stale    : {} {}".format(len(summary["stale"]), summary["stale"] or ""))
    if summary["changed"]:
        print("\n>>> Review CHANGED sources: the live page differs from what we last curated.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
