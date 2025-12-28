class ContinuousConstantStrategy(OrderGenerationStrategy):
    def __init__(self, config: SimConfig, map_inst: GridMap, specific_config: ContinuousConstantConfig):
        super().__init__(config, map_inst, specific_config)
        self.next_order_id = 0
        self.next_generation_step = 0

    def update(self, current_step: int) -> List[Order]:
        if self._should_stop():
            return []

        new_orders = []
        if current_step >= self.next_generation_step:
            # 计算本批次 size 分布
            num_size2 = int(self.specific_config.batch_size * self.config.size2_ratio)
            num_size1 = self.specific_config.batch_size - num_size2

            for size, count in [(1, num_size1), (2, num_size2)]:
                for _ in range(count):
                    order = self._generate_single_order(size, self.next_order_id)
                    if order:
                        new_orders.append(order)
                        self.next_order_id += 1
                        self.generated_count += 1

            # 安排下一波
            self.next_generation_step = current_step + self.specific_config.generation_interval_steps

        return new_orders