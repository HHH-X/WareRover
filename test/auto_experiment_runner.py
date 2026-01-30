# 自动化全组合实验脚本
# auto_experiment_runner.py
# - 覆盖 2 Scheduler × 3 Planner × 5 OrderMode × 3 Scene
# - 每个组合重复 NUM_RUNS 次
# - 每个 Scene 输出一个 CSV（行=算法组合，列=平均指标）

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

from test.single_run import run_experiments, summarize  # 假设你把给我的脚本存成 single_run.py

# =========================
# 全局实验参数（你只改这里）
# =========================
NUM_RUNS = 100
BASE_SEED = 42
OUT_DIR = "batch_results"

# =========================
# 场景定义
# =========================
SCENES = {
    "homogeneous": {
        "map_file": "config/map_20_15_32.json",
        "size2_ratio": 0.0,
        "enable_faults": False,
    },
    "heterogeneous": {
        "map_file": "config/map_20_15_hetero.json",
        "size2_ratio": 0.3,
        "enable_faults": False,
    },
    "fault": {
        "map_file": "config/map_20_15_32.json",
        "size2_ratio": 0.0,
        "enable_faults": True,
    },
}

# =========================
# 算法空间
# =========================
SCHEDULERS = [SchedulerType.RANDOM, SchedulerType.TA]
PLANNERS = [PlannerType.ASTAR, PlannerType.CBS_FW, PlannerType.DHC]
ORDER_MODES = list(OrderMode)


# =========================
# 工具函数
# =========================

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


# =========================
# 主流程
# =========================

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

        # ===== 保存 CSV =====
        out_path = os.path.join(OUT_DIR, f"{scene_name}.csv")
        with open(out_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=scene_rows[0].keys())
            writer.writeheader()
            writer.writerows(scene_rows)

        print(f"Saved scene results to {out_path}")


if __name__ == "__main__":
    run_all()
