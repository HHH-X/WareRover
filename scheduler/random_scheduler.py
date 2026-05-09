import random
from typing import Dict, List, Optional, Set, Tuple

from core.agv import AGVAction
from core.order import Order
from scheduler.base_scheduler import BaseScheduler
from utils.simulation_context import SimulationContext


class RandomScheduler(BaseScheduler):
    """Random scheduler supporting same-floor and cross-floor orders.

    Same-floor: PICK -> HANDOVER -> PLACE.
    Cross-floor: single AGV rides elevator both ways:
        PICK -> ENTER_ELEVATOR -> HANDOVER -> ENTER_ELEVATOR -> PLACE.

    Orders are considered in creation order (order_id ascending), so cross-floor
    and same-floor work is interleaved instead of deferring all cross-floor
    assignments until after same-floor backlog.
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

        # FIFO by generation: order_id reflects acceptance order at the manager.
        for order in sorted(unprocessed_orders, key=lambda o: o.order_id):
            if order.is_cross_floor:
                self._try_assign_cross_floor_order(order, idle_agv_ids, agv_task_map)
            else:
                self._try_assign_same_floor_order(order, idle_agv_ids, agv_task_map)

        return agv_task_map

    def _try_assign_same_floor_order(
        self,
        order: Order,
        idle_agv_ids: Set[int],
        agv_task_map: Dict[int, List[Tuple[Tuple[int, int], AGVAction, int]]],
    ) -> None:
        candidates: List[int] = []
        for agv_id in idle_agv_ids:
            if agv_id in agv_task_map:
                continue
            if self.agv_manager.get_agv_size(agv_id) != order.required_size:
                continue
            if self.agv_manager.get_agv_floor(agv_id) != order.source_floor:
                continue
            candidates.append(agv_id)
        if not candidates:
            return

        agv_id = random.choice(candidates)
        agv_floor = self.agv_manager.get_agv_floor(agv_id)
        floor_grid = self.warehouse_map.get_floor(agv_floor)
        box_ids = floor_grid.get_boxes_by_goods(order.goods_id)
        if not box_ids:
            return
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

    def _try_assign_cross_floor_order(
        self,
        order: Order,
        idle_agv_ids: Set[int],
        agv_task_map: Dict[int, List[Tuple[Tuple[int, int], AGVAction, int]]],
    ) -> None:
        candidates: List[int] = []
        src_floor = order.source_floor
        for agv_id in idle_agv_ids:
            if agv_id in agv_task_map:
                continue
            agv = self.agv_manager.get_agv(agv_id)
            if agv.floor_id == src_floor and agv.size == order.required_size:
                candidates.append(agv_id)
        if not candidates:
            return

        agv_id = random.choice(candidates)
        tasks = self._build_cross_floor_tasks(agv_id, order)
        if tasks is None:
            return
        agv_task_map[agv_id] = tasks
        self.order_manager.mark_order_as_processing(order.order_id, agv_id)
