import json
import random
from abc import ABC, abstractmethod
from typing import List, Dict, Optional

from config.settings import SystemConfig
from core.order import Order


class OrderGenerationStrategy(ABC):

    def __init__(self, system_config: SystemConfig):
        self.system_config = system_config
        self.rng = random.Random(self.system_config.sim_config.order_seed)
        self._all_boxes_by_size: Dict[int, List[dict]] = self._prepare_boxes_by_size()
        self._all_receivers_by_size: Dict[int, List[dict]] = self._prepare_receivers_by_size()

    @abstractmethod
    def update(self, current_step: int) -> List[Order]:
        pass

    def _load_map_data(self) -> dict:
        map_path = self.system_config.sim_config.map_file
        with open(map_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def _collect_from_floors(self, map_data: dict, key: str) -> List[dict]:
        """Collect items from all floors, or from top-level for single-floor maps."""
        if "floors" in map_data:
            items = []
            for floor_entry in map_data["floors"]:
                items.extend(floor_entry.get(key, []))
            return items
        return map_data.get(key, [])

    def _prepare_boxes_by_size(self) -> Dict[int, List[dict]]:
        map_data = self._load_map_data()
        boxes = self._collect_from_floors(map_data, "boxes")
        boxes_by_size: Dict[int, List[dict]] = {}
        for box in boxes:
            size = box.get("size", 1)
            boxes_by_size.setdefault(size, []).append(box)
        return boxes_by_size

    def _prepare_receivers_by_size(self) -> Dict[int, List[dict]]:
        map_data = self._load_map_data()
        receivers = self._collect_from_floors(map_data, "receivers")
        receivers_by_size: Dict[int, List[dict]] = {}
        for recv in receivers:
            size = recv.get("size", 1)
            receivers_by_size.setdefault(size, []).append(recv)
        return receivers_by_size

    def _generate_single_order(self, size: int) -> Optional[Order]:
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

    def _generate_batch_orders(self, batch_size: int) -> List[Order]:
        num_size2 = int(batch_size * self.system_config.sim_config.size2_ratio)
        num_size1 = batch_size - num_size2
        new_orders: List[Order] = []
        for size, count in [(1, num_size1), (2, num_size2)]:
            for _ in range(count):
                order = self._generate_single_order(size)
                if order:
                    new_orders.append(order)
        return new_orders
