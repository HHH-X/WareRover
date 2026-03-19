"""
SimConfig delta validator for MAPF Agent.

Purpose:
Given a dict produced by the environment parser (LLM), validate:
1) unknown fields -> ask user with close matches
2) wrong value types / enum values -> ask user to correct

It returns a structured result consumable by LangGraph env_validate node.
"""

from __future__ import annotations

import difflib
import re
from dataclasses import fields as dataclass_fields
from typing import Any, Dict, List, Optional, Tuple

from config.settings import FaultConfig, OrderMode, PlannerType, SchedulerType, SimConfig


_ENUM_BY_FIELD = {
    "scheduler_type": SchedulerType,
    "planner_type": PlannerType,
    "order_mode": OrderMode,
}


def _normalize_key(key: str) -> str:
    """
    Best-effort normalize: turn camelCase / hyphenated / spaced variants into snake_case.
    """
    k = (key or "").strip()
    k = re.sub(r"[\s\-]+", "_", k)
    # camelCase -> snake_case
    k = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", k)
    return k.lower()


def _coerce_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        v = value.strip().lower()
        if v in ("true", "t", "yes", "y", "1"):
            return True
        if v in ("false", "f", "no", "n", "0"):
            return False
    raise ValueError(f"Cannot coerce {value!r} to bool")


def _coerce_number(value: Any, kind: str) -> int | float:
    if isinstance(value, (int, float)) and kind == "int" and int(value) == value:
        return int(value)
    if kind == "int":
        return int(float(value))
    if kind == "float":
        return float(value)
    raise ValueError(f"Unsupported number kind: {kind}")


def _coerce_enum(field_name: str, value: Any) -> str:
    enum_cls = _ENUM_BY_FIELD[field_name]
    if isinstance(value, enum_cls):
        return value.value
    if isinstance(value, str):
        v = value.strip()
        # Try by `.value` first.
        for member in enum_cls:
            if getattr(member, "value", None) == v:
                return member.value
        # Fallback: try by enum name.
        try:
            return enum_cls[v].value
        except Exception:
            raise ValueError(f"Invalid {field_name} enum value {value!r}")
    # Also accept JSON numbers for enum? unlikely; keep strict.
    raise ValueError(f"Invalid {field_name} enum value type: {type(value).__name__}")


def validate_sim_config_delta(sim_delta: Dict[str, Any]) -> Dict[str, Any]:
    """
    Validate SimConfig overrides (subset).

    Returns:
      {
        "ok": bool,
        "cleaned_delta": dict (only if ok),
        "pending_question": str (only if not ok),
        "errors": [..] (debug)
      }
    """
    if not sim_delta:
        return {"ok": True, "cleaned_delta": {}}

    sim_field_names = {f.name for f in dataclass_fields(SimConfig)}
    fault_field_names = {f.name for f in dataclass_fields(FaultConfig)}
    cleaned: Dict[str, Any] = {}
    errors: List[str] = []

    for raw_key, raw_value in sim_delta.items():
        key = _normalize_key(str(raw_key))
        if key not in sim_field_names and key not in fault_field_names:
            candidates = difflib.get_close_matches(key, sorted(sim_field_names | fault_field_names), n=3, cutoff=0.65)
            if candidates:
                errors.append(f"未知字段 `{raw_key}`，疑似应为 `{candidates[0]}`")
                return {
                    "ok": False,
                    "pending_question": (
                        f"仿真配置字段 `{raw_key}` 在 `SimConfig` 中不存在。你可能想设置的是 `{candidates[0]}` 吗？"
                        f"请回复正确的字段名/值（例如 `{candidates[0]}=...`）。"
                    ),
                    "errors": errors,
                }
            errors.append(f"未知字段 `{raw_key}`")
            return {
                "ok": False,
                "pending_question": f"仿真配置字段 `{raw_key}` 在 `SimConfig` 中不存在。请给出正确字段名。",
                "errors": errors,
            }

        if raw_value is None:
            # For Optional fields, null could be meaningful; accept None.
            cleaned[key] = None
            continue

        if key in _ENUM_BY_FIELD:
            try:
                cleaned[key] = _coerce_enum(key, raw_value)
            except Exception as e:
                return {
                    "ok": False,
                    "pending_question": f"字段 `{key}` 的值 `{raw_value}` 不合法（需为枚举字符串）。请更正后重试。",
                    "errors": [str(e)],
                }
            continue

        # Coerce by field name heuristics (best-effort; accept string numbers).
        # NOTE: this validator covers both SimConfig and FaultConfig keys.
        if key.startswith("log_") or key in ("enable_faults", "allow_multiple_faults") or key.startswith("force_replan"):
            try:
                cleaned[key] = _coerce_bool(raw_value)
            except Exception as e:
                return {
                    "ok": False,
                    "pending_question": f"字段 `{key}` 需要布尔值（true/false）。请更正后重试。",
                    "errors": [str(e)],
                }
        elif any(k in key for k in ("timeout", "max_steps", "interval_steps", "count", "mean_repair_time", "seed")):
            try:
                cleaned[key] = _coerce_number(raw_value, "int")
            except Exception as e:
                return {
                    "ok": False,
                    "pending_question": f"字段 `{key}` 需要整数值。请更正后重试。",
                    "errors": [str(e)],
                }
        elif any(k in key for k in ("ratio", "time_step", "agv_max_speed", "agv_turn_time_90", "fault_prob")):
            try:
                cleaned[key] = _coerce_number(raw_value, "float")
            except Exception as e:
                return {
                    "ok": False,
                    "pending_question": f"字段 `{key}` 需要浮点数值。请更正后重试。",
                    "errors": [str(e)],
                }
        else:
            # Treat as str by default.
            cleaned[key] = raw_value

    # Validate cleaned fields are still a subset of SimConfig fields.
    for k in cleaned:
        if k not in (sim_field_names | fault_field_names):
            return {
                "ok": False,
                "pending_question": f"字段 `{k}` 校验后仍不在 SimConfig/FaultConfig 中，请重试。",
                "errors": [],
            }

    return {"ok": True, "cleaned_delta": cleaned}

