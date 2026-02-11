from typing import Dict, List, Tuple, Optional, Set
import numpy as np
from config.settings import SimConfig
import json
from utils.logger import global_logger

class GridMap:
    def __init__(self):
        
        with open(SimConfig.map_file, "r") as f:
            map_data = json.load(f)
            
        self.width = map_data["map"]["width"]
        self.height = map_data["map"]["height"]
        # static_grid: -2=obstacle, -1=free, >=0=box_id
        self.static_grid = np.full((self.height, self.width), -1, dtype=int)

        self.box_positions: Dict[int, Tuple[int, int]] = {}
        self.box_sizes: Dict[int, int] = {}
        self.box_to_goods: Dict[int, List[int]] = {}
        self.box_status: Dict[int, bool] = {}
        self.box_id_set: Set[int] = set()
        self.goods_to_boxes: Dict[int, List[int]] = {}
        self.goods_id_set: Set[int] = set()

        for box in map_data.get("boxes", []):
            box_id = box["box_id"]
            x, y = box["position"]
            goods_ids = box.get("goods_ids", [])
            size = box.get("size", 1)
            self.box_positions[box_id] = (x, y)
            self.box_sizes[box_id] = size
            self.box_to_goods[box_id] = goods_ids
            self.box_status[box_id] = True
            self.box_id_set.add(box_id)
            for gid in goods_ids:
                self.goods_to_boxes.setdefault(gid, []).append(box_id)
                self.goods_id_set.add(gid)
            for dx in range(size):
                for dy in range(size):
                    self.static_grid[y + dy][x + dx] = box_id

        self.obstacles: Set[Tuple[int, int]] = set()
        for x, y in map_data.get("obstacles", []):
            self.static_grid[y][x] = -2
            self.obstacles.add((x, y))
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

        self.wait_zones: Dict[int, Tuple[int, int]] = {}
        self.wait_zones_size: Dict[int, int] = {}
        for zone in map_data.get("wait_zones", []):
            zid = zone["wait_zone_id"]
            pos = tuple(zone["position"])
            size = zone.get("size", 1)
            self.wait_zones[zid] = pos
            self.wait_zones_size[zid] = size

        self.dynamic_occupied: Dict[str, list[Tuple[int, int]]] = {}

    def add_dynamic_occupancy(self, key: str, cells: List[Tuple[int, int]]):
        """Register a set of temporarily occupied cells (e.g. repair path)."""
        self.dynamic_occupied[key] = cells

    def remove_dynamic_occupancy(self, key: str):
        """Remove a set of temporary occupancies."""
        if key in self.dynamic_occupied:
            del self.dynamic_occupied[key]

    def is_occupied(self, x: int, y: int) -> bool:
        """True if cell is temporarily occupied (excludes static obstacles)."""
        for cells in self.dynamic_occupied.values():
            if (x, y) in cells:
                return True
        return False

    def is_walkable(self,
                    agv_size: int,
                    to_pos: Tuple[int, int],
                    from_pos: Tuple[int, int],
                    carrying_goods: bool) -> bool:
        """Whether AGV (top-left at from_pos) can move one step to to_pos; uses head-edge and target-cell rules."""
        x_from, y_from = from_pos
        x_to, y_to = to_pos
        dx, dy = x_to - x_from, y_to - y_from

        if abs(dx) + abs(dy) != 1:
            return False

        if not (0 <= x_to and x_to + agv_size - 1 < self.width and
                0 <= y_to and y_to + agv_size - 1 < self.height):
            return False

        if not (0 <= x_from and x_from + agv_size - 1 < self.width and
                0 <= y_from and y_from + agv_size - 1 < self.height):
            return False

        if dx == 1:
            head_positions = [(x_from + agv_size - 1, y_from + i) for i in range(agv_size)]
        elif dx == -1:
            head_positions = [(x_from, y_from + i) for i in range(agv_size)]
        elif dy == 1:
            head_positions = [(x_from + i, y_from + agv_size - 1) for i in range(agv_size)]
        else:
            head_positions = [(x_from + i, y_from) for i in range(agv_size)]

        next_positions = [(hx + dx, hy + dy) for (hx, hy) in head_positions]

        for (hx, hy) in head_positions + next_positions:
            if not (0 <= hx < self.width and 0 <= hy < self.height):
                return False

        head_vals = [self.static_grid[hy][hx] for (hx, hy) in head_positions]
        next_vals = [self.static_grid[ny][nx] for (nx, ny) in next_positions]

        if any(v == -2 for v in head_vals + next_vals):
            return False

        if self.dynamic_occupied:
            for (hx, hy) in head_positions + next_positions:
                if self.is_occupied(hx, hy):
                    return False

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

        if head_type == "mixed" or next_type == "mixed":
            return False

        if carrying_goods:
            if head_type == "empty" and next_type == "empty":
                return True
            if head_type == "empty" and next_type == "shelf":
                return not self.box_status.get(next_id, True)
            if head_type == "shelf" and next_type == "empty":
                return True
            if head_type == "shelf" and next_type == "shelf":
                return head_id == next_id
            return False

        else:
            if head_type == "empty" and next_type == "empty":
                return True
            if head_type == "empty" and next_type == "shelf":
                return True
            if head_type == "shelf" and next_type == "empty":
                return True
            if head_type == "shelf" and next_type == "shelf":
                return True
            return False

    def get_walkable_neighbors(
        self,
        agv_size: int,
        pos: Tuple[int, int],
        carrying_goods: bool) -> List[Tuple[int, int]]:
        """All adjacent top-left positions the AGV can move to from pos."""
        x, y = pos
        neighbors = []
        directions = [(-1, 0), (1, 0), (0, -1), (0, 1)]

        for dx, dy in directions:
            nx, ny = x + dx, y + dy
            if not (0 <= nx and nx + agv_size - 1 < self.width and
                    0 <= ny and ny + agv_size - 1 < self.height):
                continue
            if self.is_walkable(agv_size, (nx, ny), (x, y), carrying_goods):
                neighbors.append((nx, ny))

        return neighbors

    def pick_box_at(self, pos: Tuple[int, int]) -> Optional[int]:
        x, y = pos
        box_id = self.static_grid[y][x]
        expected_pos = self.box_positions.get(box_id)
        if expected_pos != pos:
            return None
        if self.box_status[box_id]:
            self.box_status[box_id] = False
            return box_id

        return None


    def place_box_at(self, pos: Tuple[int, int], box_id: int) -> bool:
        x, y = pos
        expected_pos = self.box_positions.get(box_id)
        if expected_pos != pos:
            return False
        if not self.box_status.get(box_id, True):
            self.box_status[box_id] = True
            return True

        return False
    
    def get_all_box_status(self) -> Dict[int, bool]:
        """Return whether each box is in place."""
        return dict(self.box_status)

    def get_box_position(self, box_id: int) -> Optional[Tuple[int, int]]:
        return self.box_positions.get(box_id)

    def get_goods_by_box(self, box_id: int) -> List[int]:
        return self.box_to_goods.get(box_id, [])

    def get_boxes_by_goods(self, goods_id: int) -> List[int]:
        return self.goods_to_boxes.get(goods_id, [])

    def get_all_goods_ids(self) -> Set[int]:
        return self.goods_id_set

    def get_receiver_position(self, receiver_id: int) -> Optional[Tuple[int, int]]:
        return self.receiver_zones.get(receiver_id)

    def get_all_receiver_zone_ids(self) -> Set[int]:
        return self.receiver_id_set

    def get_wait_zone_position(self, zone_id: int) -> Optional[Tuple[int, int]]:
        return self.wait_zones.get(zone_id)

    def reset_map(self):
        """Reset dynamic map state (box presence, temporary occupancies)."""
        for box_id in self.box_status:
            self.box_status[box_id] = True
        self.dynamic_occupied.clear()
        global_logger.add_runtime_log("[GridMap] Map has been reset.")

