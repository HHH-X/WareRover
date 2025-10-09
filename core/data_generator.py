import numpy as np
from typing import Dict, Any, Tuple
from core.gridmap import GridMap
from core.env import Env
from core.agvmanager import AGVManager
from core.order import OrderManager


def to_real_position(pos: Tuple[int, int], size: int = 1) -> Tuple[float, float]:
    """逻辑坐标 → 实际坐标（中心点），考虑size偏移"""
    x, y = pos
    offset = (size - 1) / 2
    return (x + 0.5 + offset, y + 0.5 + offset)

def agv_to_real_center(real_pos: Tuple[float, float], size: int) -> Tuple[float, float]:
    """
    将AGV的逻辑左上角坐标转换为几何中心（真实坐标）
    - 对于 size=1：中心为 (x+0.5, y+0.5)
    - 对于 size>1：中心为 (x + size/2, y + size/2)
    """
    if size <= 1:
        return real_pos
    offset = (size - 1) / 2.0
    return (real_pos[0] + offset, real_pos[1] + offset)

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
                # 2. AGV 初始信息
        agvs_info = {}
        for agv in agvmanager.all_agvs():
            agv_id = agv.id
            grid_pos = agv.real_pos  # 左上角逻辑坐标
            size = agv.size
            center_pos = agv_to_real_center(grid_pos, size)
            agvs_info[agv_id] = {
                "pos": center_pos,
                "size": size
            }

        data['agvs'] = agvs_info

        # 3. 统一转换为真实坐标
        data['boxes'] = {
            bid: {
                "pos": to_real_position(pos, map.box_sizes.get(bid, 1)),
                "size": map.box_sizes.get(bid, 1)
            }
            for bid, pos in map.box_positions.items()
        }

        data['receivers'] = {
            rid: {
                "pos": to_real_position(pos, size),
                "size": size
            }
            for rid, (pos, size) in map.receiver_zones.items()
        }

        data['wait_zones'] = {
            wid: {
                "pos": to_real_position(pos, size),
                "size": size
            }
            for wid, (pos, size) in map.wait_zones.items()
        }
        
        data['obstacles'] = [to_real_position(pos) for pos in map.obstacles]

    elif data_type == "update":
        data['type'] = 'update'
        agv_pos = {aid: agv_to_real_center(pos) for aid, pos in agvmanager.get_all_real_positions().items()}
        data['agvs'] = agv_pos
        
        carrying_status = agvmanager.get_carried_box_ids()
        boxes_on_agv = {}
        boxes_on_shelf = {}

        # 遍历所有 box
        for agv_id, b_id in carrying_status.items():
            if b_id is not None:
                boxes_on_agv[b_id] = agv_pos[agv_id]
        
        boxes_on_shelf_id_set = map.box_id_set - set(boxes_on_agv.keys())
        for b_id in boxes_on_shelf_id_set:
            shelf_pos = map.box_positions[b_id]
            real_pos = to_real_position(shelf_pos, map.box_sizes.get(b_id, 1))
            boxes_on_shelf[b_id] = real_pos
          
        data['boxes_on_agv'] = boxes_on_agv
        data['boxes_on_shelf'] = boxes_on_shelf

    return data
