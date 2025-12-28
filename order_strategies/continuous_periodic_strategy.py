import math

class ContinuousPeriodicStrategy(OrderGenerationStrategy):
    def __init__(self, config: SimConfig, map_inst: GridMap, specific_config: ContinuousPeriodicConfig):
        super().__init__(config, map_inst, specific_config)
        self.next_order_id = 0
        self.next_generation_step = 0

    def _current_multiplier(self, current_step: int) -> float:
        cfg = self.specific_config
        progress = (current_step % cfg.cycle_duration_steps) / cfg.cycle_duration_steps  # 0~1

        if cfg.wave_type == "sine":
            # 从谷到峰再到谷的正弦波
            angle = progress * 2 * math.pi
            normalized = (math.sin(angle) + 1) / 2  # 0~1
        elif cfg.wave_type == "square":
            normalized = 1.0 if progress < 0.5 else 0.0
        else:
            normalized = 1.0

        # 映射到 valley ~ peak
        return cfg.valley_multiplier + normalized * (cfg.peak_multiplier - cfg.valley_multiplier)

    def update(self, current_step: int) -> List[Order]:
        if self._should_stop():
            return []

        new_orders = []
        if current_step >= self.next_generation_step:
            multiplier = self._current_multiplier(current_step)
            current_batch_size = max(1, int(cfg.base_batch_size * multiplier))

            num_size2 = int(current_batch_size * self.config.size2_ratio)
            num_size1 = current_batch_size - num_size2

            for size, count in [(1, num_size1), (2, num_size2)]:
                for _ in range(count):
                    order = self._generate_single_order(size, self.next_order_id)
                    if order:
                        new_orders.append(order)
                        self.next_order_id += 1
                        self.generated_count += 1

            self.next_generation_step = current_step + cfg.generation_interval_steps

        return new_orders