"""
LangGraph workflow definition for MAPF Agent.
Defines the state schema and builds the state graph with conditional routing,
multi-turn conversation, validation retry loops, and optimization iteration.
"""
from __future__ import annotations

import json
import os
from typing import Any, Annotated, Dict, List, Optional, Sequence, TypedDict

from langgraph.graph import StateGraph, END


# ---------------------------------------------------------------------------
# State schema
# ---------------------------------------------------------------------------

class MAPFState(TypedDict, total=False):
    user_input: str
    # Final resolved route for this turn: "map_only" | "algorithm_only" | "both"
    route: str
    # Optional hint injected by caller/CLI to bias routing
    route_hint: str

    # Input parsing
    map_text: str
    algorithm_text: str
    parse_result: Dict[str, Any]

    # Map generation
    map_config: Dict[str, Any]
    # Per-session sim config overrides parsed from user input
    sim_config_delta: Dict[str, Any]
    map_json: Dict[str, Any]
    map_path: str
    map_gen_attempts: int

    # Algorithm
    algo_config: Dict[str, Any]
    algo_nl: str

    # Simulation
    metrics: Dict[str, Any]
    optimization_history: List[Dict[str, Any]]
    iteration: int
    max_iterations: int

    # Environment config (full, high-priority over defaults)
    env_config: Dict[str, Any]
    # Explicit optimization rounds requested by user (if any)
    requested_iterations: int

    # Conversation
    pending_question: str  # Non-empty means we need user input
    human_response: str

    # Control
    error: str
    use_llm: bool
    output_path: str


# ---------------------------------------------------------------------------
# Node functions
# ---------------------------------------------------------------------------

def route_input(state: MAPFState) -> Dict[str, Any]:
    """
    Classify user input into one of three routes:
      - map_only       : 只生成/更新地图与环境配置
      - algorithm_only : 只配置/优化算法（使用已有环境）
      - both           : 同时涉及地图/环境和算法
    """
    use_llm = state.get("use_llm", True)
    user_input = state.get("user_input", "")

    # 1) If caller provided an explicit route_hint, respect it first
    hint = (state.get("route_hint") or "").strip()
    if hint in ("map_only", "algorithm_only", "both"):
        if hint == "map_only":
            return {"route": "map_only", "map_text": user_input, "algorithm_text": ""}
        if hint == "algorithm_only":
            return {"route": "algorithm_only", "map_text": "", "algorithm_text": user_input}
        return {"route": "both", "map_text": user_input, "algorithm_text": user_input}

    # 2) Otherwise, try LLM-based router (can also output route + separated texts)
    if use_llm:
        try:
            from mapf_agent.llm import chat_completion_json
            from mapf_agent.config import agent_config

            prompt_path = os.path.join(agent_config.prompts_dir, "router.txt")
            with open(prompt_path, "r", encoding="utf-8") as f:
                system_prompt = f.read()

            result = chat_completion_json([
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_input},
            ])
            raw_route = result.get("route", "map_only")
            if raw_route in ("map_only", "algorithm_only", "both"):
                route = raw_route
            elif raw_route == "map":
                route = "map_only"
            elif raw_route == "algorithm":
                route = "algorithm_only"
            else:
                route = "map_only"

            return {
                "route": route,
                "map_text": result.get("map_text", "") or (user_input if route != "algorithm_only" else ""),
                "algorithm_text": result.get("algorithm_text", "") or (user_input if route != "map_only" else ""),
            }
        except Exception:
            pass

    # 3) Fallback keyword heuristic
    text_lower = user_input.lower()
    has_map = any(k in text_lower for k in ("地图", "map", "x", "agv", "台", "货架", "shelf"))
    has_algo = any(k in text_lower for k in ("算法", "algorithm", "planner", "cbs", "astar", "优化"))

    if has_map and has_algo:
        return {"route": "both", "map_text": user_input, "algorithm_text": user_input}
    if has_algo:
        return {"route": "algorithm_only", "map_text": "", "algorithm_text": user_input}
    return {"route": "map_only", "map_text": user_input, "algorithm_text": ""}


def parse_map_input(state: MAPFState) -> Dict[str, Any]:
    """Parse map-related text into structured config."""
    from mapf_agent.agents.input_parser import InputParserAgent

    parser = InputParserAgent()
    use_llm = state.get("use_llm", True)

    text = state.get("human_response") or state.get("map_text", "")
    if state.get("parse_result") and state.get("human_response"):
        result = parser.parse(text, use_llm=use_llm)
        prev = state["parse_result"]
        merged_mc = {**prev.get("map_config", {}), **result.get("map_config", {})}
        merged_sc = {**prev.get("sim_config", {}), **result.get("sim_config", {})}
        result["map_config"] = merged_mc
        result["sim_config"] = merged_sc
    else:
        result = parser.parse(text, use_llm=use_llm)

    updates: Dict[str, Any] = {
        "parse_result": result,
        "map_config": result.get("map_config", {}),
        "sim_config_delta": result.get("sim_config", {}),
        "human_response": "",
    }

    if not result.get("complete", False):
        updates["pending_question"] = result.get("follow_up_question", "请补充地图配置信息。")
    else:
        updates["pending_question"] = ""

    return updates


