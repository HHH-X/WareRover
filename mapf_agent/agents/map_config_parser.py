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


def _load_prompt() -> str:
    path = os.path.join(agent_config.prompts_dir, "input_parser.txt")
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


class MapConfigParser:
    """Parse natural language into structured map/sim config via LLM with fallback to regex."""

    def __init__(self):
        self._prompt = _load_prompt()
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

    # ---- Regex fallback (legacy) ----

    def _parse_regex(self, nl_text: str) -> Dict[str, Any]:
        text = (nl_text or "").strip().lower()
        mc: Dict[str, Any] = json.loads(json.dumps(DEFAULT_MAP_CONFIG))

        size_match = re.search(r"(\d+)\s*[x*×]\s*(\d+)", text, re.IGNORECASE)
        if size_match:
            mc["width"] = int(size_match.group(1))
            mc["height"] = int(size_match.group(2))
        for m in re.finditer(r"width\s*[=:]?\s*(\d+)", text):
            mc["width"] = int(m.group(1))
        for m in re.finditer(r"height\s*[=:]?\s*(\d+)", text):
            mc["height"] = int(m.group(1))

        agv_match = re.search(r"(\d+)\s*(?:agvs?|台|辆车)", text)
        if agv_match:
            mc["agvs"]["count"] = max(1, int(agv_match.group(1)))

        sizes = []
        large_m = re.findall(r"(\d+)\s*(?:large|大)", text)
        small_m = re.findall(r"(\d+)\s*(?:small|小)", text)
        for n in large_m:
            sizes.extend([2] * int(n))
        for n in small_m:
            sizes.extend([1] * int(n))
        if sizes:
            mc["agvs"]["sizes"] = sizes
            mc["agvs"]["count"] = len(sizes)

        if not mc["agvs"]["sizes"] and mc["agvs"]["count"] > 0:
            mc["agvs"]["sizes"] = [1] * mc["agvs"]["count"]

        for key, pattern in [
            ("shelves", r"(?:box|shelf|shelves|货架|箱子)\s*(?:数)?\s*(\d+)"),
            ("receivers", r"(?:receiver|station|站台|接收)\s*(?:数)?\s*(\d+)"),
            ("obstacles", r"(?:obstacle|障碍)\s*(?:数)?\s*(\d+)"),
        ]:
            m = re.search(pattern, text)
            if m:
                mc[key]["count"] = max(0, int(m.group(1)))

        if not mc["shelves"]["count"] and mc["agvs"]["count"] > 0:
            mc["shelves"]["count"] = mc["agvs"]["count"] * 3

        missing = []
        if mc["width"] < 1 or mc["height"] < 1:
            missing.append("map dimensions (width, height)")
        if mc["agvs"]["count"] < 1:
            missing.append("AGV count")

        return {
            "complete": len(missing) == 0,
            "missing_fields": missing,
            "follow_up_question": f"请补充以下信息：{', '.join(missing)}" if missing else "",
            "map_config": mc,
            "sim_config": {},
        }
