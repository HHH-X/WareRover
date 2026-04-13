"""Unified algorithm registry: register, look-up, build and dynamically load
planner / scheduler implementations.

Built-in algorithms are registered lazily (as import specs) so that heavy
dependencies like ``torch`` are only loaded when actually needed.

Each ``AlgorithmRegistry`` instance holds its own mapping so that concurrent
processes (or threads) never interfere with each other.  A module-level
``default_registry`` is provided for convenience in single-process entry
points.
"""
from __future__ import annotations

import importlib
from typing import TYPE_CHECKING, Any, Dict, Tuple, Type, Union

if TYPE_CHECKING:
    from planner.base_planner import BasePlanner
    from scheduler.base_scheduler import BaseScheduler
    from utils.simulation_context import SimulationContext

_LazySpec = Tuple[str, str]  # (module_path, class_name)
_Entry = Union[Type, _LazySpec]


def _build_exec_namespace() -> dict:
    """Build a namespace pre-populated with common imports for exec'd code."""
    import abc
    import math
    import random
    import heapq
    from collections import defaultdict, deque
    from typing import Dict, List, Set, Tuple, Optional

    from utils.simulation_context import SimulationContext
    from core.agv import AGVAction
    from core.gridmap import GridMap
    from core.ordermanager import OrderManager, Order
    from core.env import Env
    from core.fault_manager import FaultManager
    from core.agvmanager import AGVManager

    return {
        "ABC": abc.ABC,
        "abstractmethod": abc.abstractmethod,
        "math": math,
        "random": random,
        "heapq": heapq,
        "defaultdict": defaultdict,
        "deque": deque,
        "Dict": Dict,
        "List": List,
        "Set": Set,
        "Tuple": Tuple,
        "Optional": Optional,
        "SimulationContext": SimulationContext,
        "AGVAction": AGVAction,
        "GridMap": GridMap,
        "OrderManager": OrderManager,
        "Order": Order,
        "Env": Env,
        "FaultManager": FaultManager,
        "AGVManager": AGVManager,
    }


# ── Default built-in algorithms (lazy specs) ──

_DEFAULT_PLANNERS: Dict[str, _LazySpec] = {
    "astar": ("planner.astar_planner", "AStarPlanner"),
    "cbs_fw": ("planner.cbs_fw_planner", "FixedWindowCBSPlanner"),
    "dhc": ("planner.dhc_planner", "DHCPlanner"),
}

_DEFAULT_SCHEDULERS: Dict[str, _LazySpec] = {
    "random": ("scheduler.random_scheduler", "RandomScheduler"),
    "ta": ("scheduler.TA_scheduler", "TAScheduler"),
}


class AlgorithmRegistry:
    def __init__(self) -> None:
        self._planners: Dict[str, _Entry] = dict(_DEFAULT_PLANNERS)
        self._schedulers: Dict[str, _Entry] = dict(_DEFAULT_SCHEDULERS)

    # ── internal ──

    @staticmethod
    def _resolve(entry: _Entry) -> Type:
        if isinstance(entry, tuple):
            module_path, class_name = entry
            mod = importlib.import_module(module_path)
            return getattr(mod, class_name)
        return entry

    # ── registration ──

    def register_planner(self, name: str, cls: Type) -> None:
        self._planners[name.strip().lower()] = cls

    def register_scheduler(self, name: str, cls: Type) -> None:
        self._schedulers[name.strip().lower()] = cls

    def register_planner_lazy(self, name: str, module_path: str, class_name: str) -> None:
        self._planners[name.strip().lower()] = (module_path, class_name)

    def register_scheduler_lazy(self, name: str, module_path: str, class_name: str) -> None:
        self._schedulers[name.strip().lower()] = (module_path, class_name)

    # ── lookup ──

    def get_planner(self, name: str) -> Type:
        key = name.strip().lower()
        if key not in self._planners:
            raise ValueError(
                f"Planner '{name}' not found. Available: {sorted(self._planners)}"
            )
        cls = self._resolve(self._planners[key])
        self._planners[key] = cls
        return cls

    def get_scheduler(self, name: str) -> Type:
        key = name.strip().lower()
        if key not in self._schedulers:
            raise ValueError(
                f"Scheduler '{name}' not found. Available: {sorted(self._schedulers)}"
            )
        cls = self._resolve(self._schedulers[key])
        self._schedulers[key] = cls
        return cls

    def has_planner(self, name: str) -> bool:
        return name.strip().lower() in self._planners

    def has_scheduler(self, name: str) -> bool:
        return name.strip().lower() in self._schedulers

    # ── factory helpers ──

    def build_planner(self, ctx: SimulationContext) -> BasePlanner:
        sim_cfg = ctx.system_config.sim_config
        planner_cls = self.get_planner(sim_cfg.planner_type)
        sim_cfg.force_replan_every_step = sim_cfg.planner_type.strip().lower() == "dhc"
        return planner_cls(ctx)

    def build_scheduler(self, ctx: SimulationContext) -> BaseScheduler:
        name = ctx.system_config.sim_config.scheduler_type
        scheduler_cls = self.get_scheduler(name)
        return scheduler_cls(ctx)

    # ── dynamic code loading ──

    def load_generated_planner(self, code_str: str, name: str) -> Type[BasePlanner]:
        from planner.base_planner import BasePlanner

        namespace: dict = _build_exec_namespace()
        namespace["BasePlanner"] = BasePlanner
        exec(code_str, namespace)
        for value in namespace.values():
            if isinstance(value, type) and issubclass(value, BasePlanner) and value is not BasePlanner:
                self.register_planner(name, value)
                return value
        raise ValueError("No planner class inheriting BasePlanner found in generated code")

    def load_generated_scheduler(self, code_str: str, name: str) -> Type[BaseScheduler]:
        from scheduler.base_scheduler import BaseScheduler

        namespace: dict = _build_exec_namespace()
        namespace["BaseScheduler"] = BaseScheduler
        exec(code_str, namespace)
        for value in namespace.values():
            if isinstance(value, type) and issubclass(value, BaseScheduler) and value is not BaseScheduler:
                self.register_scheduler(name, value)
                return value
        raise ValueError("No scheduler class inheriting BaseScheduler found in generated code")


default_registry = AlgorithmRegistry()
