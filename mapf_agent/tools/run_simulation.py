"""
Run WareRover simulation with temporary config (map file, planner type, etc.) and return metrics.
"""
import os
from typing import Dict, Any, List, Optional

from config.settings import SimConfig, PlannerType, SchedulerType
from test.single_run import run_single_episode


def run_simulation(
    num_runs: int = 1,
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
   

    results: List[Dict[str, Any]] = []
    metrics = run_single_episode()
    results.append(metrics)

    if num_runs == 1:
        out = {"ok": True, "metrics": results[0]}
    else:
        summary = _summarize(results)
        out = {"ok": True, "metrics": results, "summary": summary}
    return out

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
