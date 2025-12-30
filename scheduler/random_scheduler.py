# random_scheduler.py
import random
from typing import Dict, List, Set, Tuple

from core.agv import AGVAction
from core.gridmap import GridMap
from core.order import Order
from core.ordermanager import OrderManager
from core.agvmanager import AGVManager
from scheduler.base_scheduler import BaseScheduler


class RandomScheduler(BaseScheduler):
    """
    纯粹随机的调度器。
    每轮 assign_tasks 时会：
        1. 按 size 把空闲 AGV 分组
        2. 按 size 把当前未处理的订单分组并打乱
        3. 同 size 内随机匹配，分配「取箱 → 交付 → 放箱」三连任务
    """

    def __init__(self, order_manager: OrderManager, map_instance: GridMap, agv_manager: AGVManager):
        self.order_manager = order_manager
        self.map = map_instance
        self.agv_manager = agv_manager

        # 内部缓存：每种 size 剩余的可分配订单（reset 时会刷新）
        self._remaining_orders_by_size: Dict[int, List[Order]] = {}

        # 初始化一次（相当于第一次 reset）
        self.reset()

    # ==================================================================
    #                     必须调用的 reset 接口
    # ==================================================================
    def reset(self) -> None:
        """
        当外部调用 order_manager.reset_order() 之后，
        一定要同步调用 scheduler.reset()，让调度器“感知”到新一批订单。
        """
        # 重新获取当前所有未处理订单
        fresh_orders = self.order_manager.get_unprocessed_orders()

        # 按 size 分组并打乱顺序（保证随机性）
        self._remaining_orders_by_size.clear()
        for order in fresh_orders:
            self._remaining_orders_by_size.setdefault(order.required_size, []).append(order)

        for order_list in self._remaining_orders_by_size.values():
            random.shuffle(order_list)

        # 可选：打日志方便调试
        total = sum(len(lst) for lst in self._remaining_orders_by_size.values())
        # print(f"[RandomScheduler] reset completed, {total} new orders ready.")

    # ==================================================================
    #                     核心调度接口
    # ==================================================================
    def assign_tasks(
        self, idle_agv_ids: Set[int]
    ) -> Dict[int, List[Tuple[Tuple[int, int], AGVAction, int]]]:
        """
        为当前空闲的 AGV 分配任务。
        返回格式：{agv_id: [(pos, action, extra), ...], ...}
        """
        if not idle_agv_ids:
            return {}

        agv_task_map: Dict[int, List[Tuple[Tuple[int, int], AGVAction, int]]] = {}

        # 1. 按 size 把空闲 AGV 分组并随机化顺序
        idle_agvs_by_size: Dict[int, List[int]] = {}
        for agv_id in idle_agv_ids:
            size = self.agv_manager.get_agv_size(agv_id)
            idle_agvs_by_size.setdefault(size, []).append(agv_id)

        for agv_list in idle_agvs_by_size.values():
            random.shuffle(agv_list)

        # 2. 遍历每一种 size，尝试匹配订单
        for size, agv_ids in idle_agvs_by_size.items():
            # 该 size 已经没有订单了，直接跳过
            if size not in self._remaining_orders_by_size:
                continue
            remaining_orders = self._remaining_orders_by_size[size]
            if not remaining_orders:
                continue

            for agv_id in agv_ids:
                if not remaining_orders:      # 这批 size 的订单已经分配完
                    break

                # 随机取一个订单（从尾部 pop 效率更高）
                order: Order = remaining_orders.pop()

                # 找到包含该货物的一个箱子（随机选）
                candidate_box_ids = self.map.get_boxes_by_goods(order.goods_id)
                if not candidate_box_ids:
                    # 极端情况：地图数据错误，货物找不到箱子
                    continue

                box_id = random.choice(candidate_box_ids)
                box_pos = self.map.get_box_position(box_id)
                receiver_pos = self.map.get_receiver_position(order.receiver_id)

                # 构造经典三连任务
                tasks = [
                    (box_pos,       AGVAction.PICK,     box_id),        # 取货箱
                    (receiver_pos,  AGVAction.HANDOVER, order.order_id),  # 交付订单
                    (box_pos,       AGVAction.PLACE,    None),           # 放回货箱
                ]

                agv_task_map[agv_id] = tasks
                # 标记订单进入“处理中”状态
                self.order_manager.mark_order_as_processing(order.order_id)

        return agv_task_map