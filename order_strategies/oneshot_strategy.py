from order_strategies.order_generation_strategy import OrderGenerationStrategy
from config.settings import SystemConfig
from core.order import Order
from typing import List
from core.warehouse_map import WarehouseMap

class OneShotStrategy(OrderGenerationStrategy):
    def __init__(self, system_config: SystemConfig, warehouse_map: WarehouseMap):
        super().__init__(system_config, warehouse_map)
        self.orders_to_generate = self.system_config.sim_config.total_orders_limit
        self.next_order_id = 0
        self.generated_in_first_step = False

    def update(self, current_step: int) -> List[Order]:
        if self.generated_in_first_step:
            return []

        new_orders = []
        remaining = self.orders_to_generate
        num_size2 = int(remaining * self.system_config.sim_config.size2_ratio)
        num_size1 = remaining - num_size2

        for size, count in [(1, num_size1), (2, num_size2)]:
            for _ in range(count):
                order = self._generate_single_order(size)
                if order:
                    new_orders.append(order)

        self.generated_in_first_step = True
        return new_orders