def generate_map(state: MAPFState) -> Dict[str, Any]:
    """Generate map JSON from map_config."""
    from mapf_agent.agents.env_config_agent import EnvConfigAgent

    agent = EnvConfigAgent()
    use_llm = state.get("use_llm", True)
    attempts = state.get("map_gen_attempts", 0) + 1
    result = agent.generate(state.get("map_config", {}), use_llm=use_llm)

    updates: Dict[str, Any] = {"map_gen_attempts": attempts}
    if result.get("ok"):
        map_json = result["map_json"]
        updates["map_json"] = map_json

        output_path = state.get("output_path", "")
        if output_path:
            os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(map_json, f, indent=2, ensure_ascii=False)
            updates["map_path"] = output_path
    else:
        updates["error"] = result.get("error", "Map generation failed")

    return updates


def apply_sim_config(state: MAPFState) -> Dict[str, Any]:
    """
    Apply simulation configuration overrides at runtime.

    Priority (high → low):
      1. Per-session overrides from user input (sim_config_delta)
      2. Full environment config in state.env_config (if any)
      3. Defaults defined in config.settings.SimConfig (import time)
    """
    from config.settings import SimConfig
    from mapf_agent.tools.runtime_config import load_runtime_config, merge_dataclass

    # 1) Start from defaults defined in config.settings
    base_sim = SimConfig()

    # 2) Apply env_config from state (if any) as a lower-priority override layer.
    #    Here we only look at a flat sim_config-style dict; the richer JSON
    #    file format is handled by load_runtime_config elsewhere.
    env_conf = state.get("env_config") or {}
    env_sim_overrides = env_conf.get("sim_config") or {}
    sim_after_env = merge_dataclass(base_sim, env_sim_overrides)

    # 3) Apply per-session delta from current conversation (highest priority).
    delta = state.get("sim_config_delta", {}) or {}
    sim_final = merge_dataclass(sim_after_env, delta)

    # Propagate effective values back to the SimConfig class so the rest of
    # the simulator (which currently imports SimConfig as globals) sees them.
    for field in sim_final.__dataclass_fields__.keys():
        setattr(SimConfig, field, getattr(sim_final, field))

    applied = {
        k: getattr(sim_final, k)
        for k in sim_final.__dataclass_fields__.keys()
        if getattr(sim_final, k) != getattr(base_sim, k)
    }

    return {"sim_config_applied": applied}


def select_algorithm(state: MAPFState) -> Dict[str, Any]:
    """Select algorithm config from NL."""
    from mapf_agent.agents.algorithm_agent import AlgorithmAgent

    agent = AlgorithmAgent()
    use_llm = state.get("use_llm", True)
    nl = state.get("algorithm_text") or state.get("algo_nl", "")
    map_info = state.get("map_json", {}).get("map") if state.get("map_json") else None

    result = agent.select(nl, map_info=map_info, use_llm=use_llm)

    return {
        "algo_config": result,
        "max_iterations": result.get("max_iterations", 3),
    }


def run_simulation_node(state: MAPFState) -> Dict[str, Any]:
    """Run the simulation with current map and algorithm config."""
    from mapf_agent.tools.run_simulation import run_simulation

    algo = state.get("algo_config", {})
    map_path = state.get("map_path", "")
    map_json = state.get("map_json")

    if not map_path and map_json:
        import tempfile
        fd, map_path = tempfile.mkstemp(suffix=".json")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(map_json, f, indent=2)

    if not map_path:
        return {"error": "No map file available for simulation", "metrics": {}}

    from mapf_agent.config import agent_config
    result = run_simulation(
        map_file=map_path,
        planner_type=algo.get("planner_type"),
        scheduler_type=algo.get("scheduler_type"),
        seed=agent_config.default_simulation_seed,
        num_runs=1,
    )

    if result.get("ok"):
        return {"metrics": result.get("metrics", {})}
    return {"error": result.get("error", "Simulation failed"), "metrics": {}}


