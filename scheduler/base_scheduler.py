import random
from typing import Dict, List, Set, Tuple

from core.agv import AGVAction
from core.gridmap import GridMap
from core.order import OrderManager, Order


class Scheduler:
    def __init__(self, order_manager: OrderManager, map_instance: GridMap):
        self.order_manager = order_manager
        self.map = map_instance
        self.orders = self.order_manager.get_all_orders()
        self.order_iter = iter(self.orders)

    def assign_tasks(self, idle_agv_ids: Set[int]) -> Dict[int, List[Tuple[Tuple[int, int], AGVAction, int]]]:
        """
        为空闲AGV分配任务
        返回：agv_id -> task列表（task是一个三元组：目标位置、动作类型、附加字段）
        """
        agv_task_map: Dict[int, List[Tuple[Tuple[int, int], AGVAction, int]]] = {}

        for agv_id in idle_agv_ids:
            try:
                # 获取一个订单
                order: Order = next(self.order_iter)
            except StopIteration:
                # 所有订单已经分配完毕
                break

            # 获取包含该货物的所有货箱 id 列表
            candidate_box_ids = self.map.get_boxes_by_goods(order.goods_id)
            if not candidate_box_ids:
                # 无法找到包含该货物的箱子，记录异常
                print(f"No box contains goods for order {order.order_id}")
                continue

            # 随机选择一个货箱 id
            selected_box_id = random.choice(candidate_box_ids)

            # 获取该货箱的位置
            box_position = self.map.get_box_position(selected_box_id)

            # 获取接收区的位置
            receiver_position = self.map.get_receiver_position(order.receiver_id)

            # 形成task列表
            tasks = [
                (box_position, AGVAction.PICK, selected_box_id),         # 去取货箱
                (receiver_position, AGVAction.HANDOVER, order.order_id), # 去交付订单
                (box_position, AGVAction.PLACE, None)                    # 去放回箱
            ]

            agv_task_map[agv_id] = tasks

        return agv_task_map

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
