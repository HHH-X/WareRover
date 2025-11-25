from dataclasses import dataclass
from typing import Optional
import json
@dataclass
class SimConfig:
    width: int
    height: int
    # num_orders: int = 20
    num_orders_size1 = 20
    num_orders_size2 = 0

    map_file: str = "config/default_map.json"  # 默认地图路径
    max_steps: int = 1000

    cell_size: int = 40
    panel_width: int = 300

    dhc_model_path = 'D:\\Project\\AGVSim\\algorithm\\DHC\\models\\337500.pth'

def init_sim_config(map_file: str = "config/default_map.json",) -> SimConfig:
    with open(map_file, "r") as f:
        data = json.load(f)
    map_data = data.get("map", {})  # 获取 map 字典

    cfg = SimConfig(
        width=map_data.get("width", 20),
        height=map_data.get("height", 20),
        map_file=map_file
    )

    return cfg