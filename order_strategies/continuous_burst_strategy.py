import random
from typing import List

from core.order import Order
from config.settings import SimConfig, ContinuousBurstConfig
from order_strategies.order_generation_strategy import OrderGenerationStrategy
from utils.logger import global_logger


class ContinuousBurstStrategy(OrderGenerationStrategy):
    """
    自动随机爆发式促销模式（模拟秒杀/突发高并发）
    - 平时以低频率、小批量生成订单
    - 随机触发“促销”状态，期间订单生成频率和数量大幅提升
    """

    def __init__(self):
        super().__init__()
        self.config = ContinuousBurstConfig()

        # 常态参数
        self.base_batch_size = self.config.base_batch_size
        self.base_interval = self.config.generation_interval_steps

        # 爆发状态参数
        self.burst_batch_size = self.config.burst_peak_batch_size
        self.burst_interval = self.config.burst_interval_steps

        # 状态机
        self.in_burst = False
        self.steps_remaining_in_burst = 0
        self.next_generation_step = 0

    def _try_trigger_burst(self, current_step: int) -> bool:
        """根据概率判断是否触发一次促销"""
        prob_per_step = self.config.burst_probability_per_1000_steps / 1000.0
        return random.random() < prob_per_step

    def update(self, current_step: int) -> List[Order]:
        new_orders = []

        # 检查是否需要触发新的爆发
        if not self.in_burst and self._try_trigger_burst(current_step):
            self.in_burst = True
            self.steps_remaining_in_burst = self.config.burst_duration_steps
            global_logger.add_runtime_log(
                f"[OrderManager] Burst promotion triggered at step {current_step} "
                f"for {self.config.burst_duration_steps} steps!"
            )

        # 更新爆发剩余时间
        if self.in_burst:
            self.steps_remaining_in_burst -= 1
            if self.steps_remaining_in_burst <= 0:
                self.in_burst = False
                global_logger.add_runtime_log(f"[OrderManager] Burst promotion ended at step {current_step}")

        if current_step >= self.next_generation_step:
            # 决定当前批次大小和下一波间隔
            if self.in_burst:
                current_batch_size = self.burst_batch_size
                next_interval = self.burst_interval
            else:
                current_batch_size = self.base_batch_size
                next_interval = self.base_interval

            # 按比例分配 size1 / size2
            num_size2 = int(current_batch_size * SimConfig.size2_ratio)
            num_size1 = current_batch_size - num_size2

            for size, count in [(1, num_size1), (2, num_size2)]:
                for _ in range(count):
                    order = self._generate_single_order(size)
                    if order:
                        new_orders.append(order)

            # 安排下一波
            self.next_generation_step = current_step + next_interval

        return new_orders