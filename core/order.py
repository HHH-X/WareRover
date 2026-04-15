from dataclasses import dataclass
from typing import Optional


@dataclass
class Order:
    order_id: int
    goods_id: int
    receiver_id: int
    required_size: int

    source_floor: int = 0
    target_floor: int = 0
    is_cross_floor: bool = False

    created_step: Optional[int] = None
    start_processing_step: Optional[int] = None
    finished_step: Optional[int] = None
