from __future__ import annotations

from typing import Dict

from mapf_agent_v2.session.state import AgentState


def respond_node(state: AgentState) -> Dict:
    summary = state.get("result_summary", "")
    error = state.get("error", "")
    msg = summary or ("执行完成。" if not error else f"执行失败: {error}")
    history = list(state.get("conversation_history") or [])
    history.append({"role": "assistant", "content": msg})
    return {"conversation_history": history, "blocking_stage": "", "pending_question": "", "need_user_input": False}

