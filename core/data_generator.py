import numpy as np
from typing import Dict, Any, Tuple
from core.gridmap import GridMap
from core.env import Env
from core.agvmanager import AGVManager
from core.order import OrderManager


def to_real_position(pos: Tuple[int, int]) -> Tuple[float, float]:
    """逻辑坐标 → 真实坐标"""
    x, y = pos
    return (x + 0.5, y + 0.5)


def generate_send_data(map: GridMap, agvmanager: AGVManager, data_type: str = "init") -> Dict[str, Any]:
    """
    生成发送给前端的数据，所有位置统一为真实坐标
    """
    data = {}
    
    if data_type == "init":
        data['type'] = 'init'
        # 1. 地图大小
        data['map_size'] = {
            "width": map.width,
            "height": map.height
        }

        # 2. AGV 初始位置（已经是真实坐标）
        data['agvs'] = agvmanager.get_all_real_positions()

        # 3. 统一转换为真实坐标
        data['boxes'] = {bid: to_real_position(pos) for bid, pos in map.box_positions.items()}
        data['receivers'] = {rid: to_real_position(pos) for rid, pos in map.receiver_zones.items()}
        data['wait_zones'] = {wid: to_real_position(pos) for wid, pos in map.wait_zones.items()}
        data['obstacles'] = [to_real_position(pos) for pos in map.obstacles]

    elif data_type == "update":
        data['type'] = 'update'
        agv_pos = agvmanager.get_all_real_positions()
        data['agv_pos'] = agv_pos
        carrying_status = agvmanager.get_carried_box_ids()

        boxes_on_agv = {}
        boxes_on_shelf = {}

        # 遍历所有 box
        for box_id in map.goods_id_set:
            agv_carrying_box = next((agv_id for agv_id, b_id in carrying_status.items() if b_id == box_id), None)
            if agv_carrying_box is not None:
                # 被AGV搬运 → 用AGV真实坐标
                boxes_on_agv[box_id] = agv_pos[agv_carrying_box]
            else:
                # 在货架上 → 转换为真实坐标
                x, y = map.get_box_position(box_id)
                boxes_on_shelf[box_id] = to_real_position((x, y))

        data['boxes_on_agv'] = boxes_on_agv
        data['boxes_on_shelf'] = boxes_on_shelf

    return data
