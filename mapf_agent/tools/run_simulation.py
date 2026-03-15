"""
Run WareRover simulation with temporary config (map file, planner type, etc.) and return metrics.
"""
import os
from typing import Dict, Any, List, Optional

from config.settings import SimConfig, PlannerType, SchedulerType
from test.single_run import run_single_episode


def run_simulation(
    map_file: str,
    planner_type: Optional[str] = None,
    scheduler_type: Optional[str] = None,
    seed: Optional[int] = None,
    num_runs: int = 1,
    max_steps: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Run one or more simulation episodes with the given map and algorithm config.

    Args:
        map_file: Path to map JSON file (must exist).
        planner_type: One of "astar", "cbs_fw", "dhc". If None, use SimConfig default.
        scheduler_type: One of "random", "ta". If None, use SimConfig default.
        seed: Random seed; if None, use AgentConfig.default_simulation_seed or 42.
        num_runs: Number of episodes to run; metrics will be averaged if num_runs > 1.
        max_steps: Override SimConfig.max_steps for this run. None = use current.

    Returns:
        Dict with "ok", "metrics" (per-run or single run), "summary" (if num_runs > 1),
        and "error" if ok is False.
    """
    if not os.path.isfile(map_file):
        return {"ok": False, "error": f"Map file not found: {map_file}"}

    planner_enum = None
    if planner_type is not None:
        try:
            planner_enum = PlannerType(planner_type)
        except ValueError:
            return {"ok": False, "error": f"Unknown planner_type: {planner_type}"}

    scheduler_enum = None
    if scheduler_type is not None:
        try:
            scheduler_enum = SchedulerType(scheduler_type)
        except ValueError:
            return {"ok": False, "error": f"Unknown scheduler_type: {scheduler_type}"}

    seed = seed if seed is not None else 42
    original_map = SimConfig.map_file
    original_planner = SimConfig.planner_type
    original_scheduler = SimConfig.scheduler_type
    original_max_steps = SimConfig.max_steps

    try:
        SimConfig.map_file = os.path.abspath(map_file)
        if planner_enum is not None:
            SimConfig.planner_type = planner_enum
        if scheduler_enum is not None:
            SimConfig.scheduler_type = scheduler_enum
        if max_steps is not None:
            SimConfig.max_steps = max_steps

        results: List[Dict[str, Any]] = []
        for i in range(num_runs):
            s = seed + i
            metrics = run_single_episode(s)
            results.append(metrics)

        if num_runs == 1:
            out = {"ok": True, "metrics": results[0]}
        else:
            summary = _summarize(results)
            out = {"ok": True, "metrics": results, "summary": summary}
        return out
    except Exception as e:
        return {"ok": False, "error": str(e)}
    finally:
        SimConfig.map_file = original_map
        SimConfig.planner_type = original_planner
        SimConfig.scheduler_type = original_scheduler
        SimConfig.max_steps = original_max_steps


def _summarize(results: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Average numeric metrics across runs (excluding seed)."""
    if not results:
        return {}
    summary = {}
    for k in results[0]:
        if k == "seed":
            continue
        vals = [r[k] for r in results if k in r and isinstance(r[k], (int, float))]
        if vals:
            summary[k] = sum(vals) / len(vals)
    return summary
