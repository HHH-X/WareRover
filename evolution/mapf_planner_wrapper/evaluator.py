"""
OpenEvolve evaluator for MAPF evolved planner wrapper.
"""

from __future__ import annotations

import importlib.util
import sys
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Sequence

# Ensure local vendored OpenEvolve package is importable without pip install.
_REPO_ROOT = Path(__file__).resolve().parents[2]
_OPENEVOLE_SRC = _REPO_ROOT / "openevolve"
if str(_OPENEVOLE_SRC) not in sys.path:
    sys.path.insert(0, str(_OPENEVOLE_SRC))
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from config.settings import SystemConfig
from core.agvmanager import AGVManager
from core.env import Env
from core.fault_manager import FaultManager
from core.gridmap import GridMap
from core.ordermanager import OrderManager
from core.simulator import Simulator
from planner.evolved_wrapper_planner import set_ranker_function
from utils.algorithm_factory import build_planner, build_scheduler
from utils.algorithm_registry import init_default_registries
from utils.logger import GlobalLogger
from utils.simulation_clock import SimulationClock
from utils.simulation_context import SimulationContext


DEFAULT_SEEDS: Sequence[int] = (42, 43, 44)


@dataclass
class EpisodeResult:
    completion_rate: float
    sim_steps: int
    planner_avg_time: float
    finished: bool


def _safe_score01(raw: float) -> float:
    if raw < 0.0:
        return 0.0
    if raw > 1.0:
        return 1.0
    return float(raw)


def _normalize_inverse(value: float) -> float:
    if value < 0:
        value = 0
    return 1.0 / (1.0 + float(value))


def _run_single_episode(seed: int) -> EpisodeResult:
    import random
    import numpy as np

    random.seed(seed)
    np.random.seed(seed)

    ctx = SimulationContext()
    ctx.system_config = SystemConfig()
    ctx.system_config.sim_config.order_seed = seed
    ctx.system_config.fault_config.fault_seed = seed
    ctx.system_config.sim_config.planner_type = "evolved_wrapper"
    init_default_registries()

    ctx.logger = GlobalLogger(ctx)
    ctx.clock = SimulationClock(ctx)
    ctx.grid_map = GridMap(ctx)
    ctx.order_manager = OrderManager(ctx)
    ctx.agv_manager = AGVManager(ctx)
    ctx.env = Env(ctx)
    ctx.fault_manager = FaultManager(ctx)
    ctx.scheduler = build_scheduler(ctx)
    ctx.planner = build_planner(ctx)
    ctx.simulator = Simulator(ctx)

    while (
        not ctx.order_manager.is_all_orders_completed()
        and ctx.clock.now() < ctx.system_config.sim_config.max_steps
    ):
        ctx.simulator.step()
        ctx.fault_manager.step()

    metrics = ctx.logger.get_final_metrics(ctx.clock.now())
    return EpisodeResult(
        completion_rate=float(metrics.get("Task Success Rate", 0.0)),
        sim_steps=int(metrics.get("Sim Steps", ctx.clock.now())),
        planner_avg_time=float(metrics.get("Planner Avg Time", 0.0)),
        finished=bool(ctx.order_manager.is_all_orders_completed()),
    )


def _build_ranker_from_program(program_path: str):
    spec = importlib.util.spec_from_file_location("evolved_program", program_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("Cannot load evolved program spec")
    program = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(program)
    if not hasattr(program, "rank_targets"):
        raise RuntimeError("Program must provide rank_targets(target_rows, current_step=0)")
    return program.rank_targets


def evaluate(program_path: str):
    """
    Evaluate evolved target ranking logic and return OpenEvolve metrics.
    """
    try:
        ranker = _build_ranker_from_program(program_path)
        set_ranker_function(ranker)

        episode_results: List[EpisodeResult] = []
        for seed in DEFAULT_SEEDS:
            episode_results.append(_run_single_episode(seed))

        completion_mean = sum(r.completion_rate for r in episode_results) / len(episode_results)
        makespan_mean = sum(r.sim_steps for r in episode_results) / len(episode_results)
        planner_time_mean = sum(r.planner_avg_time for r in episode_results) / len(episode_results)
        stability_ratio = sum(1.0 if r.finished else 0.0 for r in episode_results) / len(episode_results)

        completion_score = _safe_score01(completion_mean)
        makespan_score = _normalize_inverse(makespan_mean)
        time_score = _normalize_inverse(planner_time_mean * 1e3)
        stability_score = _safe_score01(stability_ratio)

        combined_score = (
            0.35 * completion_score
            + 0.35 * makespan_score
            + 0.20 * time_score
            + 0.10 * stability_score
        )

        return {
            "completion_score": float(completion_score),
            "makespan_score": float(makespan_score),
            "time_score": float(time_score),
            "stability_score": float(stability_score),
            "combined_score": float(combined_score),
            "completion_mean": float(completion_mean),
            "makespan_mean": float(makespan_mean),
            "planner_time_mean": float(planner_time_mean),
            "stability_ratio": float(stability_ratio),
            "seed_count": float(len(DEFAULT_SEEDS)),
        }
    except Exception as exc:
        return {
            "completion_score": 0.0,
            "makespan_score": 0.0,
            "time_score": 0.0,
            "stability_score": 0.0,
            "combined_score": 0.0,
            "error": str(exc),
            "traceback": traceback.format_exc(),
        }
    finally:
        set_ranker_function(None)
