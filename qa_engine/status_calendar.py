"""Visa status calendar — cited, rule-based milestones from dates the student enters.

Given key dates (I-20 program end, OPT EAD, I-94, visa), this computes the
important F-1 milestones — grace period, post-completion OPT application window,
STEM OPT filing window, unemployment limits — each tied to an official source.

It intentionally reflects BOTH regimes during the 2026 transition:
  * current rules (duration of status, 60-day grace), and
  * the DHS final rule effective 2026-09-15 (fixed admission period, I-20 end
    capped at 4 years, 30-day grace, new Extension of Stay).

Adjustment of Status (green card) is NOT modeled — it is individualized attorney
territory; the calendar only returns a cited informational pointer.

No dates are stored or logged; this is a pure function over the request.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

from ingestion.chunker import load_manifest

DS_ELIMINATION_DATE = date(2026, 9, 15)

_manifest_by_id: Optional[Dict[str, Any]] = None


def _cite(source_id: Optional[str]) -> Optional[Dict[str, str]]:
    global _manifest_by_id
    if source_id is None:
        return None
    if _manifest_by_id is None:
        _manifest_by_id = {s["id"]: s for s in load_manifest()["sources"]}
    s = _manifest_by_id.get(source_id)
    if not s:
        return None
    return {"source_id": source_id, "title": s["title"], "url": s["url"]}


def _parse(d: Optional[str]) -> Optional[date]:
    if not d:
        return None
    try:
        return datetime.strptime(d[:10], "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


def _add_days(d: date, n: int) -> date:
    return d + timedelta(days=n)


def _add_years(d: date, n: int) -> date:
    try:
        return d.replace(year=d.year + n)
    except ValueError:  # Feb 29
        return d.replace(year=d.year + n, day=28)


@dataclass
class Milestone:
    key: str
    label: str
    type: str  # "date" | "window" | "counter" | "info"
    detail: str
    date: Optional[str] = None
    end_date: Optional[str] = None
    status: str = "future"  # "past" | "soon" | "future" | "info"
    citation: Optional[Dict[str, str]] = None


def _status(d: Optional[date], today: date) -> str:
    if d is None:
        return "info"
    if d < today:
        return "past"
    if (d - today).days <= 90:
        return "soon"
    return "future"


def compute_calendar(inp: Dict[str, Any]) -> Dict[str, Any]:
    today = _parse(inp.get("as_of")) or date.today()
    prog_start = _parse(inp.get("program_start_date"))
    prog_end = _parse(inp.get("program_end_date"))
    opt_end = _parse(inp.get("opt_ead_end_date"))
    opt_start = _parse(inp.get("opt_ead_start_date"))
    i94_end = _parse(inp.get("i94_end_date"))
    visa_exp = _parse(inp.get("visa_expiry_date"))
    is_stem = bool(inp.get("is_stem"))

    ms: List[Milestone] = []

    def add(key, label, typ, detail, d=None, end=None, cite_id=None):
        ms.append(Milestone(
            key=key, label=label, type=typ, detail=detail,
            date=d.isoformat() if d else None,
            end_date=end.isoformat() if end else None,
            status=_status(d, today) if typ != "counter" else "info",
            citation=_cite(cite_id),
        ))

    if prog_end:
        add("program_end", "Program end date (on your I-20)", "date",
            "The completion date of your program of study on your Form I-20. Many key deadlines are measured from this date.",
            d=prog_end, cite_id="dhs_ds_elimination")

        # Grace period — both regimes.
        add("grace_current", "Grace period ends — current rule (60 days)", "date",
            "Under the current 'duration of status' rules, F-1 students have a 60-day grace period after the program end date to depart, transfer, or change status.",
            d=_add_days(prog_end, 60), cite_id="uscis_opt")
        add("grace_new", "Grace period ends — new rule from Sep 15, 2026 (30 days)", "date",
            "Under the DHS final rule effective 2026-09-15, the grace period after the program end date is 30 days (not 60). Confirm which rule applies to you with your DSO.",
            d=_add_days(prog_end, 30), cite_id="dhs_ds_elimination")

        # Fixed admission end (new rule): I-20 end capped at 4 years from start.
        if prog_start:
            fixed_end = min(prog_end, _add_years(prog_start, 4))
            add("fixed_admission_end", "Fixed admission end — new rule (max 4 years)", "date",
                "Under the new rule you are admitted until your I-20 program end date, but not to exceed 4 years from your start date. If your program is longer, you would need an Extension of Stay from USCIS.",
                d=fixed_end, cite_id="dhs_ds_elimination")

        # Post-completion OPT application window.
        add("opt_window", "Post-completion OPT application window", "window",
            "You may file Form I-765 for post-completion OPT no earlier than 90 days before your program end date and no later than 60 days after it — and within 30 days of your DSO's SEVIS recommendation.",
            d=_add_days(prog_end, -90), end=_add_days(prog_end, 60), cite_id="uscis_opt")

    if opt_end:
        add("opt_ead_end", "OPT work authorization ends (EAD expires)", "date",
            "Your post-completion OPT employment authorization ends on this date.",
            d=opt_end, cite_id="uscis_opt")
        add("opt_grace", "Grace period after OPT ends", "date",
            "After OPT ends there is currently a 60-day grace period (30 days under the new rule from 2026-09-15). Confirm with your DSO.",
            d=_add_days(opt_end, 60), cite_id="uscis_opt")
        if is_stem:
            add("stem_window", "STEM OPT extension filing window", "window",
                "If your degree is a DHS-designated STEM field and your employer is enrolled in E-Verify, you may file Form I-765 for the 24-month STEM extension up to 90 days before your OPT EAD expires — and it must be filed before the EAD expires. Filing on time lets you keep working for up to 180 days while it is pending.",
                d=_add_days(opt_end, -90), end=opt_end, cite_id="uscis_stem_opt")

    # Unemployment counters (informational).
    add("unemployment_opt", "Unemployment limit on OPT", "counter",
        "During post-completion OPT you may not accrue more than 90 days of unemployment.",
        cite_id="uscis_opt")
    if is_stem:
        add("unemployment_stem", "Unemployment limit with STEM OPT", "counter",
            "The STEM extension adds 60 more days, for a total of 150 days of unemployment allowed across your entire OPT period.",
            cite_id="uscis_stem_opt")

    if i94_end:
        add("i94_end", "I-94 admission 'until' date", "date",
            "Your most recent I-94 record. If it shows a date (rather than 'D/S'), that is the date your admission is authorized until.",
            d=i94_end, cite_id="dhs_initial_registration")
    if visa_exp:
        add("visa_expiry", "Visa stamp expiration (for entry only)", "date",
            "Your visa STAMP is used to enter the U.S.; it can expire while you remain in valid status. An expired visa stamp is not the same as being out of status — you only need a valid visa to RE-ENTER.",
            d=visa_exp, cite_id=None)

    ms.sort(key=lambda m: (m.date is None, m.date or ""))

    advisories = [
        {
            "text": "Major change: DHS is ending 'duration of status' for F-1 students effective September 15, 2026, replacing it with a fixed admission period (I-20 end date, max 4 years, plus a 30-day grace) and a new USCIS Extension of Stay process. This rule is still subject to Congressional review. Confirm how it affects your dates with your DSO.",
            "citation": _cite("dhs_ds_elimination"),
        },
        {
            "text": "Adjustment of Status (applying for a green card) is highly individual and time-sensitive (priority dates, category, eligibility). This tool does not calculate AOS timelines — consult your DSO and a licensed immigration attorney.",
            "citation": None,
        },
    ]

    return {
        "as_of": today.isoformat(),
        "milestones": [asdict(m) for m in ms],
        "advisories": advisories,
        "disclaimer": (
            "Informational only, not legal advice. These milestones are computed from the dates you entered and "
            "general rules that change and vary by individual. Immigration rules are in transition in 2026 — always "
            "confirm your specific dates and options with your DSO / international student office and, where appropriate, "
            "a licensed immigration attorney."
        ),
    }
