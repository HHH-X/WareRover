from typing import Dict, List, Tuple, Optional, Set
import numpy as np
from config.settings import SimConfig
import json


class GridMap:
    def __init__(self, map_data: Dict):
        # ====== 地图基本属性 ======
        self.width = map_data["map"]["width"]
        self.height = map_data["map"]["height"]

        # ====== 初始化静态地图 ======
        # -2: 障碍物（不可通行）
        # -1: 空地（可通行）
        # >=0: 货架 ID（按照box的size填满占用网格）
        self.static_grid = np.full((self.height, self.width), -1, dtype=int)

        # ====== 初始化货箱相关数据结构 ======
        self.box_positions: Dict[int, Tuple[int, int]] = {}  # 货箱左上角位置
        self.box_sizes: Dict[int, int] = {}                  # 每个货箱的尺寸
        self.box_to_goods: Dict[int, List[int]] = {}         # 货箱内的货物
        self.box_status: Dict[int, bool] = {}                # 动态状态：True 表示在位，False 表示被取走
        self.box_id_set: Set[int] = set()                    # 所有货箱 ID
        self.goods_to_boxes: Dict[int, List[int]] = {}       # 每种货物在哪些货箱中
        self.goods_id_set: Set[int] = set()                  # 所有货物 ID

        # ====== 放置货架与货箱 ======
        for box in map_data.get("boxes", []):
            box_id = box["box_id"]
            x, y = box["position"]
            goods_ids = box.get("goods_ids", [])
            size = box.get("size", 1)

            # 记录货箱信息
            self.box_positions[box_id] = (x, y)
            self.box_sizes[box_id] = size
            self.box_to_goods[box_id] = goods_ids
            self.box_status[box_id] = True  # 初始时所有货箱都在位
            self.box_id_set.add(box_id)

            # 建立反向索引
            for gid in goods_ids:
                self.goods_to_boxes.setdefault(gid, []).append(box_id)
                self.goods_id_set.add(gid)

            # 静态层：用货架ID填满区域
            for dx in range(size):
                for dy in range(size):
                    self.static_grid[y + dy][x + dx] = box_id

        # ====== 添加障碍物 ======
        self.obstacles: Set[Tuple[int, int]] = set()
        for x, y in map_data.get("obstacles", []):
            self.static_grid[y][x] = -2
            self.obstacles.add((x, y))

        # ====== 初始化接收区 ======
        self.receiver_zones: Dict[int, Tuple[int, int]] = {}
        self.receiver_id_set: Set[int] = set()
        self.receiver_zones_size: Dict[int, int] = {}
        for r in map_data.get("receivers", []):
            rid = r["receiver_id"]
            pos = tuple(r["position"])
            size = r.get("size", 1)
            self.receiver_zones[rid] = pos
            self.receiver_id_set.add(rid)
            self.receiver_zones_size[rid] = size

        # ====== 初始化等待区 ======
        self.wait_zones: Dict[int, Tuple[int, int]] = {}
        self.wait_zones_size: Dict[int, int] = {}
        for zone in map_data.get("wait_zones", []):
            zid = zone["wait_zone_id"]
            pos = tuple(zone["position"])
            size = zone.get("size", 1)
            self.wait_zones[zid] = pos
            self.wait_zones_size[zid] = size

        # ====== 动态占用格子(安全路径) ======
        self.dynamic_occupied: Dict[str, Set[Tuple[int, int]]] = {}

    # ========= 动态占用格子管理 =========
    def add_dynamic_occupancy(self, key: str, cells: List[Tuple[int, int]]):
        """注册一组临时占用格子（例如维修通道、掉落物、人工路径等）"""
        self.dynamic_occupied[key] = set(cells)

    def remove_dynamic_occupancy(self, key: str):
        """移除一组临时占用格子"""
        if key in self.dynamic_occupied:
            del self.dynamic_occupied[key]

    def is_occupied(self, x: int, y: int) -> bool:
        """判断格子是否被临时占用（不包含静态障碍物）"""
        for cells in self.dynamic_occupied.values():
            if (x, y) in cells:
                return True
        return False

    # ========= 地图通行性判断 =========
    def is_walkable(self,
                    agv_size: int,
                    to_pos: Tuple[int, int],
                    from_pos: Tuple[int, int],
                    carrying_goods: bool) -> bool:
        """
        判断 AGV 是否可以从 from_pos (左上角) 移动到 to_pos (左上角)。
        规则基于“头部”（移动前 AGV 前缘的一排格子）和头部的目标格集合进行判断，
        严格按用户提供的逻辑实现。

        参数：
            to_pos: 目标左上角 (x,y)
            from_pos: 当前左上角 (x,y)
            carrying_goods: 是否载货
            agv_size: AGV 的边长（正方形占格数）
        返回：
            bool: 是否可通行
        """

        x_from, y_from = from_pos
        x_to, y_to = to_pos
        dx, dy = x_to - x_from, y_to - y_from

        # 只允许上下左右单步移动
        if abs(dx) + abs(dy) != 1:
            return False

        # 整体目标身体（to_pos -> to_pos + size-1）必须在地图内
        if not (0 <= x_to and x_to + agv_size - 1 < self.width and
                0 <= y_to and y_to + agv_size - 1 < self.height):
            return False

        # 当前身体也应该在地图内（防御性检查）
        if not (0 <= x_from and x_from + agv_size - 1 < self.width and
                0 <= y_from and y_from + agv_size - 1 < self.height):
            return False

        # 计算“头部”位置（移动前，位于 AGV 前缘的一排格子）
        if dx == 1:  # 向右，头部是当前最右列
            head_positions = [(x_from + agv_size - 1, y_from + i) for i in range(agv_size)]
        elif dx == -1:  # 向左，头部是当前最左列
            head_positions = [(x_from, y_from + i) for i in range(agv_size)]
        elif dy == 1:  # 向下，头部是当前最下行
            head_positions = [(x_from + i, y_from + agv_size - 1) for i in range(agv_size)]
        else:  # dy == -1 向上，头部是当前最上行
            head_positions = [(x_from + i, y_from) for i in range(agv_size)]

        # 头部的目标（每个 head cell 向前推进一格）
        next_positions = [(hx + dx, hy + dy) for (hx, hy) in head_positions]

        # 边界检查（头部 & 目标）
        for (hx, hy) in head_positions + next_positions:
            if not (0 <= hx < self.width and 0 <= hy < self.height):
                return False

        # 读取静态格值（注意 indexing: static_grid[y][x]）
        head_vals = [self.static_grid[hy][hx] for (hx, hy) in head_positions]
        next_vals = [self.static_grid[ny][nx] for (nx, ny) in next_positions]

        # 障碍物直接不可通行
        if any(v == -2 for v in head_vals + next_vals):
            return False
        
        # 动态占用格子检查
        if self.dynamic_occupied:
            for (hx, hy) in head_positions + next_positions:
                if self.is_occupied(hx, hy):
                    return False

        # 分类辅助：返回 ('empty', None) 或 ('shelf', shelf_id) 或 ('mixed', None)
        def classify_group(vals):
            if all(v == -1 for v in vals):
                return ("empty", None)
            if all(v >= 0 for v in vals):
                first = vals[0]
                if all(v == first for v in vals):
                    return ("shelf", first)
                else:
                    return ("mixed", None)
            return ("mixed", None)

        head_type, head_id = classify_group(head_vals)
        next_type, next_id = classify_group(next_vals)

        # 要求头部和目标集合一致（不是 mixed）
        if head_type == "mixed" or next_type == "mixed":
            return False

        # -------- 按载货 / 不载货 的规则判断 --------
        if carrying_goods:
            # 1) head empty -> next empty: 可通行
            if head_type == "empty" and next_type == "empty":
                return True

            # 2) head empty -> next shelf: 只有当目标货架为空（没有 box）时才可通行
            if head_type == "empty" and next_type == "shelf":
                # box_status: True 表示货箱在位，False 表示被取走（即空架）
                return not self.box_status.get(next_id, True)

            # 3) head shelf -> next empty: 直接通行
            if head_type == "shelf" and next_type == "empty":
                return True

            # 4) head shelf -> next shelf: 只有当二者属于同一货架 ID 时才可通行
            if head_type == "shelf" and next_type == "shelf":
                return head_id == next_id

            # 其它情况一律不可通行
            return False

        else:  # not carrying_goods
            if head_type == "empty" and next_type == "empty":
                return True

            if head_type == "empty" and next_type == "shelf":
                return True

            if head_type == "shelf" and next_type == "empty":
                return True

            if head_type == "shelf" and next_type == "shelf":
                # 不载货的agv可以在不同货架间移动
                return True 

            return False

    def get_walkable_neighbors(
        self,
        agv_size: int,
        pos: Tuple[int, int],
        carrying_goods: bool) -> List[Tuple[int, int]]:
        """
        获取从当前位置 (pos, 左上角坐标) 出发，AGV 可以移动到的所有相邻格子（左上角位置）。

        参数：
            pos: 当前 AGV 左上角坐标 (x, y)
            carrying_goods: 是否载货
            agv_size: AGV 边长（格子数）

        返回：
            List[Tuple[int, int]]: 所有可通行的邻居位置（左上角坐标）
        """
        x, y = pos
        neighbors = []

        # 四个方向：左、右、上、下
        directions = [(-1, 0), (1, 0), (0, -1), (0, 1)]

        for dx, dy in directions:
            nx, ny = x + dx, y + dy

            # 检查AGV整体是否越界（左上角+size-1必须在地图范围内）
            if not (0 <= nx and nx + agv_size - 1 < self.width and
                    0 <= ny and ny + agv_size - 1 < self.height):
                continue

            # 判断是否可通行
            if self.is_walkable(agv_size, (nx, ny), (x, y), carrying_goods):
                neighbors.append((nx, ny))

        return neighbors

    # ========= 货箱操作 =========
    # def get_box_at_position(self, pos: Tuple[int, int]) -> Optional[int]:
    #     """获取该位置对应的货架ID（若为货架区域）"""
    #     x, y = pos
    #     cell = self.static_grid[y][x]
    #     return cell if cell >= 0 else None

    # def is_box_present(self, box_id: int) -> bool:
    #     """检查货箱是否在位"""
    #     return self.box_status.get(box_id, False)

    def pick_box_at(self, pos: Tuple[int, int]) -> Optional[int]:
        x, y = pos
        # 获取该位置的 box_id
        box_id = self.static_grid[y][x]
        # 检查位置和 box_id 是否匹配
        expected_pos = self.box_positions.get(box_id)
        if expected_pos != pos:
            return None

        # 如果当前货箱在原位，则取走
        if self.box_status[box_id]:
            self.box_status[box_id] = False
            return box_id

        return None


    def place_box_at(self, pos: Tuple[int, int], box_id: int) -> bool:

        x, y = pos
        expected_pos = self.box_positions.get(box_id)
        if expected_pos != pos:
            return False
        # 如果该货箱当前不在原位，则放回
        if not self.box_status.get(box_id, True):
            self.box_status[box_id] = True
            return True

        return False
    
    def get_all_box_status(self) -> Dict[int, bool]:
        """返回所有货箱是否在位"""
        return dict(self.box_status)

    # ========= 数据访问接口 =========
    def get_box_position(self, box_id: int) -> Optional[Tuple[int, int]]:
        return self.box_positions.get(box_id)

    def get_goods_by_box(self, box_id: int) -> List[int]:
        return self.box_to_goods.get(box_id, [])

    def get_boxes_by_goods(self, goods_id: int) -> List[int]:
        return self.goods_to_boxes.get(goods_id, [])

    def get_all_goods_ids(self) -> Set[int]:
        return self.goods_id_set

    # ========= 区域访问接口 =========
    def get_receiver_position(self, receiver_id: int) -> Optional[Tuple[int, int]]:
        return self.receiver_zones.get(receiver_id)

    def get_all_receiver_zone_ids(self) -> Set[int]:
        return self.receiver_id_set

    def get_wait_zone_position(self, zone_id: int) -> Optional[Tuple[int, int]]:
        return self.wait_zones.get(zone_id)


def load_map_from_config(cfg: SimConfig) -> GridMap:
    with open(cfg.map_file, "r") as f:
        data = json.load(f)
    return GridMap(data)
