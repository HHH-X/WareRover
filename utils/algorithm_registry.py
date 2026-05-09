"""Register, look up, build and dynamically load planner / scheduler classes.

Default algorithms are defined in ``config/algorithms.json``.  Entries are
loaded lazily so heavy dependencies like ``torch`` are imported only when the
selected algorithm is actually used.
"""
from __future__ import annotations

import importlib
import importlib.util
import json
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, Tuple, Type, Union

if TYPE_CHECKING:
    from planner.base_planner import BasePlanner
    from scheduler.base_scheduler import BaseScheduler
    from utils.simulation_context import SimulationContext

_LazySpec = Tuple[str, str]  # (module_or_file_path, class_name)
_Entry = Union[Type, _LazySpec]
_REPO_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_CONFIG_PATH = _REPO_ROOT / "config" / "algorithms.json"


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
    from core.warehouse_map import WarehouseMap
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
        "WarehouseMap": WarehouseMap,
        "OrderManager": OrderManager,
        "Order": Order,
        "Env": Env,
        "FaultManager": FaultManager,
        "AGVManager": AGVManager,
    }


class AlgorithmRegistry:
    def __init__(self, config_path: str | Path | None = None) -> None:
        self._planners: Dict[str, _Entry] = {}
        self._schedulers: Dict[str, _Entry] = {}
        self.load_config(config_path or _DEFAULT_CONFIG_PATH)

    # ── internal ──

    @staticmethod
    def _normalize_name(name: str) -> str:
        key = name.strip().lower()
        if not key:
            raise ValueError("Algorithm name cannot be empty")
        return key

    @staticmethod
    def _parse_lazy_spec(raw_spec: Any) -> _LazySpec:
        if not isinstance(raw_spec, str) or ":" not in raw_spec:
            raise ValueError(
                "Algorithm spec must be a string like "
                "'module.path:ClassName' or 'path/to/file.py:ClassName'"
            )
        import_target, class_name = (part.strip() for part in raw_spec.rsplit(":", 1))
        if not import_target or not class_name:
            raise ValueError(f"Invalid algorithm spec: {raw_spec!r}")
        return import_target, class_name

    @staticmethod
    def _looks_like_file_path(import_target: str) -> bool:
        return (
            import_target.endswith(".py")
            or "/" in import_target
            or "\\" in import_target
        )

    @staticmethod
    def _load_from_file(file_path: str, class_name: str) -> Type:
        path = Path(file_path)
        if not path.is_absolute():
            path = _REPO_ROOT / path
        path = path.resolve()
        if not path.is_file():
            raise FileNotFoundError(f"Algorithm file not found: {path}")

        module_name = f"_algorithm_registry_{path.stem}_{abs(hash(path))}"
        spec = importlib.util.spec_from_file_location(module_name, path)
        if spec is None or spec.loader is None:
            raise ImportError(f"Cannot import algorithm file: {path}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return getattr(module, class_name)

    @classmethod
    def _resolve(cls, entry: _Entry) -> Type:
        if isinstance(entry, tuple):
            import_target, class_name = entry
            if cls._looks_like_file_path(import_target):
                return cls._load_from_file(import_target, class_name)
            mod = importlib.import_module(import_target)
            return getattr(mod, class_name)
        return entry

    @staticmethod
    def _ensure_subclass(cls: Type, base_cls: Type, kind: str, name: str) -> None:
        if not isinstance(cls, type) or not issubclass(cls, base_cls) or cls is base_cls:
            raise TypeError(
                f"{kind.title()} '{name}' must inherit from {base_cls.__name__}; "
                f"got {cls!r}"
            )

    def _load_section(self, data: dict, section: str, target: Dict[str, _Entry]) -> None:
        values = data.get(section, {})
        if not isinstance(values, dict):
            raise ValueError(f"Algorithm config section '{section}' must be an object")
        for name, raw_spec in values.items():
            target[self._normalize_name(name)] = self._parse_lazy_spec(raw_spec)

    # ── config loading ──

    def load_config(self, config_path: str | Path) -> None:
        path = Path(config_path)
        if not path.is_absolute():
            path = _REPO_ROOT / path
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            raise ValueError("Algorithm config root must be an object")

        self._planners.clear()
        self._schedulers.clear()
        self._load_section(data, "planners", self._planners)
        self._load_section(data, "schedulers", self._schedulers)

    # ── registration ──

    def register_planner(self, name: str, cls: Type) -> None:
        self._planners[self._normalize_name(name)] = cls

    def register_scheduler(self, name: str, cls: Type) -> None:
        self._schedulers[self._normalize_name(name)] = cls

    def register_planner_lazy(self, name: str, import_target: str, class_name: str) -> None:
        self._planners[self._normalize_name(name)] = (import_target, class_name)

    def register_scheduler_lazy(self, name: str, import_target: str, class_name: str) -> None:
        self._schedulers[self._normalize_name(name)] = (import_target, class_name)

    # ── lookup ──

    def get_planner(self, name: str) -> Type:
        from planner.base_planner import BasePlanner

        key = self._normalize_name(name)
        if key not in self._planners:
            raise ValueError(
                f"Planner '{name}' not found. Available: {sorted(self._planners)}"
            )
        cls = self._resolve(self._planners[key])
        self._ensure_subclass(cls, BasePlanner, "planner", name)
        self._planners[key] = cls
        return cls

    def get_scheduler(self, name: str) -> Type:
        from scheduler.base_scheduler import BaseScheduler

        key = self._normalize_name(name)
        if key not in self._schedulers:
            raise ValueError(
                f"Scheduler '{name}' not found. Available: {sorted(self._schedulers)}"
            )
        cls = self._resolve(self._schedulers[key])
        self._ensure_subclass(cls, BaseScheduler, "scheduler", name)
        self._schedulers[key] = cls
        return cls

    def has_planner(self, name: str) -> bool:
        return self._normalize_name(name) in self._planners

    def has_scheduler(self, name: str) -> bool:
        return self._normalize_name(name) in self._schedulers

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
