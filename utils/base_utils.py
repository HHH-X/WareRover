from typing import List, Tuple, Optional
from dataclasses import dataclass
from core.order import Order
from core.agv import AGVAction


def orders_to_tasks(orders: List[Order], warehouse_map) -> List[Tuple]:
    """Convert order list to AGV task list; merge consecutive pick/place for the same box."""
    if not orders:
        return []
    tasks = []
    current_box_id = None

    for i, order in enumerate(orders):
        if order.box_id is None:
            raise ValueError(f"Order {order.order_id} has no box_id assigned.")
        if order.box_id != current_box_id:
            current_box_id = order.box_id
            box_position = warehouse_map.get_box_position(current_box_id)
            tasks.append((box_position, AGVAction.PICK, current_box_id))
        receiver_position = warehouse_map.get_receiver_position(order.receiver_id)
        tasks.append((receiver_position, AGVAction.HANDOVER, order.order_id))
        next_box_id = orders[i + 1].box_id if i + 1 < len(orders) else None
        if next_box_id != current_box_id:
            box_position = warehouse_map.get_box_position(current_box_id)
            tasks.append((box_position, AGVAction.PLACE, None))

    return tasks
