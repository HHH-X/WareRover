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
        data['type'] = 'update'
        agv_pos = agvmanager.get_all_real_positions()
        data['agv_pos'] = agv_pos
        carrying_status = agvmanager.get_carried_box_ids()

        boxes_on_agv = {}
        boxes_on_shelf = {}

        # 遍历所有 box
        for box_id in map.goods_id_set:
            # 判断是否被 AGV 搬运
            agv_carrying_box = next((agv_id for agv_id, b_id in carrying_status.items() if b_id == box_id), None)
            if agv_carrying_box is not None:
                boxes_on_agv[box_id] = agv_pos[agv_carrying_box]
            else:
                x, y = map.get_box_position(box_id)
                boxes_on_shelf[box_id] = (x + 0.5, y + 0.5)

        data['boxes_on_agv'] = boxes_on_agv
        data['boxes_on_shelf'] = boxes_on_shelf

    return data
