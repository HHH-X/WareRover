from __future__ import annotations

import copy
from typing import Any, Dict

from config.settings import SystemConfig
from core.agvmanager import AGVManager
from core.env import Env
from core.fault_manager import FaultManager
from core.gridmap import GridMap
from core.ordermanager import OrderManager
from core.simulator import Simulator
from utils.algorithm_factory import build_planner, build_scheduler
from utils.algorithm_registry import init_default_registries
from utils.logger import GlobalLogger
from utils.simulation_clock import SimulationClock
from utils.simulation_context import SimulationContext


def run_once(system_config: SystemConfig, seed: int = 42) -> Dict[str, Any]:
    ctx = SimulationContext()
    ctx.system_config = copy.deepcopy(system_config)
    ctx.system_config.sim_config.order_seed = seed
    ctx.system_config.fault_config.fault_seed = seed
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
    metrics["seed"] = seed
    metrics["finished"] = bool(ctx.order_manager.is_all_orders_completed())
    metrics["sim_steps"] = ctx.clock.now()
    return metrics


def run_with_config(system_config: SystemConfig, runs: int = 1, seed: int = 42) -> Dict[str, Any]:
    if runs <= 1:
        return {"ok": True, "metrics": run_once(system_config, seed=seed)}
    all_metrics = [run_once(system_config, seed + i) for i in range(runs)]
    numeric_keys = [k for k, v in all_metrics[0].items() if isinstance(v, (int, float)) and k != "seed"]
    summary = {k: sum(float(m[k]) for m in all_metrics) / len(all_metrics) for k in numeric_keys}
    return {"ok": True, "metrics": all_metrics, "summary": summary}

