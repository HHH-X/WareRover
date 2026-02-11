from dataclasses import dataclass
from typing import Optional

@dataclass
class Order:
    order_id: int
    goods_id: int
    receiver_id: int
    required_size: int

    created_step: Optional[int] = None
    start_processing_step: Optional[int] = None
    finished_step: Optional[int] = None