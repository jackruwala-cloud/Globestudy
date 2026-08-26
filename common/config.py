"""Configuration loader.

Loads config.yaml (falling back to config.example.yaml), merges it over
built-in defaults, and lets environment variables override secrets so nothing
sensitive has to live in a file. No API keys are ever hardcoded.
"""
from __future__ import annotations

import copy
import os
from typing import Any, Dict

from common import paths

DEFAULTS: Dict[str, Any] = {
    "retrieval": {
        # "tfidf" is pure-python and always works offline (default).
        # "chroma" uses a local Chroma vector store if chromadb is installed.
        "backend": "tfidf",
        "top_k": 5,
        # Cosine-similarity thresholds (tuned for the tfidf backend).
        # min_score      : if the TOP result is below this, refuse to answer.
        # support_floor  : once answering, include retrieved chunks down to here
        #                  as supporting citations (lower, so on-point secondary
        #                  passages are not dropped).
        # high_conf_score: at/above this the top match is labeled "high".
        "min_score": 0.19,
        "support_floor": 0.10,
        "high_conf_score": 0.28,
        # Near-miss band: partial_floor <= top < min_score shows the CLOSEST cited
        # source, clearly flagged as partial, instead of refusing. Below
        # partial_floor we still refuse (genuinely off-topic).
        "partial_floor": 0.15,
    },
    "qa": {
        # "extractive" (default) composes the answer ONLY from retrieved source
        # text with no LLM, so it can never hallucinate. "llm" uses Claude but
        # is still constrained to answer strictly from retrieved context.
        "mode": "extractive",
        "llm_model": "claude-sonnet-5",
        "max_context_chunks": 4,
        # When the curated KB would refuse (confidence "none"), fall back to a
        # live Perplexity search restricted to OFFICIAL domains, instead of a
        # dead-end. Requires a Perplexity API key. Off unless a key is present.
        "live_fallback": True,
    },
    "anthropic": {
        # Prefer the ANTHROPIC_API_KEY environment variable. Leave blank here.
        "api_key": "",
    },
    "perplexity": {
        # Prefer the PERPLEXITY_API_KEY environment variable. Leave blank here.
        "api_key": "",
        "model": "sonar",
    },
}


def _deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    out = copy.deepcopy(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def _load_yaml(path: str) -> Dict[str, Any]:
    if not os.path.exists(path):
        return {}
    try:
        import yaml  # type: ignore
    except ImportError:
        # PyYAML not installed yet — fall back to built-in defaults rather than
        # failing. Install it (pip install pyyaml) to read the config file.
        print("[config] PyYAML not installed; using built-in defaults for now.")
        return {}
    with open(path, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


_cache: Dict[str, Any] = {}


def get_config(reload: bool = False) -> Dict[str, Any]:
    if _cache and not reload:
        return _cache

    file_cfg: Dict[str, Any] = {}
    if os.path.exists(paths.CONFIG_PATH):
        file_cfg = _load_yaml(paths.CONFIG_PATH)
    elif os.path.exists(paths.CONFIG_EXAMPLE_PATH):
        file_cfg = _load_yaml(paths.CONFIG_EXAMPLE_PATH)

    cfg = _deep_merge(DEFAULTS, file_cfg)

    # Environment overrides for secrets (never write these to disk).
    env_key = os.environ.get("ANTHROPIC_API_KEY")
    if env_key:
        cfg["anthropic"]["api_key"] = env_key
    env_pplx = os.environ.get("PERPLEXITY_API_KEY")
    if env_pplx:
        cfg["perplexity"]["api_key"] = env_pplx
    env_mode = os.environ.get("QA_MODE")
    if env_mode:
        cfg["qa"]["mode"] = env_mode
    env_backend = os.environ.get("RETRIEVAL_BACKEND")
    if env_backend:
        cfg["retrieval"]["backend"] = env_backend

    _cache.clear()
    _cache.update(cfg)
    return cfg


def get_anthropic_key() -> str:
    return (get_config().get("anthropic", {}) or {}).get("api_key", "") or ""
