from __future__ import annotations

from typing import Dict

from mapf_agent_v2.session.state import AgentState
from mapf_agent_v2.tools.codegen_tool import generate_algorithm_code


def codegen_node(state: AgentState) -> Dict:
    idx = int(state.get("intent_index", 0))
    intents = state.get("intents") or []
    intent = intents[idx] if idx < len(intents) else {}

    algo_type = str(intent.get("algorithm_type", "planner")).strip().lower()
    algo_name = str(intent.get("algorithm_name", "generated_algo")).strip()
    content = str(intent.get("content", "")).strip() or str(state.get("user_input", "")).strip()

    if algo_type not in {"planner", "scheduler"}:
        return {
            "need_user_input": True,
            "pending_question": "请指定要生成 planner 还是 scheduler。",
            "blocking_stage": "generate_algo",
        }
    try:
        reg_name, file_path = generate_algorithm_code(algo_type, algo_name, content)
    except Exception as e:
        return {
            "need_user_input": True,
            "pending_question": f"算法生成失败: {e}。请补充更明确的算法要求。",
            "blocking_stage": "generate_algo",
        }

    payload: Dict = {
        "need_user_input": False,
        "pending_question": "",
        "blocking_stage": "",
        "user_response": "",
        "error": "",
        "result_summary": f"已生成 {algo_type}: {reg_name} ({file_path})",
    }
    if algo_type == "planner":
        payload["generated_planner_name"] = reg_name
        payload["generated_planner_path"] = file_path
        state["system_config"].sim_config.planner_type = reg_name
    else:
        payload["generated_scheduler_name"] = reg_name
        payload["generated_scheduler_path"] = file_path
        state["system_config"].sim_config.scheduler_type = reg_name
    payload["system_config"] = state["system_config"]
    return payload

