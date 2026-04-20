import itertools
from copy import deepcopy
from collections import defaultdict
from typing import List, Dict, Tuple, Set
from core.order import Order
from core.agv import AGVAction
from scheduler.base_scheduler import BaseScheduler
from utils.simulation_context import SimulationContext
from scipy.optimize import linear_sum_assignment
from utils.base_utils import orders_to_tasks
import random


class TAScheduler(BaseScheduler):
    def __init__(self, ctx: SimulationContext):
        super().__init__(ctx)
        self.warehouse_map = ctx.warehouse_map
        self.order_manager = ctx.order_manager
        self.agv_manager = ctx.agv_manager
        self.elevator_manager = ctx.elevator_manager
        self.logger = ctx.logger

    def compute_manhattan_distance(self, pos1: Tuple[int, int], pos2: Tuple[int, int]) -> int:
        return abs(pos1[0] - pos2[0]) + abs(pos1[1] - pos2[1])

    def compute_task_cost(self, agv_pos: Tuple[int, int], order_group: List[Order]) -> int:
        if not order_group:
            return float('inf')
        first_order = order_group[0]
        box_ids = self.warehouse_map.get_boxes_by_goods(first_order.goods_id)
        selected_box_id = random.choice(box_ids)
        box_pos = self.warehouse_map.get_box_position(selected_box_id)
        total_cost = self.compute_manhattan_distance(agv_pos, box_pos)
        receiver_pos = self.warehouse_map.get_receiver_position(first_order.receiver_id)
        total_cost += self.compute_manhattan_distance(box_pos, receiver_pos)
        prev_receiver_pos = receiver_pos
        for order in order_group[1:]:
            next_receiver_pos = self.warehouse_map.get_receiver_position(order.receiver_id)
            total_cost += self.compute_manhattan_distance(prev_receiver_pos, next_receiver_pos)
            prev_receiver_pos = next_receiver_pos
        total_cost += self.compute_manhattan_distance(prev_receiver_pos, box_pos)
        return total_cost

    def build_cost_matrix(self, idle_agv_ids: List[int], grouped_orders: List[List[Order]]) -> List[List[int]]:
        cost_matrix = []
        for agv_id in idle_agv_ids:
            agv_pos = self.agv_manager.get_grid_position(agv_id)
            agv_costs = []
            for order_group in grouped_orders:
                cost = self.compute_task_cost(agv_pos, order_group)
                agv_costs.append(cost)
            cost_matrix.append(agv_costs)
        return cost_matrix

    def task_assignment(self, cost_matrix: List[List[int]]) -> Dict[int, int]:
        if not cost_matrix:
            return {}
        A = len(cost_matrix)
        M = len(cost_matrix[0]) if cost_matrix[0] else 0
        if M == 0:
            return {}
        for row in cost_matrix:
            if len(row) != M:
                raise ValueError("All rows in cost_matrix must have same number of columns")
        if M >= A:
            row_ind, col_ind = linear_sum_assignment(cost_matrix)
            return {int(r): int(c) for r, c in zip(row_ind, col_ind)}
        flat_max = max(max(row) for row in cost_matrix)
        if flat_max <= 0:
            big_cost = 10**9
        else:
            big_cost = int(flat_max * (A + 10)) + 1
        padded = [row + [big_cost] * (A - M) for row in cost_matrix]
        row_ind, col_ind = linear_sum_assignment(padded)
        assignment: Dict[int, int] = {}
        for r, c in zip(row_ind, col_ind):
            if c < M:
                assignment[int(r)] = int(c)
        return assignment

    def assign_tasks(
        self, idle_agv_ids: Set[int], planner
    ) -> Dict[int, List[Tuple[Tuple[int, int], AGVAction, int]]]:
        if self.order_manager.is_all_orders_completed() or not idle_agv_ids:
            return {}

        unprocessed = self.order_manager.get_unprocessed_orders()

        # Only handle same-floor orders with TA; cross-floor falls back to simple assignment
        same_floor_orders = [o for o in unprocessed if not o.is_cross_floor]

        size_to_orders = defaultdict(list)
        for order in same_floor_orders:
            size_to_orders[order.required_size].append(order)

        # Filter AGVs: only assign to AGVs on the same floor as the orders' source
        size_to_agvs = defaultdict(list)
        for agv_id in idle_agv_ids:
            agv_size = self.agv_manager.get_agv_size(agv_id)
            size_to_agvs[agv_size].append(agv_id)

        agv_task_map = {}
        for size, agv_ids in size_to_agvs.items():
            valid_orders = size_to_orders.get(size, [])
            if not valid_orders:
                continue

            # Group AGVs by floor, orders by source_floor
            floor_agvs = defaultdict(list)
            for aid in agv_ids:
                floor_agvs[self.agv_manager.get_agv_floor(aid)].append(aid)

            floor_orders = defaultdict(list)
            for o in valid_orders:
                floor_orders[o.source_floor].append(o)

            for fid, f_agvs in floor_agvs.items():
                f_orders = floor_orders.get(fid, [])
                if not f_orders:
                    continue

                goods_to_orders = defaultdict(list)
                for order in f_orders:
                    goods_to_orders[order.goods_id].append(order)
                grouped_orders = list(goods_to_orders.values())

                cost_matrix = self.build_cost_matrix(f_agvs, grouped_orders)
                assignment = self.task_assignment(cost_matrix)

                agv_to_orders = defaultdict(list)
                for agv_idx, task_idx in assignment.items():
                    agv_id = f_agvs[agv_idx]
                    agv_to_orders[agv_id] = grouped_orders[task_idx]

                for agv_id, orders in agv_to_orders.items():
                    copied_orders = deepcopy(orders)
                    for order in copied_orders:
                        box_ids = self.warehouse_map.get_boxes_by_goods(order.goods_id)
                        if not box_ids:
                            raise ValueError(f"No available box for goods_id={order.goods_id}")
                        order.box_id = random.choice(box_ids)

                    agv_task_map[agv_id] = orders_to_tasks(copied_orders, self.warehouse_map)
                    for original_order in orders:
                        self.order_manager.mark_order_as_processing(original_order.order_id, agv_id)

        remaining_cross_floor_orders = [
            o for o in self.order_manager.get_unprocessed_orders() if o.is_cross_floor
        ]
        self._assign_cross_floor(idle_agv_ids, remaining_cross_floor_orders, agv_task_map)
        return agv_task_map

    def _assign_cross_floor(self, idle_agv_ids, orders, agv_task_map):
        if not orders:
            return

        for order in list(orders):
            src_floor = order.source_floor
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
