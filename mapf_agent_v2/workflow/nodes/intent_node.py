from __future__ import annotations

from typing import Dict

from mapf_agent_v2.intent.parser import parse_intents
from mapf_agent_v2.session.state import AgentState


def intent_node(state: AgentState) -> Dict:
    user_input = (state.get("user_input") or "").strip()
    if user_input.lower() in {"quit", "exit", "q", "end", "结束", "退出"}:
        return {"terminate": True, "result_summary": "已结束会话。"}
    intents = parse_intents(user_input)
    history = list(state.get("conversation_history") or [])
    history.append({"role": "user", "content": user_input})
    return {
        "intents": intents,
        "intent_index": 0,
        "conversation_history": history,
        "error": "",
        "result_summary": "",
    }

