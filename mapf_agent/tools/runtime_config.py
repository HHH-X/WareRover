from __future__ import annotations

"""
Runtime configuration loading and merging for WareRover.

This module provides:

- A generic dataclass merge helper that applies a JSON/dict override
  on top of defaults defined in ``config/settings.py``.
- A ``RuntimeConfig`` aggregate object that holds all relevant
  configuration dataclasses for a simulation run.
- A single entry function ``load_runtime_config`` that:
    * reads an optional JSON config file (see knowledge/env_runtime_config.md),
    * merges it with defaults from ``config/settings.py``,
    * returns a ``RuntimeConfig`` instance.

The goal is to avoid modifying ``config/settings.py`` on disk while
still allowing LLMs and users to define full environment configs.
"""

import json
from dataclasses import asdict, dataclass, fields, is_dataclass, replace
from enum import Enum
from typing import Any, Dict, Mapping, MutableMapping, Optional, Type, TypeVar, cast

from config.settings import (
    ContinuousBurstConfig,
    ContinuousConstantConfig,
    ContinuousParetoConfig,
    ContinuousPeriodicConfig,
    FaultConfig,
    OneShotConfig,
    OrderMode,
    PlannerType,
    SchedulerType,
    SimConfig,
)

T = TypeVar("T")


def _deep_merge_dict(base: MutableMapping[str, Any], override: Mapping[str, Any]) -> Dict[str, Any]:
    """
    Recursively merge override into base and return a new dict.

    - If a value in override is a mapping and the corresponding base value
      is also a mapping, merge them recursively.
    - Otherwise, override replaces base.
    """
    result: Dict[str, Any] = dict(base)
    for key, value in override.items():
        if (
            key in result
            and isinstance(result[key], Mapping)
            and isinstance(value, Mapping)
        ):
            result[key] = _deep_merge_dict(
                cast(MutableMapping[str, Any], result[key]),
                cast(Mapping[str, Any], value),
            )
        else:
            result[key] = value
    return result


def _convert_enum(value: Any, enum_cls: Type[Enum], field_name: str) -> Enum:
    """
    Convert a JSON value into an Enum member.

    Accepts either:
    - the enum's .value (recommended), or
    - the enum member name (fallback).

    Raises ValueError on invalid values.
    """
    if isinstance(value, enum_cls):
        return value

    # Try by .value
    for member in enum_cls:
        if getattr(member, "value", None) == value:
            return member

    # Fallback: try by name
    try:
        return enum_cls[str(value)]
    except (KeyError, TypeError):
        raise ValueError(f"Invalid value {value!r} for enum field {field_name}")


def merge_dataclass(
    default: T,
    override: Mapping[str, Any],
    *,
    enum_fields: Optional[Mapping[str, Type[Enum]]] = None,
) -> T:
    """
    Generic helper to merge a dataclass instance with a dict of overrides.

    - ``default``: existing dataclass instance providing default values.
    - ``override``: flat dict of field_name -> value to override.
    - ``enum_fields``: optional mapping from field_name to Enum classes.

    Returns a **new** dataclass instance; does not mutate ``default``.
    """
    if not is_dataclass(default):
        raise TypeError("merge_dataclass expects a dataclass instance as default")

    enum_fields = enum_fields or {}

    current = asdict(default)
    # Shallow merge on top-level; nested dataclasses should be handled separately.
    merged: Dict[str, Any] = _deep_merge_dict(current, dict(override))

    # Convert enums and filter unknown fields
    kwargs: Dict[str, Any] = {}
    field_names = {f.name for f in fields(default)}

    for name, value in merged.items():
        if name not in field_names:
            # Unknown field: ignore to avoid silent misconfiguration
            continue

        if value is None:
            kwargs[name] = None
            continue

        enum_cls = enum_fields.get(name)
        if enum_cls is not None:
            kwargs[name] = _convert_enum(value, enum_cls, name)
        else:
            kwargs[name] = value

    # Use replace to preserve any extra dataclass metadata
    return replace(default, **kwargs)  # type: ignore[arg-type]


@dataclass
class RuntimeConfig:
    """
    Aggregate runtime configuration for a simulation run.

    - ``sim``: core simulation and algorithm selection parameters.
    - ``fault``: fault injection configuration.
    - ``order_modes``: per-order-mode configuration dataclasses.
    """

    sim: SimConfig
    fault: FaultConfig
    order_modes: Dict[OrderMode, Any]


def _load_json(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        raw = json.load(f)
    if not isinstance(raw, Mapping):
        raise ValueError(f"Config JSON at {path!r} must be a JSON object")
    return cast(Dict[str, Any], raw)


def load_runtime_config(override_config_path: Optional[str] = None) -> RuntimeConfig:
    """
    Load runtime configuration by merging defaults from ``config/settings.py``
    with an optional JSON override file.

    The JSON format is documented in ``knowledge/env_runtime_config.md`` and
    has the following shape (simplified):

        {
          "meta": {...},
          "config": {
            "sim": {...},
            "fault": {...},
            "order_modes": {
              "oneshot": {...},
              "continuous_constant": {...},
              "continuous_periodic": {...},
              "continuous_pareto": {...},
              "continuous_burst": {...}
            }
          }
        }

    Any missing sections or fields fall back to defaults from ``config/settings.py``.
    """
    # 1) Defaults from settings.py
    sim_default = SimConfig()
    fault_default = FaultConfig()

    order_mode_defaults: Dict[OrderMode, Any] = {
        OrderMode.ONESHOT: OneShotConfig(),
        OrderMode.CONTINUOUS_CONSTANT: ContinuousConstantConfig(),
        OrderMode.CONTINUOUS_PERIODIC: ContinuousPeriodicConfig(),
        OrderMode.CONTINUOUS_PARETO: ContinuousParetoConfig(),
        OrderMode.CONTINUOUS_BURST: ContinuousBurstConfig(),
    }

    if not override_config_path:
        return RuntimeConfig(sim=sim_default, fault=fault_default, order_modes=order_mode_defaults)

    data = _load_json(override_config_path)
    config_block = cast(Dict[str, Any], data.get("config") or {})

    sim_overrides = cast(Dict[str, Any], config_block.get("sim") or {})
    fault_overrides = cast(Dict[str, Any], config_block.get("fault") or {})
    order_modes_overrides = cast(Dict[str, Any], config_block.get("order_modes") or {})

    sim_enum_fields: Dict[str, Type[Enum]] = {
        "scheduler_type": SchedulerType,
        "planner_type": PlannerType,
        "order_mode": OrderMode,
    }

    sim = merge_dataclass(sim_default, sim_overrides, enum_fields=sim_enum_fields)
    fault = merge_dataclass(fault_default, fault_overrides)

    # Per-order-mode configs
    merged_order_modes: Dict[OrderMode, Any] = {}

    for mode, default_cfg in order_mode_defaults.items():
        key = mode.value  # "oneshot", "continuous_constant", etc.
        overrides = cast(Dict[str, Any], order_modes_overrides.get(key) or {})
        merged_order_modes[mode] = merge_dataclass(default_cfg, overrides)

    return RuntimeConfig(sim=sim, fault=fault, order_modes=merged_order_modes)


