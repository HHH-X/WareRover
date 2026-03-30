from __future__ import annotations

import json
from typing import Any, Dict, List

from config.settings import SystemConfig


FIELD_SCHEMA: Dict[str, Dict[str, Any]] = {
    # ===== Sim =====
    "sim_config.scheduler_type": {"type": "str"},
    "sim_config.planner_type": {"type": "str"},
    "sim_config.force_replan_every_step": {"type": "bool"},
    "sim_config.order_mode": {"type": "str"},
    "sim_config.total_orders_limit": {"type": "int", "min": 1},
    "sim_config.max_steps": {"type": "int", "min": 1},
    "sim_config.size2_ratio": {"type": "float", "min": 0, "max": 1},
    "sim_config.map_file": {"type": "str"},
    "sim_config.agv_max_speed": {"type": "float", "min": 0},
    "sim_config.agv_turn_time_90": {"type": "float", "min": 0},
    "sim_config.log_to_file": {"type": "bool"},
    "sim_config.log_to_console": {"type": "bool"},
    # ===== Fault =====
    "fault_config.enable_faults": {"type": "bool"},
    "fault_config.fault_prob": {"type": "float", "min": 0, "max": 1},
    "fault_config.mean_repair_time": {"type": "int", "min": 1},
    # ===== Order: Constant =====
    "continuous_constant_config.batch_size": {"type": "int", "min": 1},
    "continuous_constant_config.generation_interval_steps": {"type": "int", "min": 1},
    # ===== Order: Periodic =====
    "continuous_periodic_config.base_batch_size": {"type": "int", "min": 1},
    "continuous_periodic_config.peak_multiplier": {"type": "float", "min": 0},
    # ===== Order: Pareto =====
    "continuous_pareto_config.alpha": {"type": "float", "min": 1},
    "continuous_pareto_config.scale": {"type": "float", "min": 0},
    # ===== Order: Burst =====
    "continuous_burst_config.base_batch_size": {"type": "int", "min": 1},
}

# ===================== Validation =====================
def validate_patch(patch: Dict[str, Any]) -> List[str]:
    errors: List[str] = []

    updates = patch.get("updates", [])
    if not isinstance(updates, list):
        return ["updates must be a list"]

    for idx, upd in enumerate(updates):
        if not isinstance(upd, dict):
            errors.append(f"updates[{idx}] must be object")
            continue

        key = upd.get("key")
        value = upd.get("value")

        if key is None:
            errors.append(f"updates[{idx}] missing key")
            continue
        if "value" not in upd:
            errors.append(f"updates[{idx}] missing value")
            continue

        if key not in FIELD_SCHEMA:
            errors.append(f"Unknown field: {key}")
            continue

        schema = FIELD_SCHEMA[key]
        t = schema["type"]

        try:
            if t == "float":
                if not isinstance(value, (int, float)):
                    raise ValueError("Must be float")
                if "min" in schema and value < schema["min"]:
                    raise ValueError(f"< min {schema['min']}")
                if "max" in schema and value > schema["max"]:
                    raise ValueError(f"> max {schema['max']}")

            elif t == "int":
                if not isinstance(value, int):
                    raise ValueError("Must be int")
                if "min" in schema and value < schema["min"]:
                    raise ValueError(f"< min {schema['min']}")

            elif t == "bool":
                if not isinstance(value, bool):
                    raise ValueError("Must be bool")

            elif t == "str":
                if not isinstance(value, str):
                    raise ValueError("Must be string")

        except Exception as e:
            errors.append(f"{key}: {str(e)}")

    return errors

# ===================== Apply =====================
def set_by_path(obj: Any, path: str, value: Any) -> None:
    keys = path.split(".")
    cur = obj
    for key in keys[:-1]:
        if not hasattr(cur, key):
            raise AttributeError(f"Invalid path segment: {key}")
        cur = getattr(cur, key)

    if not hasattr(cur, keys[-1]):
        raise AttributeError(f"Invalid target field: {path}")

    setattr(cur, keys[-1], value)


def apply_patch(config: SystemConfig, patch: Dict[str, Any]) -> List[str]:
    """
    Apply patch with partial success support.
    Returns runtime errors (NOT schema errors).
    """
    runtime_errors: List[str] = []

    for upd in patch.get("updates", []):
        key = upd.get("key")
        value = upd.get("value")

        try:
            set_by_path(config, key, value)
        except Exception as e:
            runtime_errors.append(f"{key}: {str(e)}")

    return runtime_errors

# ===================== Normalize =====================
def normalize_to_patch(parsed: Any) -> Dict[str, Any]:
    """
    Ensure parsed result matches standard patch format.
    """
    if isinstance(parsed, dict) and isinstance(parsed.get("updates"), list):
        return {
            "success": parsed.get("success", True),
            "updates": parsed.get("updates", []),
            "errors": parsed.get("errors", []),
        }

# ===================== Pipeline =====================
def process_llm_output(config: SystemConfig, parsed: Dict[str, Any]) -> Dict[str, Any]:
    """
    Full pipeline:
    LLM → normalize → validate → apply
    """
    patch = normalize_to_patch(parsed)

    llm_errors = patch.get("errors", [])
    schema_errors = validate_patch(patch)

    runtime_errors = apply_patch(config, patch)

    all_errors = llm_errors + schema_errors + runtime_errors

    return {
        "success": len(all_errors) == 0,
        "errors": all_errors,
        "applied_updates": patch.get("updates", []),
    }


# ===================== Utils =====================
def serialize(obj: Any) -> Any:
    if hasattr(obj, "__dict__"):
        return {k: serialize(v) for k, v in obj.__dict__.items()}
    if isinstance(obj, dict):
        return {k: serialize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [serialize(v) for v in obj]
    return obj


def save_system_config(config: SystemConfig, path: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(serialize(config), f, indent=2, ensure_ascii=False)