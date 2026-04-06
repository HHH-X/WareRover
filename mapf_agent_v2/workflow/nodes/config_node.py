from __future__ import annotations

from typing import Dict

from mapf_agent_v2.session.state import AgentState
from mapf_agent_v2.tools.config_tool import generate_and_apply_patch


def config_node(state: AgentState) -> Dict:
    idx = int(state.get("intent_index", 0))
    intents = state.get("intents") or []
    intent = intents[idx] if idx < len(intents) else {"content": state.get("user_input", "")}
    text = str(intent.get("content", "")).strip() or str(state.get("user_input", "")).strip()
    if state.get("blocking_stage") == "config" and state.get("user_response"):
        text = f"{text}\n{state.get('user_response','')}"

    system_config = state["system_config"]
    if state.get("blocking_stage") == "config" and state.get("user_response"):
        text = str(state.get("user_response", "")).strip()

    try:
        _, patch_path = generate_and_apply_patch(system_config, text)
    except Exception as e:
        return {
            "need_user_input": True,
            "pending_question": f"配置 patch 失败: {e}。请重新描述配置修改。",
            "blocking_stage": "config",
        }

    return {
        "system_config": system_config,
        "config_patch_path": patch_path,
        "need_user_input": False,
        "pending_question": "",
        "blocking_stage": "",
        "user_response": "",
        "result_summary": f"配置 patch 已应用: {patch_path}",
        "error": "",
    }

