import random
from typing import Dict, List, Set, Tuple

from core.agv import AGVAction
from core.gridmap import GridMap
from core.order import OrderManager, Order
from core.agvmanager import AGVManager  # ✅ 新增导入
from scheduler.base_scheduler import BaseScheduler


class RandomScheduler(BaseScheduler):
    def __init__(self, order_manager: OrderManager, map_instance: GridMap, agv_manager: AGVManager):
        self.order_manager = order_manager
        self.map = map_instance
        self.agv_manager = agv_manager

        # 使用 unprocessed_orders 而不是 all_orders，避免重复分配
        self.order_iter = iter(self.order_manager.get_unprocessed_orders())

    def assign_tasks(self, idle_agv_ids: Set[int]) -> Dict[int, List[Tuple[Tuple[int, int], AGVAction, int]]]:
        """
        为空闲 AGV 分配任务（仅分配匹配 size 的订单）
        返回：agv_id -> task列表（task是一个三元组：目标位置、动作类型、附加字段）
        """
        agv_task_map: Dict[int, List[Tuple[Tuple[int, int], AGVAction, int]]] = {}

        # 将空闲AGV按size分类，便于匹配
        idle_agvs_by_size: Dict[int, Set[int]] = {}
        for agv_id in idle_agv_ids:
            size = self.agv_manager.get_agv_size(agv_id)
            idle_agvs_by_size.setdefault(size, set()).add(agv_id)

        # 随机化空闲AGV列表以打散分配顺序
        for size, agv_ids in idle_agvs_by_size.items():
            agv_ids = list(agv_ids)
            random.shuffle(agv_ids)

            for agv_id in agv_ids:
                try:
                    # 获取下一个匹配尺寸的订单
                    order: Order = next(order for order in self.order_iter if order.required_size == size)
                except StopIteration:
                    # 没有匹配该尺寸的订单
                    break

                # 获取包含该货物的所有货箱 id 列表
                candidate_box_ids = self.map.get_boxes_by_goods(order.goods_id)
                if not candidate_box_ids:
                    print(f"[WARN] No box contains goods for order {order.order_id}")
                    continue

                # 随机选择一个货箱 id
                selected_box_id = random.choice(candidate_box_ids)

                # 获取该货箱和接收区的位置
                box_position = self.map.get_box_position(selected_box_id)
                receiver_position = self.map.get_receiver_position(order.receiver_id)

                # 生成 task 列表
                tasks = [
                    (box_position, AGVAction.PICK, selected_box_id),         # 去取货箱
                    (receiver_position, AGVAction.HANDOVER, order.order_id), # 去交付订单
                    (box_position, AGVAction.PLACE, None)                    # 去放回箱
                ]

                # 记录任务
                agv_task_map[agv_id] = tasks
                self.order_manager.mark_order_as_processing(order.order_id)

        return agv_task_map
