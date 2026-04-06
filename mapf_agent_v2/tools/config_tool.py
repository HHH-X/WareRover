from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, List, Tuple

from config.settings import SystemConfig
from mapf_agent_v2.llm.client import chat_completion_json

ALLOWED_KEYS = {
    "sim_config.scheduler_type",
    "sim_config.planner_type",
    "sim_config.force_replan_every_step",
    "sim_config.order_mode",
    "sim_config.total_orders_limit",
    "sim_config.max_steps",
    "sim_config.size2_ratio",
    "sim_config.map_file",
    "sim_config.agv_max_speed",
    "sim_config.agv_turn_time_90",
    "sim_config.log_to_file",
    "sim_config.log_to_console",
    "fault_config.enable_faults",
    "fault_config.fault_prob",
    "fault_config.mean_repair_time",
}

PATCH_PROMPT = """
你是配置 patch 生成器。将用户自然语言转换为 JSON:
{
  "updates":[
    {"key":"sim_config.max_steps","value":1200}
  ]
}
只允许给定字段，不允许输出解释文本。
"""


def _set_by_path(obj: Any, path: str, value: Any) -> None:
    keys = path.split(".")
    cur = obj
    for key in keys[:-1]:
        cur = getattr(cur, key)
    setattr(cur, keys[-1], value)


def build_patch_from_text(text: str) -> Dict[str, Any]:
    result = chat_completion_json(
        [
            {"role": "system", "content": PATCH_PROMPT},
            {"role": "user", "content": text},
        ]
    )
    updates = result.get("updates", [])
    if not isinstance(updates, list):
        raise ValueError("patch updates 必须是列表")
    return {"updates": updates}


def validate_patch(patch: Dict[str, Any]) -> List[str]:
    errors: List[str] = []
    updates = patch.get("updates", [])
    if not isinstance(updates, list):
        return ["updates 必须是 list"]
    for i, upd in enumerate(updates):
        if not isinstance(upd, dict):
            errors.append(f"updates[{i}] 不是对象")
            continue
        key = upd.get("key")
        if key not in ALLOWED_KEYS:
            errors.append(f"不支持字段: {key}")
    return errors


def apply_patch_to_system_config(system_config: SystemConfig, patch: Dict[str, Any]) -> List[str]:
    errors: List[str] = []
    for upd in patch.get("updates", []):
        key = upd.get("key")
        value = upd.get("value")
        try:
            _set_by_path(system_config, str(key), value)
        except Exception as e:
            errors.append(f"{key}: {e}")
    return errors


def save_patch(patch: Dict[str, Any], output_dir: str = "mapf_agent_v2/runs/config_patches") -> str:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"patch_{time.strftime('%Y%m%d_%H%M%S')}.json"
    path.write_text(json.dumps(patch, indent=2, ensure_ascii=False), encoding="utf-8")
    return str(path)


def generate_and_apply_patch(system_config: SystemConfig, user_text: str) -> Tuple[Dict[str, Any], str]:
    patch = build_patch_from_text(user_text)
    errors = validate_patch(patch)
    if errors:
        raise ValueError("; ".join(errors))
    apply_errors = apply_patch_to_system_config(system_config, patch)
    if apply_errors:
        raise ValueError("; ".join(apply_errors))
    patch_path = save_patch(patch)
    return patch, patch_path