def analyze_and_optimize(state: MAPFState) -> Dict[str, Any]:
    """Analyze metrics and decide whether to continue optimization."""
    from mapf_agent.agents.optimizer_agent import OptimizerAgent

    agent = OptimizerAgent()
    use_llm = state.get("use_llm", True)
    metrics = state.get("metrics", {})
    algo_config = state.get("algo_config", {})
    history = list(state.get("optimization_history", []))
    iteration = state.get("iteration", 0) + 1

    current_config = {
        "planner_type": algo_config.get("planner_type", "astar"),
        "scheduler_type": algo_config.get("scheduler_type", "ta"),
    }

    result = agent.suggest(metrics, current_config, history, use_llm=use_llm)

    history.append({
        "iteration": iteration,
        "planner_type": current_config["planner_type"],
        "scheduler_type": current_config["scheduler_type"],
        "metrics": metrics,
        "suggestion": result.get("suggestion", {}),
    })

    updates: Dict[str, Any] = {
        "optimization_history": history,
        "iteration": iteration,
    }

    suggestion = result.get("suggestion", {})
    if result.get("should_continue") and iteration < state.get("max_iterations", 3):
        if suggestion.get("action") == "change_algorithm":
            new_algo = dict(algo_config)
            if suggestion.get("new_planner_type"):
                new_algo["planner_type"] = suggestion["new_planner_type"]
            if suggestion.get("new_scheduler_type"):
                new_algo["scheduler_type"] = suggestion["new_scheduler_type"]
            updates["algo_config"] = new_algo
        elif suggestion.get("action") == "adjust_params":
            param_changes = suggestion.get("param_changes", {})
            if param_changes.get("max_steps"):
                from config.settings import SimConfig
                SimConfig.max_steps = int(param_changes["max_steps"])

    return updates


# ---------------------------------------------------------------------------
# Conditional edge functions
# ---------------------------------------------------------------------------

def route_after_classify(state: MAPFState) -> str:
    """
    Decide where to go after routing:
      - map_only       → 解析地图/环境，再生成地图
      - algorithm_only → 直接进入算法选择/仿真（依赖已有环境）
      - both           → 先解析地图/环境，再到算法
    """
    route = state.get("route", "map_only")
    if route == "algorithm_only":
        return "select_algorithm"
    # both/map_only 都需要先走 parse_map_input
    return "parse_map_input"


def check_parse_complete(state: MAPFState) -> str:
    if state.get("pending_question"):
        return "wait_for_human"
    return "generate_map"


def check_map_gen(state: MAPFState) -> str:
    if state.get("map_json") and not state.get("error"):
        return "apply_sim_config"
    if state.get("map_gen_attempts", 0) < 3:
        return "generate_map"
    return "end_with_error"


def after_sim_config(state: MAPFState) -> str:
    """
    Decide what to do after environment configuration has been applied.

    - map_only       → 直接成功结束（只需要地图/环境）
    - algorithm_only → 正常不会走到这里（没有 map 流程）
    - both           → 在生成地图和应用配置后继续进行算法阶段
    """
    route = state.get("route", "map_only")
    if route == "both" and state.get("algorithm_text"):
        return "select_algorithm"
    # map_only：完成后直接结束
    return "end_success"


def check_optimization(state: MAPFState) -> str:
    history = state.get("optimization_history", [])
    if not history:
        return "end_success"

    last = history[-1]
    suggestion = last.get("suggestion", {})
    iteration = state.get("iteration", 0)
    # 优化轮数上限：用户显式请求 > algo_config.max_iterations > 默认 3
    requested = state.get("requested_iterations") or 0
    max_iter = requested or state.get("max_iterations", 3)
    algo_config = state.get("algo_config", {})

    if not algo_config.get("optimize", False):
        return "end_success"

    if suggestion.get("action") == "satisfied":
        return "end_success"

    if iteration >= max_iter:
        return "end_success"

    if suggestion.get("action") in ("change_algorithm", "adjust_params"):
        return "run_simulation"

    return "end_success"


# ---------------------------------------------------------------------------
# Build the graph
# ---------------------------------------------------------------------------

def build_graph() -> StateGraph:
    """Construct the LangGraph StateGraph for the MAPF workflow."""
    graph = StateGraph(MAPFState)

    graph.add_node("route_input", route_input)
    graph.add_node("parse_map_input", parse_map_input)
    graph.add_node("generate_map", generate_map)
    graph.add_node("apply_sim_config", apply_sim_config)
    graph.add_node("select_algorithm", select_algorithm)
    graph.add_node("run_simulation", run_simulation_node)
    graph.add_node("analyze_optimize", analyze_and_optimize)

    graph.set_entry_point("route_input")

    graph.add_conditional_edges("route_input", route_after_classify, {
        "parse_map_input": "parse_map_input",
        "select_algorithm": "select_algorithm",
    })

    graph.add_conditional_edges("parse_map_input", check_parse_complete, {
        "wait_for_human": END,
        "generate_map": "generate_map",
    })

    graph.add_conditional_edges("generate_map", check_map_gen, {
        "apply_sim_config": "apply_sim_config",
        "generate_map": "generate_map",
        "end_with_error": END,
    })

    graph.add_conditional_edges("apply_sim_config", after_sim_config, {
        "select_algorithm": "select_algorithm",
        "end_success": END,
    })

    graph.add_edge("select_algorithm", "run_simulation")
    graph.add_edge("run_simulation", "analyze_optimize")

    graph.add_conditional_edges("analyze_optimize", check_optimization, {
        "run_simulation": "run_simulation",
        "end_success": END,
    })

    return graph
