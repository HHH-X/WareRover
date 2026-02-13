# auto_experiment_runner.py
# Full grid: 2 Schedulers x 3 Planners x 5 OrderModes x 3 Scenes; each combo runs NUM_RUNS times.
# One CSV per scene (rows=algorithm combo, columns=average metrics).

import os
import csv
import itertools
from typing import Dict, List

from config.settings import (
    SimConfig,
    FaultConfig,
    SchedulerType,
    PlannerType,
    OrderMode,
)

from test.single_run import run_experiments, summarize

NUM_RUNS = 100
BASE_SEED = 42
OUT_DIR = "batch_results"

SCENES = {
    "homogeneous": {
        "map_file": "config/maps/map_20_15_32.json",
        "size2_ratio": 0.0,
        "enable_faults": False,
    },
    "heterogeneous": {
        "map_file": "config/maps/map_20_15_hetero.json",
        "size2_ratio": 0.3,
        "enable_faults": False,
    },
    "fault": {
        "map_file": "config/maps/map_20_15_32.json",
        "size2_ratio": 0.0,
        "enable_faults": True,
    },
}

SCHEDULERS = [SchedulerType.RANDOM, SchedulerType.TA]
PLANNERS = [PlannerType.ASTAR, PlannerType.CBS_FW, PlannerType.DHC]
ORDER_MODES = list(OrderMode)


def apply_scene(scene_cfg: Dict):
    SimConfig.map_file = scene_cfg["map_file"]
    SimConfig.size2_ratio = scene_cfg["size2_ratio"]
    FaultConfig.enable_faults = scene_cfg["enable_faults"]


def apply_algorithm(scheduler, planner, order_mode):
    SimConfig.scheduler_type = scheduler
    SimConfig.planner_type = planner
    SimConfig.order_mode = order_mode


def combo_name():
    return f"{SimConfig.scheduler_type.value}+{SimConfig.planner_type.value}+{SimConfig.order_mode.value}"


def run_all():
    os.makedirs(OUT_DIR, exist_ok=True)

    for scene_name, scene_cfg in SCENES.items():
        print(f"\n===== Scene: {scene_name} =====")
        apply_scene(scene_cfg)

        scene_rows: List[Dict] = []

        for scheduler, planner, order_mode in itertools.product(
            SCHEDULERS, PLANNERS, ORDER_MODES
        ):
            apply_algorithm(scheduler, planner, order_mode)

            print(f"Running {combo_name()} ...")

            results = run_experiments(
                num_runs=NUM_RUNS,
                base_seed=BASE_SEED,
            )

            avg = summarize(results)

            row = {
                "scheduler": scheduler.value,
                "planner": planner.value,
                "order_mode": order_mode.value,
            }
            row.update(avg)
            scene_rows.append(row)

        out_path = os.path.join(OUT_DIR, f"{scene_name}.csv")
        with open(out_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=scene_rows[0].keys())
            writer.writeheader()
            writer.writerows(scene_rows)

        print(f"Saved scene results to {out_path}")


if __name__ == "__main__":
    run_all()
