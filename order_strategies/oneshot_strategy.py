class OneShotStrategy(OrderGenerationStrategy):
    def __init__(self, config: SimConfig, map_inst: GridMap, specific_config: OneShotConfig):
        super().__init__(config, map_inst, specific_config)
        self.orders_to_generate = specific_config.total_orders
        self.next_order_id = 0
        self.generated_in_first_step = False

    def update(self, current_step: int) -> List[Order]:
        if self.generated_in_first_step or self._should_stop():
            return []

        new_orders = []
        remaining = self.orders_to_generate - self.generated_count
        
        # 计算 size 比例（你已有 size2_ratio）
        num_size2 = int(remaining * self.config.size2_ratio)
        num_size1 = remaining - num_size2

        for size, count in [(1, num_size1), (2, num_size2)]:
            for _ in range(count):
                order = self._generate_single_order(size, self.next_order_id)
                if order:
                    new_orders.append(order)
                    self.next_order_id += 1
                    self.generated_count += 1

        self.generated_in_first_step = True
        return new_orders