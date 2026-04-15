# random_scheduler.py
import random
from typing import Dict, List, Set, Tuple

from core.agv import AGVAction
from core.order import Order
from scheduler.base_scheduler import BaseScheduler
from utils.simulation_context import SimulationContext


class RandomScheduler(BaseScheduler):
    """
    Random scheduler supporting same-floor and cross-floor orders.
    Same-floor: PICK -> HANDOVER -> PLACE (as before).
    Cross-floor: source AGV does PICK -> ELEVATOR_LOAD; destination AGV does ELEVATOR_UNLOAD -> HANDOVER.
    Box auto-resets after cross-floor delivery (simplified).
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

        # Separate same-floor and cross-floor orders
        same_floor_orders: List[Order] = []
        cross_floor_orders: List[Order] = []
        for order in unprocessed_orders:
            if order.is_cross_floor:
                cross_floor_orders.append(order)
            else:
                same_floor_orders.append(order)

        # Handle same-floor orders (original logic)
        self._assign_same_floor(idle_agv_ids, same_floor_orders, agv_task_map)

        # Handle cross-floor orders
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
            if agv_id in {aid for tasks in agv_task_map.values() for aid in [agv_id] if aid in agv_task_map}:
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

                # Find an order whose source_floor matches this AGV's floor
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
        """Assign cross-floor orders: source-floor AGV picks and loads elevator,
        destination-floor AGV unloads and delivers."""
        if not orders:
            return

        for order in list(orders):
            src_floor = order.source_floor
            dst_floor = order.target_floor

            # Find elevator connecting the two floors
            elev_id = self.elevator_manager.find_elevator_for_floors(src_floor, dst_floor)
            if elev_id is None:
                continue
            elev_pos = self.warehouse_map.get_elevator_position(elev_id)
            if elev_pos is None:
                continue

            # Find idle source-floor AGV
            src_agv = None
            for aid in idle_agv_ids:
                if aid in agv_task_map:
                    continue
                agv = self.agv_manager.get_agv(aid)
                if agv.floor_id == src_floor and agv.size == order.required_size:
                    src_agv = aid
                    break
            if src_agv is None:
                continue

            # Find idle destination-floor AGV
            dst_agv = None
            for aid in idle_agv_ids:
                if aid in agv_task_map or aid == src_agv:
                    continue
                agv = self.agv_manager.get_agv(aid)
                if agv.floor_id == dst_floor and agv.size == order.required_size:
                    dst_agv = aid
                    break
            if dst_agv is None:
                continue

            # Assign box
            src_grid = self.warehouse_map.get_floor(src_floor)
            box_ids = src_grid.get_boxes_by_goods(order.goods_id)
            if not box_ids:
                continue
            box_id = random.choice(box_ids)
            order.box_id = box_id
            box_pos = src_grid.get_box_position(box_id)

            # Source AGV: PICK box -> go to elevator -> ELEVATOR_LOAD
            src_tasks = [
                (box_pos, AGVAction.PICK, box_id),
                (elev_pos, AGVAction.ELEVATOR_LOAD, elev_id),
            ]
            agv_task_map[src_agv] = src_tasks

            # Queue elevator transport
            self.elevator_manager.request_transport(elev_id, box_id, src_floor, dst_floor, order.order_id)

            # Destination AGV: go to elevator -> ELEVATOR_UNLOAD -> deliver -> HANDOVER
            dst_grid = self.warehouse_map.get_floor(dst_floor)
            receiver_pos = dst_grid.get_receiver_position(order.receiver_id)
            dst_tasks = [
                (elev_pos, AGVAction.ELEVATOR_UNLOAD, elev_id),
                (receiver_pos, AGVAction.HANDOVER, order.order_id),
            ]
            agv_task_map[dst_agv] = dst_tasks

            self.order_manager.mark_order_as_processing(order.order_id, src_agv)
            orders.remove(order)
