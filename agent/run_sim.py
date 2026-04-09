"""Headless simulation runner, modelled after test/single_run.py."""
from __future__ import annotations

import random
from typing import Any, Dict, Optional

import numpy as np

from config.settings import SystemConfig
from core.agvmanager import AGVManager
from core.env import Env
from core.fault_manager import FaultManager
from core.gridmap import GridMap
from core.ordermanager import OrderManager
from core.simulator import Simulator
from utils.algorithm_registry import default_registry
from utils.logger import GlobalLogger
from utils.simulation_clock import SimulationClock
from utils.simulation_context import SimulationContext


def run_simulation(
    config: Optional[SystemConfig] = None,
    seed: int = 42,
    max_steps: Optional[int] = None,
) -> Dict[str, Any]:
    """Run a single headless simulation episode and return metrics."""
    random.seed(seed)
    np.random.seed(seed)

    cfg = config or SystemConfig()
    if max_steps is not None:
        cfg.sim_config.max_steps = max_steps
    cfg.sim_config.order_seed = seed
    cfg.fault_config.fault_seed = seed

    ctx = SimulationContext()
    ctx.system_config = cfg
    default_registry.init_defaults()

    ctx.logger = GlobalLogger(ctx)
    ctx.clock = SimulationClock(ctx)
    ctx.grid_map = GridMap(ctx)
    ctx.order_manager = OrderManager(ctx)
    ctx.agv_manager = AGVManager(ctx)
    ctx.env = Env(ctx)
    ctx.fault_manager = FaultManager(ctx)
    ctx.scheduler = default_registry.build_scheduler(ctx)
    ctx.planner = default_registry.build_planner(ctx)
    ctx.simulator = Simulator(ctx)

    while (
        not ctx.order_manager.is_all_orders_completed()
        and ctx.clock.now() < cfg.sim_config.max_steps
    ):
        ctx.simulator.step()
        ctx.fault_manager.step()

    metrics = ctx.logger.get_final_metrics(ctx.clock.now())
    metrics["finished"] = ctx.order_manager.is_all_orders_completed()
    metrics["sim_steps"] = ctx.clock.now()
    return metrics
