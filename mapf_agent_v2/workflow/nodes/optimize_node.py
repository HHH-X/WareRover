from __future__ import annotations

from typing import Dict

from mapf_agent_v2.session.state import AgentState
from mapf_agent_v2.tools.optimize_tool import run_stage2_optimization


def optimize_node(state: AgentState) -> Dict:
    idx = int(state.get("intent_index", 0))
    intents = state.get("intents") or []
    intent = intents[idx] if idx < len(intents) else {}

    target = str(intent.get("target", "planner")).strip().lower()
    planner_source = str(intent.get("planner_source", "")).strip()
    scheduler_source = str(intent.get("scheduler_source", "")).strip()
    if not planner_source:
        planner_source = state.get("generated_planner_path", "") or ""
    if not scheduler_source:
        scheduler_source = state.get("generated_scheduler_path", "") or ""
    iterations = int(intent.get("iterations", 3))
    config_path = str(intent.get("config_path", "")).strip() or None
    output_root = str(intent.get("output_root", "mapf_agent_v2/runs/stage2")).strip()

    if target in {"planner", "both"} and not planner_source:
        return {
            "need_user_input": True,
            "pending_question": "缺少 planner_source，请先生成 planner 或提供路径。",
            "blocking_stage": "optimize",
        }
    if target in {"scheduler", "both"} and not scheduler_source:
        return {
            "need_user_input": True,
            "pending_question": "缺少 scheduler_source，请先生成 scheduler 或提供路径。",
            "blocking_stage": "optimize",
        }

    try:
        out = run_stage2_optimization(
            target=target,
            planner_source=planner_source or None,
            scheduler_source=scheduler_source or None,
            config_path=config_path,
            iterations=iterations,
            output_root=output_root,
        )
    except Exception as e:
        return {
            "need_user_input": True,
            "pending_question": f"优化执行失败: {e}。请调整后重试。",
            "blocking_stage": "optimize",
        }

    return {
        "latest_optimize_run_dir": str(out.get("run_dir", "")),
        "latest_optimize_best_code": str(out.get("best_code", "")),
        "result_summary": f"优化完成: score={out.get('best_score')} run_dir={out.get('run_dir')}",
        "error": "",
        "need_user_input": False,
        "pending_question": "",
        "blocking_stage": "",
        "user_response": "",
    }

