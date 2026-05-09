from __future__ import annotations

import json

from planner.astar_planner import AStarPlanner
from scheduler.random_scheduler import RandomScheduler
from utils.algorithm_registry import AlgorithmRegistry, default_registry


def _write_config(tmp_path, data: dict):
    path = tmp_path / "algorithms.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_default_registry_loads_config_names() -> None:
    assert default_registry.has_planner("astar")
    assert default_registry.has_planner("cbs_fw")
    assert default_registry.has_planner("dhc")
    assert default_registry.has_scheduler("random")
    assert default_registry.has_scheduler("ta")


def test_registry_resolves_module_specs(tmp_path) -> None:
    config_path = _write_config(
        tmp_path,
        {
            "planners": {"astar": "planner.astar_planner:AStarPlanner"},
            "schedulers": {"random": "scheduler.random_scheduler:RandomScheduler"},
        },
    )

    registry = AlgorithmRegistry(config_path)

    assert registry.get_planner("ASTAR") is AStarPlanner
    assert registry.get_scheduler("random") is RandomScheduler


def test_registry_resolves_file_path_specs(tmp_path) -> None:
    algorithm_file = tmp_path / "external_algorithms.py"
    algorithm_file.write_text(
        """
from typing import Dict, List, Set, Tuple

from core.agv import AGVAction
from planner.base_planner import BasePlanner
from scheduler.base_scheduler import BaseScheduler


class ExternalPlanner(BasePlanner):
    def plan(self, targets: Dict[int, Tuple[Tuple[int, int], Tuple[int, int]]], scheduler):
        return {agv_id: [] for agv_id in targets}


class ExternalScheduler(BaseScheduler):
    def assign_tasks(self, idle_agv_ids: Set[int], planner):
        return {}
""".strip(),
        encoding="utf-8",
    )
    config_path = _write_config(
        tmp_path,
        {
            "planners": {"external": f"{algorithm_file}:ExternalPlanner"},
            "schedulers": {"external": f"{algorithm_file}:ExternalScheduler"},
        },
    )

    registry = AlgorithmRegistry(config_path)

    assert registry.get_planner("external").__name__ == "ExternalPlanner"
    assert registry.get_scheduler("external").__name__ == "ExternalScheduler"


def test_generated_planner_registration_still_works(tmp_path) -> None:
    config_path = _write_config(tmp_path, {"planners": {}, "schedulers": {}})
    registry = AlgorithmRegistry(config_path)
    code = """
from typing import Dict, List, Tuple


class GeneratedPlanner(BasePlanner):
    def plan(self, targets: Dict[int, Tuple[Tuple[int, int], Tuple[int, int]]], scheduler):
        return {agv_id: [] for agv_id in targets}
"""

    planner_cls = registry.load_generated_planner(code, "generated")

    assert registry.has_planner("generated")
    assert registry.get_planner("generated") is planner_cls
