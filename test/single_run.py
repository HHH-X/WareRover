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

from config.settings import SimConfig,FaultConfig
from core.gridmap import GridMap
from core.ordermanager import OrderManager
from core.agvmanager import AGVManager
from core.env import Env
from core.simulator import Simulator
from utils.algorithm_factory import build_scheduler, build_planner
from core.fault_manager import FaultManager
from utils.logger import global_logger
from utils.simulation_clock import clock
from tqdm import trange


def run_single_episode(seed: int) -> Dict:
    """Run one full simulation and return final metrics."""
    random.seed(seed)
    np.random.seed(seed)
    SimConfig.order_seed = seed
    FaultConfig.fault_seed = seed
    clock.reset()
    global_logger.reset()
    grid_map = GridMap()
    ordermanager = OrderManager(grid_map)
    agv_manager = AGVManager(grid_map, ordermanager)
    env = Env(agv_manager, grid_map, ordermanager)
    fault_manager = FaultManager(agv_manager, env, grid_map)

    scheduler = build_scheduler(env,agv_manager,ordermanager, grid_map, fault_manager)
    planner = build_planner(env,agv_manager, ordermanager, grid_map, fault_manager)

    simulator = Simulator(
        grid_map,
        agv_manager,
        ordermanager,
        env,
        scheduler,
        planner,
    )
    while (
        not ordermanager.is_all_orders_completed()
        and clock.now() < SimConfig.max_steps
    ):
        simulator.step()
        fault_manager.step()
    metrics = global_logger.get_final_metrics(clock.now())
    metrics["seed"] = seed
    metrics["finished"] = ordermanager.is_all_orders_completed()
    metrics["sim_steps"] = clock.now()

    return metrics


def run_experiments(
    num_runs: int,
    base_seed: int,
) -> List[Dict]:
    """Run num_runs episodes with seeds base_seed, base_seed+1, ...; return list of metrics."""

    results: List[Dict] = []

    for i in trange(num_runs, desc="Running episodes"):
        global_logger.add_runtime_log(f"=== Starting Run {i} with seed {base_seed + i} ===")
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
    global_logger.close()


if __name__ == "__main__":
    main()
