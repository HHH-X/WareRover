from __future__ import annotations

from typing import Any, Dict, Optional

from mapf_agent_v2.optimization.stage2 import (
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
    output_root: str = "mapf_agent_v2/runs/stage2",
) -> Dict[str, Any]:
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
        "best_code": result.best_code,
    }

