import random
from typing import Dict, List, Set, Tuple

from core.agv import AGVAction
from core.order import Order
from scheduler.base_scheduler import BaseScheduler
from utils.simulation_context import SimulationContext


class RandomScheduler(BaseScheduler):
    """Random scheduler supporting same-floor and cross-floor orders.

    Same-floor: PICK -> HANDOVER -> PLACE.
    Cross-floor: single AGV rides elevator both ways:
        PICK -> ENTER_ELEVATOR -> HANDOVER -> ENTER_ELEVATOR -> PLACE.
    """

    def __init__(self, ctx: SimulationContext):
        super().__init__(ctx)
        self.warehouse_map = ctx.warehouse_map
        self.order_manager = ctx.order_manager
        self.agv_manager = ctx.agv_manager
        self.elevator_manager = ctx.elevator_manager
        self.logger = ctx.logger

    def reset(self) -> None:
        self.logger.add_runtime_log(
            "[RandomScheduler] Reset called (stateless scheduler, nothing to clear).")

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

        self._fill_orders_floor_info(unprocessed_orders)

        same_floor_orders: List[Order] = []
        cross_floor_orders: List[Order] = []
        for order in unprocessed_orders:
            if order.is_cross_floor:
                cross_floor_orders.append(order)
            else:
                same_floor_orders.append(order)

        self._assign_same_floor(idle_agv_ids, same_floor_orders, agv_task_map)
        self._assign_cross_floor(idle_agv_ids, cross_floor_orders, agv_task_map)

        return agv_task_map

    def _assign_same_floor(self, idle_agv_ids, orders, agv_task_map):
        if not orders:
            return

        orders_by_size: Dict[int, List[Order]] = {}
        for order in orders:
            orders_by_size.setdefault(order.required_size, []).append(order)
        for lst in orders_by_size.values():
            random.shuffle(lst)

        idle_agvs_by_size: Dict[int, List[int]] = {}
        for agv_id in idle_agv_ids:
            if agv_id in agv_task_map:
                continue
            size = self.agv_manager.get_agv_size(agv_id)
            idle_agvs_by_size.setdefault(size, []).append(agv_id)
        for lst in idle_agvs_by_size.values():
            random.shuffle(lst)

        for size, agv_ids in idle_agvs_by_size.items():
            if size not in orders_by_size:
                continue
            available_orders = orders_by_size[size]
            for agv_id in agv_ids:
                if agv_id in agv_task_map:
                    continue
                if not available_orders:
                    break
                agv_floor = self.agv_manager.get_agv_floor(agv_id)

                matched_order = None
                for i, order in enumerate(available_orders):
                    if order.source_floor == agv_floor:
                        matched_order = available_orders.pop(i)
                        break
                if matched_order is None:
                    continue

                order = matched_order
                floor_grid = self.warehouse_map.get_floor(agv_floor)
                box_ids = floor_grid.get_boxes_by_goods(order.goods_id)
                if not box_ids:
                    continue
                box_id = random.choice(box_ids)
                order.box_id = box_id
                box_pos = floor_grid.get_box_position(box_id)
                receiver_pos = floor_grid.get_receiver_position(order.receiver_id)

                tasks = [
                    (box_pos, AGVAction.PICK, box_id),
                    (receiver_pos, AGVAction.HANDOVER, order.order_id),
                    (box_pos, AGVAction.PLACE, None),
                ]
                agv_task_map[agv_id] = tasks
                self.order_manager.mark_order_as_processing(order.order_id, agv_id)

    def _assign_cross_floor(self, idle_agv_ids, orders, agv_task_map):
        """Single AGV handles the entire cross-floor order by riding the elevator."""
        if not orders:
            return

        for order in list(orders):
            src_floor = order.source_floor
            dst_floor = order.target_floor

            # Find idle AGV on source floor with matching size
            agv_id = None
            for aid in idle_agv_ids:
                if aid in agv_task_map:
                    continue
                agv = self.agv_manager.get_agv(aid)
                if agv.floor_id == src_floor and agv.size == order.required_size:
                    agv_id = aid
                    break
            if agv_id is None:
                continue

            tasks = self._build_cross_floor_tasks(agv_id, order)
            if tasks is None:
                continue
            agv_task_map[agv_id] = tasks
            self.order_manager.mark_order_as_processing(order.order_id, agv_id)
            orders.remove(order)
