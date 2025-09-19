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
        data['agv_positions'] = agvmanager.get_all_real_positions()

        # 你可以在这里增加其他初始化信息，比如货架信息、箱子信息等
        # data['shelves'] = ...
        # data['boxes'] = ...

    elif data_type == "update":
        # 更新数据，可能只包含动态变化的信息
        # 例如 AGV 的位置、状态等
        data['agv_positions'] = env.agvmanager.get_all_real_positions()

        # 如果有其他动态信息也可以加进来
        # data['agv_status'] = ...
        # data['box_status'] = ...

    else:
        raise ValueError(f"Unknown data_type: {data_type}")

    return data
