import json
import random
from abc import ABC, abstractmethod
from typing import List, Dict, Optional

from config.settings import SimConfig
from core.gridmap import GridMap
from core.order import Order  # Order dataclass 所在位置


class OrderGenerationStrategy(ABC):
    """订单生成策略抽象接口"""

    def __init__(self, config: SimConfig, map_inst: GridMap, specific_config):
        self.config = config
        self.map = map_inst
        self.specific_config = specific_config  # 对应模式的专用配置 dataclass
        self.generated_count = 0  # 已生成订单总数，用于判断是否达到上限

        # 预先从地图文件读取并按 size 分类的 box 和 receiver 数据
        self._all_goods_by_size: Dict[int, List[dict]] = self._prepare_goods_by_size()
        self._all_receivers_by_size: Dict[int, List[dict]] = self._prepare_receivers_by_size()

    @abstractmethod
    def update(self, current_step: int) -> List[Order]:
        """
        每仿真 step 调用一次。
        返回本 step 需要新增的订单列表（可能为空列表）。
        """
        pass

    # ==================== 数据预处理 ====================
    def _prepare_goods_by_size(self) -> Dict[int, List[dict]]:
        """
        从地图 JSON 文件中读取所有 box，按 size 分类。
        返回结构: {size: [{"goods_ids": [...], ...}, ...]}
        """
        map_path = self.config.map_file
        with open(map_path, "r", encoding="utf-8") as f:
            map_data = json.load(f)

        boxes = map_data.get("boxes", [])
        boxes_by_size: Dict[int, List[dict]] = {}

        for box in boxes:
            size = box.get("size", 1)
            boxes_by_size.setdefault(size, []).append(box)

        return boxes_by_size

    def _prepare_receivers_by_size(self) -> Dict[int, List[dict]]:
        """
        从地图 JSON 文件中读取所有 receiver，按 size 分类。
        返回结构: {size: [{"receiver_id": xxx, ...}, ...]}
        """
        map_path = self.config.map_file
        with open(map_path, "r", encoding="utf-8") as f:
            map_data = json.load(f)

        receivers = map_data.get("receivers", [])
        receivers_by_size: Dict[int, List[dict]] = {}

        for recv in receivers:
            size = recv.get("size", 1)
            receivers_by_size.setdefault(size, []).append(recv)

        return receivers_by_size

    # ==================== 通用订单生成工具 ====================
    def _generate_single_order(self, size: int, order_id: int) -> Optional[Order]:
        """
        生成单个订单的通用逻辑，所有策略均可复用。
        如果对应 size 没有 box 或 receiver，返回 None。
        """
        boxes = self._all_goods_by_size.get(size, [])
        receivers = self._all_receivers_by_size.get(size, [])

        if not boxes or not receivers:
            return None

        box = random.choice(boxes)
        goods_ids = box.get("goods_ids", [])
        if not goods_ids:
            return None

        goods_id = random.choice(goods_ids)
        receiver = random.choice(receivers)

        return Order(
            order_id=order_id,
            goods_id=goods_id,
            receiver_id=receiver["receiver_id"],
            required_size=size
        )

    def _generate_batch_orders(self, batch_size: int, next_order_id: int) -> tuple[List[Order], int]:
        """
        根据 config.size2_ratio 生成一批订单，返回 (新订单列表, 下一个可用的 order_id)
        """
        if batch_size <= 0:
            return [], next_order_id

        # 计算 size1 和 size2 的数量（按比例）
        num_size2 = int(batch_size * self.config.size2_ratio)
        num_size1 = batch_size - num_size2

        new_orders: List[Order] = []
        current_id = next_order_id

        for size, count in [(1, num_size1), (2, num_size2)]:
            for _ in range(count):
                order = self._generate_single_order(size, current_id)
                if order:
                    new_orders.append(order)
                    self.generated_count += 1
                    current_id += 1

        return new_orders, current_id

    # ==================== 通用停止判断 ====================
    def _should_stop(self) -> bool:
        """检查是否已达到总订单数量上限"""
        limit = getattr(self.specific_config, "total_orders_limit", None)
        return limit is not None and self.generated_count >= limit