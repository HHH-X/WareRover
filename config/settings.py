from dataclasses import dataclass
from typing import Optional
import json
@dataclass
class SimConfig:

    num_orders_size1 = 20
    num_orders_size2 = 0

    map_file: str = "config/default_map.json"  # 默认地图路径
    max_steps: int = 1000

    cell_size: int = 40
    panel_width: int = 300

    dhc_model_path = 'D:\\Project\\AGVSim\\algorithm\\DHC\\models\\10000.pth'

