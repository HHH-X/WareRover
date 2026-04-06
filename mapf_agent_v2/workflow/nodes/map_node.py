from __future__ import annotations

from typing import Dict

from mapf_agent_v2.session.state import AgentState
from mapf_agent_v2.tools.map_tool import (
    fill_defaults,
    generate_map_json,
    missing_required,
    parse_map_spec,
    save_map_json,
)


def map_node(state: AgentState) -> Dict:
    idx = int(state.get("intent_index", 0))
    intents = state.get("intents") or []
    intent = intents[idx] if idx < len(intents) else {"content": state.get("user_input", "")}
    text = str(intent.get("content", "")).strip() or str(state.get("user_input", "")).strip()

    if state.get("blocking_stage") == "map" and state.get("user_response"):
        text = f"{text}\n{state.get('user_response','')}"

    spec = fill_defaults(parse_map_spec(text))
    missing = missing_required(spec)
    if missing:
        return {
            "need_user_input": True,
            "pending_question": f"地图信息缺失: {', '.join(missing)}。请补充。",
            "blocking_stage": "map",
        }

    map_json = generate_map_json(spec)
    map_path = save_map_json(map_json)
    system_config = state["system_config"]
    system_config.sim_config.map_file = map_path
    return {
        "system_config": system_config,
        "map_file_path": map_path,
        "need_user_input": False,
        "pending_question": "",
        "blocking_stage": "",
        "user_response": "",
        "result_summary": f"已生成地图: {map_path}",
        "error": "",
    }

