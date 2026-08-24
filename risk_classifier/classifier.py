"""Rule-based risk classifier.

Categorizes each incoming question by stakes so the UI can attach the right
guidance. HIGH-stakes questions (visa status, tax filing specifics, work
authorization) always get a "verify with a licensed professional / your DSO"
notice. The full matching reasoning is returned so it can be logged and tuned.

Policy: default to HIGH when uncertain — over-warning is safer than presenting
a visa/tax answer as the final word.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Dict, List

_RULES_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "rules.yaml")

# Fallback defaults if rules.yaml or PyYAML is unavailable.
_FALLBACK = {
    "high_stakes": {
        "keywords": [
            "visa", "status", "immigration", "opt", "cpt", "stem", "ead",
            "work authorization", "sevis", "i-765", "i-20", "tax", "taxes",
            "taxed", "filing", "1040", "8843", "1042", "fica", "social security",
            "medicare", "withholding", "treaty", "resident", "nonresident",
            "ssn", "itin", "refund", "scholarship", "hours can i work",
        ]
    },
    "low_stakes": {
        "keywords": [
            "budget", "budgeting", "saving", "remittance", "send money",
            "exchange rate", "credit score", "bank account", "cost of living",
        ]
    },
}


def _load_rules() -> Dict:
    try:
        import yaml  # type: ignore

        with open(_RULES_PATH, "r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
        if data.get("high_stakes", {}).get("keywords"):
            return data
    except Exception:
        pass
    return _FALLBACK


_RULES = _load_rules()


@dataclass
class RiskResult:
    level: str  # "HIGH" or "LOW"
    matched_high: List[str] = field(default_factory=list)
    matched_low: List[str] = field(default_factory=list)
    reasoning: str = ""

    def to_dict(self) -> Dict:
        return {
            "level": self.level,
            "matched_high": self.matched_high,
            "matched_low": self.matched_low,
            "reasoning": self.reasoning,
        }


def _find_matches(text: str, keywords: List[str]) -> List[str]:
    hits: List[str] = []
    for kw in keywords:
        kw = str(kw)  # YAML may parse bare numbers (1040, 8843) as ints.
        # Word-boundary match where the keyword is a single alnum token,
        # substring match for multi-word phrases.
        if re.search(r"\b" + re.escape(kw) + r"\b", text):
            hits.append(kw)
    return hits


def classify(question: str) -> RiskResult:
    text = (question or "").lower()

    high = _find_matches(text, _RULES.get("high_stakes", {}).get("keywords", []))
    low = _find_matches(text, _RULES.get("low_stakes", {}).get("keywords", []))

    if high:
        reasoning = (
            "HIGH: matched high-stakes term(s): {}. These touch visa status, tax "
            "filing, or work-authorization limits, so a professional-verification "
            "notice is required.".format(", ".join(high))
        )
        return RiskResult("HIGH", high, low, reasoning)

    if low:
        reasoning = (
            "LOW: matched low-stakes term(s): {}, and no high-stakes terms. Treated "
            "as general financial literacy — still answered only from cited sources."
            .format(", ".join(low))
        )
        return RiskResult("LOW", high, low, reasoning)

    reasoning = (
        "HIGH (default): no low-stakes terms matched and stakes are unclear. "
        "Defaulting to HIGH so the answer is not presented as the final word."
    )
    return RiskResult("HIGH", high, low, reasoning)
