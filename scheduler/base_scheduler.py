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

if TYPE_CHECKING:
    from planner.base_planner import BasePlanner

class BaseScheduler(ABC):
    
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

    @abstractmethod
    def assign_tasks(
        self, 
        idle_agv_ids: Set[int], 
        planner: BasePlanner
    ) -> Dict[int, List[Tuple[Tuple[int, int], AGVAction, int]]]:
        """
        为空闲AGV分配任务
        返回：agv_id -> task列表（task是一个三元组：目标位置、动作类型、附加字段）
        """
        pass

    def assign_rest_areas(self, agv_ids: Set[int]) -> None:
        """
        为需要分配休息区的 AGV 分配休息区
        """
        rest_assignments: Dict[int, Tuple[int, int]] = {}
        for agv_id in agv_ids:
            try:
                rest_assignments[agv_id] = self.map.get_wait_zone_position(agv_id)
            except StopIteration:
                # 没有可用休息区了，可以选择忽略或日志记录
                break

        return rest_assignments
    
    def reset(self) -> None:
        """
        当外部调用 order_manager.reset_order() 之后，
        一定要同步调用 scheduler.reset()，让调度器“感知”到新一批订单。
        """
        pass