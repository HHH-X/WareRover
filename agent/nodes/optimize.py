"""Optimization node: invoke OpenEvolve to optimize planner/scheduler code."""
from __future__ import annotations

from pathlib import Path
from typing import Dict

from agent.evolve import EvolveRequest, OptimizationTarget, run_evolution
from agent.state import AgentState

_PLANNER_DIR = Path(__file__).resolve().parent.parent.parent / "planner"
_SCHEDULER_DIR = Path(__file__).resolve().parent.parent.parent / "scheduler"


def _resolve_source(algo_type: str, optimize_source: str, state: AgentState) -> str:
    """Determine the file path of the code to optimize."""
    if optimize_source == "generated":
        gen = state.get("generated_code") or {}
        path = gen.get(algo_type)
        if path:
            return path
        raise ValueError(f"没有找到已生成的 {algo_type} 代码")

    if optimize_source and Path(optimize_source).exists():
        return optimize_source

    # Try to find in planner/ or scheduler/ directory
    base_dir = _PLANNER_DIR if algo_type == "planner" else _SCHEDULER_DIR
    candidate = base_dir / optimize_source
    if candidate.exists():
        return str(candidate)

    raise ValueError(f"找不到要优化的代码: {optimize_source}")


def optimize_node(state: AgentState) -> Dict:
    intents = state.get("intents") or []
    idx = state.get("intent_index", 0)
    intent = intents[idx] if idx < len(intents) else {}

    algo_type = intent.get("algo_type", "planner")
    optimize_source = intent.get("optimize_source", "generated")

    try:
        source_path = _resolve_source(algo_type, optimize_source, state)
    except ValueError as exc:
        return {"error": str(exc)}

    target = OptimizationTarget(algo_type)
    req_kwargs = {"target": target}
    if algo_type == "planner":
        req_kwargs["planner_source"] = source_path
    else:
        req_kwargs["scheduler_source"] = source_path

    try:
        result = run_evolution(EvolveRequest(**req_kwargs))
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
