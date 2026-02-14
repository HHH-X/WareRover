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
from utils.simulation_clock import clock

class OrderManager:
    def __init__(self, map_inst: GridMap):
        self.map = map_inst
        self.total_orders_limit = SimConfig.total_orders_limit

        self.all_orders: List[Order] = []
        self.unprocessed_orders: Dict[int, Order] = {}
        self.processing_orders: Dict[int, Order] = {}
        self.finished_orders: Dict[int, Order] = {}

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

    def step(self):
        """Called once per simulator step."""
        if self.can_generate_more_orders():  
            current_step = clock.now()
            new_orders = self.strategy.update(current_step)
            accepted_count = 0
            for order in new_orders:
                if(self.can_generate_more_orders()):
                    order.order_id = self.next_order_id
                    order.created_step = current_step
                    self.unprocessed_orders[self.next_order_id] = order
                    self.all_orders.append(order)
                    self.next_order_id += 1
                    accepted_count += 1
                else:
                    break
            if accepted_count:
                for order in new_orders[:accepted_count]:
                    global_logger.add_order_generation_log(
                        order_id=order.order_id,
                        receiver_id=order.receiver_id,
                        goods_id=order.goods_id,
                        box_id=getattr(order, 'box_id', None),
                    )
                global_logger.add_runtime_log(f"[OrderManager] Step {current_step}: Accepted {accepted_count} new orders. Total orders: {len(self.all_orders)}")
        self.check_processing_timeouts()
        
    def get_all_orders(self) -> List[Order]:
        return self.all_orders
    
    def get_unprocessed_orders(self) -> List[Order]:
        return list(self.unprocessed_orders.values())
    
    def mark_order_as_processing(self, order_id: int, agv_id: int) -> bool:
        if order_id not in self.unprocessed_orders:
            return False
        order = self.unprocessed_orders.pop(order_id)
        order.start_processing_step = clock.now()
        self.processing_orders[order_id] = order
        box_id = getattr(order, 'box_id', None)
        global_logger.add_order_assignment_log(order_id=order_id, agv_id=agv_id, box_id=box_id)
        return True
    
    def complete_order(self, order_id: int, agv_id: int, box_id: Optional[int], agv_pos: Tuple[int, int]) -> bool:
        """Complete order: move from processing_orders or unprocessed_orders to finished_orders."""
        if order_id in self.processing_orders:
            order_source = self.processing_orders
        elif order_id in self.unprocessed_orders:
            order_source = self.unprocessed_orders
        else:
            global_logger.add_runtime_log(f"[ERROR] Order {order_id} not found in processing or unprocessed orders.")
            return False

        order = order_source[order_id]
        goods_list = self.map.get_goods_by_box(box_id) if box_id is not None else []
        receiver_pos = self.map.get_receiver_position(order.receiver_id)

        if order.goods_id in goods_list and agv_pos == receiver_pos:
            order.finished_step = clock.now()
            self.finished_orders[order_id] = order_source.pop(order_id)
            global_logger.add_runtime_log(f"[OrderManager] Order {order_id} completed by AGV {agv_id} at step {clock.now()}.")
            global_logger.add_order_completion_log(order_id=order_id, agv_id=agv_id)
            global_logger.record_order_completed(self.finished_orders[order_id])
            return True
        else:
            global_logger.add_runtime_log(
                f"[FAIL] Order {order_id} not fulfilled by AGV {agv_id}. "
                f"Expected goods {order.goods_id} at receiver {receiver_pos}, "
                f"but got goods {goods_list} at {agv_pos} with box_id={box_id}."
            )

            return False
    
    def is_all_orders_completed(self) -> bool:
        return len(self.unprocessed_orders) == 0 and len(self.processing_orders) == 0 and not self.can_generate_more_orders()

    def check_processing_timeouts(self):
        """Return timed-out processing orders to unprocessed."""
        timeout_orders = []
        current_step = clock.now()
        for order_id, order in self.processing_orders.items():
            if order.start_processing_step is None:
                continue
            if current_step - order.start_processing_step > SimConfig.order_processing_timeout:
                timeout_orders.append(order_id)

        for order_id in timeout_orders:
            order = self.processing_orders.pop(order_id)
            order.start_processing_step = None
            self.unprocessed_orders[order_id] = order

            global_logger.add_runtime_log(
                f"[OrderManager] Order {order_id} timeout, returned to unprocessed queue."
            )

    def reset_order(self):
        self.all_orders.clear()
        self.unprocessed_orders.clear()
        self.processing_orders.clear()
        self.finished_orders.clear()
        self.next_order_id = 0
        self.strategy = self._create_strategy()
        global_logger.add_runtime_log("[OrderManager] Orders have been reset.")
