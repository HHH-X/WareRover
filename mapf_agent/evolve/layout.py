"""Utilities for OpenEvolve map layout optimization."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, MutableMapping, Optional, Union

import yaml

CodeSource = Union[str, Path]


def _read_mapping(source: CodeSource) -> Dict[str, Any]:
    path = Path(str(source))
    if path.exists():
        text = path.read_text(encoding="utf-8")
        suffix = path.suffix.lower()
    else:
        text = str(source)
        suffix = ""

    if not text.strip():
        raise ValueError("layout constraints are empty")

    if suffix in {".yaml", ".yml"}:
        data = yaml.safe_load(text)
    else:
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            data = yaml.safe_load(text)

    if not isinstance(data, dict):
        raise ValueError("layout constraints must be a JSON/YAML object")
    return data


def _as_int(value: Any, name: str, minimum: int = 0) -> int:
    try:
        result = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be an integer") from exc
    if result < minimum:
        raise ValueError(f"{name} must be >= {minimum}")
    return result


def _normalize_groups(raw: Any, name: str, default_size: int = 1) -> List[Dict[str, int]]:
    if raw is None:
        return []
    if isinstance(raw, int):
        raw = [{"count": raw, "size": default_size}]
    elif isinstance(raw, dict):
        if "items" in raw:
            raw = raw["items"]
        else:
            raw = [raw]
    if not isinstance(raw, list):
        raise ValueError(f"{name} must be a list, object, or integer count")

    groups: List[Dict[str, int]] = []
    for idx, item in enumerate(raw):
        if isinstance(item, int):
            item = {"count": item, "size": default_size}
        if not isinstance(item, dict):
            raise ValueError(f"{name}[{idx}] must be an object")
        count = _as_int(item.get("count", 0), f"{name}[{idx}].count")
        size = _as_int(item.get("size", default_size), f"{name}[{idx}].size", minimum=1)
        if count:
            groups.append({"count": count, "size": size})
    return groups


def _normalize_elevators(raw: Any) -> List[Dict[str, Any]]:
    if raw is None:
        return []
    if isinstance(raw, int):
        raw = [{"count": raw}]
    elif isinstance(raw, dict):
        raw = [raw]
    if not isinstance(raw, list):
        raise ValueError("elevators must be a list, object, or integer count")

    groups: List[Dict[str, Any]] = []
    for idx, item in enumerate(raw):
        if isinstance(item, int):
            item = {"count": item}
        if not isinstance(item, dict):
            raise ValueError(f"elevators[{idx}] must be an object")

        positions = item.get("fixed_positions") or []
        if item.get("position") is not None:
            positions = [item["position"]]
        norm_positions = []
        for pos in positions:
            if isinstance(pos, dict):
                pos = pos.get("position")
            if not isinstance(pos, (list, tuple)) or len(pos) != 2:
                raise ValueError(f"elevators[{idx}].fixed_positions entries must be [row, col]")
            norm_positions.append([_as_int(pos[0], "elevator row"), _as_int(pos[1], "elevator col")])

        count = item.get("count", len(norm_positions) or 0)
        groups.append(
            {
                "count": _as_int(count, f"elevators[{idx}].count"),
                "size": _as_int(item.get("size", 1), f"elevators[{idx}].size", minimum=1),
                "fixed": bool(item.get("fixed", bool(norm_positions))),
                "fixed_positions": norm_positions,
                "floors": list(item.get("floors", [])),
                "travel_time": item.get("travel_time"),
            }
        )
    return [g for g in groups if g["count"]]


def _total(groups: Iterable[Dict[str, Any]]) -> int:
    return sum(int(g.get("count", 0)) for g in groups)


def load_layout_constraints(source: CodeSource) -> Dict[str, Any]:
    """Load and normalize layout constraints from YAML/JSON text or path."""
    raw = _read_mapping(source)
    map_cfg = raw.get("map") or {}
    if not isinstance(map_cfg, dict):
        raise ValueError("layout constraints require a map object")

    width = _as_int(map_cfg.get("width"), "map.width", minimum=3)
    height = _as_int(map_cfg.get("height"), "map.height", minimum=3)
    floors = _as_int(map_cfg.get("floors", 1), "map.floors", minimum=1)

    agvs = _normalize_groups(raw.get("agvs"), "agvs")
    boxes = _normalize_groups(raw.get("boxes"), "boxes")
    receivers = _normalize_groups(raw.get("receivers"), "receivers")
    elevators = _normalize_elevators(raw.get("elevators"))

    wait_raw = raw.get("wait_zones")
    wait_per_agv = True
    wait_groups: List[Dict[str, int]] = []
    if isinstance(wait_raw, dict):
        wait_per_agv = bool(wait_raw.get("per_agv", True))
        wait_groups = _normalize_groups(wait_raw.get("items"), "wait_zones")
    elif wait_raw is not None:
        wait_per_agv = False
        wait_groups = _normalize_groups(wait_raw, "wait_zones")

    if wait_per_agv:
        wait_groups = [dict(group) for group in agvs]

    if _total(agvs) <= 0:
        raise ValueError("layout constraints require at least one AGV")
    if _total(boxes) <= 0:
        raise ValueError("layout constraints require at least one box")
    if _total(receivers) <= 0:
        raise ValueError("layout constraints require at least one receiver")
    if _total(wait_groups) < _total(agvs):
        raise ValueError("wait zone count must be at least AGV count")

    return {
        "map": {"width": width, "height": height, "floors": floors},
        "agvs": agvs,
        "boxes": boxes,
        "receivers": receivers,
        "wait_zones": {"per_agv": wait_per_agv, "items": wait_groups},
        "elevators": elevators,
        "obstacles": raw.get("obstacles", []),
        "simulation": dict(raw.get("simulation") or {}),
    }


def layout_system_config_patch(constraints: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """Return a SystemConfig patch derived from normalized layout constraints."""
    sim = dict(constraints.get("simulation") or {})
    patch: Dict[str, Dict[str, Any]] = {"sim_config": {}}
    for key in (
        "planner_type",
        "scheduler_type",
        "max_steps",
        "total_orders_limit",
        "order_mode",
        "size2_ratio",
        "cross_floor_order_ratio",
        "elevator_travel_time_per_floor",
    ):
        if key in sim:
            patch["sim_config"][key] = sim[key]
    return patch


def build_layout_initial_program(custom_code: str = "") -> str:
    """Build an evolvable Python map generator program."""
    if custom_code.strip():
        code = custom_code.strip()
        if "# EVOLVE-BLOCK-START" in code and "# EVOLVE-BLOCK-END" in code:
            compile(code, "initial_program.py", "exec")
            return code + "\n"
        program = f"# EVOLVE-BLOCK-START\n{code}\n# EVOLVE-BLOCK-END\n"
        compile(program, "initial_program.py", "exec")
        return program

    program = r'''
from __future__ import annotations

from typing import Any, Dict, Iterable, List, Tuple


Coord = Tuple[int, int]


def _expand(groups: Iterable[Dict[str, int]]) -> List[int]:
    result: List[int] = []
    for group in groups:
        result.extend([int(group.get("size", 1))] * int(group.get("count", 0)))
    return result


def _split_even(items: List[int], parts: int) -> List[List[int]]:
    buckets = [[] for _ in range(parts)]
    for idx, item in enumerate(items):
        buckets[idx % parts].append(item)
    return buckets


def _cells(pos: Coord, size: int) -> List[Coord]:
    row, col = pos
    return [(row + dr, col + dc) for dr in range(size) for dc in range(size)]


def _fits(pos: Coord, size: int, width: int, height: int, occupied: set[Coord]) -> bool:
    cells = _cells(pos, size)
    return all(0 <= r < height and 0 <= c < width and (r, c) not in occupied for r, c in cells)


def _reserve(pos: Coord, size: int, occupied: set[Coord]) -> None:
    occupied.update(_cells(pos, size))


def _scan_positions(width: int, height: int, band: str) -> List[Coord]:
    rows = list(range(height))
    cols = list(range(width))
    if band == "top":
        rows = rows[: max(1, height // 3)]
    elif band == "bottom":
        rows = rows[max(0, 2 * height // 3):]
    elif band == "middle":
        rows = rows[max(0, height // 3): max(height // 3 + 1, 2 * height // 3)]
    elif band == "edges":
        return [(r, c) for r in rows for c in (0, width - 1)]
    return [(r, c) for r in rows for c in cols]


def _place_one(size: int, width: int, height: int, occupied: set[Coord], band: str) -> Coord:
    for pos in _scan_positions(width, height, band):
        if _fits(pos, size, width, height, occupied):
            _reserve(pos, size, occupied)
            return pos
    for pos in _scan_positions(width, height, "all"):
        if _fits(pos, size, width, height, occupied):
            _reserve(pos, size, occupied)
            return pos
    raise ValueError(f"no free position for size {size}")


def generate_map(constraints: Dict[str, Any]) -> Dict[str, Any]:
    """Return a WareRover map dict satisfying normalized layout constraints."""
    width = int(constraints["map"]["width"])
    height = int(constraints["map"]["height"])
    num_floors = int(constraints["map"].get("floors", 1))
    agv_sizes = _expand(constraints.get("agvs", []))
    box_sizes = _expand(constraints.get("boxes", []))
    receiver_sizes = _expand(constraints.get("receivers", []))

    agvs_by_floor = _split_even(agv_sizes, num_floors)
    boxes_by_floor = _split_even(box_sizes, num_floors)
    receivers_by_floor = _split_even(receiver_sizes, num_floors)
    floors = []

    elevator_defs = []
    eid = 0
    # EVOLVE-BLOCK-START
    for group in constraints.get("elevators", []):
        count = int(group.get("count", 0))
        size = int(group.get("size", 1))
        fixed_positions = list(group.get("fixed_positions") or [])
        for idx in range(count):
            if idx < len(fixed_positions):
                pos = fixed_positions[idx]
            else:
                pos = [height // 2, min(width - size, max(0, width // 2 + idx * (size + 1)))]
            elevator_defs.append(
                {
                    "elevator_id": eid,
                    "position": [int(pos[0]), int(pos[1])],
                    "floors": group.get("floors") or list(range(num_floors)),
                    "size": size,
                }
            )
            if group.get("travel_time") is not None:
                elevator_defs[-1]["travel_time"] = int(group["travel_time"])
            eid += 1

    next_agv_id = 0
    next_box_id = 0
    next_receiver_id = 0
    for floor_id in range(num_floors):
        occupied: set[Coord] = set()
        for elev in elevator_defs:
            if floor_id in elev["floors"]:
                _reserve(tuple(elev["position"]), int(elev.get("size", 1)), occupied)

        agvs = []
        wait_zones = []
        for size in agvs_by_floor[floor_id]:
            pos = _place_one(size, width, height, occupied, "top")
            agvs.append({"agv_id": next_agv_id, "size": size})
            wait_zones.append({"wait_zone_id": next_agv_id, "position": list(pos), "size": size})
            next_agv_id += 1

        receivers = []
        for size in receivers_by_floor[floor_id]:
            pos = _place_one(size, width, height, occupied, "edges")
            receivers.append({"receiver_id": next_receiver_id, "position": list(pos), "size": size})
            next_receiver_id += 1

        boxes = []
        for size in boxes_by_floor[floor_id]:
            pos = _place_one(size, width, height, occupied, "middle")
            boxes.append({"box_id": next_box_id, "position": list(pos), "goods_ids": [next_box_id], "size": size})
            next_box_id += 1

        floors.append(
            {
                "floor_id": floor_id,
                "boxes": boxes,
                "receivers": receivers,
                "wait_zones": wait_zones,
                "agvs": agvs,
                "obstacles": [],
            }
        )
    # EVOLVE-BLOCK-END

    return {
        "map": {"width": width, "height": height, "floors": num_floors},
        "floors": floors,
        "elevators": elevator_defs,
    }
'''
    program = program.strip() + "\n"
    compile(program, "initial_program.py", "exec")
    return program
