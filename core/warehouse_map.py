from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Dict, List, Tuple, Optional, Set, TYPE_CHECKING
from core.elevator import ElevatorDef
from core.gridmap import GridMap

if TYPE_CHECKING:
    from utils.simulation_context import SimulationContext


class WarehouseMap:
    """Top-level map container managing multiple floors and elevators.

    Coordinate convention: all positions are (row, col) tuples.
    JSON map files store positions as [row, col] arrays.
    """

    def __init__(self, ctx: SimulationContext):
        assert ctx.system_config is not None
        sim_config = ctx.system_config.sim_config
        self.ctx = ctx

        with open(sim_config.map_file, "r") as f:
            map_data = json.load(f)

        self.width: int = map_data["map"]["width"]
        self.height: int = map_data["map"]["height"]
        self.num_floors: int = map_data["map"].get("floors", 1)

        # Parse elevator definitions
        default_travel_time = sim_config.elevator_travel_time_per_floor
        self.elevator_defs: Dict[int, ElevatorDef] = {}
        for e in map_data.get("elevators", []):
            ed = ElevatorDef(
                elevator_id=e["elevator_id"],
                position=tuple(e["position"]),
                connected_floors=e.get("floors", list(range(self.num_floors))),
                travel_time=e.get("travel_time", default_travel_time),
                size=e.get("size", 1),
            )
            self.elevator_defs[ed.elevator_id] = ed

        # Build per-floor elevator list for GridMap
        floor_elevators: Dict[int, list] = {f: [] for f in range(self.num_floors)}
        for ed in self.elevator_defs.values():
            for fid in ed.connected_floors:
                floor_elevators[fid].append(
                    {
                        "elevator_id": ed.elevator_id,
                        "position": list(ed.position),
                        "size": ed.size,
                    }
                )

        # Create per-floor GridMap instances
        self.floors: Dict[int, GridMap] = {}
        if "floors" in map_data:
            for floor_entry in map_data["floors"]:
                fid = floor_entry["floor_id"]
                floor_entry["elevators"] = floor_elevators.get(fid, [])
                self.floors[fid] = GridMap(fid, self.width, self.height, floor_entry, self.ctx)
        else:
            # Backward compatible: single-floor map
            floor_data = {
                "boxes": map_data.get("boxes", []),
                "receivers": map_data.get("receivers", []),
                "wait_zones": map_data.get("wait_zones", []),
                "agvs": map_data.get("agvs", []),
                "obstacles": map_data.get("obstacles", []),
                "elevators": floor_elevators.get(0, []),
            }
            self.floors[0] = GridMap(0, self.width, self.height, floor_data, self.ctx)

        # Build cross-floor indexes
        self._box_floor: Dict[int, int] = {}
        self._receiver_floor: Dict[int, int] = {}
        self._goods_to_boxes_global: Dict[int, List[int]] = {}
        for fid, gm in self.floors.items():
            for box_id in gm.box_id_set:
                self._box_floor[box_id] = fid
            for rid in gm.receiver_id_set:
                self._receiver_floor[rid] = fid
            for gid, bids in gm.goods_to_boxes.items():
                self._goods_to_boxes_global.setdefault(gid, []).extend(bids)

        # Store raw agv data per floor for AGVManager
        self._agv_data_per_floor: Dict[int, list] = {}
        if "floors" in map_data:
            for floor_entry in map_data["floors"]:
                fid = floor_entry["floor_id"]
                self._agv_data_per_floor[fid] = floor_entry.get("agvs", [])
        else:
            self._agv_data_per_floor[0] = map_data.get("agvs", [])

    # ── Floor access ──

    def get_floor(self, floor_id: int) -> GridMap:
        return self.floors[floor_id]

    def all_floor_ids(self) -> List[int]:
        return sorted(self.floors.keys())

    # ── Cross-floor queries ──

    def get_box_floor(self, box_id: int) -> Optional[int]:
        return self._box_floor.get(box_id)

    def get_receiver_floor(self, receiver_id: int) -> Optional[int]:
        return self._receiver_floor.get(receiver_id)

    def get_box_position(self, box_id: int) -> Optional[Tuple[int, int]]:
        fid = self._box_floor.get(box_id)
        if fid is None:
            return None
        return self.floors[fid].get_box_position(box_id)

    def get_receiver_position(self, receiver_id: int) -> Optional[Tuple[int, int]]:
        fid = self._receiver_floor.get(receiver_id)
        if fid is None:
            return None
        return self.floors[fid].get_receiver_position(receiver_id)

    def get_goods_by_box(self, box_id: int) -> List[int]:
        fid = self._box_floor.get(box_id)
        if fid is None:
            return []
        return self.floors[fid].get_goods_by_box(box_id)

    def get_boxes_by_goods(self, goods_id: int) -> List[int]:
        return self._goods_to_boxes_global.get(goods_id, [])

    def get_all_goods_ids(self) -> Set[int]:
        result: Set[int] = set()
        for gm in self.floors.values():
            result |= gm.goods_id_set
        return result

    def get_all_receiver_zone_ids(self) -> Set[int]:
        result: Set[int] = set()
        for gm in self.floors.values():
            result |= gm.receiver_id_set
        return result

    def get_elevator_position(self, elevator_id: int) -> Optional[Tuple[int, int]]:
        ed = self.elevator_defs.get(elevator_id)
        return ed.position if ed else None

    def get_agv_data_for_floor(self, floor_id: int) -> list:
        return self._agv_data_per_floor.get(floor_id, [])

    # ── Reset ──

    def reset(self):
        for gm in self.floors.values():
            gm.reset_map()
