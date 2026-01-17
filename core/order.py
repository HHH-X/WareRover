from dataclasses import dataclass
from typing import Optional

@dataclass
class Order:
    order_id: int
    goods_id: int
    receiver_id: int
    required_size: int

    created_step: Optional[int] = None       # 订单生成时间
    start_processing_step: Optional[int] = None  # 被调度/分配给 AGV 的时间
    finished_step: Optional[int] = None       # 完成时间