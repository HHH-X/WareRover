from abc import ABC, abstractmethod
import random
from typing import Dict, List, Set, Tuple

from core.agv import AGVAction
from core.gridmap import GridMap
from core.ordermanager import OrderManager, Order


class BaseScheduler(ABC):
    
    def __init__(self, order_manager: OrderManager, map_instance: GridMap):
        self.order_manager = order_manager
        self.map = map_instance
        # self.orders = self.order_manager.get_all_orders()
        # self.order_iter = iter(self.orders)

    @abstractmethod
    def assign_tasks(self, idle_agv_ids: Set[int]) -> Dict[int, List[Tuple[Tuple[int, int], AGVAction, int]]]:
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