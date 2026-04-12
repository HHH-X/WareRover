"""Optimization node: resolve algorithm source, then invoke OpenEvolve."""
from __future__ import annotations

import json
from typing import Dict

from mapf_agent.evolve.core import EvolveRequest, OptimizationTarget, run_evolution
from mapf_agent.evolve.resolver import resolve_algorithm_source
from mapf_agent.state import AgentState


def _serialize_system_config(state: AgentState) -> str:
    """Serialize the current SystemConfig from state into a JSON string
    so the evaluator can reconstruct it."""
    cfg = state.get("system_config")
    if cfg is None:
        return ""
    from dataclasses import asdict
    try:
        return json.dumps(asdict(cfg), ensure_ascii=False, default=str)
    except Exception:
        return ""


_TARGET_LABELS = {
    OptimizationTarget.PLANNER: "路径规划器",
    OptimizationTarget.SCHEDULER: "任务调度器",
    OptimizationTarget.BOTH: "路径规划器 + 任务调度器",
}


def optimize_node(state: AgentState) -> Dict:
    intents = state.get("intents") or []
    idx = state.get("intent_index", 0)
    intent = intents[idx] if idx < len(intents) else {}

    algo_type = intent.get("algo_type", "planner")
    detail = intent.get("detail", "")
    source_hint = intent.get("optimize_source", "")

    target = OptimizationTarget(algo_type) if algo_type != "both" else OptimizationTarget.BOTH
    print(f"[算法优化] 优化目标: {_TARGET_LABELS.get(target, algo_type)}")

    try:
        if target == OptimizationTarget.BOTH:
            planner_path = resolve_algorithm_source("planner", detail, state, source_hint)
            scheduler_path = resolve_algorithm_source("scheduler", detail, state, source_hint)
        elif target == OptimizationTarget.PLANNER:
            planner_path = resolve_algorithm_source("planner", detail, state, source_hint)
            scheduler_path = None
        else:
            planner_path = None
            scheduler_path = resolve_algorithm_source("scheduler", detail, state, source_hint)
    except ValueError as exc:
        return {"error": str(exc)}

    req = EvolveRequest(
        target=target,
        planner_source=planner_path,
        scheduler_source=scheduler_path,
        system_config_json=_serialize_system_config(state),
    )

    print("[算法优化] 开始进化优化，这可能需要较长时间...")
    try:
        result = run_evolution(req)
    except Exception as exc:
        print("[算法优化] 优化异常终止")
        return {"error": f"优化运行失败: {exc}"}

    print(f"[算法优化] 完成 — 最佳分数: {result.best_score}")
    return {
        "optimize_result": {
            "run_dir": result.run_dir,
            "best_score": result.best_score,
            "best_metrics": result.best_metrics,
            "best_code_preview": result.best_code[:500] if result.best_code else "",
        },
        "error": "",
    }
