"""Config patch node: LLM generates a patch, validate and apply to SystemConfig."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from config.settings import SystemConfig
from agent.llm import chat_json
from agent.state import AgentState

_PROMPT_PATH = Path(__file__).resolve().parent.parent / "prompts" / "config_patch.txt"

# Whitelist of fields with their expected types
_FIELD_TYPES: Dict[str, str] = {
    "sim_config.scheduler_type": "str",
    "sim_config.planner_type": "str",
    "sim_config.force_replan_every_step": "bool",
    "sim_config.order_mode": "str",
    "sim_config.total_orders_limit": "int",
    "sim_config.max_steps": "int",
    "sim_config.size2_ratio": "float",
    "sim_config.map_file": "str",
    "sim_config.agv_max_speed": "float",
    "sim_config.agv_turn_time_90": "float",
    "sim_config.log_to_file": "bool",
    "sim_config.log_to_console": "bool",
    "fault_config.enable_faults": "bool",
    "fault_config.fault_prob": "float",
    "fault_config.mean_repair_time": "int",
    "fault_config.allow_multiple_faults": "bool",
    "continuous_constant_config.batch_size": "int",
    "continuous_constant_config.generation_interval_steps": "int",
    "continuous_periodic_config.base_batch_size": "int",
    "continuous_periodic_config.peak_multiplier": "float",
    "continuous_pareto_config.alpha": "float",
    "continuous_pareto_config.scale": "float",
    "continuous_burst_config.base_batch_size": "int",
}


def _set_by_path(obj: Any, path: str, value: Any) -> None:
    keys = path.split(".")
    cur = obj
    for k in keys[:-1]:
        cur = getattr(cur, k)
    setattr(cur, keys[-1], value)


def _validate_and_apply(config: SystemConfig, patch: Dict) -> List[str]:
    errors: List[str] = []
    for upd in patch.get("updates", []):
        key, value = upd.get("key"), upd.get("value")
        if key not in _FIELD_TYPES:
            errors.append(f"未知字段: {key}")
            continue
        expected = _FIELD_TYPES[key]
        if expected == "float" and not isinstance(value, (int, float)):
            errors.append(f"{key}: 需要数值类型")
            continue
        if expected == "int" and not isinstance(value, int):
            errors.append(f"{key}: 需要整数")
            continue
        if expected == "bool" and not isinstance(value, bool):
            errors.append(f"{key}: 需要布尔值")
            continue
        if expected == "str" and not isinstance(value, str):
            errors.append(f"{key}: 需要字符串")
            continue
        try:
            _set_by_path(config, key, value)
        except Exception as exc:
            errors.append(f"{key}: {exc}")
    return errors


def config_node(state: AgentState) -> Dict:
    config: SystemConfig = state.get("system_config") or SystemConfig()

    # Auto-apply map path from earlier map_gen step
    map_path = state.get("map_file_path")
    if map_path:
        config.sim_config.map_file = map_path

    intents = state.get("intents") or []
    idx = state.get("intent_index", 0)
    detail = intents[idx].get("detail", "") if idx < len(intents) else ""
    user_msg = detail or state.get("user_input", "")

    system_prompt = _PROMPT_PATH.read_text(encoding="utf-8")
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_msg},
    ]
    patch = chat_json(messages)

    errors = _validate_and_apply(config, patch)
    if errors:
        return {"system_config": config, "error": f"配置应用部分失败: {'; '.join(errors)}"}

    return {"system_config": config, "error": ""}
