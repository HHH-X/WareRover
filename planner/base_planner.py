from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Dict, Tuple, List, Set
from collections import defaultdict
from typing import TYPE_CHECKING

from utils.simulation_context import SimulationContext

if TYPE_CHECKING:
    from scheduler.base_scheduler import BaseScheduler

class BasePlanner(ABC):
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