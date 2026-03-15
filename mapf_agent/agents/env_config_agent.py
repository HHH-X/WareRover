"""
Environment config Agent: generate WareRover map JSON from structured map_config
via LLM, then validate with JSON Schema + semantic checks.
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional

from mapf_agent.config import agent_config
from mapf_agent.tools.validate_map import validate_schema, validate_semantic


def _load_prompt() -> str:
    path = os.path.join(agent_config.prompts_dir, "env_config.txt")
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _load_template() -> str:
    path = os.path.join(agent_config.knowledge_dir, "examples", "template_map.json")
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


class EnvConfigAgent:
    """Generate map JSON from structured map_config via LLM with fallback."""

    def __init__(self):
        self._prompt = _load_prompt()
        self._template = _load_template()

    def generate(self, map_config: Dict[str, Any], use_llm: bool = True, max_retries: int = 3) -> Dict[str, Any]:
        """
        Generate and validate a map JSON.

        Returns {"ok": True, "map_json": ...} or {"ok": False, "error": ..., "map_json": ...}.
        """
        if use_llm:
            try:
                return self._generate_llm(map_config, max_retries)
            except Exception as e:
                pass
        return self._generate_fallback(map_config)

    def _generate_llm(self, map_config: Dict[str, Any], max_retries: int) -> Dict[str, Any]:
        from mapf_agent.llm import chat_completion_json

        system_msg = (
            f"{self._prompt}\n\n"
            f"## Example output (template_map.json):\n```json\n{self._template}\n```"
        )
        user_msg = f"Generate a map JSON for this configuration:\n```json\n{json.dumps(map_config, ensure_ascii=False, indent=2)}\n```"

        messages = [
            {"role": "system", "content": system_msg},
            {"role": "user", "content": user_msg},
        ]

        last_error = None
        for attempt in range(max_retries):
            map_json = chat_completion_json(messages)

            schema_result = validate_schema(map_json)
            if not schema_result.get("ok", True):
                last_error = schema_result["error"]
                messages.append({"role": "assistant", "content": json.dumps(map_json, ensure_ascii=False)})
                messages.append({
                    "role": "user",
                    "content": f"Validation failed: {last_error}\nPlease fix the issues and regenerate.",
                })
                continue

            semantic_result = validate_semantic(map_json)
            if not semantic_result.get("ok"):
                last_error = semantic_result["error"]
                messages.append({"role": "assistant", "content": json.dumps(map_json, ensure_ascii=False)})
                messages.append({
                    "role": "user",
                    "content": f"Semantic validation failed: {last_error}\nPlease fix the issues and regenerate.",
                })
                continue

            return {"ok": True, "map_json": map_json}

        return {"ok": False, "error": last_error or "Max retries exceeded", "map_json": map_json}

    def _generate_fallback(self, map_config: Dict[str, Any]) -> Dict[str, Any]:
        """Deterministic fallback generator (no LLM)."""
        import random

        w = max(5, int(map_config.get("width", 20)))
        h = max(5, int(map_config.get("height", 15)))
        agvs_spec = map_config.get("agvs", {})
        num_agvs = max(1, int(agvs_spec.get("count", 2)))
        agv_sizes = agvs_spec.get("sizes", [1] * num_agvs)
        if len(agv_sizes) != num_agvs:
            agv_sizes = [1] * num_agvs

        shelves_spec = map_config.get("shelves", {})
        num_boxes = max(0, int(shelves_spec.get("count", num_agvs * 3)))
        receivers_spec = map_config.get("receivers", {})
        num_receivers = max(1, int(receivers_spec.get("count", 2)))
        obstacles_spec = map_config.get("obstacles", {})
        num_obstacles = max(0, int(obstacles_spec.get("count", 0)))

        occupied: set = set()

        def pick_cell(margin: int = 1) -> tuple:
            candidates = [
                (x, y)
                for x in range(margin, w - margin)
                for y in range(margin, h - margin)
                if (x, y) not in occupied
            ]
            if not candidates:
                return (w // 2, h // 2)
            return random.choice(candidates)

        wait_zones = []
        for i in range(num_agvs):
            size = agv_sizes[i] if i < len(agv_sizes) else 1
            pos = pick_cell()
            wait_zones.append({"wait_zone_id": i, "position": list(pos), "size": size})
            for dx in range(size):
                for dy in range(size):
                    occupied.add((pos[0] + dx, pos[1] + dy))

        agvs = [{"agv_id": i, "size": agv_sizes[i] if i < len(agv_sizes) else 1} for i in range(num_agvs)]

        goods_id_counter = 0
        boxes = []
        for i in range(num_boxes):
            pos = pick_cell()
            gids = [goods_id_counter, goods_id_counter + 1]
            goods_id_counter += 2
            boxes.append({"box_id": i, "position": list(pos), "goods_ids": gids, "size": 1})
            occupied.add(pos)

        receivers = []
        for i in range(num_receivers):
            pos = pick_cell()
            receivers.append({"receiver_id": i, "position": list(pos), "size": 1})
            occupied.add(pos)

        obstacles_list = []
        for _ in range(num_obstacles):
            pos = pick_cell()
            obstacles_list.append(list(pos))
            occupied.add(pos)

        map_json = {
            "map": {"width": w, "height": h},
            "boxes": boxes,
            "receivers": receivers,
            "wait_zones": wait_zones,
            "agvs": agvs,
            "obstacles": obstacles_list,
        }
        return {"ok": True, "map_json": map_json}
