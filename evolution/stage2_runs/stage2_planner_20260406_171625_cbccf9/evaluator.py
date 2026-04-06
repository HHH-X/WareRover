from __future__ import annotations

import importlib.util
import random
from typing import Any, Dict, List, Tuple, Type

import numpy as np

from config.settings import SystemConfig
from core.agvmanager import AGVManager
from core.env import Env
from core.fault_manager import FaultManager
from core.gridmap import GridMap
from core.ordermanager import OrderManager
from core.simulator import Simulator
from planner.base_planner import BasePlanner
from scheduler.base_scheduler import BaseScheduler
from utils.algorithm_factory import build_planner, build_scheduler
from utils.algorithm_registry import PlannerRegistry, SchedulerRegistry, init_default_registries
from utils.logger import GlobalLogger
from utils.simulation_clock import SimulationClock
from utils.simulation_context import SimulationContext

TARGET = 'planner'
BASELINE_PLANNER = 'astar'
BASELINE_SCHEDULER = 'random'
PLANNER_REG_NAME = 'stage2_evolved_planner'
SCHEDULER_REG_NAME = 'stage2_evolved_scheduler'
SEEDS = [42, 43, 44]


def _safe_score01(v: float) -> float:
    if v < 0:
        return 0.0
    if v > 1:
        return 1.0
    return float(v)


def _normalize_inverse(value: float) -> float:
    if value < 0:
        value = 0
    return 1.0 / (1.0 + float(value))


def _load_module(program_path: str):
    spec = importlib.util.spec_from_file_location("stage2_candidate", program_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("Cannot load candidate module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _pick_subclass(module, base_cls: Type, kind: str):
    candidates = []
    for _, value in module.__dict__.items():
        if isinstance(value, type) and issubclass(value, base_cls) and value is not base_cls:
            candidates.append(value)
    if not candidates:
        raise RuntimeError(f"No {kind} subclass found in candidate module")
    local = [c for c in candidates if c.__module__ == module.__name__]
    return local[0] if local else candidates[0]


def _run_single(seed: int, planner_type: str, scheduler_type: str) -> Dict[str, Any]:
    random.seed(seed)
    np.random.seed(seed)

    ctx = SimulationContext()
    ctx.system_config = SystemConfig()
    ctx.system_config.sim_config.order_seed = seed
    ctx.system_config.fault_config.fault_seed = seed
    ctx.system_config.sim_config.planner_type = planner_type
    ctx.system_config.sim_config.scheduler_type = scheduler_type
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
    return {
        "finished": bool(ctx.order_manager.is_all_orders_completed()),
        "task_success_rate": float(metrics.get("Task Success Rate", 0.0)),
        "sim_steps": float(metrics.get("Sim Steps", ctx.clock.now())),
        "planner_avg_time": float(metrics.get("Planner Avg Time", 0.0)),
    }


def evaluate(program_path: str):
    try:
        module = _load_module(program_path)

        planner_cls = None
        scheduler_cls = None
        if TARGET in ("planner", "both"):
            planner_cls = _pick_subclass(module, BasePlanner, "planner")
            PlannerRegistry.register(PLANNER_REG_NAME, planner_cls)
        if TARGET in ("scheduler", "both"):
            scheduler_cls = _pick_subclass(module, BaseScheduler, "scheduler")
            SchedulerRegistry.register(SCHEDULER_REG_NAME, scheduler_cls)

        run_metrics = []
        for seed in SEEDS:
            # Set active algo types before each run.
            if TARGET == "planner":
                active_planner = PLANNER_REG_NAME
                active_scheduler = BASELINE_SCHEDULER
            elif TARGET == "scheduler":
                active_planner = BASELINE_PLANNER
                active_scheduler = SCHEDULER_REG_NAME
            else:
                active_planner = PLANNER_REG_NAME
                active_scheduler = SCHEDULER_REG_NAME

            run_metrics.append(_run_single(int(seed), active_planner, active_scheduler))

        completion_mean = sum(m["task_success_rate"] for m in run_metrics) / len(run_metrics)
        makespan_mean = sum(m["sim_steps"] for m in run_metrics) / len(run_metrics)
        planner_time_mean = sum(m["planner_avg_time"] for m in run_metrics) / len(run_metrics)
        stability_ratio = sum(1.0 if m["finished"] else 0.0 for m in run_metrics) / len(run_metrics)

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
            "seed_count": float(len(SEEDS)),
        }
    except Exception as e:
        return {
            "completion_score": 0.0,
            "makespan_score": 0.0,
            "time_score": 0.0,
            "stability_score": 0.0,
            "combined_score": 0.0,
            "error": str(e),
        }
