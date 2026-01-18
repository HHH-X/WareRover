from typing import List

from core.order import Order
from config.settings import SimConfig, ContinuousParetoConfig
from order_strategies.order_generation_strategy import OrderGenerationStrategy


class ContinuousParetoStrategy(OrderGenerationStrategy):
    """
    Pareto 分布 + 热点 SKU 模式
    - 每隔固定步数生成一批订单
    - 每批的订单数量服从 Pareto 分布（长尾，模拟订单量波动）
    - 商品（goods_id）选择时，少数热点 SKU 被大幅偏向选中（80/20 法则）
    """

    def __init__(self):
        super().__init__()
        self.config = ContinuousParetoConfig()
        self.next_generation_step = 0

        # 预计算热点 SKU
        self.all_goods_ids = self._prepare_all_goods_ids()
        self.hot_goods_ids = self._prepare_hot_goods()

        if not self.all_goods_ids:
            raise ValueError("Map 中没有找到任何 goods，无法生成订单")

    def _prepare_all_goods_ids(self) -> List[int]:
        """收集地图中所有可用的 goods_id"""
        all_ids = []
        for size in self._all_goods_by_size:
            for box in self._all_goods_by_size[size]:
                all_ids.extend(box.get("goods_ids", []))
        return list(set(all_ids))  # 去重

    def _prepare_hot_goods(self) -> List[int]:
        """根据配置选取热点 SKU"""
        if not self.all_goods_ids:
            return []

        hot_percentage = self.config.hot_sku_percentage
        num_hot = max(1, int(len(self.all_goods_ids) * hot_percentage))
        return self.rng.sample(self.all_goods_ids, num_hot)

    def _choose_goods_id_with_hot_bias(self) -> int:
        """
        带热点偏置的 goods_id 选择
        - 热点 SKU 被选中的概率 = 正常概率 × multiplier
        """
        if self.rng.random() < 0.8 and self.hot_goods_ids:  # 粗略实现 80% 来自热点（可调）
            return self.rng.choice(self.hot_goods_ids)
        else:
            return self.rng.choice(self.all_goods_ids)

    def update(self, current_step: int) -> List[Order]:
        new_orders = []

        if current_step >= self.next_generation_step:
            # 使用 Pareto 分布决定本批次订单数量（长尾分布）
            # paretovariate(alpha) 返回 ≥1 的值，alpha 越小尾巴越重
            raw_count = self.rng.paretovariate(self.config.alpha)
            batch_size = max(1, int(raw_count * self.config.scale))

            # 根据 size2_ratio 分配 size1 / size2
            num_size2 = int(batch_size * SimConfig.size2_ratio)
            num_size1 = batch_size - num_size2

            for size, count in [(1, num_size1), (2, num_size2)]:
                boxes = self._all_goods_by_size.get(size, [])
                receivers = self._all_receivers_by_size.get(size, [])
                if not boxes or not receivers:
                    continue

                for _ in range(count):
                    box = self.rng.choice(boxes)
                    # 关键：使用带偏置的 goods 选择
                    goods_id = self._choose_goods_id_with_hot_bias()

                    # 确保该 goods_id 确实属于选中的 box（如果不属于则重新选 box）
                    while goods_id not in box.get("goods_ids", []):
                        box = self.rng.choice(boxes)

                    receiver = self.rng.choice(receivers)

                    order = Order(
                        order_id=-1,  # 由 OrderManager 分配最终 id
                        goods_id=goods_id,
                        receiver_id=receiver["receiver_id"],
                        required_size=size
                    )
                    new_orders.append(order)

            # 安排下一波
            self.next_generation_step = current_step + self.config.generation_interval_steps

        return new_orders