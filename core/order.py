from dataclasses import dataclass
from typing import Dict, List, Tuple, Optional, Generator
import random
from config.settings import SimConfig
from core.gridmap import GridMap
from utils.logger import global_logger
@dataclass
class Order:
    order_id: int
    goods_id: int
    receiver_id: int

class OrderManager:
    def __init__(self, config: SimConfig, map_inst: GridMap):
        self.config = config
        self.map = map_inst
        self.total_orders = config.num_orders

        self.all_orders: List[Order] = []
        # 三个订单状态管理：order_id -> Order
        self.unprocessed_orders: Dict[int, Order] = {}
        self.processing_orders: Dict[int, Order] = {}
        self.finished_orders: Dict[int, Order] = {}

        # 日志记录（异常信息）
        self.logs: List[str] = []

        self._all_goods = list(self.map.get_all_goods_ids())
        self._all_receivers = list(self.map.get_all_receiver_zone_ids())
        # 初始化时直接生产订单
        self._produce_orders()

    # ========== 订单生产 ==========
    def _produce_orders(self) -> None:
        """生成一批订单并放入 unprocessed_orders 和 all_orders"""
        for order_id in range(self.total_orders):
            goods_id = random.choice(self._all_goods)
            receiver_id = random.choice(self._all_receivers)
            order = Order(
                order_id=order_id,
                goods_id=goods_id,
                receiver_id=receiver_id
            )
            self.unprocessed_orders[order_id] = order
            self.all_orders.append(order)

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
            return True
        else:
            self.logs.append(
                f"[FAIL] Order {order_id} not fulfilled by AGV {agv_id}. "
                f"Expected goods {order.goods_id} at receiver {receiver_pos}, "
                f"but got goods {goods_list} at {agv_pos} with box_id={box_id}."
            )

            return False
    
    def is_all_orders_completed(self) -> bool:
        return len(self.unprocessed_orders) == 0 and len(self.processing_orders) == 0

    # ========== 日志访问 ==========

    def get_logs(self) -> List[str]:
        return self.logs

    def reset(self):
        self._order_counter = 0
        self.unprocessed_orders.clear()
        self.finished_orders.clear()
        self.logs.clear()
