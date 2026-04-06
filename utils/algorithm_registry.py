from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Type

from planner.base_planner import BasePlanner
from scheduler.base_scheduler import BaseScheduler


@dataclass
class RegistryEntry:
    algorithm_cls: Type


class _BaseRegistry:
    _registry: Dict[str, RegistryEntry] = {}

    @classmethod
    def register(cls, name: str, algorithm_cls: Type) -> None:
        normalized = name.strip().lower()
        if not normalized:
            raise ValueError("Algorithm name must be a non-empty string")
        cls._registry[normalized] = RegistryEntry(algorithm_cls=algorithm_cls)

    @classmethod
    def get(cls, name: str) -> Type:
        normalized = name.strip().lower()
        if normalized not in cls._registry:
            raise ValueError(
                f"{cls.__name__} algorithm '{name}' not found. "
                f"Available: {sorted(cls._registry.keys())}"
            )
        return cls._registry[normalized].algorithm_cls

    @classmethod
    def has(cls, name: str) -> bool:
        return name.strip().lower() in cls._registry

    @classmethod
    def list_names(cls) -> list[str]:
        return sorted(cls._registry.keys())


class PlannerRegistry(_BaseRegistry):
    _registry: Dict[str, RegistryEntry] = {}


class SchedulerRegistry(_BaseRegistry):
    _registry: Dict[str, RegistryEntry] = {}


def init_default_registries() -> None:
    from planner.astar_planner import AStarPlanner
    from planner.cbs_fw_planner import FixedWindowCBSPlanner
    from planner.evolved_wrapper_planner import EvolvedWrapperPlanner
    from scheduler.random_scheduler import RandomScheduler
    from scheduler.TA_scheduler import TAScheduler

    PlannerRegistry.register("astar", AStarPlanner)
    PlannerRegistry.register("cbs_fw", FixedWindowCBSPlanner)
    PlannerRegistry.register("evolved_wrapper", EvolvedWrapperPlanner)

    # DHC depends on torch; keep registry usable when torch is absent.
    try:
        from planner.dhc_planner import DHCPlanner
        PlannerRegistry.register("dhc", DHCPlanner)
    except Exception:
        pass

    SchedulerRegistry.register("random", RandomScheduler)
    SchedulerRegistry.register("ta", TAScheduler)


def load_generated_planner(code_str: str, name: str) -> Type[BasePlanner]:
    namespace: dict = {}
    exec(code_str, namespace)

    planner_cls = None
    for value in namespace.values():
        if isinstance(value, type) and issubclass(value, BasePlanner) and value is not BasePlanner:
            planner_cls = value
            break

    if planner_cls is None:
        raise ValueError("No planner class inheriting BasePlanner found in generated code")

    PlannerRegistry.register(name, planner_cls)
    return planner_cls


def load_generated_scheduler(code_str: str, name: str) -> Type[BaseScheduler]:
    namespace: dict = {}
    exec(code_str, namespace)

    scheduler_cls = None
    for value in namespace.values():
        if isinstance(value, type) and issubclass(value, BaseScheduler) and value is not BaseScheduler:
            scheduler_cls = value
            break

    if scheduler_cls is None:
        raise ValueError("No scheduler class inheriting BaseScheduler found in generated code")

    SchedulerRegistry.register(name, scheduler_cls)
    return scheduler_cls
