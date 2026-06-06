from __future__ import annotations

import pytest

from mapf_agent import llm
from mapf_agent.llm_config import DEFAULT_BASE_URL, DEFAULT_MODEL
from mapf_agent.llm_config import (
    apply_to_environment,
    build_openai_client_kwargs,
    load_llm_settings,
    render_openevolve_config,
)


def test_load_llm_settings_uses_defaults_and_api_key_file(monkeypatch, tmp_path):
    key_file = tmp_path / "api_key.txt"
    key_file.write_text("file-key\n", encoding="utf-8")
    monkeypatch.setattr("mapf_agent.llm_config._API_KEY_FILE", key_file)

    settings = load_llm_settings(env={})

    assert settings.api_key == "file-key"
    assert settings.base_url == DEFAULT_BASE_URL
    assert settings.model == DEFAULT_MODEL
    assert settings.evolve_primary_model == DEFAULT_MODEL
    assert settings.evolve_secondary_model == DEFAULT_MODEL


def test_load_llm_settings_prefers_mapf_env(monkeypatch):
    monkeypatch.setenv("MAPF_AGENT_API_KEY", "env-key")
    monkeypatch.setenv("MAPF_AGENT_BASE_URL", "https://env.example/v1")
    monkeypatch.setenv("MAPF_AGENT_MODEL", "env-model")
    monkeypatch.setenv("MAPF_AGENT_EVOLVE_PRIMARY_MODEL", "evolve-a")
    monkeypatch.setenv("MAPF_AGENT_EVOLVE_SECONDARY_MODEL", "evolve-b")

    settings = load_llm_settings()

    assert settings.api_key == "env-key"
    assert settings.base_url == "https://env.example/v1"
    assert settings.model == "env-model"
    assert settings.evolve_primary_model == "evolve-a"
    assert settings.evolve_secondary_model == "evolve-b"


def test_openai_env_aliases_are_supported(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "openai-key")
    monkeypatch.setenv("OPENAI_API_BASE", "https://openai-base.example/v1")

    settings = load_llm_settings()

    assert settings.api_key == "openai-key"
    assert settings.base_url == "https://openai-base.example/v1"
    assert settings.model == DEFAULT_MODEL


def test_build_client_kwargs_requires_key(monkeypatch, tmp_path):
    monkeypatch.setattr("mapf_agent.llm_config._API_KEY_FILE", tmp_path / "missing-key.txt")
    settings = load_llm_settings(env={})

    with pytest.raises(RuntimeError, match="未找到 API Key"):
        build_openai_client_kwargs(settings)


def test_apply_to_environment_sets_downstream_openai_vars():
    env: dict[str, str] = {}
    settings = load_llm_settings(
        env={
            "MAPF_AGENT_API_KEY": "key",
            "MAPF_AGENT_BASE_URL": "https://base.example/v1",
            "MAPF_AGENT_MODEL": "model",
        }
    )

    apply_to_environment(settings, env)

    assert env["OPENAI_API_KEY"] == "key"
    assert env["OPENAI_BASE_URL"] == "https://base.example/v1"
    assert env["OPENAI_API_BASE"] == "https://base.example/v1"
    assert env["MAPF_AGENT_MODEL"] == "model"


def test_render_openevolve_config_uses_unified_settings(monkeypatch):
    monkeypatch.setenv("MAPF_AGENT_MODEL", "agent-model")
    monkeypatch.setenv("MAPF_AGENT_BASE_URL", "https://base.example/v1")
    monkeypatch.setenv("MAPF_AGENT_EVOLVE_PRIMARY_MODEL", "evolve-a")
    monkeypatch.setenv("MAPF_AGENT_EVOLVE_SECONDARY_MODEL", "evolve-b")

    settings = load_llm_settings()
    rendered = render_openevolve_config(
        "\n".join(
            [
                "primary_model: {llm_primary_model}",
                "primary_model_weight: {llm_primary_weight}",
                "secondary_model: {llm_secondary_model}",
                "secondary_model_weight: {llm_secondary_weight}",
                "api_base: {llm_api_base}",
            ]
        ),
        settings,
    )

    assert 'primary_model: "evolve-a"' in rendered
    assert "primary_model_weight: 0.8" in rendered
    assert 'secondary_model: "evolve-b"' in rendered
    assert "secondary_model_weight: 0.2" in rendered
    assert 'api_base: "https://base.example/v1"' in rendered


def test_llm_model_reads_unified_settings(monkeypatch):
    monkeypatch.setenv("MAPF_AGENT_MODEL", "env-model")

    assert llm._model() == "env-model"
