from __future__ import annotations
from abc import ABC, abstractmethod
import random
from typing import Dict, List, Optional, Set, Tuple
from typing import TYPE_CHECKING
from core.agv import AGVAction
from core.ordermanager import OrderManager, Order
from core.env import Env
from core.fault_manager import FaultManager
from core.agvmanager import AGVManager
from utils.simulation_context import SimulationContext

if TYPE_CHECKING:
    from planner.base_planner import BasePlanner


class BaseScheduler(ABC):

    def __init__(self, ctx: SimulationContext):
        assert (
            ctx.env is not None
            and ctx.agv_manager is not None
            and ctx.order_manager is not None
            and ctx.warehouse_map is not None
            and ctx.fault_manager is not None
            and ctx.logger is not None
        )
        self.ctx = ctx

    @abstractmethod
    def assign_tasks(
        self,
        idle_agv_ids: Set[int],
        planner: BasePlanner
    ) -> Dict[int, List[Tuple[Tuple[int, int], AGVAction, int]]]:
        pass

    def assign_rest_areas(self, agv_ids: Set[int]) -> Dict[int, Tuple[int, int]]:
        rest_assignments: Dict[int, Tuple[int, int]] = {}
        for agv_id in agv_ids:
            agv = self.ctx.agv_manager.get_agv(agv_id)
            floor_grid = self.ctx.warehouse_map.get_floor(agv.floor_id)
            pos = floor_grid.get_wait_zone_position(agv_id)
            if pos is not None:
                rest_assignments[agv_id] = pos
        return rest_assignments

    def reset(self) -> None:
        pass

    def _fill_orders_floor_info(self, orders: List[Order]) -> None:
        """Set target_floor from receiver, source_floor from nearest box floor, and is_cross_floor."""
        wm = self.ctx.warehouse_map
        for order in orders:
            tf = wm.get_receiver_floor(order.receiver_id)
            order.target_floor = tf if tf is not None else 0

            box_ids = wm.get_boxes_by_goods(order.goods_id)
            if not box_ids:
                order.source_floor = 0
                order.is_cross_floor = order.source_floor != order.target_floor
                continue

            best: Optional[Tuple[int, int, int]] = None  # (distance, box_id, floor)
            for bid in box_ids:
                bf = wm.get_box_floor(bid)
                if bf is None:
                    continue
                dist = abs(bf - order.target_floor)
                cand = (dist, bid, bf)
                if best is None or cand < best:
                    best = cand
            if best is None:
                order.source_floor = 0
            else:
                order.source_floor = best[2]
            order.is_cross_floor = order.source_floor != order.target_floor
            if order.is_cross_floor:
                print("Cross floor order: ", order.order_id)

    def _build_cross_floor_tasks(
        self,
        agv_id: int,
        order: Order,
    ) -> Optional[List[Tuple[Tuple[int, int], AGVAction, object]]]:
        src_floor = order.source_floor
        dst_floor = order.target_floor
        agv_size = self.ctx.agv_manager.get_agv_size(agv_id)

        elev_id = self.ctx.elevator_manager.find_elevator(src_floor, dst_floor, agv_size)
        if elev_id is None:
            return None
        elev_pos = self.ctx.warehouse_map.get_elevator_position(elev_id)
        if elev_pos is None:
            return None

        src_grid = self.ctx.warehouse_map.get_floor(src_floor)
        box_ids = src_grid.get_boxes_by_goods(order.goods_id)
        if not box_ids:
            return None
        box_id = random.choice(box_ids)
        order.box_id = box_id
        box_pos = src_grid.get_box_position(box_id)
        if box_pos is None:
            return None

        dst_grid = self.ctx.warehouse_map.get_floor(dst_floor)
        receiver_pos = dst_grid.get_receiver_position(order.receiver_id)
        if receiver_pos is None:
            return None

        outbound_ok = self.ctx.elevator_manager.enqueue_task(
            elevator_id=elev_id,
            agv_id=agv_id,
            from_floor=src_floor,
            to_floor=dst_floor,
        )
        return_ok = self.ctx.elevator_manager.enqueue_task(
            elevator_id=elev_id,
            agv_id=agv_id,
            from_floor=dst_floor,
            to_floor=src_floor,
        )
        if not outbound_ok or not return_ok:
            return None

        return [
            (box_pos, AGVAction.PICK, box_id),
            (elev_pos, AGVAction.ENTER_ELEVATOR, (elev_id, dst_floor)),
            (receiver_pos, AGVAction.HANDOVER, order.order_id),
            (elev_pos, AGVAction.ENTER_ELEVATOR, (elev_id, src_floor)),
            (box_pos, AGVAction.PLACE, None),
        ]
