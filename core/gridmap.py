from __future__ import annotations

from enum import IntEnum
from typing import Callable, Dict, List, Tuple, Optional, Set, TYPE_CHECKING
import numpy as np

if TYPE_CHECKING:
    from utils.logger import GlobalLogger
    from utils.simulation_context import SimulationContext


class CellType(IntEnum):
    FREE = 0
    OBSTACLE = 1
    SHELF = 2
    ELEVATOR = 3


class GridMap:
    """Single-floor grid map. Created by WarehouseMap for each floor.

    Coordinate convention: all positions are (row, col) tuples.
    - row: vertical axis (0 = top, increases downward)
    - col: horizontal axis (0 = left, increases rightward)
    Grid arrays have shape (height, width) = (num_rows, num_cols).
    """

    def __init__(
        self,
        floor_id: int,
        width: int,
        height: int,
        floor_data: dict,
        ctx: SimulationContext,
    ):
        self.floor_id = floor_id
        self.width = width
        self.height = height
        self.ctx = ctx

        self.type_grid = np.full((self.height, self.width), CellType.FREE, dtype=np.int8)
        self.shelf_id_grid = np.full((self.height, self.width), -1, dtype=np.int32)
        self.elevator_id_grid = np.full((self.height, self.width), -1, dtype=np.int32)

        self.box_positions: Dict[int, Tuple[int, int]] = {}
        self.box_sizes: Dict[int, int] = {}
        self.box_to_goods: Dict[int, List[int]] = {}
        self.box_status: Dict[int, bool] = {}
        self.box_id_set: Set[int] = set()
        self.goods_to_boxes: Dict[int, List[int]] = {}
        self.goods_id_set: Set[int] = set()

        for box in floor_data.get("boxes", []):
            box_id = box["box_id"]
            row, col = box["position"]
            goods_ids = box.get("goods_ids", [])
            size = box.get("size", 1)
            self.box_positions[box_id] = (row, col)
            self.box_sizes[box_id] = size
            self.box_to_goods[box_id] = goods_ids
            self.box_status[box_id] = True
            self.box_id_set.add(box_id)
            for gid in goods_ids:
                self.goods_to_boxes.setdefault(gid, []).append(box_id)
                self.goods_id_set.add(gid)
            for dr in range(size):
                for dc in range(size):
                    self.type_grid[row + dr][col + dc] = CellType.SHELF
                    self.shelf_id_grid[row + dr][col + dc] = box_id

        self.obstacles: Set[Tuple[int, int]] = set()
        for obs in floor_data.get("obstacles", []):
            row, col = obs[0], obs[1] if isinstance(obs, (list, tuple)) else (obs["position"][0], obs["position"][1])
            self.type_grid[row][col] = CellType.OBSTACLE
            self.obstacles.add((row, col))

        self.receiver_zones: Dict[int, Tuple[int, int]] = {}
        self.receiver_id_set: Set[int] = set()
        self.receiver_zones_size: Dict[int, int] = {}
        for r in floor_data.get("receivers", []):
            rid = r["receiver_id"]
            pos = tuple(r["position"])
            size = r.get("size", 1)
            self.receiver_zones[rid] = pos
            self.receiver_id_set.add(rid)
            self.receiver_zones_size[rid] = size

        self.wait_zones: Dict[int, Tuple[int, int]] = {}
        self.wait_zones_size: Dict[int, int] = {}
        for zone in floor_data.get("wait_zones", []):
            zid = zone["wait_zone_id"]
            pos = tuple(zone["position"])
            size = zone.get("size", 1)
            self.wait_zones[zid] = pos
            self.wait_zones_size[zid] = size

        self.elevator_positions: Dict[int, Tuple[int, int]] = {}
        self.elevator_sizes: Dict[int, int] = {}
        for elev in floor_data.get("elevators", []):
            elevator_id = elev["elevator_id"]
            row, col = tuple(elev["position"])
            size = elev.get("size", 1)
            self.elevator_positions[elevator_id] = (row, col)
            self.elevator_sizes[elevator_id] = size
            for dr in range(size):
                for dc in range(size):
                    self.type_grid[row + dr][col + dc] = CellType.ELEVATOR
                    self.elevator_id_grid[row + dr][col + dc] = elevator_id

        self.dynamic_occupied: Dict[str, list[Tuple[int, int]]] = {}

    def add_dynamic_occupancy(self, key: str, cells: List[Tuple[int, int]]):
        self.dynamic_occupied[key] = cells

    def remove_dynamic_occupancy(self, key: str):
        if key in self.dynamic_occupied:
            del self.dynamic_occupied[key]

    def is_occupied(self, row: int, col: int) -> bool:
        for cells in self.dynamic_occupied.values():
            if (row, col) in cells:
                return True
        return False

    def is_walkable(self,
                    agv_id: int,
                    to_pos: Tuple[int, int],
                    from_pos: Tuple[int, int],
                    carrying_goods: bool) -> bool:
        agv_size =self.ctx.agv_manager.get_agv_size(agv_id)         
        r_from, c_from = from_pos
        r_to, c_to = to_pos
        dr, dc = r_to - r_from, c_to - c_from

        if abs(dr) + abs(dc) != 1:
            return False

        if not (0 <= r_to and r_to + agv_size - 1 < self.height and
                0 <= c_to and c_to + agv_size - 1 < self.width):
            return False

        if not (0 <= r_from and r_from + agv_size - 1 < self.height and
                0 <= c_from and c_from + agv_size - 1 < self.width):
            return False

        if dc == 1:
            head_positions = [(r_from + i, c_from + agv_size - 1) for i in range(agv_size)]
        elif dc == -1:
            head_positions = [(r_from + i, c_from) for i in range(agv_size)]
        elif dr == 1:
            head_positions = [(r_from + agv_size - 1, c_from + i) for i in range(agv_size)]
        else:
            head_positions = [(r_from, c_from + i) for i in range(agv_size)]

        next_positions = [(hr + dr, hc + dc) for (hr, hc) in head_positions]

        for (hr, hc) in head_positions + next_positions:
            if not (0 <= hr < self.height and 0 <= hc < self.width):
                return False

        head_types = [self.type_grid[hr, hc] for (hr, hc) in head_positions]
        head_shelf_ids = [self.shelf_id_grid[hr, hc] for (hr, hc) in head_positions]
        head_elevator_ids = [self.elevator_id_grid[hr, hc] for (hr, hc) in head_positions]
        next_types = [self.type_grid[nr, nc] for (nr, nc) in next_positions]
        next_shelf_ids = [self.shelf_id_grid[nr, nc] for (nr, nc) in next_positions]
        next_elevator_ids = [self.elevator_id_grid[nr, nc] for (nr, nc) in next_positions]

        if any(t == CellType.OBSTACLE for t in head_types + next_types):
            return False

        if self.dynamic_occupied:
            for (hr, hc) in head_positions + next_positions:
                if self.is_occupied(hr, hc):
                    return False

        def classify_group(types, shelf_ids, elevator_ids):
            if all(t == CellType.FREE for t in types):
                return ("empty", None)
            if all(t == CellType.SHELF for t in types):
                first = shelf_ids[0]
                if all(i == first for i in shelf_ids):
                    return ("shelf", first)
                return ("mixed", None)
            if all(t == CellType.ELEVATOR for t in types):
                first = elevator_ids[0]
                if first >= 0 and all(i == first for i in elevator_ids):
                    return ("elevator", first)
                return ("mixed", None)
            return ("mixed", None)

        head_type, head_id = classify_group(head_types, head_shelf_ids, head_elevator_ids)
        next_type, next_id = classify_group(next_types, next_shelf_ids, next_elevator_ids)

        if head_type == "mixed" or next_type == "mixed":
            return False

        if next_type == "elevator":
            return True
        
        if next_type == "empty":
            return True
        
        if carrying_goods:
            if (head_type == "empty" or head_type == "elevator") and next_type == "empty":
                return True
            if (head_type == "empty" or head_type == "elevator") and next_type == "shelf":
                return not self.box_status.get(next_id, True)
            if head_type == "shelf" and next_type == "empty":
                return True
            if head_type == "shelf" and next_type == "shelf":
                return head_id == next_id
            return False

        else:
            if (head_type == "empty" or head_type == "elevator") and next_type == "empty":
                return True
            if (head_type == "empty" or head_type == "elevator") and next_type == "shelf":
                return True
            if head_type == "shelf" and next_type == "empty":
                return True
            if head_type == "shelf" and next_type == "shelf":
                return True
            return False

    def get_walkable_neighbors(
        self,
        agv_id: int,
        pos: Tuple[int, int],
        carrying_goods: bool) -> List[Tuple[int, int]]:
        row, col = pos
        neighbors = []
        directions = [(-1, 0), (1, 0), (0, -1), (0, 1)]

        for dr, dc in directions:
            nr, nc = row + dr, col + dc
            # if not (0 <= nr and nr + agv_size - 1 < self.height and
            #         0 <= nc and nc + agv_size - 1 < self.width):
            #     continue
            if self.is_walkable(
                agv_id=agv_id,
                to_pos=(nr, nc),
                from_pos=(row, col),
                carrying_goods=carrying_goods,
            ):
                neighbors.append((nr, nc))

        return neighbors

    def pick_box_at(self, pos: Tuple[int, int]) -> Optional[int]:
        row, col = pos
        if self.type_grid[row, col] != CellType.SHELF:
            return None
        box_id = self.shelf_id_grid[row, col]
        expected_pos = self.box_positions.get(box_id)
        if expected_pos != pos:
            return None
        if self.box_status[box_id]:
            self.box_status[box_id] = False
            return box_id
        return None

    def place_box_at(self, pos: Tuple[int, int], box_id: int) -> bool:
        expected_pos = self.box_positions.get(box_id)
        if expected_pos != pos:
            return False
        if not self.box_status.get(box_id, True):
            self.box_status[box_id] = True
            return True
        return False

    def get_all_box_status(self) -> Dict[int, bool]:
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

    def get_elevator_position(self, elevator_id: int) -> Optional[Tuple[int, int]]:
        return self.elevator_positions.get(elevator_id)

    def get_elevator_cells(self, elevator_id: int) -> List[Tuple[int, int]]:
        pos = self.elevator_positions.get(elevator_id)
        if pos is None:
            return []
        row, col = pos
        size = self.elevator_sizes.get(elevator_id, 1)
        return [(row + dr, col + dc) for dr in range(size) for dc in range(size)]

    def reset_map(self):
        for box_id in self.box_status:
            self.box_status[box_id] = True
        self.dynamic_occupied.clear()
        self.ctx.logger.add_runtime_log(f"[GridMap F{self.floor_id}] Map has been reset.")
