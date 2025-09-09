from typing import List, Tuple, Optional
from dataclasses import dataclass
from core.order import Order
from core.agv import AGVAction
from core.gridmap import GridMap

def orders_to_tasks(orders: List[Order], map_obj:GridMap) -> List[Tuple]:
    """
    将订单列表转化为AGV任务列表，合并相邻相同箱子的取放操作
    :param orders: Order列表
    :param map_obj: 提供 get_box_position(box_id) 和 get_receiver_position(receiver_id) 方法的对象
    :return: 任务列表 [(position, action, id), ...]
    """
    if not orders:
        return []

    tasks = []
    current_box_id = None
    box_start_index = None  # 当前箱子序列开始的索引

    for i, order in enumerate(orders):
        if order.box_id is None:
            raise ValueError(f"Order {order.order_id} 的 box_id 还未赋值")

        # 如果是新箱子序列，先取货箱
        if order.box_id != current_box_id:
            current_box_id = order.box_id
            box_start_index = i
            box_position = map_obj.get_box_position(current_box_id)
            tasks.append((box_position, AGVAction.PICK, current_box_id))

        # 对每个订单都添加交付任务
        receiver_position = map_obj.get_receiver_position(order.receiver_id)
        tasks.append((receiver_position, AGVAction.HANDOVER, order.order_id))

        # 检查下一个订单，如果下一个订单的 box_id 不同，说明当前箱子序列结束，需要放回
        next_box_id = orders[i + 1].box_id if i + 1 < len(orders) else None
        if next_box_id != current_box_id:
            box_position = map_obj.get_box_position(current_box_id)
            tasks.append((box_position, AGVAction.PLACE, None))

    return tasks
