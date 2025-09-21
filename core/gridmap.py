from typing import Dict, List, Tuple, Optional, Set
import numpy as np
from config.settings import SimConfig
import json

class GridMap:
    def __init__(self, map_data: Dict):
        # 地图尺寸
        self.width = map_data["map"]["width"]
        self.height = map_data["map"]["height"]
        # 地图网格初始化
        # -3: 障碍物（都不可通行）
        # -2: 空格（都可以通行）
        # -1: 空货架（是否可通行依赖来源方向和是否载货）
        # >=0: 有货箱（载货不可通行，不载货可通行）
        self.map_grid = np.full((self.height, self.width), -2, dtype=int)

        # ====== 初始化 box 数据结构 ======
        self.box_positions: Dict[int, Tuple[int, int]] = {}
        self.box_to_goods: Dict[int, List[int]] = {}
        self.goods_to_boxes: Dict[int, List[int]] = {}
        self.goods_id_set: Set[int] = set()

        for box in map_data.get("boxes", []):
            box_id = box["box_id"]
            x, y = box["position"]
            goods_ids = box.get("goods_ids", [])

            self.box_positions[box_id] = (x, y)
            self.box_to_goods[box_id] = goods_ids

            for goods_id in goods_ids:
                self.goods_to_boxes.setdefault(goods_id, []).append(box_id)
                self.goods_id_set.add(goods_id)

            self.map_grid[y][x] = box_id

        # ====== 添加障碍物 ======
        self.obstacles: Set[Tuple[int, int]] = set()
        for x, y in map_data.get("obstacles", []):
            self.map_grid[y][x] = -3
            self.obstacles.add((x, y))

        # ====== 初始化接收区 ======
        self.receiver_zones: Dict[int, Tuple[int, int]] = {}
        self.receiver_id_set: Set[int] = set()
        for r in map_data.get("receivers", []):
            rid = r["receiver_id"]
            pos = tuple(r["position"])
            self.receiver_zones[rid] = pos
            self.receiver_id_set.add(rid)

        # ====== 初始化等待区 ======
        self.wait_zones: Dict[int, Tuple[int, int]] = {
            zone["wait_zone_id"]: tuple(zone["position"])
            for zone in map_data.get("wait_zones", [])
        }
    # ========= 地图访问接口 =========
    def is_walkable(self, to_pos: Tuple[int, int], from_pos: Tuple[int, int], carrying_goods: bool) -> bool:
        x_to, y_to = to_pos
        if not (0 <= x_to < self.width and 0 <= y_to < self.height):
            return False

        cell = self.map_grid[y_to][x_to]

        if cell == -3:  # 障碍物
            return False
        if cell == -2:  # 空格
            return True
        if cell == -1:  # 空货架
            return not carrying_goods or self.map_grid[from_pos[1]][from_pos[0]] == -2
        if cell >= 0:   # 有货箱
            return not carrying_goods

        return False

    def get_walkable_neighbors(self, pos: Tuple[int, int], carrying_goods: bool) -> List[Tuple[int, int]]:
        x, y = pos
        directions = [(-1, 0), (1, 0), (0, -1), (0, 1)]
        neighbors = []

        for dx, dy in directions:
            nx, ny = x + dx, y + dy
            if self.is_walkable((nx, ny), (x, y), carrying_goods):
                neighbors.append((nx, ny))

        return neighbors

    # ========= 地图实时信息（map_grid）接口 =========
    def get_box_id_at(self, pos: Tuple[int, int]) -> Optional[int]:
        x, y = pos
        box_id = self.map_grid[y][x]
        return box_id if box_id >= 0 else None
    
    def get_all_box_status(self) -> Dict[int, bool]:
        """返回所有货箱的状态字典，True表示货箱在原位，False表示货箱被取走"""
        status = {}
        for box_id, (x, y) in self.box_positions.items():
            status[box_id] = (self.map_grid[y][x] >= 0)
        return status
    
    def pick_box_at(self, pos: Tuple[int, int]) -> Optional[int]:
        x, y = pos
        box_id = self.map_grid[y][x]
        if box_id >= 0:
            self.map_grid[y][x] = -1
            return box_id
        return None

    def place_box_at(self, pos: Tuple[int, int], box_id: int) -> bool:
        expected_pos = self.get_box_position(box_id)
        x, y = pos
        if self.map_grid[y][x] == -1 and expected_pos == pos:
            self.map_grid[y][x] = box_id
            return True
        return False
    
    # ========= 货箱接口 =========
    def get_box_position(self, box_id: int) -> Optional[Tuple[int, int]]:
        return self.box_positions.get(box_id)
        
    def get_goods_by_box(self, box_id: int) -> List[int]:
        return self.box_to_goods.get(box_id, [])

    # ========= 货物接口 =========
    def get_boxes_by_goods(self, goods_id: int) -> List[int]:
        return self.goods_to_boxes.get(goods_id, [])

    def get_all_goods_ids(self) -> Set[int]:
        return self.goods_id_set

    # ========= 接收区接口 =========
    def get_receiver_position(self, receiver_id: int) -> Optional[Tuple[int, int]]:
        return self.receiver_zones.get(receiver_id)

    def get_all_receiver_zone_ids(self) -> Set[int]:
        return self.receiver_id_set

    # ========= 等待区接口 =========
    def get_wait_zone_position(self, zone_id: int) -> Optional[Tuple[int, int]]:
        return self.wait_zones.get(zone_id)

def load_map_from_config(cfg: SimConfig) -> GridMap:
    with open(cfg.map_file, "r") as f:
        data = json.load(f)
    return GridMap(data)
