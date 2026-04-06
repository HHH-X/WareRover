# random_scheduler.py
import random
from typing import Dict, List, Set, Tuple

from core.agv import AGVAction
from core.order import Order
from scheduler.base_scheduler import BaseScheduler
from utils.simulation_context import SimulationContext

class RandomScheduler(BaseScheduler):
    """
    Stateless random scheduler: fetches unprocessed orders from OrderManager each time
    and randomly matches idle AGVs to orders (by size).
    """

    def __init__(self, ctx: SimulationContext):
        super().__init__(ctx)
        self.map = ctx.grid_map
        self.order_manager = ctx.order_manager
        self.agv_manager = ctx.agv_manager
        self.logger = ctx.logger


    def reset(self) -> None:
        self.logger.add_runtime_log(
            "[RandomScheduler] Reset called (stateless scheduler, nothing to clear)."
        )

    def assign_tasks(
        self, 
        idle_agv_ids: Set[int], 
        planner
    ) -> Dict[int, List[Tuple[Tuple[int, int], AGVAction, int]]]:

        if not idle_agv_ids:
            return {}

        agv_task_map: Dict[int, List[Tuple[Tuple[int, int], AGVAction, int]]] = {}
        unprocessed_orders: List[Order] = self.order_manager.get_unprocessed_orders()
        if not unprocessed_orders:
            return {}

        orders_by_size: Dict[int, List[Order]] = {}
        for order in unprocessed_orders:
            orders_by_size.setdefault(order.required_size, []).append(order)
        for orders in orders_by_size.values():
            random.shuffle(orders)

        idle_agvs_by_size: Dict[int, List[int]] = {}
        for agv_id in idle_agv_ids:
            size = self.agv_manager.get_agv_size(agv_id)
            idle_agvs_by_size.setdefault(size, []).append(agv_id)
        for agv_list in idle_agvs_by_size.values():
            random.shuffle(agv_list)

        for size, agv_ids in idle_agvs_by_size.items():
            if size not in orders_by_size:
                continue

            available_orders = orders_by_size[size]

            for agv_id in agv_ids:
                if not available_orders:
                    break

                order = available_orders.pop()
                box_ids = self.map.get_boxes_by_goods(order.goods_id)
                if not box_ids:
                    continue
                box_id = random.choice(box_ids)
                order.box_id = box_id
                box_pos = self.map.get_box_position(box_id)
                receiver_pos = self.map.get_receiver_position(order.receiver_id)

                tasks = [
                    (box_pos, AGVAction.PICK, box_id),
                    (receiver_pos, AGVAction.HANDOVER, order.order_id),
                    (box_pos, AGVAction.PLACE, None),
                ]

                agv_task_map[agv_id] = tasks
                self.order_manager.mark_order_as_processing(order.order_id, agv_id)

        return agv_task_map
