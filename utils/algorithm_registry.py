"""Unified algorithm registry: register, look-up, build and dynamically load
planner / scheduler implementations.

Each ``AlgorithmRegistry`` instance holds its own mapping so that concurrent
processes (or threads) never interfere with each other.  A module-level
``default_registry`` is provided for convenience in single-process entry
points.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Dict, Type

if TYPE_CHECKING:
    from planner.base_planner import BasePlanner
    from scheduler.base_scheduler import BaseScheduler
    from utils.simulation_context import SimulationContext


class AlgorithmRegistry:
    def __init__(self) -> None:
        self._planners: Dict[str, Type] = {}
        self._schedulers: Dict[str, Type] = {}

    # ── registration ──

    def register_planner(self, name: str, cls: Type) -> None:
        self._planners[name.strip().lower()] = cls

    def register_scheduler(self, name: str, cls: Type) -> None:
        self._schedulers[name.strip().lower()] = cls

    # ── lookup ──

    def get_planner(self, name: str) -> Type:
        key = name.strip().lower()
        if key not in self._planners:
            raise ValueError(
                f"Planner '{name}' not found. Available: {sorted(self._planners)}"
            )
        return self._planners[key]

    def get_scheduler(self, name: str) -> Type:
        key = name.strip().lower()
        if key not in self._schedulers:
            raise ValueError(
                f"Scheduler '{name}' not found. Available: {sorted(self._schedulers)}"
            )
        return self._schedulers[key]

    def has_planner(self, name: str) -> bool:
        return name.strip().lower() in self._planners

    def has_scheduler(self, name: str) -> bool:
        return name.strip().lower() in self._schedulers

    # ── default built-in algorithms ──

    def init_defaults(self) -> None:
        from planner.astar_planner import AStarPlanner
        from planner.cbs_fw_planner import FixedWindowCBSPlanner
        from scheduler.random_scheduler import RandomScheduler
        from scheduler.TA_scheduler import TAScheduler

        self.register_planner("astar", AStarPlanner)
        self.register_planner("cbs_fw", FixedWindowCBSPlanner)

        try:
            from planner.dhc_planner import DHCPlanner
            self.register_planner("dhc", DHCPlanner)
        except Exception:
            pass

        self.register_scheduler("random", RandomScheduler)
        self.register_scheduler("ta", TAScheduler)

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

        namespace: dict = {}
        exec(code_str, namespace)
        for value in namespace.values():
            if isinstance(value, type) and issubclass(value, BasePlanner) and value is not BasePlanner:
                self.register_planner(name, value)
                return value
        raise ValueError("No planner class inheriting BasePlanner found in generated code")

    def load_generated_scheduler(self, code_str: str, name: str) -> Type[BaseScheduler]:
        from scheduler.base_scheduler import BaseScheduler

        namespace: dict = {}
        exec(code_str, namespace)
        for value in namespace.values():
            if isinstance(value, type) and issubclass(value, BaseScheduler) and value is not BaseScheduler:
                self.register_scheduler(name, value)
                return value
        raise ValueError("No scheduler class inheriting BaseScheduler found in generated code")


default_registry = AlgorithmRegistry()
