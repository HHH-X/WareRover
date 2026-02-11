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
        """计算曼哈顿距离"""
        return abs(pos1[0] - pos2[0]) + abs(pos1[1] - pos2[1])
    
    def compute_task_cost(self, agv_pos: Tuple[int, int], order_group: List[Order]) -> int:
        """
        计算某个AGV执行一个连续任务组的成本
        """
        if not order_group:
            return float('inf')

        # 随机选择一个货箱
        first_order = order_group[0]
        box_ids = self.map.get_boxes_by_goods(first_order.goods_id)
        selected_box_id = random.choice(box_ids)
        box_pos = self.map.get_box_position(selected_box_id)

        # 起点：AGV到第一个货箱
        total_cost = self.compute_manhattan_distance(agv_pos, box_pos)

        # 从货箱到第一个接收区
        receiver_pos = self.map.get_receiver_position(first_order.receiver_id)
        total_cost += self.compute_manhattan_distance(box_pos, receiver_pos)

        # 遍历后续订单：前一个接收区 → 下一个接收区
        prev_receiver_pos = receiver_pos
        for order in order_group[1:]:
            next_receiver_pos = self.map.get_receiver_position(order.receiver_id)
            total_cost += self.compute_manhattan_distance(prev_receiver_pos, next_receiver_pos)
            prev_receiver_pos = next_receiver_pos

        # 最后从最后一个接收区回到货箱位置
        total_cost += self.compute_manhattan_distance(prev_receiver_pos, box_pos)

        return total_cost

    def build_cost_matrix(self, idle_agv_ids: List[int], grouped_orders: List[List['Order']]) -> List[List[int]]:
        """
        构建成本矩阵:
        cost_matrix[agv_id_index][order_group_index] = 执行这个任务组的完整成本
        """
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
        使用匈牙利算法在 A x M 的成本矩阵上寻找最优分配：
          - 如果 M >= A：从 M 个任务中为 A 个 AGV 选择 A 个不同的任务，使总成本最小。
          - 如果 M < A：给每个 AGV 添加虚拟任务（大代价），之后过滤掉分配到虚拟任务的 AGV。
        返回: {agv_idx -> task_idx}，其中 task_idx 为原始 grouped_orders 的索引（0..M-1）。
        如果某个 agv 没有被分配到真实任务（仅在 M < A 且该 agv 被分配到虚拟任务时），
        则该 agv 不会出现在返回的字典中。
        """
        if not cost_matrix:
            return {}

        A = len(cost_matrix)                # AGV 数（行数）
        M = len(cost_matrix[0]) if cost_matrix[0] else 0  # 任务数（列数）
        if M == 0:
            return {}

        # 快速检查矩阵形状一致性
        for row in cost_matrix:
            if len(row) != M:
                raise ValueError("All rows in cost_matrix must have same number of columns")

        # 情况一：任务数 >= AGV数 —— 直接运行匈牙利算法
        if M >= A:
            row_ind, col_ind = linear_sum_assignment(cost_matrix)
            # linear_sum_assignment 保证 row_ind 的长度等于 A（所有行都有分配）
            return {int(r): int(c) for r, c in zip(row_ind, col_ind)}

        # 情况二：任务数 < AGV数 —— 填充虚拟任务列
        # 选一个足够大的 big_cost，保证优先选择真实任务
        # 这里用当前矩阵最大值的若干倍 + 1，若所有值都较大则 fallback 到 1e9
        flat_max = max(max(row) for row in cost_matrix)
        if flat_max <= 0:
            big_cost = 10**9
        else:
            big_cost = int(flat_max * (A + 10)) + 1

        # 构造填充后的矩阵（每行追加 A-M 列）
        padded = [row + [big_cost] * (A - M) for row in cost_matrix]  # 现在是 A x A

        row_ind, col_ind = linear_sum_assignment(padded)
        assignment: Dict[int, int] = {}
        for r, c in zip(row_ind, col_ind):
            # 只有当分配列索引小于原始 M 时，说明分配到真实任务
            if c < M:
                assignment[int(r)] = int(c)
            else:
                # 分配到虚拟任务 -> 视为未分配，不放入 assignment
                pass

        return assignment
    
    def assign_tasks(
        self, idle_agv_ids: Set[int], planner
    ) -> Dict[int, List[Tuple[Tuple[int, int], AGVAction, int]]]:
        """
        根据当前空闲 AGV，为其分配任务列表
        :param idle_agv_ids: 空闲 AGV id 集合
        :return: agv_task_map {agv_id: [task_list]}
        """
        if self.order_manager.is_all_orders_completed() or not idle_agv_ids:
            return {}
        
        # 1. 获取所有订单并按尺寸分类
        size_to_orders = defaultdict(list)
        for order in self.order_manager.get_unprocessed_orders():
            size_to_orders[order.required_size].append(order)

        # 2. 获取所有AGV及其尺寸，并按尺寸分类
        size_to_agvs = defaultdict(list)
        for agv_id in idle_agv_ids:
            agv_size = self.agv_manager.get_agv_size(agv_id)
            size_to_agvs[agv_size].append(agv_id)

        agv_task_map = {}

        # 3. 对每种尺寸分别进行任务分配
        for size, agv_ids in size_to_agvs.items():
            valid_orders = size_to_orders.get(size, [])
            if not valid_orders:
                continue  # 该尺寸没有订单，跳过
            #按 goods_id 分组
            goods_to_orders = defaultdict(list)
            for order in valid_orders:
                goods_to_orders[order.goods_id].append(order)
            grouped_orders = list(goods_to_orders.values())

            #构建成本矩阵并分配
            cost_matrix = self.build_cost_matrix(agv_ids, grouped_orders)
            assignment = self.task_assignment(cost_matrix)

            #构建 agv -> orders 映射
            agv_to_orders = defaultdict(list)
            for agv_idx, task_idx in assignment.items():
                agv_id = agv_ids[agv_idx]
                agv_to_orders[agv_id] = grouped_orders[task_idx]

            #转换 orders -> tasks
            for agv_id, orders in agv_to_orders.items():
                copied_orders = deepcopy(orders)
                for order in copied_orders:
                    box_ids = self.map.get_boxes_by_goods(order.goods_id)
                    if not box_ids:
                        raise ValueError(f"No available box found for goods_id={order.goods_id}")
                    order.box_id = random.choice(box_ids)

                agv_task_map[agv_id] = orders_to_tasks(copied_orders, self.map)
                for original_order in orders:
                    self.order_manager.mark_order_as_processing(original_order.order_id)

        return agv_task_map
    