"""Compatibility API-key loader."""
from __future__ import annotations

from mapf_agent.llm_config import load_llm_settings


def load_api_key() -> str:
    return load_llm_settings().require_api_key()
