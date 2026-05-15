"""Validation helpers for generated WareRover map layouts."""
from __future__ import annotations

import json
from collections import Counter, deque
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

import jsonschema

Coord = Tuple[int, int]

_SCHEMA_PATH = Path(__file__).resolve().parent.parent / "schema" / "map_schema.json"


def _schema() -> Dict[str, Any]:
    return json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))


def _groups_counter(groups: Iterable[Dict[str, Any]]) -> Counter:
    counter: Counter = Counter()
    for group in groups:
        counter[int(group.get("size", 1))] += int(group.get("count", 0))
    return counter


def _cells(pos: Coord, size: int) -> List[Coord]:
    row, col = pos
    return [(row + dr, col + dc) for dr in range(size) for dc in range(size)]


def _in_bounds(pos: Coord, size: int, width: int, height: int) -> bool:
    row, col = pos
    return row >= 0 and col >= 0 and row + size <= height and col + size <= width


def _pos(value: Any) -> Coord:
    return int(value[0]), int(value[1])


def _obstacle_pos(value: Any) -> Coord:
    if isinstance(value, dict):
        return _pos(value["position"])
    return _pos(value)


def _floors(map_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    if "floors" in map_data:
        return list(map_data["floors"])
    return [
        {
            "floor_id": 0,
            "boxes": map_data.get("boxes", []),
            "receivers": map_data.get("receivers", []),
            "wait_zones": map_data.get("wait_zones", []),
            "agvs": map_data.get("agvs", []),
            "obstacles": map_data.get("obstacles", []),
        }
    ]


def _entity_counter(floors: Iterable[Dict[str, Any]], key: str) -> Counter:
    counter: Counter = Counter()
    for floor in floors:
        for item in floor.get(key, []):
            counter[int(item.get("size", 1))] += 1
    return counter


def _elevator_counter(elevators: Iterable[Dict[str, Any]]) -> Counter:
    counter: Counter = Counter()
    for elev in elevators:
        counter[int(elev.get("size", 1))] += 1
    return counter


def _all_ids(floors: Iterable[Dict[str, Any]], key: str, id_key: str) -> List[int]:
    ids: List[int] = []
    for floor in floors:
        ids.extend(int(item[id_key]) for item in floor.get(key, []))
    return ids


def _summary(map_data: Dict[str, Any]) -> Dict[str, Any]:
    floors = _floors(map_data)
    return {
        "map": dict(map_data.get("map") or {}),
        "floors": [
            {
                "floor_id": floor.get("floor_id"),
                "boxes": len(floor.get("boxes", [])),
                "receivers": len(floor.get("receivers", [])),
                "wait_zones": len(floor.get("wait_zones", [])),
                "agvs": len(floor.get("agvs", [])),
                "obstacles": len(floor.get("obstacles", [])),
            }
            for floor in floors
        ],
        "elevators": [
            {
                "elevator_id": e.get("elevator_id"),
                "position": e.get("position"),
                "floors": e.get("floors"),
                "size": e.get("size", 1),
            }
            for e in map_data.get("elevators", [])
        ],
    }


def _check_unique(ids: List[int], label: str, errors: List[str]) -> None:
    duplicates = sorted(i for i, count in Counter(ids).items() if count > 1)
    if duplicates:
        errors.append(f"{label} IDs must be unique; duplicates={duplicates}")


def _add_footprint(
    occupied: Dict[Tuple[int, int], str],
    pos: Coord,
    size: int,
    label: str,
    width: int,
    height: int,
    errors: List[str],
) -> None:
    if not _in_bounds(pos, size, width, height):
        errors.append(f"{label} footprint is out of bounds at {list(pos)} size={size}")
        return
    for cell in _cells(pos, size):
        if cell in occupied:
            errors.append(f"{label} overlaps {occupied[cell]} at {list(cell)}")
        occupied[cell] = label


def _blocked_cells_for_floor(floor: Dict[str, Any]) -> Set[Coord]:
    return {_obstacle_pos(obs) for obs in floor.get("obstacles", [])}


def _reachable(start: Coord, target: Coord, size: int, width: int, height: int, blocked: Set[Coord]) -> bool:
    if not _in_bounds(start, size, width, height) or not _in_bounds(target, size, width, height):
        return False
    q = deque([start])
    seen = {start}
    while q:
        row, col = q.popleft()
        if (row, col) == target:
            return True
        for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nxt = (row + dr, col + dc)
            if nxt in seen or not _in_bounds(nxt, size, width, height):
                continue
            if any(cell in blocked for cell in _cells(nxt, size)):
                continue
            seen.add(nxt)
            q.append(nxt)
    return False


def validate_layout_map(map_data: Dict[str, Any], constraints: Dict[str, Any]) -> Dict[str, Any]:
    """Validate generated map data against schema and layout constraints."""
    errors: List[str] = []
    warnings: List[str] = []

    try:
        jsonschema.validate(instance=map_data, schema=_schema())
    except jsonschema.ValidationError as exc:
        errors.append(f"schema: {exc.message}")
        return {"valid": False, "errors": errors, "warnings": warnings, "summary": _summary(map_data)}

    width = int(map_data["map"]["width"])
    height = int(map_data["map"]["height"])
    floor_count = int(map_data["map"].get("floors", 1))
    expected_map = constraints.get("map") or {}
    if width != int(expected_map.get("width", width)):
        errors.append(f"map.width expected {expected_map.get('width')} got {width}")
    if height != int(expected_map.get("height", height)):
        errors.append(f"map.height expected {expected_map.get('height')} got {height}")
    if floor_count != int(expected_map.get("floors", floor_count)):
        errors.append(f"map.floors expected {expected_map.get('floors')} got {floor_count}")

    floors = _floors(map_data)
    if len(floors) != floor_count:
        errors.append(f"floors array length expected {floor_count} got {len(floors)}")
    floor_ids = [int(f.get("floor_id", -1)) for f in floors]
    if sorted(floor_ids) != list(range(floor_count)):
        errors.append(f"floor_id values must be 0..{floor_count - 1}; got {floor_ids}")

    expected_agvs = _groups_counter(constraints.get("agvs", []))
    expected_boxes = _groups_counter(constraints.get("boxes", []))
    expected_receivers = _groups_counter(constraints.get("receivers", []))
    expected_waits = _groups_counter((constraints.get("wait_zones") or {}).get("items", []))
    expected_elevators = _groups_counter(constraints.get("elevators", []))
    if _entity_counter(floors, "agvs") != expected_agvs:
        errors.append(f"AGV size counts expected {dict(expected_agvs)} got {dict(_entity_counter(floors, 'agvs'))}")
    if _entity_counter(floors, "boxes") != expected_boxes:
        errors.append(f"box size counts expected {dict(expected_boxes)} got {dict(_entity_counter(floors, 'boxes'))}")
    if _entity_counter(floors, "receivers") != expected_receivers:
        errors.append(
            f"receiver size counts expected {dict(expected_receivers)} got {dict(_entity_counter(floors, 'receivers'))}"
        )
    if _entity_counter(floors, "wait_zones") != expected_waits:
        errors.append(
            f"wait zone size counts expected {dict(expected_waits)} got {dict(_entity_counter(floors, 'wait_zones'))}"
        )
    if _elevator_counter(map_data.get("elevators", [])) != expected_elevators:
        errors.append(
            f"elevator size counts expected {dict(expected_elevators)} got {dict(_elevator_counter(map_data.get('elevators', [])))}"
        )

    _check_unique(_all_ids(floors, "agvs", "agv_id"), "AGV", errors)
    _check_unique(_all_ids(floors, "boxes", "box_id"), "box", errors)
    _check_unique(_all_ids(floors, "receivers", "receiver_id"), "receiver", errors)
    _check_unique(_all_ids(floors, "wait_zones", "wait_zone_id"), "wait zone", errors)
    _check_unique([int(e["elevator_id"]) for e in map_data.get("elevators", [])], "elevator", errors)

    elevator_by_floor: Dict[int, List[Dict[str, Any]]] = {fid: [] for fid in range(floor_count)}
    for elev in map_data.get("elevators", []):
        size = int(elev.get("size", 1))
        pos = _pos(elev["position"])
        if not _in_bounds(pos, size, width, height):
            errors.append(f"elevator {elev.get('elevator_id')} out of bounds at {list(pos)} size={size}")
        for fid in elev.get("floors", []):
            if int(fid) not in elevator_by_floor:
                errors.append(f"elevator {elev.get('elevator_id')} references unknown floor {fid}")
            else:
                elevator_by_floor[int(fid)].append(elev)

    expected_elevator_positions: List[Tuple[int, Coord, int]] = []
    for group in constraints.get("elevators", []):
        size = int(group.get("size", 1))
        for pos in group.get("fixed_positions") or []:
            expected_elevator_positions.append((size, _pos(pos), len(group.get("floors") or [])))
    actual_fixed = {(int(e.get("size", 1)), _pos(e["position"])) for e in map_data.get("elevators", [])}
    for size, pos, _ in expected_elevator_positions:
        if (size, pos) not in actual_fixed:
            errors.append(f"fixed elevator position missing: size={size} position={list(pos)}")

    agv_floor: Dict[int, int] = {}
    wait_by_id: Dict[int, Tuple[int, Dict[str, Any]]] = {}
    for floor in floors:
        fid = int(floor["floor_id"])
        occupied: Dict[Coord, str] = {}
        for obs in floor.get("obstacles", []):
            _add_footprint(occupied, _obstacle_pos(obs), 1, f"floor {fid} obstacle", width, height, errors)
        for elev in elevator_by_floor.get(fid, []):
            _add_footprint(
                occupied,
                _pos(elev["position"]),
                int(elev.get("size", 1)),
                f"floor {fid} elevator {elev.get('elevator_id')}",
                width,
                height,
                errors,
            )
        for box in floor.get("boxes", []):
            _add_footprint(
                occupied,
                _pos(box["position"]),
                int(box.get("size", 1)),
                f"floor {fid} box {box.get('box_id')}",
                width,
                height,
                errors,
            )
        for receiver in floor.get("receivers", []):
            _add_footprint(
                occupied,
                _pos(receiver["position"]),
                int(receiver.get("size", 1)),
                f"floor {fid} receiver {receiver.get('receiver_id')}",
                width,
                height,
                errors,
            )
        for zone in floor.get("wait_zones", []):
            _add_footprint(
                occupied,
                _pos(zone["position"]),
                int(zone.get("size", 1)),
                f"floor {fid} wait_zone {zone.get('wait_zone_id')}",
                width,
                height,
                errors,
            )
            wait_by_id[int(zone["wait_zone_id"])] = (fid, zone)
        for agv in floor.get("agvs", []):
            agv_id = int(agv["agv_id"])
            agv_floor[agv_id] = fid
            zone_record = wait_by_id.get(agv_id)
            if zone_record is None:
                errors.append(f"AGV {agv_id} on floor {fid} has no wait_zone with the same id")
            elif zone_record[0] != fid:
                errors.append(f"AGV {agv_id} wait_zone is on floor {zone_record[0]} but AGV is on floor {fid}")

    reachability_checks = 0
    reachability_passed = 0
    for floor in floors:
        fid = int(floor["floor_id"])
        blocked = _blocked_cells_for_floor(floor)
        starts = [
            (int(agv.get("size", 1)), _pos(wait_by_id[int(agv["agv_id"])][1]["position"]))
            for agv in floor.get("agvs", [])
            if int(agv["agv_id"]) in wait_by_id
        ]
        targets: List[Tuple[str, Coord]] = []
        targets.extend((f"box {b.get('box_id')}", _pos(b["position"])) for b in floor.get("boxes", []))
        targets.extend((f"receiver {r.get('receiver_id')}", _pos(r["position"])) for r in floor.get("receivers", []))
        targets.extend((f"elevator {e.get('elevator_id')}", _pos(e["position"])) for e in elevator_by_floor.get(fid, []))
        for label, target in targets:
            if not starts:
                continue
            reachability_checks += 1
            if any(_reachable(start, target, size, width, height, blocked) for size, start in starts):
                reachability_passed += 1
            else:
                errors.append(f"floor {fid} {label} is unreachable from all AGV wait zones")

    reachability_score = (
        reachability_passed / reachability_checks if reachability_checks else 1.0
    )

    return {
        "valid": not errors,
        "errors": errors,
        "warnings": warnings,
        "summary": _summary(map_data),
        "reachability_score": reachability_score,
    }
