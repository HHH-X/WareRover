from typing import Dict, List, Set, Tuple
from collections import defaultdict
import math

from core.agv import AGVAction
from core.gridmap import GridMap
from core.order import OrderManager, Order
from .base_scheduler import BaseScheduler


class CongestionAwareScheduler(BaseScheduler):

    def __init__(self, order_manager: OrderManager, map_instance: GridMap):
        super().__init__(order_manager, map_instance)

        # 拥塞修正参数
        self.total_actual_duration = 0
        self.total_min_duration = 0
        self.num_task_finished = 0
        self.gamma = 0.0  # 自适应系数

        # 可调参数
        self.catac_radius = 5  # CATAC 搜索半径
        self.cats_square_size = 12  # CATS 方块大小

    # ========== 订单合并 ==========
    def _group_orders_by_goods(self, unprocessed_orders: List[Order]) -> Dict[int, List[Order]]:
        """把同类 goods 的订单合并"""
        grouped = defaultdict(list)
        for order in unprocessed_orders:
            grouped[order.goods_id].append(order)
        return grouped

    # ========== Box 选择 ==========
    def _choose_box_for_goods(self, goods_id: int, receiver_id: int) -> int:
        """
        选择 box：目前用到接收区最近的 box
        """
        candidate_boxes = self.map.get_boxes_with_goods(goods_id)
        receiver_pos = self.map.get_receiver_position(receiver_id)

        if not candidate_boxes:
            return None

        best_box, best_dist = None, float("inf")
        for box_id in candidate_boxes:
            box_pos = self.map.get_box_position(box_id)
            dist = self.map.shortest_distance(box_pos, receiver_pos)
            if dist < best_dist:
                best_box, best_dist = box_id, dist

        return best_box

    # ========== 拥塞评估 ==========
    def _evaluate_congestion_catac(self, pos: Tuple[int, int], all_agv_positions: List[Tuple[int, int]]) -> int:
        """CATAC: 统计在 box 周围半径内的 AGV 数量"""
        count = 0
        for agv_pos in all_agv_positions:
            dist = self.map.shortest_distance(pos, agv_pos)
            if dist <= self.catac_radius:
                count += 1
        return count

    def _evaluate_congestion_cats(self, pos: Tuple[int, int], all_agv_positions: List[Tuple[int, int]]) -> int:
        """CATS: 把地图分成固定方块，统计所在方块的 AGV 数"""
        square_x = pos[0] // self.cats_square_size
        square_y = pos[1] // self.cats_square_size

        count = 0
        for agv_pos in all_agv_positions:
            if (agv_pos[0] // self.cats_square_size == square_x
                and agv_pos[1] // self.cats_square_size == square_y):
                count += 1
        return count

    def _estimate_delay(self, ai_pos: Tuple[int, int], box_pos: Tuple[int, int], all_agv_positions: List[Tuple[int, int]]) -> float:
        """
        综合 CATAC + CATS 的拥塞延迟估计
        """
        catac_score = self._evaluate_congestion_catac(box_pos, all_agv_positions)
        cats_score = self._evaluate_congestion_cats(box_pos, all_agv_positions)

        congestion_score = catac_score + cats_score
        return self.gamma * congestion_score

    # ========== γ 更新 ==========
    def update_gamma(self, actual_duration: int, min_duration: int):
        self.total_actual_duration += actual_duration
        self.total_min_duration += min_duration
        self.num_task_finished += 1
        self.gamma = (self.total_actual_duration - self.total_min_duration) / max(1, self.num_task_finished)

    # ========== 核心分配 ==========
    def assign_tasks(self, idle_agv_ids: Set[int]) -> Dict[int, List[Tuple[Tuple[int, int], AGVAction, int]]]:
        assignments: Dict[int, List[Tuple[Tuple[int, int], AGVAction, int]]] = {}

        unprocessed_orders = self.order_manager.get_unprocessed_orders()
        if not unprocessed_orders:
            return assignments

        # Step1: 合并订单
        grouped_orders = self._group_orders_by_goods(unprocessed_orders)

        # 获取所有 AGV 位置（这里假设 map 提供接口 get_all_agv_positions）
        all_agv_positions = self.map.get_all_agv_positions()

        for agv_id in idle_agv_ids:
            if not grouped_orders:
                break

            best_task, best_score = None, float("inf")

            # Step2: 遍历合并后的订单组
            for goods_id, orders in grouped_orders.items():
                # 取该组里第一个订单代表（receiver 不一定一样，这里先简化）
                order = orders[0]

                # 选择 box
                box_id = self._choose_box_for_goods(goods_id, order.receiver_id)
                if box_id is None:
                    continue
                box_pos = self.map.get_box_position(box_id)
                receiver_pos = self.map.get_receiver_position(order.receiver_id)

                # 计算最短路径距离
                min_duration = self.map.shortest_distance(self.map.get_agv_position(agv_id), box_pos) \
                               + self.map.shortest_distance(box_pos, receiver_pos)

                # 拥塞延迟
                delay = self._estimate_delay(self.map.get_agv_position(agv_id), box_pos, all_agv_positions)

                total_score = min_duration + delay

                if total_score < best_score:
                    best_score = total_score
                    best_task = (goods_id, orders, box_id, box_pos, receiver_pos)

            if best_task is None:
                continue

            goods_id, orders, box_id, box_pos, receiver_pos = best_task

            # Step3: 生成批量任务（串联多个相同 goods 的订单）
            tasks = [(box_pos, AGVAction.PICK, goods_id)]
            for o in orders:
                tasks.append((receiver_pos, AGVAction.DELIVER, o.order_id))
                self.order_manager.mark_order_as_processing(o.order_id)

            assignments[agv_id] = tasks

            # 分配后移除已处理的订单组
            grouped_orders.pop(goods_id)

        return assignments
