"""Intent parsing node: split user input into ordered IntentTask list."""
from __future__ import annotations

from pathlib import Path
from typing import Dict, List

from mapf_agent.llm import chat_json
from mapf_agent.state import AgentState, IntentTask

_PROMPT_PATH = Path(__file__).resolve().parent.parent / "prompts" / "intent.txt"

_INTENT_ORDER = {"map": 0, "config": 1, "codegen": 2, "optimize": 3, "run": 4}


def _load_system_prompt() -> str:
    return _PROMPT_PATH.read_text(encoding="utf-8")


_INTENT_LABELS = {
    "map": "生成地图", "config": "修改配置", "codegen": "生成算法",
    "optimize": "优化算法", "run": "运行仿真",
}


def intent_node(state: AgentState) -> Dict:
    user_input = state.get("user_input", "")
    if not user_input:
        return {"intents": [], "intent_index": 0, "error": "未收到用户输入"}

    print("[意图解析] 正在分析用户指令...")
    messages = [
        {"role": "system", "content": _load_system_prompt()},
        {"role": "user", "content": user_input},
    ]
    parsed = chat_json(messages)
    raw_intents: List[Dict] = parsed.get("intents", [])

    intents: List[IntentTask] = []
    for item in raw_intents:
        t = item.get("type", "")
        if t not in _INTENT_ORDER:
            continue
        task = IntentTask(type=t, detail=item.get("detail", ""))
        if t == "codegen":
            task["algo_type"] = item.get("algo_type", "planner")
            task["algo_name"] = item.get("algo_name", "")
            task["skill_name"] = item.get("skill_name", "")
        elif t == "optimize":
            task["algo_type"] = item.get("algo_type", "planner")
            task["optimize_source"] = item.get("optimize_source", "")
        intents.append(task)

    if intents:
        labels = [_INTENT_LABELS.get(i["type"], i["type"]) for i in intents]
        print(f"[意图解析] 识别到 {len(intents)} 个任务: {' → '.join(labels)}")
    else:
        print("[意图解析] 未识别到有效任务")

    return {"intents": intents, "intent_index": 0, "error": ""}
