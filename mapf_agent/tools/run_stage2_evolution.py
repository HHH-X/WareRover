"""
Tool wrapper: run stage-2 OpenEvolve optimization for planner/scheduler/both.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from evolution.stage2 import (
    OptimizationTarget,
    Stage2EvolutionRequest,
    run_stage2_evolution,
)


def run_stage2_optimization(
    target: str,
    planner_source: Optional[str] = None,
    scheduler_source: Optional[str] = None,
    config_path: Optional[str] = None,
    iterations: Optional[int] = None,
    output_root: str = "evolution/stage2_runs",
) -> Dict[str, Any]:
    """
    Execute stage-2 optimization.

    Args:
        target: "planner" | "scheduler" | "both"
        planner_source: file path or raw code string
        scheduler_source: file path or raw code string
        config_path: optional OpenEvolve yaml path
        iterations: optional override
        output_root: where generated run folders are saved
    """
    req = Stage2EvolutionRequest(
        target=OptimizationTarget(target),
        planner_source=planner_source,
        scheduler_source=scheduler_source,
        config_path=config_path,
        iterations=iterations,
        output_root=output_root,
    )
    result = run_stage2_evolution(req)
    return {
        "ok": True,
        "run_dir": result.run_dir,
        "output_dir": result.output_dir,
        "initial_program_path": result.initial_program_path,
        "evaluator_path": result.evaluator_path,
        "config_path": result.config_path,
        "best_score": result.best_score,
        "metrics": result.best_metrics,
    }
