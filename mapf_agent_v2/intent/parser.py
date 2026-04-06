from __future__ import annotations

import json
from typing import Any, Dict, List

from mapf_agent_v2.llm.client import chat_completion_json
from mapf_agent_v2.session.state import IntentTask

INTENT_PROMPT = """
你是 MAPF Agent 的意图解析器。
请把用户输入拆成 intents 数组，支持多意图且顺序固定:
1) map 2) config 3) run 4) generate_algo 5) optimize

返回 JSON:
{
  "intents": [
    {"type":"map","content":"..."},
    {"type":"config","content":"..."},
    {"type":"run","content":"..."},
    {
      "type":"generate_algo",
      "algorithm_type":"planner|scheduler",
      "algorithm_name":"name",
      "content":"..."
    },
    {
      "type":"optimize",
      "target":"planner|scheduler|both",
      "planner_source":"可为空",
      "scheduler_source":"可为空",
      "iterations":3,
      "config_path":"",
      "output_root":"mapf_agent_v2/runs/stage2",
      "content":"..."
    }
  ]
}

要求:
- 未提及的意图不要输出。
- run 只有在用户明确提出运行时才输出。
- JSON 必须合法。
"""


def _order_key(t: Dict[str, Any]) -> int:
    order = {"map": 0, "config": 1, "run": 2, "generate_algo": 3, "optimize": 4}
    return order.get(str(t.get("type", "")), 99)


def parse_intents(user_input: str) -> List[IntentTask]:
    result = chat_completion_json(
        [
            {"role": "system", "content": INTENT_PROMPT},
            {"role": "user", "content": user_input},
        ]
    )
    intents = result.get("intents", [])
    if not isinstance(intents, list):
        raise ValueError(f"解析结果不合法: {json.dumps(result, ensure_ascii=False)}")
    valid: List[IntentTask] = []
    for item in intents:
        if not isinstance(item, dict):
            continue
        typ = str(item.get("type", "")).strip()
        if typ not in {"map", "config", "run", "generate_algo", "optimize"}:
            continue
        clean: IntentTask = {"type": typ, "content": str(item.get("content", "")).strip()}
        if typ == "generate_algo":
            clean["algorithm_type"] = str(item.get("algorithm_type", "planner")).strip()  # type: ignore[assignment]
            clean["algorithm_name"] = str(item.get("algorithm_name", "generated_algo")).strip()
        if typ == "optimize":
            clean["target"] = str(item.get("target", "planner")).strip()  # type: ignore[assignment]
            clean["planner_source"] = str(item.get("planner_source", "")).strip()
            clean["scheduler_source"] = str(item.get("scheduler_source", "")).strip()
            try:
                clean["iterations"] = int(item.get("iterations", 3))
            except Exception:
                clean["iterations"] = 3
            clean["config_path"] = str(item.get("config_path", "")).strip()
            clean["output_root"] = str(item.get("output_root", "mapf_agent_v2/runs/stage2")).strip()
        valid.append(clean)
    valid.sort(key=_order_key)
    return valid

