from typing import List, Dict

from core.order import Order
from config.settings import SimConfig, ContinuousParetoConfig
from order_strategies.order_generation_strategy import OrderGenerationStrategy


class ContinuousParetoStrategy(OrderGenerationStrategy):
    """
    Pareto-distributed batch sizes with size-aware hot-SKU bias.
    Generates batches at fixed intervals; SKU choice is biased toward hot SKUs per size.
    """

    def __init__(self):
        super().__init__()
        self.config = ContinuousParetoConfig()
        self.next_generation_step = 0
        self.all_goods_ids_by_size = self._prepare_all_goods_ids_by_size()
        self.hot_goods_ids_by_size = self._prepare_hot_goods_by_size()
        if not any(self.all_goods_ids_by_size.values()):
            raise ValueError("Map has no goods; cannot generate orders.")

    def _prepare_all_goods_ids_by_size(self) -> Dict[int, List[int]]:
        """Collect all goods_id by size."""
        goods_by_size = {}
        for size, boxes in self._all_boxes_by_size.items():
            ids = []
            for box in boxes:
                ids.extend(box.get("goods_ids", []))
            goods_by_size[size] = list(set(ids))
        return goods_by_size

    def _prepare_hot_goods_by_size(self) -> Dict[int, List[int]]:
        """Precompute hot SKUs per size."""
        hot = {}
        for size, goods_ids in self.all_goods_ids_by_size.items():
            if not goods_ids:
                hot[size] = []
                continue
            num_hot = max(1, int(len(goods_ids) * self.config.hot_sku_percentage))
            hot[size] = self.rng.sample(goods_ids, num_hot)
        return hot

    # ------------------------------------------------------------------
    # sampling
    # ------------------------------------------------------------------

    def _choose_goods_id(self, size: int) -> int:
        """Choose goods_id for given size with hot-SKU bias."""
        all_goods = self.all_goods_ids_by_size.get(size, [])
        hot_goods = self.hot_goods_ids_by_size.get(size, [])

        if not all_goods:
            raise RuntimeError(f"No available goods for size={size}")

        if hot_goods and self.rng.random() < 0.8:
            return self.rng.choice(hot_goods)
        return self.rng.choice(all_goods)

    # ------------------------------------------------------------------
    # main update
    # ------------------------------------------------------------------

    def update(self, current_step: int) -> List[Order]:
        new_orders: List[Order] = []

        if current_step < self.next_generation_step:
            return new_orders

        # Pareto-distributed batch size
        raw_count = self.rng.paretovariate(self.config.alpha)
        batch_size = max(1, int(raw_count * self.config.scale))

        # size split
        num_size2 = int(batch_size * SimConfig.size2_ratio)
        num_size1 = batch_size - num_size2

        for size, count in [(1, num_size1), (2, num_size2)]:
            boxes = self._all_boxes_by_size.get(size, [])
            receivers = self._all_receivers_by_size.get(size, [])

            if not boxes or not receivers or count <= 0:
                continue

            for _ in range(count):
                goods_id = self._choose_goods_id(size)
                candidate_boxes = [
                    box for box in boxes
                    if goods_id in box.get("goods_ids", [])
                ]
                if not candidate_boxes:
                    continue

                box = self.rng.choice(candidate_boxes)
                receiver = self.rng.choice(receivers)

                order = Order(
                    order_id=-1,
                    goods_id=goods_id,
                    receiver_id=receiver["receiver_id"],
                    required_size=size
                )
                new_orders.append(order)

        self.next_generation_step = (
            current_step + self.config.generation_interval_steps
        )

        return new_orders
