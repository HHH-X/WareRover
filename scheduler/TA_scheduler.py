import itertools
from copy import deepcopy
from collections import defaultdict
from typing import List, Dict, Tuple, Set
from core.gridmap import GridMap
from core.order import Order
from core.ordermanager import OrderManager
from core.agv import AGVAction
from core.agvmanager import AGVManager
from core.env import Env
from core.fault_manager import FaultManager
from scheduler.base_scheduler import BaseScheduler
from scipy.optimize import linear_sum_assignment
from utils.base_utils import orders_to_tasks
import random

class TAScheduler(BaseScheduler):
    def __init__(
        self, 
        env: Env,
        agv_manager: AGVManager,
        order_manager: OrderManager, 
        map: GridMap,
        fault_manager: FaultManager
    ):
        super().__init__(env, agv_manager, order_manager, map, fault_manager)

    def compute_manhattan_distance(self, pos1: Tuple[int, int], pos2: Tuple[int, int]) -> int:
        """Manhattan distance between two grid positions."""
        return abs(pos1[0] - pos2[0]) + abs(pos1[1] - pos2[1])

    def compute_task_cost(self, agv_pos: Tuple[int, int], order_group: List[Order]) -> int:
        """Total cost for one AGV to execute a contiguous order group (pick -> deliver -> ... -> return to box)."""
        if not order_group:
            return float('inf')
        first_order = order_group[0]
        box_ids = self.map.get_boxes_by_goods(first_order.goods_id)
        selected_box_id = random.choice(box_ids)
        box_pos = self.map.get_box_position(selected_box_id)
        total_cost = self.compute_manhattan_distance(agv_pos, box_pos)
        receiver_pos = self.map.get_receiver_position(first_order.receiver_id)
        total_cost += self.compute_manhattan_distance(box_pos, receiver_pos)
        prev_receiver_pos = receiver_pos
        for order in order_group[1:]:
            next_receiver_pos = self.map.get_receiver_position(order.receiver_id)
            total_cost += self.compute_manhattan_distance(prev_receiver_pos, next_receiver_pos)
            prev_receiver_pos = next_receiver_pos
        total_cost += self.compute_manhattan_distance(prev_receiver_pos, box_pos)
        return total_cost

    def build_cost_matrix(self, idle_agv_ids: List[int], grouped_orders: List[List['Order']]) -> List[List[int]]:
        """Build cost matrix: cost_matrix[agv_idx][order_group_idx] = full cost for that AGV to do that group."""
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
        """
        Hungarian algorithm on A x M cost matrix. If M >= A: assign A tasks to A AGVs to minimize total cost.
        If M < A: pad with dummy columns (high cost), then return only AGVs assigned to real tasks.
        Returns: {agv_idx -> task_idx} where task_idx is index into grouped_orders (0..M-1).
        """
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
        """Assign task lists to idle AGVs using cost-based assignment (Hungarian) per size and goods group."""
        if self.order_manager.is_all_orders_completed() or not idle_agv_ids:
            return {}
        size_to_orders = defaultdict(list)
        for order in self.order_manager.get_unprocessed_orders():
            size_to_orders[order.required_size].append(order)
        size_to_agvs = defaultdict(list)
        for agv_id in idle_agv_ids:
            agv_size = self.agv_manager.get_agv_size(agv_id)
            size_to_agvs[agv_size].append(agv_id)
        agv_task_map = {}
        for size, agv_ids in size_to_agvs.items():
            valid_orders = size_to_orders.get(size, [])
            if not valid_orders:
                continue
            goods_to_orders = defaultdict(list)
            for order in valid_orders:
                goods_to_orders[order.goods_id].append(order)
            grouped_orders = list(goods_to_orders.values())
            cost_matrix = self.build_cost_matrix(agv_ids, grouped_orders)
            assignment = self.task_assignment(cost_matrix)
            agv_to_orders = defaultdict(list)
            for agv_idx, task_idx in assignment.items():
                agv_id = agv_ids[agv_idx]
                agv_to_orders[agv_id] = grouped_orders[task_idx]
            for agv_id, orders in agv_to_orders.items():
                copied_orders = deepcopy(orders)
                for order in copied_orders:
                    box_ids = self.map.get_boxes_by_goods(order.goods_id)
                    if not box_ids:
                        raise ValueError(f"No available box found for goods_id={order.goods_id}")
                    order.box_id = random.choice(box_ids)

                agv_task_map[agv_id] = orders_to_tasks(copied_orders, self.map)
                for original_order in orders:
                    self.order_manager.mark_order_as_processing(original_order.order_id, agv_id)

        return agv_task_map
    