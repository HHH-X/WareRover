"""SimulationContext: mutable bag of references, filled incrementally at startup."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from config.settings import SystemConfig
# from utils.logger import GlobalLogger
# from utils.simulation_clock import SimulationClock
# from core.gridmap import GridMap
# from core.ordermanager import OrderManager
# from core.agvmanager import AGVManager
# from core.env import Env
# from core.fault_manager import FaultManager
# from core.simulator import Simulator
# from planner.base_planner import BasePlanner
# from scheduler.base_scheduler import BaseScheduler

@dataclass
class SimulationContext:
    """Create empty, then assign fields in dependency order (see run.py)."""

    system_config: Optional[SystemConfig] = None
    logger: Any = None
    clock: Any = None
    grid_map: Any = None
    order_manager: Any = None
    agv_manager: Any = None
    env: Any = None
    fault_manager: Any = None
    scheduler: Any = None
    planner: Any = None
    simulator: Any = None

