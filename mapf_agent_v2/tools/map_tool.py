from __future__ import annotations

import json
import random
import time
from pathlib import Path
from typing import Any, Dict, List, Tuple

from mapf_agent_v2.llm.client import chat_completion_json

MAP_SPEC_PROMPT = """
你是 MAPF 地图参数提取器。请输出 JSON:
{
  "width": 25,
  "height": 20,
  "agv_count": 14,
  "size2_agv_count": 3,
  "receiver_count": 10,
  "obstacle_count": 0
}
如果用户未提及某项，可省略字段。
"""


REQUIRED_KEYS = ["width", "height", "agv_count"]


def parse_map_spec(text: str) -> Dict[str, Any]:
    return chat_completion_json(
        [
            {"role": "system", "content": MAP_SPEC_PROMPT},
            {"role": "user", "content": text},
        ]
    )


def fill_defaults(spec: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(spec)
    out.setdefault("receiver_count", 6)
    out.setdefault("size2_agv_count", 0)
    out.setdefault("obstacle_count", 0)
    return out


def missing_required(spec: Dict[str, Any]) -> List[str]:
    missing: List[str] = []
    for key in REQUIRED_KEYS:
        if key not in spec:
            missing.append(key)
    return missing


def _random_empty_cells(width: int, height: int, k: int, blocked: set[Tuple[int, int]]) -> List[Tuple[int, int]]:
    cells = [(x, y) for x in range(width) for y in range(height) if (x, y) not in blocked]
    random.shuffle(cells)
    return cells[:k]


def generate_map_json(spec: Dict[str, Any]) -> Dict[str, Any]:
    width = int(spec["width"])
    height = int(spec["height"])
    agv_count = int(spec["agv_count"])
    size2_count = int(spec.get("size2_agv_count", 0))
    receiver_count = int(spec.get("receiver_count", 6))
    obstacle_count = int(spec.get("obstacle_count", 0))

    if width < 4 or height < 4:
        raise ValueError("地图尺寸过小，至少 4x4")
    if agv_count <= 0:
        raise ValueError("agv_count 必须 > 0")
    if size2_count < 0 or size2_count > agv_count:
        raise ValueError("size2_agv_count 范围非法")

    blocked: set[Tuple[int, int]] = set()
    wait_positions = _random_empty_cells(width, height, agv_count, blocked)
    blocked.update(wait_positions)

    receiver_positions = _random_empty_cells(width, height, receiver_count, blocked)
    blocked.update(receiver_positions)

    obstacle_positions = _random_empty_cells(width, height, obstacle_count, blocked)
    blocked.update(obstacle_positions)

    # Keep it simple: no shelves for generated maps.
    wait_zones = [{"wait_zone_id": i, "position": [x, y]} for i, (x, y) in enumerate(wait_positions)]
    agvs = []
    for i in range(agv_count):
        item: Dict[str, Any] = {"agv_id": i}
        if i >= agv_count - size2_count:
            item["size"] = 2
        agvs.append(item)
    receivers = [{"receiver_id": i, "position": [x, y]} for i, (x, y) in enumerate(receiver_positions)]
    obstacles = [[x, y] for (x, y) in obstacle_positions]

    return {
        "map": {"width": width, "height": height},
        "boxes": [],
        "receivers": receivers,
        "wait_zones": wait_zones,
        "agvs": agvs,
        "obstacles": obstacles,
    }


def save_map_json(map_json: Dict[str, Any], output_dir: str = "config/maps") -> str:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"agent_v2_map_{time.strftime('%Y%m%d_%H%M%S')}.json"
    path.write_text(json.dumps(map_json, indent=2, ensure_ascii=False), encoding="utf-8")
    return str(path)

