import json
import random
from abc import ABC, abstractmethod
from typing import List, Dict, Optional

from config.settings import SimConfig
from core.gridmap import GridMap
from core.order import Order
from config.settings import SimConfig

class OrderGenerationStrategy(ABC):
    """Abstract order generation strategy."""

    def __init__(self):
        self.rng = random.Random(SimConfig.order_seed)
        self._all_boxes_by_size: Dict[int, List[dict]] = self._prepare_boxes_by_size()
        self._all_receivers_by_size: Dict[int, List[dict]] = self._prepare_receivers_by_size()

    @abstractmethod
    def update(self, current_step: int) -> List[Order]:
        """Called each simulation step; returns new orders to add (may be empty)."""
        pass

    def _prepare_boxes_by_size(self) -> Dict[int, List[dict]]:
        """Load boxes from map JSON and group by size. Returns {size: [box_dict, ...]}."""
        map_path = SimConfig.map_file
        with open(map_path, "r", encoding="utf-8") as f:
            map_data = json.load(f)

        boxes = map_data.get("boxes", [])
        boxes_by_size: Dict[int, List[dict]] = {}

        for box in boxes:
            size = box.get("size", 1)
            boxes_by_size.setdefault(size, []).append(box)

        return boxes_by_size

    def _prepare_receivers_by_size(self) -> Dict[int, List[dict]]:
        """Load receivers from map JSON and group by size. Returns {size: [receiver_dict, ...]}."""
        map_path = SimConfig.map_file
        with open(map_path, "r", encoding="utf-8") as f:
            map_data = json.load(f)

        receivers = map_data.get("receivers", [])
        receivers_by_size: Dict[int, List[dict]] = {}

        for recv in receivers:
            size = recv.get("size", 1)
            receivers_by_size.setdefault(size, []).append(recv)

        return receivers_by_size

    def _generate_single_order(self, size: int) -> Optional[Order]:
        """Generate one order for the given size; returns None if no box/receiver for that size."""
        boxes = self._all_boxes_by_size.get(size, [])
        receivers = self._all_receivers_by_size.get(size, [])

        if not boxes or not receivers:
            return None

        box = self.rng.choice(boxes)
        goods_ids = box.get("goods_ids", [])
        if not goods_ids:
            return None

        goods_id = self.rng.choice(goods_ids)
        receiver = self.rng.choice(receivers)

        return Order(
            order_id=-1,
            goods_id=goods_id,
            receiver_id=receiver["receiver_id"],
            required_size=size
        )

    def _generate_batch_orders(self, batch_size: int) -> tuple[List[Order], int]:
        """Generate a batch of orders by size2_ratio; returns (new_orders, next_order_id)."""
        num_size2 = int(batch_size * SimConfig.size2_ratio)
        num_size1 = batch_size - num_size2

        new_orders: List[Order] = []

        for size, count in [(1, num_size1), (2, num_size2)]:
            for _ in range(count):
                order = self._generate_single_order(size)
                if order:
                    new_orders.append(order)

        return new_orders
