"""
Input parsing Agent: use LLM to understand complex NL descriptions,
extract structured map config + sim config, and ask follow-up questions
when required information is missing.
"""
from __future__ import annotations

import os
import json
import re
from typing import Any, Dict, List, Optional

from mapf_agent.config import agent_config


DEFAULT_MAP_CONFIG = {
    "width": 0,
    "height": 0,
    "agvs": {"count": 0, "sizes": [], "placement": "top", "placement_detail": ""},
    "shelves": {
        "count": 0, "size": 1, "rows": None, "cols": None,
        "placement": "center", "placement_detail": "", "spacing": 1,
    },
    "receivers": {"count": 2, "size": 1, "placement": "bottom", "placement_detail": ""},
    "obstacles": {"count": 0, "placement": "random", "placement_detail": ""},
    "layout_hints": [],
}

REQUIRED_FIELDS = ["map_config.width", "map_config.height", "map_config.agvs.count"]


# def _load_prompt() -> str:
#     path = os.path.join(agent_config.prompts_dir, "input_parser.txt")
#     with open(path, "r", encoding="utf-8") as f:
#         return f.read()


class MapConfigParser:
    """Parse natural language into structured map/sim config via LLM with fallback to regex."""

    def __init__(self):
        path = os.path.join(agent_config.prompts_dir, "input_parser.txt")
        with open(path, "r", encoding="utf-8") as f:
            self._prompt = f.read()
        self._conversation: List[Dict[str, str]] = []

    def reset_conversation(self):
        self._conversation = []

    def continue_parse(self, follow_up_text: str) -> Dict[str, Any]:
        """Continue multi-turn conversation with user's follow-up answer."""
        return self.parse(follow_up_text)

    def parse(self, nl_text: str) -> Dict[str, Any]:
        from mapf_agent.llm import chat_completion_json

        if not self._conversation:
            self._conversation.append({"role": "system", "content": self._prompt})

        self._conversation.append({"role": "user", "content": nl_text})

        result = chat_completion_json(self._conversation)
        self._conversation.append({"role": "assistant", "content": json.dumps(result, ensure_ascii=False)})

        result.setdefault("complete", False)
        result.setdefault("missing_fields", [])
        result.setdefault("follow_up_question", "")
        result.setdefault("map_config", {})
        result.setdefault("sim_config", {})
        self._fill_defaults(result)
        return result

    def _fill_defaults(self, result: Dict[str, Any]):
        """Apply defaults to optional fields when user didn't specify them."""
        mc = result.get("map_config", {})
        if not mc:
            return

        agvs = mc.setdefault("agvs", {})
        agvs.setdefault("placement", "top")
        agv_count = agvs.get("count", 0)
        if not agvs.get("sizes") and agv_count > 0:
            agvs["sizes"] = [1] * agv_count

        shelves = mc.setdefault("shelves", {})
        if not shelves.get("count") and agv_count > 0:
            shelves["count"] = agv_count * 3
        shelves.setdefault("size", 1)
        shelves.setdefault("placement", "center")
        shelves.setdefault("spacing", 1)

        receivers = mc.setdefault("receivers", {})
        receivers.setdefault("count", 2)
        receivers.setdefault("size", 1)
        receivers.setdefault("placement", "bottom")

        obstacles = mc.setdefault("obstacles", {})
        obstacles.setdefault("count", 0)
        obstacles.setdefault("placement", "random")

        mc.setdefault("layout_hints", [])
