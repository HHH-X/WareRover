import numpy as np
from typing import Dict, Any
from core.gridmap import GridMap
from core.env import Env
from core.agvmanager import AGVManager
from core.order import OrderManager


def generate_send_data(map:GridMap, agvmanager:AGVManager, data_type: str = "init") -> Dict[str, Any]:
    """
    生成发送给前端的数据
    :param env: 当前环境对象，包含 map 和 agvmanager
    :param data_type: "init" 表示初始化数据，"update" 表示更新数据
    :return: 字典形式的数据
    """
    data = {}
    
    if data_type == "init":
        data['type'] = 'init'
        # 1. 地图信息
        # 转成列表方便JSON序列化
        data['map_size'] = {
                "width": map.width,
                "height": map.height
            }
        data['map_grid'] = map.map_grid.tolist()

        # 2. AGV 初始位置
        # 返回 {agv_id: (x, y)}
        data['agvs'] = agvmanager.get_all_real_positions()
        data['boxes'] = map.box_positions
        data['receivers'] = map.receiver_zones
        data['wait_zones'] = map.wait_zones
        data['obstacles'] = list(map.obstacles)

    elif data_type == "update":

        # 更新数据，可能只包含动态变化的信息
        # 例如 AGV 的位置、状态等
        data['type'] = 'update'
        real_positions = agvmanager.get_all_real_positions()
        carrying_status = agvmanager.get_carried_box_ids()

        data['agv_status'] = {
            agv_id: {
                "position": real_positions.get(agv_id),
                "carried_box_id": carrying_status.get(agv_id),
            }
            for agv_id in set(real_positions.keys()) | set(carrying_status.keys())
        }


    else:
        raise ValueError(f"Unknown data_type: {data_type}")

    return data
