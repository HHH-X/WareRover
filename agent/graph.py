"""LangGraph workflow: intent → route → execute → advance → respond."""
from __future__ import annotations

from typing import Dict, Literal

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, StateGraph
from langgraph.types import interrupt

from agent.state import AgentState
from agent.nodes.intent import intent_node
from agent.nodes.map_gen import map_gen_node
from agent.nodes.config import config_node
from agent.nodes.run import run_node
from agent.nodes.codegen import codegen_node
from agent.nodes.optimize import optimize_node


# ── routing helpers ──────────────────────────────────────────────

def _current_intent_type(state: AgentState) -> str:
    intents = state.get("intents") or []
    idx = state.get("intent_index", 0)
    if idx >= len(intents):
        return "done"
    return intents[idx].get("type", "done")


def route_intent(state: AgentState) -> Literal[
    "map", "config", "run", "codegen", "optimize", "done"
]:
    if state.get("error"):
        return "done"
    return _current_intent_type(state)  # type: ignore[return-value]


def post_node_route(state: AgentState) -> Literal["ask", "next"]:
    if state.get("error") and state["error"].startswith("NEED_INPUT:"):
        return "ask"
    return "next"


# ── utility nodes ────────────────────────────────────────────────

def advance_node(state: AgentState) -> Dict:
    return {"intent_index": state.get("intent_index", 0) + 1}


def ask_user_node(state: AgentState) -> Dict:
    question = (state.get("error") or "").removeprefix("NEED_INPUT:")
    answer = interrupt({"question": question})
    return {"error": "", "user_input": str(answer).strip()}


def respond_node(state: AgentState) -> Dict:
    parts = []
    if state.get("error"):
        parts.append(f"[错误] {state['error']}")
    if state.get("map_file_path"):
        parts.append(f"地图已保存: {state['map_file_path']}")
    if state.get("generated_code"):
        for kind, path in state["generated_code"].items():
            parts.append(f"生成算法 ({kind}): {path}")
    if state.get("run_metrics"):
        m = state["run_metrics"]
        parts.append(f"仿真完成 — 步数: {m.get('sim_steps')}, "
                      f"完成率: {m.get('task_success_rate', 'N/A')}")
    if state.get("optimize_result"):
        r = state["optimize_result"]
        parts.append(f"优化完成 — 最佳分数: {r.get('best_score', 'N/A')}")
    if not parts:
        parts.append("操作已完成。")
    return {"response": "\n".join(parts)}


def resume_route(state: AgentState) -> str:
    return _current_intent_type(state)


# ── graph builder ────────────────────────────────────────────────

def build_graph():
    g = StateGraph(AgentState)

    g.add_node("intent", intent_node)
    g.add_node("map", map_gen_node)
    g.add_node("config", config_node)
    g.add_node("run", run_node)
    g.add_node("codegen", codegen_node)
    g.add_node("optimize", optimize_node)
    g.add_node("advance", advance_node)
    g.add_node("ask_user", ask_user_node)
    g.add_node("respond", respond_node)

    g.set_entry_point("intent")

    _intent_map = {
        "map": "map",
        "config": "config",
        "run": "run",
        "codegen": "codegen",
        "optimize": "optimize",
        "done": "respond",
    }

    g.add_conditional_edges("intent", route_intent, _intent_map)

    for node_name in ("map", "config", "codegen"):
        g.add_conditional_edges(
            node_name, post_node_route,
            {"ask": "ask_user", "next": "advance"},
        )

    g.add_edge("run", "advance")
    g.add_edge("optimize", "advance")

    g.add_conditional_edges(
        "ask_user", resume_route,
        {
            "map": "map",
            "config": "config",
            "codegen": "codegen",
            "optimize": "optimize",
            "run": "run",
            "done": "respond",
        },
    )

    g.add_conditional_edges("advance", route_intent, _intent_map)
    g.add_edge("respond", END)

    return g.compile(checkpointer=InMemorySaver())
