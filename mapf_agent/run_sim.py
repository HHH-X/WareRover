"""Simulation runner used by both headless and Agent-driven visual runs."""
from __future__ import annotations

import random
import time
from typing import Any, Dict, Optional, Protocol

import numpy as np

from config.settings import SystemConfig
from core.data_generator import generate_send_data
from core.agvmanager import AGVManager
from core.env import Env
from core.fault_manager import FaultManager
from core.elevator import ElevatorManager
from core.warehouse_map import WarehouseMap
from core.ordermanager import OrderManager
from core.simulator import Simulator
from utils.algorithm_registry import default_registry
from utils.logger import GlobalLogger
from utils.simulation_clock import SimulationClock
from utils.simulation_context import SimulationContext


VISUALIZATION_FRAME_DELAY = 0.05


class SimulationVisualizer(Protocol):
    """Optional sink for Agent-driven visualization frames."""

    def start_run(self) -> None: ...

    def has_clients(self) -> bool: ...

    def publish(self, payload: Dict[str, Any]) -> None: ...


def build_simulation_context(cfg: SystemConfig) -> SimulationContext:
    """Create a fully wired simulation context for the given configuration."""
    ctx = SimulationContext()
    ctx.system_config = cfg

    ctx.logger = GlobalLogger(ctx)
    ctx.clock = SimulationClock(ctx)
    ctx.warehouse_map = WarehouseMap(ctx)
    ctx.order_manager = OrderManager(ctx)
    ctx.agv_manager = AGVManager(ctx)
    ctx.elevator_manager = ElevatorManager(ctx)
    ctx.env = Env(ctx)
    ctx.fault_manager = FaultManager(ctx)
    ctx.scheduler = default_registry.build_scheduler(ctx)
    ctx.planner = default_registry.build_planner(ctx)
    ctx.simulator = Simulator(ctx)
    return ctx


def run_simulation(
    config: Optional[SystemConfig] = None,
    seed: int = 42,
    max_steps: Optional[int] = None,
    visualizer: Optional[SimulationVisualizer] = None,
) -> Dict[str, Any]:
    """Run a single simulation episode and return metrics."""
    random.seed(seed)
    np.random.seed(seed)

    cfg = config or SystemConfig()
    if max_steps is not None:
        cfg.sim_config.max_steps = max_steps
    cfg.sim_config.order_seed = seed
    cfg.fault_config.fault_seed = seed

    if visualizer:
        visualizer.start_run()

    ctx = build_simulation_context(cfg)
    visual_init_sent = False
    if visualizer and visualizer.has_clients():
        visualizer.publish(generate_send_data(ctx, data_type="init"))
        visual_init_sent = True

    while (
        not ctx.order_manager.is_all_orders_completed()
        and ctx.clock.now() < cfg.sim_config.max_steps
    ):
        ctx.simulator.step()
        ctx.fault_manager.step()
        if visualizer and visualizer.has_clients():
            if not visual_init_sent:
                visualizer.publish(generate_send_data(ctx, data_type="init"))
                visual_init_sent = True
            visualizer.publish(generate_send_data(ctx, data_type="update"))
            time.sleep(VISUALIZATION_FRAME_DELAY)

    metrics = ctx.logger.get_final_metrics(ctx.clock.now())
    metrics["finished"] = ctx.order_manager.is_all_orders_completed()
    metrics["sim_steps"] = ctx.clock.now()
    return metrics
