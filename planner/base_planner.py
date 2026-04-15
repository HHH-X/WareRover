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
            and ctx.warehouse_map is not None
            and ctx.fault_manager is not None
            and ctx.system_config is not None
        )
        self.ctx = ctx
        self.max_time = 100

    @abstractmethod
    def plan(
        self,
        targets: Dict[int, Tuple[Tuple[int, int], Tuple[int, int]]],
        scheduler: BaseScheduler
    ) -> Dict[int, List[Tuple[int, int]]]:
        """
        Centralized path planning for AGVs that need replanning.
        Plans are per-floor (AGVs on different floors don't interact).

        Args:
            targets: {agv_id: (start_pos, target_pos)}
        Returns:
            {agv_id: path} (path excludes start position)
        """
        pass
