from typing import List

from core.order import Order
from config.settings import SystemConfig, ContinuousBurstConfig
from order_strategies.order_generation_strategy import OrderGenerationStrategy
from utils.logger import GlobalLogger

class ContinuousBurstStrategy(OrderGenerationStrategy):
    """
    Burst promotion mode: low-frequency small batches normally; randomly triggers
    high-frequency large batches for a duration.
    """

    def __init__(self, system_config: SystemConfig, logger: GlobalLogger):
        super().__init__(system_config)
        self.config = self.system_config.continuous_burst_config
        self.base_batch_size = self.config.base_batch_size
        self.base_interval = self.config.generation_interval_steps
        self.burst_batch_size = self.config.burst_peak_batch_size
        self.burst_interval = self.config.burst_interval_steps
        self.in_burst = False
        self.steps_remaining_in_burst = 0
        self.next_generation_step = 0
        self.logger = logger

    def _try_trigger_burst(self, current_step: int) -> bool:
        """Whether to trigger a burst this step (probability-based)."""
        prob_per_step = self.config.burst_probability_per_1000_steps / 1000.0
        return self.rng.random() < prob_per_step

    def update(self, current_step: int) -> List[Order]:
        new_orders = []

        if not self.in_burst and self._try_trigger_burst(current_step):
            self.in_burst = True
            self.steps_remaining_in_burst = self.config.burst_duration_steps
            self.logger.add_runtime_log(
                f"[OrderManager] Burst promotion triggered at step {current_step} "
                f"for {self.config.burst_duration_steps} steps!"
            )

        if self.in_burst:
            self.steps_remaining_in_burst -= 1
            if self.steps_remaining_in_burst <= 0:
                self.in_burst = False
                self.logger.add_runtime_log(f"[OrderManager] Burst promotion ended at step {current_step}")

        if current_step >= self.next_generation_step:
            if self.in_burst:
                current_batch_size = self.burst_batch_size
                next_interval = self.burst_interval
            else:
                current_batch_size = self.base_batch_size
                next_interval = self.base_interval

            num_size2 = int(current_batch_size * self.system_config.sim_config.size2_ratio)
            num_size1 = current_batch_size - num_size2

            for size, count in [(1, num_size1), (2, num_size2)]:
                for _ in range(count):
                    order = self._generate_single_order(size)
                    if order:
                        new_orders.append(order)
            self.next_generation_step = current_step + next_interval

        return new_orders