from dataclasses import dataclass

@dataclass
class Order:
    order_id: int
    goods_id: int
    receiver_id: int
    required_size: int
