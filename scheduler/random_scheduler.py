# random_scheduler.py
import random
from typing import Dict, List, Set, Tuple

from core.agv import AGVAction
from core.gridmap import GridMap
from core.order import Order
from core.ordermanager import OrderManager
from core.agvmanager import AGVManager
from scheduler.base_scheduler import BaseScheduler
from utils.logger import global_logger


class RandomScheduler(BaseScheduler):
    """
    无缓存、无状态的随机调度器：
    - 每次调度都从 OrderManager 拉取最新的未处理订单
    - 随机匹配空闲 AGV 与订单
    """

    def __init__(
        self,
        order_manager: OrderManager,
        map_instance: GridMap,
        agv_manager: AGVManager,
    ):
        self.order_manager = order_manager
        self.map = map_instance
        self.agv_manager = agv_manager

    # ==================================================================
    # reset 接口（现在几乎是空的）
    # ==================================================================
    def reset(self) -> None:
        global_logger.add_runtime_log(
            "[RandomScheduler] Reset called (stateless scheduler, nothing to clear)."
        )

    # ==================================================================
    # 核心调度接口
    # ==================================================================
    def assign_tasks(
        self, idle_agv_ids: Set[int]
    ) -> Dict[int, List[Tuple[Tuple[int, int], AGVAction, int]]]:

        if not idle_agv_ids:
            return {}

        agv_task_map: Dict[int, List[Tuple[Tuple[int, int], AGVAction, int]]] = {}

        # 1. 获取当前所有未处理订单（实时）
        unprocessed_orders: List[Order] = self.order_manager.get_unprocessed_orders()
        if not unprocessed_orders:
            return {}

        # 2. 按 size 对订单分组
        orders_by_size: Dict[int, List[Order]] = {}
        for order in unprocessed_orders:
            orders_by_size.setdefault(order.required_size, []).append(order)

        # 每个 size 内部打乱，保证随机性
        for orders in orders_by_size.values():
            random.shuffle(orders)

        # 3. 按 size 对空闲 AGV 分组
        idle_agvs_by_size: Dict[int, List[int]] = {}
        for agv_id in idle_agv_ids:
            size = self.agv_manager.get_agv_size(agv_id)
            idle_agvs_by_size.setdefault(size, []).append(agv_id)

        for agv_list in idle_agvs_by_size.values():
            random.shuffle(agv_list)

        # 4. 同 size 内随机匹配
        for size, agv_ids in idle_agvs_by_size.items():
            if size not in orders_by_size:
                continue

            available_orders = orders_by_size[size]

            for agv_id in agv_ids:
                if not available_orders:
                    break

                order = available_orders.pop()

                # 随机选择一个包含该货物的箱子
                box_ids = self.map.get_boxes_by_goods(order.goods_id)
                if not box_ids:
                    continue  # 地图异常，跳过

                box_id = random.choice(box_ids)
                box_pos = self.map.get_box_position(box_id)
                receiver_pos = self.map.get_receiver_position(order.receiver_id)

                tasks = [
                    (box_pos, AGVAction.PICK, box_id),
                    (receiver_pos, AGVAction.HANDOVER, order.order_id),
                    (box_pos, AGVAction.PLACE, None),
                ]

                agv_task_map[agv_id] = tasks

                # 标记订单进入 processing
                self.order_manager.mark_order_as_processing(order.order_id)

        return agv_task_map
