"""SimulationContext: mutable bag of references, filled incrementally at startup."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional

from config.settings import SystemConfig

if TYPE_CHECKING:
    from core.agvmanager import AGVManager
    from core.env import Env
    from core.fault_manager import FaultManager
    from core.gridmap import GridMap
    from core.ordermanager import OrderManager
    from core.simulator import Simulator
    from planner.base_planner import BasePlanner
    from scheduler.base_scheduler import BaseScheduler
    from utils.logger import GlobalLogger
    from utils.simulation_clock import SimulationClock


@dataclass
class SimulationContext:
    """Create empty, then assign fields in dependency order (see run.py)."""

    system_config: Optional[SystemConfig] = None
    logger: Optional[GlobalLogger] = None
    clock: Optional[SimulationClock] = None
    grid_map: Optional[GridMap] = None
    order_manager: Optional[OrderManager] = None
    agv_manager: Optional[AGVManager] = None
    env: Optional[Env] = None
    fault_manager: Optional[FaultManager] = None
    scheduler: Optional[BaseScheduler] = None
    planner: Optional[BasePlanner] = None
    simulator: Optional[Simulator] = None
