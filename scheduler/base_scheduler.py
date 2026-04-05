from __future__ import annotations
from abc import ABC, abstractmethod
import random
from typing import Dict, List, Set, Tuple
from typing import TYPE_CHECKING
from core.agv import AGVAction
from core.gridmap import GridMap
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
            and ctx.grid_map is not None
            and ctx.fault_manager is not None
        )
        self.ctx = ctx
        self.env = ctx.env
        self.agv_manager = ctx.agv_manager
        self.order_manager = ctx.order_manager
        self.map = ctx.grid_map
        self.fault_manager = ctx.fault_manager

    @abstractmethod
    def assign_tasks(
        self,
        idle_agv_ids: Set[int],
        planner: BasePlanner
    ) -> Dict[int, List[Tuple[Tuple[int, int], AGVAction, int]]]:
        """
        Assign tasks to idle AGVs.

        Args:
            idle_agv_ids: Set of AGV IDs that are currently idle.
            planner: The planner instance (for context; may be used by implementations).

        Returns:
            Mapping from agv_id to a list of tasks. Each task is a 3-tuple:
            (target_position, action_type, extra_field).
        """
        pass

    def assign_rest_areas(self, agv_ids: Set[int]) -> None:
        """
        Assign rest/wait zone positions to AGVs that need them.

        Args:
            agv_ids: Set of AGV IDs that need a rest area assignment.
        """
        rest_assignments: Dict[int, Tuple[int, int]] = {}
        for agv_id in agv_ids:
            try:
                rest_assignments[agv_id] = self.map.get_wait_zone_position(agv_id)
            except StopIteration:
                break

        return rest_assignments

    def reset(self) -> None:
        """
        Reset scheduler state after a new batch of orders.
        Must be called when order_manager.reset_order() is invoked so the
        scheduler is aware of the new orders.
        """
        pass