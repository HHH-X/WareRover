"""
SimConfig delta parsing agent.

Convert natural language "modify simulation config" into a validated subset dict
that can be applied on top of config.settings.SimConfig/FaultConfig.
"""

from __future__ import annotations

import os
import re
from typing import Any, Dict

from mapf_agent.config import agent_config
from mapf_agent.llm import chat_completion_json


def _load_prompt() -> str:
    path = os.path.join(agent_config.prompts_dir, "sim_config_delta_parser.txt")
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


class SimConfigDeltaParserAgent:
    def __init__(self) -> None:
        self._prompt = _load_prompt()

    def parse(self, nl_text: str, *, use_llm: bool = True) -> Dict[str, Any]:
        text = (nl_text or "").strip()
        if not text:
            return {}

        if use_llm:
            result = chat_completion_json(
                [
                    {"role": "system", "content": self._prompt},
                    {"role": "user", "content": text},
                ]
            )
            return result if isinstance(result, dict) else {}

        return self._parse_regex(text)

    # ---- No-LLM regex fallback (best-effort) ----
    def _parse_regex(self, text: str) -> Dict[str, Any]:
        t = text.lower()
        out: Dict[str, Any] = {}

        def _find_num(patterns: list[str], kind: str) -> None:
            for p in patterns:
                m = re.search(p, t)
                if not m:
                    continue
                raw = m.group(1)
                try:
                    out_key = _find_out_key_from_pattern(p)
                    if kind == "int":
                        out[out_key] = int(float(raw))
                    else:
                        out[out_key] = float(raw)
                    return
                except Exception:
                    return

        def _find_out_key_from_pattern(pattern: str) -> str:
            # Encode the target key inside the pattern by convention: (... "KEY:" ...)
            m = re.search(r"KEY:([a-z0-9_]+)", pattern)
            return (m.group(1) if m else "")

        # max_steps
        for pat in [
            r"(?:max_steps|max步数|最大步数|步数上限)\s*[:=]?\s*(\d+(?:\.\d+)?)\s*(?:steps)?\s*.*?KEY:max_steps",
            r"KEY:max_steps",
        ]:
            # unreachable; keep out_key helper simple (patterns below handle key directly)
            pass

        m = re.search(r"(?:max_steps|max步数|最大步数|步数上限)\s*[:=]?\s*(\d+)", t)
        if m:
            out["max_steps"] = int(m.group(1))

        m = re.search(r"(?:time_step|时间步长|步长)\s*[:=]?\s*(\d+(?:\.\d+)?)", t)
        if m:
            out["time_step"] = float(m.group(1))

        m = re.search(r"(?:agv_max_speed|最大速度|速度)\s*[:=]?\s*(\d+(?:\.\d+)?)", t)
        if m:
            out["agv_max_speed"] = float(m.group(1))

        m = re.search(r"(?:total_orders_limit|订单上限|总订单|订单数上限)\s*[:=]?\s*(\d+)", t)
        if m:
            out["total_orders_limit"] = int(m.group(1))

        m = re.search(r"(?:order_processing_timeout|订单超时|超时)\s*[:=]?\s*(\d+)", t)
        if m:
            out["order_processing_timeout"] = int(m.group(1))

        if any(k in t for k in ("force_replan_every_step", "每步重规划", "强制每步重规划", "强制重规划")):
            out["force_replan_every_step"] = True

        if "disable_faults" in t or "no faults" in t or "不启用故障" in t:
            out["enable_faults"] = False
        elif "fault" in t or "故障" in t:
            # enable faults if user mentions fault at all
            out["enable_faults"] = True

        m = re.search(r"(?:fault_prob|故障概率|故障概率)\s*[:=]?\s*(\d+(?:\.\d+)?)", t)
        if m:
            out["fault_prob"] = float(m.group(1))

        m = re.search(r"(?:mean_repair_time|平均修复时间|修复时间)\s*[:=]?\s*(\d+)", t)
        if m:
            out["mean_repair_time"] = int(m.group(1))

        # planner/scheduler enums
        if "scheduler" in t or "调度" in t:
            if "ta" in t:
                out["scheduler_type"] = "ta"
            elif "random" in t or "随机" in t:
                out["scheduler_type"] = "random"

        if "planner" in t or "规划" in t:
            if "cbs" in t:
                out["planner_type"] = "cbs_fw"
            elif "dhc" in t:
                out["planner_type"] = "dhc"
            elif "astar" in t or "a*" in t:
                out["planner_type"] = "astar"

        if "order_mode" in t or "订单模式" in t or "oneshot" in t:
            if "oneshot" in t or "一次性" in t:
                out["order_mode"] = "oneshot"
            elif "continuous_constant" in t or "连续常量" in t:
                out["order_mode"] = "continuous_constant"
            elif "continuous_periodic" in t or "连续周期" in t:
                out["order_mode"] = "continuous_periodic"
            elif "continuous_pareto" in t or "帕累托" in t:
                out["order_mode"] = "continuous_pareto"
            elif "continuous_burst" in t or "突发" in t:
                out["order_mode"] = "continuous_burst"

        # Avoid returning unknown keys.
        return out

