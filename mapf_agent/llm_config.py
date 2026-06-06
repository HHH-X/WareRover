"""Unified LLM configuration for MAPF Agent and OpenEvolve."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, MutableMapping

DEFAULT_MODEL = "deepseek-v4-flash"
DEFAULT_BASE_URL = "https://api.deepseek.com"
DEFAULT_EVOLVE_PRIMARY_WEIGHT = 0.8
DEFAULT_EVOLVE_SECONDARY_WEIGHT = 0.2

_REPO_ROOT = Path(__file__).resolve().parent.parent
_API_KEY_FILE = _REPO_ROOT / "api_key.txt"


@dataclass(frozen=True)
class LLMSettings:
    model: str = DEFAULT_MODEL
    base_url: str = DEFAULT_BASE_URL
    api_key: str = ""
    evolve_primary_model: str = DEFAULT_MODEL
    evolve_secondary_model: str = DEFAULT_MODEL
    evolve_primary_weight: float = DEFAULT_EVOLVE_PRIMARY_WEIGHT
    evolve_secondary_weight: float = DEFAULT_EVOLVE_SECONDARY_WEIGHT

    def require_api_key(self) -> str:
        if self.api_key:
            return self.api_key
        raise RuntimeError(
            "未找到 API Key：请在项目根目录创建 api_key.txt，"
            "或设置 MAPF_AGENT_API_KEY/OPENAI_API_KEY。"
        )


def _read_api_key_file(path: Path | None = None) -> str:
    key_path = path or _API_KEY_FILE
    if not key_path.is_file():
        return ""
    return key_path.read_text(encoding="utf-8").strip()


def _first_text(*values: Any) -> str:
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return ""


def load_llm_settings(*, env: Mapping[str, str] | None = None) -> LLMSettings:
    """Load LLM settings from constants, environment variables, and api_key.txt."""
    env_map = env if env is not None else os.environ
    model = _first_text(
        env_map.get("MAPF_AGENT_MODEL"),
        DEFAULT_MODEL,
    )
    base_url = _first_text(
        env_map.get("MAPF_AGENT_BASE_URL"),
        env_map.get("OPENAI_BASE_URL"),
        env_map.get("OPENAI_API_BASE"),
        DEFAULT_BASE_URL,
    )
    api_key = _first_text(
        env_map.get("MAPF_AGENT_API_KEY"),
        env_map.get("OPENAI_API_KEY"),
        _read_api_key_file(),
    )
    evolve_primary_model = _first_text(
        env_map.get("MAPF_AGENT_EVOLVE_PRIMARY_MODEL"),
        model,
    )
    evolve_secondary_model = _first_text(
        env_map.get("MAPF_AGENT_EVOLVE_SECONDARY_MODEL"),
        evolve_primary_model,
    )

    return LLMSettings(
        model=model,
        base_url=base_url,
        api_key=api_key,
        evolve_primary_model=evolve_primary_model,
        evolve_secondary_model=evolve_secondary_model,
        evolve_primary_weight=DEFAULT_EVOLVE_PRIMARY_WEIGHT,
        evolve_secondary_weight=DEFAULT_EVOLVE_SECONDARY_WEIGHT,
    )


def build_openai_client_kwargs(settings: LLMSettings | None = None) -> dict[str, Any]:
    settings = settings or load_llm_settings()
    kwargs: dict[str, Any] = {"api_key": settings.require_api_key()}
    if settings.base_url:
        kwargs["base_url"] = settings.base_url
    return kwargs


def apply_to_environment(
    settings: LLMSettings | None = None,
    env: MutableMapping[str, str] | None = None,
) -> LLMSettings:
    """Populate common OpenAI-compatible env vars for downstream libraries."""
    settings = settings or load_llm_settings()
    target_env = env if env is not None else os.environ
    target_env["OPENAI_API_KEY"] = settings.require_api_key()
    if settings.base_url:
        target_env["OPENAI_BASE_URL"] = settings.base_url
        target_env["OPENAI_API_BASE"] = settings.base_url
    if settings.model:
        target_env["MAPF_AGENT_MODEL"] = settings.model
    return settings


def _yaml_string(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def render_openevolve_config(template: str, settings: LLMSettings | None = None) -> str:
    settings = settings or load_llm_settings()
    replacements = {
        "{llm_primary_model}": _yaml_string(settings.evolve_primary_model),
        "{llm_secondary_model}": _yaml_string(settings.evolve_secondary_model),
        "{llm_primary_weight}": str(settings.evolve_primary_weight),
        "{llm_secondary_weight}": str(settings.evolve_secondary_weight),
        "{llm_api_base}": _yaml_string(settings.base_url),
    }
    rendered = template
    for placeholder, value in replacements.items():
        rendered = rendered.replace(placeholder, value)
    return rendered
