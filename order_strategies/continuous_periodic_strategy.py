import math
from order_strategies.order_generation_strategy import OrderGenerationStrategy
from config.settings import SimConfig, ContinuousPeriodicConfig
from core.gridmap import GridMap
from core.order import Order
from typing import List

class ContinuousPeriodicStrategy(OrderGenerationStrategy):
    def __init__(self):
        super().__init__()
        self.next_generation_step = 0

    def _current_multiplier(self, current_step: int) -> float:
        
        progress = (current_step % ContinuousPeriodicConfig.cycle_duration_steps) / ContinuousPeriodicConfig.cycle_duration_steps

        if ContinuousPeriodicConfig.wave_type == "sine":
            angle = progress * 2 * math.pi
            normalized = (math.sin(angle) + 1) / 2
        elif ContinuousPeriodicConfig.wave_type == "square":
            normalized = 1.0 if progress < 0.5 else 0.0
        else:
            normalized = 1.0

        return ContinuousPeriodicConfig.valley_multiplier + normalized * (ContinuousPeriodicConfig.peak_multiplier - ContinuousPeriodicConfig.valley_multiplier)

    def update(self, current_step: int) -> List[Order]:
        new_orders = []
        if current_step >= self.next_generation_step:
            multiplier = self._current_multiplier(current_step)
            current_batch_size = max(1, int(ContinuousPeriodicConfig.base_batch_size * multiplier))

            num_size2 = int(current_batch_size * SimConfig.size2_ratio)
            num_size1 = current_batch_size - num_size2

            for size, count in [(1, num_size1), (2, num_size2)]:
                for _ in range(count):
                    order = self._generate_single_order(size)
                    if order:
                        new_orders.append(order)

            self.next_generation_step = current_step + ContinuousPeriodicConfig.generation_interval_steps

        return new_orders