"""
Validate a WareRover map JSON:
  1. JSON Schema validation (structure + types)
  2. Semantic constraint checks (overlaps, bounds, wait_zone/agv matching)
  3. Optional: runtime load via GridMap/AGVManager
"""
from __future__ import annotations

import json
import os
import tempfile
from typing import Any, Dict, List, Set, Tuple, Union

from mapf_agent.config import agent_config


def _load_schema() -> Dict[str, Any]:
    path = os.path.join(agent_config.knowledge_dir, "map_schema.json")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def validate_schema(map_json: Dict[str, Any]) -> Dict[str, Any]:
    """Validate map_json against the JSON Schema. Returns {"ok": True} or {"ok": False, "error": ...}."""
    try:
        import jsonschema
    except ImportError:
        return {"ok": True, "warning": "jsonschema not installed, skipping schema validation"}

    schema = _load_schema()
    try:
        jsonschema.validate(instance=map_json, schema=schema)
        return {"ok": True}
    except jsonschema.ValidationError as e:
        return {"ok": False, "error": f"Schema validation: {e.message} (path: {list(e.absolute_path)})"}


def validate_semantic(map_json: Dict[str, Any]) -> Dict[str, Any]:
    """Check domain-specific constraints beyond what JSON Schema can express."""
    errors: List[str] = []
    w = map_json.get("map", {}).get("width", 0)
    h = map_json.get("map", {}).get("height", 0)

    agvs = map_json.get("agvs", [])
    wait_zones = map_json.get("wait_zones", [])
    boxes = map_json.get("boxes", [])
    receivers = map_json.get("receivers", [])
    obstacles = map_json.get("obstacles", [])

    agv_ids = {a["agv_id"] for a in agvs}
    wz_ids = {wz["wait_zone_id"] for wz in wait_zones}

    if len(wait_zones) < len(agvs):
        errors.append(f"wait_zones count ({len(wait_zones)}) < agvs count ({len(agvs)})")

    if agv_ids != wz_ids:
        errors.append(f"wait_zone_ids {sorted(wz_ids)} don't match agv_ids {sorted(agv_ids)}")

    agv_size_map = {a["agv_id"]: a.get("size", 1) for a in agvs}
    for wz in wait_zones:
        wz_id = wz["wait_zone_id"]
        wz_size = wz.get("size", 1)
        agv_size = agv_size_map.get(wz_id)
        if agv_size is not None and wz_size != agv_size:
            errors.append(f"wait_zone {wz_id} size ({wz_size}) != agv {wz_id} size ({agv_size})")

    occupied: Dict[Tuple[int, int], str] = {}

    def _mark_cells(label: str, pos: List[int], size: int):
        for dx in range(size):
            for dy in range(size):
                cx, cy = pos[0] + dx, pos[1] + dy
                if cx < 0 or cx >= w or cy < 0 or cy >= h:
                    errors.append(f"{label} at [{pos[0]},{pos[1]}] size={size}: cell ({cx},{cy}) out of bounds")
                    continue
                cell = (cx, cy)
                if cell in occupied:
                    errors.append(f"{label} at ({cx},{cy}) overlaps with {occupied[cell]}")
                else:
                    occupied[cell] = label

    for b in boxes:
        _mark_cells(f"box_{b.get('box_id', '?')}", b["position"], b.get("size", 1))
    for r in receivers:
        _mark_cells(f"receiver_{r.get('receiver_id', '?')}", r["position"], r.get("size", 1))
    for wz in wait_zones:
        _mark_cells(f"wait_zone_{wz.get('wait_zone_id', '?')}", wz["position"], wz.get("size", 1))
    for idx, obs in enumerate(obstacles):
        _mark_cells(f"obstacle_{idx}", obs, 1)

    if errors:
        return {"ok": False, "error": "; ".join(errors)}
    return {"ok": True}


def validate_map(
    map_input: Union[str, Dict[str, Any]],
    trial_steps: int = 0,
) -> Dict[str, Any]:
    """
    Full validation pipeline:
      1. Parse input (file path / JSON string / dict)
      2. JSON Schema validation
      3. Semantic constraint checks
      4. Optional runtime load trial
    """
    if isinstance(map_input, str):
        if os.path.isfile(map_input):
            with open(map_input, "r", encoding="utf-8") as f:
                map_json = json.load(f)
        else:
            try:
                map_json = json.loads(map_input)
            except json.JSONDecodeError as e:
                return {"ok": False, "error": f"Invalid JSON: {e}"}
    elif isinstance(map_input, dict):
        map_json = map_input
    else:
        return {"ok": False, "error": "map_input must be a file path (str), JSON str, or dict"}

    schema_result = validate_schema(map_json)
    if not schema_result.get("ok", True):
        return schema_result

    semantic_result = validate_semantic(map_json)
    if not semantic_result.get("ok"):
        return semantic_result

    if trial_steps > 0:
        return _runtime_validate(map_json, trial_steps)

    return {"ok": True}


def _runtime_validate(map_json: Dict[str, Any], trial_steps: int) -> Dict[str, Any]:
    """Load map into WareRover core and optionally run trial steps."""
    fd, tmp_path = tempfile.mkstemp(suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(map_json, f, indent=2)

        from config.settings import SimConfig
        from core.gridmap import GridMap
        from core.ordermanager import OrderManager
        from core.agvmanager import AGVManager

        original_map = SimConfig.map_file
        try:
            SimConfig.map_file = tmp_path
            grid_map = GridMap()
            ordermanager = OrderManager(grid_map)
            agv_manager = AGVManager(grid_map, ordermanager)

            if trial_steps <= 0:
                return {"ok": True}

            from core.env import Env
            from core.fault_manager import FaultManager
            from utils.algorithm_factory import build_scheduler, build_planner
            from core.simulator import Simulator
            from utils.logger import global_logger
            from utils.simulation_clock import clock

            clock.reset()
            global_logger.reset()
            env = Env(agv_manager, grid_map, ordermanager)
            fault_manager = FaultManager(agv_manager, env, grid_map)
            scheduler = build_scheduler(env, agv_manager, ordermanager, grid_map, fault_manager)
            planner = build_planner(env, agv_manager, ordermanager, grid_map, fault_manager)
            simulator = Simulator(grid_map, agv_manager, ordermanager, env, scheduler, planner)
            for _ in range(trial_steps):
                simulator.step()
                fault_manager.step()
                if clock.now() >= SimConfig.max_steps:
                    break
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": str(e)}
        finally:
            SimConfig.map_file = original_map
    finally:
        if os.path.isfile(tmp_path):
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
