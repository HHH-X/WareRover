"""
Environment config helpers.

This module defines how MAPF Agent stores and applies environment-level
simulation configuration without modifying the upstream ``config/settings.py``
file on disk.

Environment config JSON structure (stored under ``config/envs/``):

{
  "env_name": "optional-environment-name",
  "map_file": "config/maps/xxx.json",
  "sim_config": {
    "order_mode": "oneshot" | "continuous_constant" | ...,
    "total_orders_limit": 150,
    "size2_ratio": 0.2,
    "order_processing_timeout": 30,
    "max_steps": 1000,
    "time_step": 1.0,
    "agv_max_speed": 1.0,
    "agv_turn_time_90": 0.0,
    "log_to_file": true,
    "log_to_console": false,
    "force_replan_every_step": false
  }
}

At runtime, values in ``sim_config`` are applied on top of the default
``SimConfig`` values. During a workflow, any per-session overrides from the
agent (``sim_config_delta``) will take precedence over this environment
configuration.
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict

from mapf_agent.config import PROJECT_ROOT


ENV_CONFIG_DIR = os.path.join(PROJECT_ROOT, "config", "envs")


def ensure_env_config_dir() -> str:
    """Ensure the environment config directory exists and return its path."""
    os.makedirs(ENV_CONFIG_DIR, exist_ok=True)
    return ENV_CONFIG_DIR


def build_env_config_payload(map_file: str | None = None) -> Dict[str, Any]:
    """
    Build a full env_config payload from the current in-memory SimConfig.

    The returned dict is suitable for serialization to JSON and later
    re-applied via ``apply_env_config_to_simconfig``.
    """
    from config.settings import SimConfig, OrderMode

    sim = SimConfig  # use class-level defaults / current overrides

    def _order_mode_value(mode: OrderMode) -> str:
        return mode.value if hasattr(mode, "value") else str(mode)

    payload: Dict[str, Any] = {
        "env_name": "",
        "map_file": map_file or getattr(sim, "map_file", ""),
        "sim_config": {
            "order_mode": _order_mode_value(getattr(sim, "order_mode", OrderMode.ONESHOT)),
            "total_orders_limit": int(getattr(sim, "total_orders_limit", 150)),
            "size2_ratio": float(getattr(sim, "size2_ratio", 0.2)),
            "order_processing_timeout": int(getattr(sim, "order_processing_timeout", 30)),
            "max_steps": int(getattr(sim, "max_steps", 1000)),
            "time_step": float(getattr(sim, "time_step", 1.0)),
            "agv_max_speed": float(getattr(sim, "agv_max_speed", 1.0)),
            "agv_turn_time_90": float(getattr(sim, "agv_turn_time_90", 0.0)),
            "log_to_file": bool(getattr(sim, "log_to_file", True)),
            "log_to_console": bool(getattr(sim, "log_to_console", False)),
            "force_replan_every_step": bool(
                getattr(sim, "force_replan_every_step", False)
            ),
        },
    }
    return payload


def save_env_config(env_config: Dict[str, Any], env_name: str | None = None) -> str:
    """
    Save an env_config dict to ``config/envs/<env_name>.json`` and
    return the file path. If ``env_name`` is not provided, a timestamp-based
    name will be used.
    """
    import datetime as _dt

    ensure_env_config_dir()

    name = env_name or env_config.get("env_name") or _dt.datetime.now().strftime(
        "env_%Y%m%d_%H%M%S"
    )
    safe_name = "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in name)
    path = os.path.join(ENV_CONFIG_DIR, f"{safe_name}.json")

    with open(path, "w", encoding="utf-8") as f:
        json.dump(env_config, f, indent=2, ensure_ascii=False)

    return path


def load_env_config(path: str) -> Dict[str, Any]:
    """Load an environment config JSON file."""
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def apply_env_config_to_simconfig(env_config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Apply an env_config's ``sim_config`` section to the in-memory SimConfig.

    Returns a dict of applied fields for logging/inspection. This does *not*
    persist anything back to ``settings.py`` on disk.
    """
    from config.settings import SimConfig, OrderMode

    sim_conf = env_config.get("sim_config") or {}

    field_map = {
        "order_mode": lambda v: setattr(SimConfig, "order_mode", OrderMode(v)),
        "total_orders_limit": lambda v: setattr(
            SimConfig, "total_orders_limit", int(v)
        ),
        "size2_ratio": lambda v: setattr(SimConfig, "size2_ratio", float(v)),
        "order_processing_timeout": lambda v: setattr(
            SimConfig, "order_processing_timeout", int(v)
        ),
        "max_steps": lambda v: setattr(SimConfig, "max_steps", int(v)),
        "time_step": lambda v: setattr(SimConfig, "time_step", float(v)),
        "agv_max_speed": lambda v: setattr(SimConfig, "agv_max_speed", float(v)),
        "agv_turn_time_90": lambda v: setattr(
            SimConfig, "agv_turn_time_90", float(v)
        ),
        "log_to_file": lambda v: setattr(SimConfig, "log_to_file", bool(v)),
        "log_to_console": lambda v: setattr(SimConfig, "log_to_console", bool(v)),
        "force_replan_every_step": lambda v: setattr(
            SimConfig, "force_replan_every_step", bool(v)
        ),
    }

    applied: Dict[str, Any] = {}
    for key, value in sim_conf.items():
        if key in field_map and value is not None:
            try:
                field_map[key](value)
                applied[key] = value
            except Exception:
                # ignore invalid values silently; caller can inspect 'applied'
                continue

    # Optionally apply map_file override if present
    map_file = env_config.get("map_file")
    if map_file:
        try:
            setattr(SimConfig, "map_file", str(map_file))
            applied["map_file"] = str(map_file)
        except Exception:
            pass

    return applied

