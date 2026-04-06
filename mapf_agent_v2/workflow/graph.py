from __future__ import annotations

from typing import Dict, Literal

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, StateGraph
from langgraph.types import interrupt

from mapf_agent_v2.session.state import AgentState
from mapf_agent_v2.workflow.nodes.codegen_node import codegen_node
from mapf_agent_v2.workflow.nodes.config_node import config_node
from mapf_agent_v2.workflow.nodes.intent_node import intent_node
from mapf_agent_v2.workflow.nodes.map_node import map_node
from mapf_agent_v2.workflow.nodes.optimize_node import optimize_node
from mapf_agent_v2.workflow.nodes.respond_node import respond_node
from mapf_agent_v2.workflow.nodes.run_node import run_node


def _current_intent_type(state: AgentState) -> str:
    intents = state.get("intents") or []
    idx = int(state.get("intent_index", 0))
    if idx >= len(intents):
        return "done"
    return str(intents[idx].get("type", "done"))


def route_by_intent(state: AgentState) -> Literal["map", "config", "run", "generate_algo", "optimize", "done"]:
    if state.get("terminate"):
        return "done"
    return _current_intent_type(state)  # type: ignore[return-value]


def post_node_route(state: AgentState) -> Literal["ask", "next"]:
    if state.get("need_user_input"):
        return "ask"
    return "next"


def advance_intent_node(state: AgentState) -> Dict:
    idx = int(state.get("intent_index", 0))
    return {"intent_index": idx + 1}


def ask_user_node(state: AgentState) -> Dict:
    payload = {
        "type": "user_question",
        "question": state.get("pending_question", ""),
        "stage": state.get("blocking_stage", ""),
    }
    answer = interrupt(payload)
    return {
        "user_response": str(answer).strip(),
        "need_user_input": False,
        "pending_question": "",
    }


def resume_route(state: AgentState) -> Literal["map", "config", "generate_algo", "optimize", "intent"]:
    stage = str(state.get("blocking_stage", "")).strip()
    if stage in {"map", "config", "generate_algo", "optimize"}:
        return stage  # type: ignore[return-value]
    return "intent"


def build_graph():
    graph = StateGraph(AgentState)
    graph.add_node("intent", intent_node)
    graph.add_node("map", map_node)
    graph.add_node("config", config_node)
    graph.add_node("run", run_node)
    graph.add_node("generate_algo", codegen_node)
    graph.add_node("optimize", optimize_node)
    graph.add_node("respond", respond_node)
    graph.add_node("ask_user", ask_user_node)
    graph.add_node("advance", advance_intent_node)

    graph.set_entry_point("intent")

    graph.add_conditional_edges(
        "intent",
        route_by_intent,
        {
            "map": "map",
            "config": "config",
            "run": "run",
            "generate_algo": "generate_algo",
            "optimize": "optimize",
            "done": "respond",
        },
    )

    for name in ["map", "config", "run", "generate_algo", "optimize"]:
        graph.add_conditional_edges(
            name,
            post_node_route,
            {"ask": "ask_user", "next": "advance"},
        )

    graph.add_conditional_edges(
        "ask_user",
        resume_route,
        {
            "map": "map",
            "config": "config",
            "generate_algo": "generate_algo",
            "optimize": "optimize",
            "intent": "intent",
        },
    )
    graph.add_conditional_edges(
        "advance",
        route_by_intent,
        {
            "map": "map",
            "config": "config",
            "run": "run",
            "generate_algo": "generate_algo",
            "optimize": "optimize",
            "done": "respond",
        },
    )
    graph.add_edge("respond", END)
    return graph.compile(checkpointer=InMemorySaver())

