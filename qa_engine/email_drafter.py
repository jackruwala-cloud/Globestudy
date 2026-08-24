"""Draft emails to a DSO or academic advisor from a short prompt.

Deterministic templates by default (work offline, predictable, professional).
If an Anthropic key is configured, an LLM can polish a free-text request instead.
The output is always a DRAFT for the student to review and send themselves — this
module never sends anything.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any, Dict, Optional

from common import config


@dataclass
class EmailDraft:
    subject: str
    body: str
    recipient_hint: str
    request_type: str
    note: str = "This is a draft — review and edit it before sending. Never share passwords or full financial details by email."

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# request_type -> (recipient_hint, subject, body-builder)
_TEMPLATES = {
    "new_i20_major_change": {
        "recipient": "Your DSO / international student office",
        "subject": "Request: Updated Form I-20 after a major change",
    },
    "travel_signature": {
        "recipient": "Your DSO / international student office",
        "subject": "Request: I-20 travel signature before international travel",
    },
    "cpt_recommendation": {
        "recipient": "Your DSO / international student office",
        "subject": "Request: CPT authorization for an upcoming internship",
    },
    "opt_recommendation": {
        "recipient": "Your DSO / international student office",
        "subject": "Request: OPT recommendation and I-20 endorsement",
    },
    "reduced_course_load": {
        "recipient": "Your DSO / international student office",
        "subject": "Request: Reduced Course Load authorization",
    },
    "advisor_meeting": {
        "recipient": "Your academic advisor",
        "subject": "Request: Meeting to discuss my academic plan",
    },
    "general_dso": {
        "recipient": "Your DSO / international student office",
        "subject": "Question about my F-1 status",
    },
}

_INTENT_RULES = [
    ("travel_signature", ["travel", "traveling", "re-entry", "reentry", "trip abroad"]),
    ("new_i20_major_change", ["major", "change of major", "add major", "drop major", "program change", "new i-20", "new i20", "updated i-20"]),
    ("cpt_recommendation", ["cpt", "internship", "curricular practical"]),
    ("opt_recommendation", ["opt", "optional practical", "work authorization after"]),
    ("reduced_course_load", ["reduced course load", "rcl", "drop below full", "part time", "part-time"]),
    ("advisor_meeting", ["advisor", "adviser", "academic plan", "course selection", "schedule a meeting"]),
]


def infer_request_type(prompt: str) -> str:
    text = (prompt or "").lower()
    for rtype, keys in _INTENT_RULES:
        if any(k in text for k in keys):
            return rtype
    return "general_dso"


def _greeting(fields: Dict[str, str]) -> str:
    name = fields.get("recipient_name")
    return "Dear {},".format(name) if name else "Dear [DSO / Advisor name],"


def _signoff(fields: Dict[str, str]) -> str:
    parts = ["Thank you for your time and help.", "", "Best regards,"]
    parts.append(fields.get("student_name", "[Your name]"))
    idline = []
    if fields.get("student_id"):
        idline.append("Student ID: {}".format(fields["student_id"]))
    if fields.get("sevis_id"):
        idline.append("SEVIS ID: {}".format(fields["sevis_id"]))
    if fields.get("program"):
        idline.append("Program: {}".format(fields["program"]))
    if idline:
        parts.append(" · ".join(idline))
    return "\n".join(parts)


def _body_for(request_type: str, fields: Dict[str, str]) -> str:
    g = _greeting(fields)
    detail = fields.get("details", "").strip()
    name = fields.get("student_name", "[your name]")

    bodies = {
        "new_i20_major_change": (
            "I am an F-1 student and my academic program has changed"
            + (" ({}).".format(detail) if detail else ".")
            + " Could you please update my SEVIS record and issue an updated Form I-20"
            " reflecting this change? Please let me know if you need anything from me"
            " or my academic advisor to process the update."
        ),
        "travel_signature": (
            "I am planning to travel internationally"
            + (" ({}).".format(detail) if detail else "")
            + " and would like to make sure my Form I-20 has a valid travel signature"
            " for re-entry. Could you please advise on how to obtain an updated travel"
            " signature, and let me know if I need to submit anything or schedule an"
            " appointment?"
        ),
        "cpt_recommendation": (
            "I have an internship opportunity that is related to my program"
            + (" ({}).".format(detail) if detail else ".")
            + " Since it appears to require Curricular Practical Training (CPT)"
            " authorization before I can begin, could you please let me know the steps,"
            " required documents, and timeline to get CPT authorized on my I-20?"
        ),
        "opt_recommendation": (
            "I am approaching the completion of my program"
            + (" ({}).".format(detail) if detail else ".")
            + " I would like to apply for post-completion OPT and understand I need an"
            " OPT recommendation and an updated I-20 from your office before filing Form"
            " I-765. Could you please advise on the process and the earliest date I can apply?"
        ),
        "reduced_course_load": (
            "I would like to ask about a Reduced Course Load"
            + (" for the following reason: {}.".format(detail) if detail else ".")
            + " I understand an RCL generally needs authorization before I drop below a"
            " full course load to keep my status. Could you please advise whether I qualify"
            " and what documentation is required?"
        ),
        "advisor_meeting": (
            "I would like to schedule a short meeting to discuss my academic plan"
            + (" ({}).".format(detail) if detail else ".")
            + " Please let me know a few times that work for you, and I will make one of"
            " them work. Thank you."
        ),
        "general_dso": (
            (detail if detail else "I have a question about my F-1 status and would"
             " appreciate your guidance.")
        ),
    }
    core = bodies.get(request_type, bodies["general_dso"])
    return "{}\n\nMy name is {} and I am writing as an F-1 international student.\n\n{}\n\n{}".format(
        g, name, core, _signoff(fields)
    )


def _llm_polish(prompt: str, draft: EmailDraft, cfg: Dict[str, Any]) -> Optional[EmailDraft]:
    api_key = (cfg.get("anthropic", {}) or {}).get("api_key", "")
    if not api_key:
        return None
    try:
        import anthropic  # type: ignore
        client = anthropic.Anthropic(api_key=api_key)
        system = (
            "You draft short, polite, professional emails from an international (F-1) "
            "student to their DSO or academic advisor. Keep it concise and specific. "
            "Do not invent policies, dates, or ID numbers. Output only the email body, "
            "starting with a greeting and ending with a sign-off placeholder."
        )
        user = "Student's request: {}\n\nHere is a template to improve, keep it factual:\n{}".format(prompt, draft.body)
        resp = client.messages.create(
            model=cfg["qa"]["llm_model"], max_tokens=500, system=system,
            messages=[{"role": "user", "content": user}],
        )
        text = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text").strip()
        if text:
            draft.body = text
            return draft
    except Exception:
        return None
    return None


def draft_email(prompt: str = "", request_type: str = "", fields: Optional[Dict[str, str]] = None,
                use_llm: bool = False) -> EmailDraft:
    fields = fields or {}
    rtype = request_type or infer_request_type(prompt)
    if rtype not in _TEMPLATES:
        rtype = "general_dso"
    tmpl = _TEMPLATES[rtype]
    draft = EmailDraft(
        subject=tmpl["subject"],
        body=_body_for(rtype, fields),
        recipient_hint=tmpl["recipient"],
        request_type=rtype,
    )
    if use_llm and prompt:
        polished = _llm_polish(prompt, draft, config.get_config())
        if polished:
            return polished
    return draft
