from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Dict, Tuple, List, Set
from collections import defaultdict
from core.env import Env
from core.gridmap import GridMap
from core.ordermanager import OrderManager
from core.fault_manager import FaultManager
from core.agvmanager import AGVManager
from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from scheduler.base_scheduler import BaseScheduler

class BasePlanner(ABC):
    def __init__(
        self, 
        env: Env,
        agv_manager: AGVManager,
        order_manager: OrderManager, 
        map: GridMap,
        fault_manager: FaultManager
    ):
        self.env = env
        self.agv_manager = agv_manager
        self.order_manager = order_manager
        self.map = map
        self.fault_manager = fault_manager
        self.max_time = 100

    @abstractmethod
    def plan(
        self,
        targets: Dict[int, Tuple[Tuple[int, int], Tuple[int, int]]],
        scheduler: BaseScheduler
    ) -> Dict[int, List[Tuple[int, int]]]:
        """
        Centralized path planning for AGVs that need replanning.

        Args:
            targets: Mapping from agv_id to (start_pos, target_pos) for each AGV to plan.
            scheduler: The scheduler instance (for context; may be used by implementations).

        Returns:
            Mapping from agv_id to a list of grid positions forming the path.
            Path must NOT include the start position; the first element is the next cell after start.
            Use self.env.get_env_info() for action_queues (waypoints without current pos)
            and current_grid_pos for current positions.
        """
        pass