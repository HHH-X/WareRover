"""Headless simulation helpers for tests and batch experiments."""
import random
import time
from typing import Dict, List

import numpy as np

from config.settings import SystemConfig
from core.elevator import ElevatorManager
from core.env import Env
from core.fault_manager import FaultManager
from core.warehouse_map import WarehouseMap
from core.agvmanager import AGVManager
from core.ordermanager import OrderManager
from core.simulator import Simulator
from utils.algorithm_registry import default_registry
from utils.logger import GlobalLogger
from utils.simulation_clock import SimulationClock
from utils.simulation_context import SimulationContext


def run_single_episode(seed: int = 42) -> Dict:
    """Run one full simulation and return final metrics."""
    start_time = time.perf_counter()
    random.seed(seed)
    np.random.seed(seed)
    ctx = SimulationContext()
    ctx.system_config = SystemConfig()
    ctx.system_config.sim_config.order_seed = seed
    ctx.system_config.fault_config.fault_seed = seed

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

    while (
        not ctx.order_manager.is_all_orders_completed()
        and ctx.clock.now() < ctx.system_config.sim_config.max_steps
    ):
        ctx.simulator.step()
        ctx.fault_manager.step()
    metrics = ctx.logger.get_final_metrics(ctx.clock.now())
    metrics.update(
        {
            "seed": seed,
            "finished": ctx.order_manager.is_all_orders_completed(),
            "timeout": False,
            "error": "",
            "sim_steps": ctx.clock.now(),
            "elapsed_seconds": time.perf_counter() - start_time,
        }
    )

    return metrics


def run_experiments(
    num_runs: int,
    base_seed: int,
) -> List[Dict]:
    """Run num_runs episodes with seeds base_seed, base_seed+1, ...; return list of metrics."""
    results: List[Dict] = []
    for i in range(num_runs):
        seed = base_seed + i
        print(f"[Run {i}] seed={seed}")
        metrics = run_single_episode(seed)
        results.append(metrics)

    return results


def summarize(results: List[Dict]) -> Dict:
    """Average all numeric metrics across results."""
    if not results:
        return {}

    summary = {}
    excluded_keys = {"seed"}
    numeric_keys = sorted(
        {
            k
            for result in results
            for k, value in result.items()
            if isinstance(value, (int, float))
            and not isinstance(value, bool)
            and k not in excluded_keys
        }
    )

    for k in numeric_keys:
        values = [r[k] for r in results if isinstance(r.get(k), (int, float))]
        if values:
            summary[k] = sum(values) / len(values)

    return summary
