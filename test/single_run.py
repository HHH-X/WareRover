"""
Batch algorithm test script (no visualization).
Runs multiple full simulations with the same seed and algorithm combo;
records metrics per run and writes CSV with per-run and averaged metrics.
"""
import os
import argparse
import csv
import random
import numpy as np
from typing import List, Dict

from config.settings import SystemConfig, SimConfig
from core.env import Env
from core.fault_manager import FaultManager
from core.gridmap import GridMap
from core.agvmanager import AGVManager
from core.ordermanager import OrderManager
from core.simulator import Simulator
from utils.algorithm_factory import build_planner, build_scheduler
from utils.algorithm_registry import init_default_registries
from utils.logger import GlobalLogger
from utils.simulation_clock import SimulationClock
from utils.simulation_context import SimulationContext
from tqdm import trange


def run_single_episode(seed: int = 42) -> Dict:
    """Run one full simulation and return final metrics."""
    random.seed(seed)
    np.random.seed(seed)
    ctx = SimulationContext()
    ctx.system_config = SystemConfig()
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
    metrics["finished"] = ctx.order_manager.is_all_orders_completed()
    metrics["sim_steps"] = ctx.clock.now()

    return metrics


def run_experiments(
    num_runs: int,
    base_seed: int,
) -> List[Dict]:
    """Run num_runs episodes with seeds base_seed, base_seed+1, ...; return list of metrics."""

    results: List[Dict] = []
    _bootstrap = SimulationContext()
    _bootstrap.system_config = SystemConfig()
    _bootstrap.logger = GlobalLogger(_bootstrap.system_config.sim_config)
    _bootstrap.clock = SimulationClock(_bootstrap.logger)
    bind_context_runtime(_bootstrap)

    for i in trange(num_runs, desc="Running episodes"):
        logger.global_logger.add_runtime_log(f"=== Starting Run {i} with seed {base_seed + i} ===")
        seed = base_seed + i
        print(f"[Run {i}] seed={seed}")
        metrics = run_single_episode(seed)
        results.append(metrics)

    return results


def summarize(results: List[Dict]) -> Dict:
    """Average all numeric metrics across results."""
    summary = {}

    numeric_keys = [
        k for k in results[0].keys()
        if isinstance(results[0][k], (int, float))
        and k not in ("seed",)
    ]

    for k in numeric_keys:
        summary[k] = sum(r[k] for r in results) / len(results)

    return summary


def save_csv(results: List[Dict], path: str):
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=results[0].keys())
        writer.writeheader()
        writer.writerows(results)

def build_output_filename(
    num_runs: int,
    base_seed: int,
    ext: str = "csv",
) -> str:
    scheduler = SimConfig.scheduler_type.value
    planner = SimConfig.planner_type.value
    order_mode = SimConfig.order_mode.value

    return (
        f"{scheduler}_{planner}_{order_mode}"
        f"_runs{num_runs}_seed{base_seed}.{ext}"
    )

def append_summary_row(results: List[Dict], summary: Dict) -> List[Dict]:
    """Append a summary row (averages) to results."""
    summary_row = {}
    for k in results[0].keys():
        if k in summary:
            summary_row[k] = summary[k]
        else:
            if k == "seed":
                summary_row[k] = "avg"
            else:
                summary_row[k] = ""

    return results + [summary_row]

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=int, default=100)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--out_dir", type=str, default="test")
    args = parser.parse_args()
    os.makedirs(args.out_dir, exist_ok=True)


    print("==== Experiment Config ====")
    print(f"Scheduler: {SimConfig.scheduler_type}")
    print(f"Planner:   {SimConfig.planner_type}")
    print(f"OrderMode: {SimConfig.order_mode}")
    print("===========================")

    results = run_experiments(
        num_runs=args.runs,
        base_seed=args.seed,
    )

    summary = summarize(results)
    results_with_avg = append_summary_row(results, summary)

    print("\n==== Average Metrics ====")
    for k, v in summary.items():
        print(f"{k}: {v:.4f}")

    filename = build_output_filename(
        num_runs=args.runs,
        base_seed=args.seed,
    )

    out_path = os.path.join(args.out_dir, filename)

    save_csv(results_with_avg, out_path)
    print(f"\nSaved detailed results to {out_path}")
    logger.global_logger.close()


if __name__ == "__main__":
    main()
