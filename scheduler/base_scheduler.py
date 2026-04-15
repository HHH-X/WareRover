from __future__ import annotations
from abc import ABC, abstractmethod
import random
from typing import Dict, List, Set, Tuple
from typing import TYPE_CHECKING
from core.agv import AGVAction
from core.ordermanager import OrderManager, Order
from core.env import Env
from core.fault_manager import FaultManager
from core.agvmanager import AGVManager
from utils.simulation_context import SimulationContext

if TYPE_CHECKING:
    from planner.base_planner import BasePlanner


class BaseScheduler(ABC):

    def __init__(self, ctx: SimulationContext):
        assert (
            ctx.env is not None
            and ctx.agv_manager is not None
            and ctx.order_manager is not None
            and ctx.warehouse_map is not None
            and ctx.fault_manager is not None
            and ctx.logger is not None
        )
        self.ctx = ctx

    @abstractmethod
    def assign_tasks(
        self,
        idle_agv_ids: Set[int],
        planner: BasePlanner
    ) -> Dict[int, List[Tuple[Tuple[int, int], AGVAction, int]]]:
        pass

    def assign_rest_areas(self, agv_ids: Set[int]) -> Dict[int, Tuple[int, int]]:
        rest_assignments: Dict[int, Tuple[int, int]] = {}
        for agv_id in agv_ids:
            agv = self.ctx.agv_manager.get_agv(agv_id)
            floor_grid = self.ctx.warehouse_map.get_floor(agv.floor_id)
            pos = floor_grid.get_wait_zone_position(agv_id)
            if pos is not None:
                rest_assignments[agv_id] = pos
        return rest_assignments

    def reset(self) -> None:
        pass
