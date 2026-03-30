from typing import List, Dict, Optional, Tuple
import random
from core.gridmap import GridMap
from core.order import Order
from config.settings import SystemConfig, ContinuousConstantConfig
from order_strategies.order_generation_strategy import OrderGenerationStrategy

class ContinuousConstantStrategy(OrderGenerationStrategy):
    def __init__(self, system_config: SystemConfig):
        super().__init__(system_config)
        self.next_generation_step = 0

    def update(self, current_step: int) -> List[Order]:
        new_orders = []
        if current_step >= self.next_generation_step:
            num_size2 = int(self.system_config.continuous_constant_config.batch_size * self.system_config.sim_config.size2_ratio)
            num_size1 = self.system_config.continuous_constant_config.batch_size - num_size2

            for size, count in [(1, num_size1), (2, num_size2)]:
                for _ in range(count):
                    order = self._generate_single_order(size)
                    if order:
                        new_orders.append(order)

            self.next_generation_step = current_step + self.system_config.continuous_constant_config.generation_interval_steps

        return new_orders