from dataclasses import dataclass
from typing import Dict, List, Tuple, Optional, Generator
import random
import json
from config.settings import SimConfig,OrderMode, OneShotConfig, ContinuousConstantConfig, ContinuousPeriodicConfig
from core.gridmap import GridMap
from order_strategies import (
    OrderGenerationStrategy,
    OneShotStrategy,
    ContinuousConstantStrategy,
    ContinuousPeriodicStrategy,
    ContinuousParetoStrategy,
    ContinuousBurstStrategy,
)
from utils.logger import global_logger
from core.order import Order


class OrderManager:
    def __init__(self, map_inst: GridMap):
        self.map = map_inst
        self.total_orders_limit = SimConfig.total_orders_limit

        self.all_orders: List[Order] = []
        # 三个订单状态管理：order_id -> Order
        self.unprocessed_orders: Dict[int, Order] = {}
        self.processing_orders: Dict[int, Order] = {}
        self.finished_orders: Dict[int, Order] = {}

        # 日志记录（异常信息）
        self.logs: List[str] = []
        self.next_order_id = 0

        self.strategy = self._create_strategy()

    def _create_strategy(self) -> OrderGenerationStrategy:
        mode = SimConfig.order_mode
        if mode == OrderMode.ONESHOT:
            return OneShotStrategy() 
        elif mode == OrderMode.CONTINUOUS_CONSTANT:
            return ContinuousConstantStrategy()
        elif mode == OrderMode.CONTINUOUS_PERIODIC:
            return ContinuousPeriodicStrategy()
        elif mode == OrderMode.CONTINUOUS_PARETO:
            return ContinuousParetoStrategy()
        elif mode == OrderMode.CONTINUOUS_BURST:
            return ContinuousBurstStrategy()
        else:
            raise ValueError(f"Unknown order_mode: {mode}")
        
    def can_generate_more_orders(self) -> bool:
        return len(self.all_orders) < self.total_orders_limit

    def step(self, current_step: int):
        """由 Simulator 每 step 调用一次"""
        new_orders = self.strategy.update(current_step)
        accepted_count = 0
        for order in new_orders:
            if(self.can_generate_more_orders()):
                order.order_id = self.next_order_id  # 确保 id 唯一
                self.unprocessed_orders[self.next_order_id] = order
                self.all_orders.append(order)
                self.next_order_id += 1
                accepted_count += 1
            else:
                break  # 达到总订单限制，停止添加
        if( accepted_count ):
            global_logger.add_runtime_log(f"[OrderManager] Step {current_step}: Accepted {accepted_count} new orders. Total orders: {len(self.all_orders)}")
    # ========== 第二块功能：订单管理 ==========
    def get_all_orders(self) -> List[Order]:
        return self.all_orders
    
    def get_unprocessed_orders(self) -> List[Order]:
        return list(self.unprocessed_orders.values())
    
    def mark_order_as_processing(self, order_id: int) -> bool:
        order = self.unprocessed_orders.pop(order_id)
        self.processing_orders[order_id] = order
        return True
    
    def complete_order(self, order_id: int, agv_id: int, box_id: Optional[int], agv_pos: Tuple[int, int]) -> bool:
        """
        完成订单，从 processing_orders 或 unprocessed_orders 移动到 finished_orders
        """
        # 确定订单来源
        if order_id in self.processing_orders:
            order_source = self.processing_orders
        elif order_id in self.unprocessed_orders:
            order_source = self.unprocessed_orders
        else:
            self.logs.append(f"[ERROR] Order {order_id} not found in processing or unprocessed orders.")
            return False

        order = order_source[order_id]
        goods_list = self.map.get_goods_by_box(box_id) if box_id is not None else []
        receiver_pos = self.map.get_receiver_position(order.receiver_id)

        if order.goods_id in goods_list and agv_pos == receiver_pos:
            # 从源字典中移除并添加到完成订单
            self.finished_orders[order_id] = order_source.pop(order_id)
            global_logger.add_runtime_log(f"finish order: {order_id}")
            global_logger.task_completed()
            return True
        else:
            self.logs.append(
                f"[FAIL] Order {order_id} not fulfilled by AGV {agv_id}. "
                f"Expected goods {order.goods_id} at receiver {receiver_pos}, "
                f"but got goods {goods_list} at {agv_pos} with box_id={box_id}."
            )

            return False
    
    def is_all_orders_completed(self) -> bool:
        return len(self.unprocessed_orders) == 0 and len(self.processing_orders) == 0 and not self.can_generate_more_orders()

    # ========== 日志访问 ==========

    def get_logs(self) -> List[str]:
        return self.logs

    def reset_order(self):
        self.all_orders.clear()
        self.unprocessed_orders.clear()
        self.processing_orders.clear()
        self.finished_orders.clear()
        self.logs.clear()
        self.next_order_id = 0
        self.strategy = self._create_strategy()  # 重新创建策略
