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
        carrying_status = agvmanager.get_carried_box_ids()
        data['agv_pos'] = agvmanager.get_all_real_positions()
        # ---------------- 额外添加 box 归属关系 ----------------
        box_on_agv = {}
        for agv_id, box_id in carrying_status.items():
            if box_id is not None:   # 说明这个 agv 搬着一个 box
                box_on_agv[str(box_id)] = agv_id

        # 所有 box id
        all_box_ids = set(map.goods_id_set) 

        # 没有被 agv 搬运的 box，就认为它在 shelf 上
        box_on_shelf = {
            box_id: box_id   # 在你的逻辑里 shelf_id = box_id
            for box_id in all_box_ids - set(box_on_agv.keys())
        }
        data['box_on_agv'] = box_on_agv
        data['box_on_shelf'] = box_on_shelf
    else:
        raise ValueError(f"Unknown data_type: {data_type}")

    return data
