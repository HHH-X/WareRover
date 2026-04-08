"""Optimization node: resolve algorithm source, then invoke OpenEvolve."""
from __future__ import annotations

import json
from typing import Dict

from agent.evolve.core import EvolveRequest, OptimizationTarget, run_evolution
from agent.evolve.resolver import resolve_algorithm_source
from agent.state import AgentState


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


def optimize_node(state: AgentState) -> Dict:
    intents = state.get("intents") or []
    idx = state.get("intent_index", 0)
    intent = intents[idx] if idx < len(intents) else {}

    algo_type = intent.get("algo_type", "planner")
    detail = intent.get("detail", "")
    source_hint = intent.get("optimize_source", "")

    target = OptimizationTarget(algo_type) if algo_type != "both" else OptimizationTarget.BOTH

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

    try:
        result = run_evolution(req)
    except Exception as exc:
        return {"error": f"优化运行失败: {exc}"}

    return {
        "optimize_result": {
            "run_dir": result.run_dir,
            "best_score": result.best_score,
            "best_metrics": result.best_metrics,
            "best_code_preview": result.best_code[:500] if result.best_code else "",
        },
        "error": "",
    }
