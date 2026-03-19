"""
Refactored LangGraph workflow for MAPF Agent.

This file is the functional replacement of `mapf_agent.workflow.graph`.
`graph.py` will re-export `MAPFState` and `build_graph` from here.
"""

from __future__ import annotations

import json
import os
import time
from typing import Any, Dict, List, Optional, TypedDict

from langgraph.graph import END, StateGraph


class MAPFState(TypedDict, total=False):
    # --- Input + routing ---
    user_input: str
    route: str  # "map_only" | "algorithm_only" | "both"
    route_hint: str
    map_text: str
    algorithm_text: str

    # --- LLM toggle ---
    use_llm: bool

    # --- Environment parsing/validation ---
    parse_result: Dict[str, Any]
    env_extract_attempts: int
    env_validation_attempts: int
    env_validation_max_attempts: int

    map_config: Dict[str, Any]
    sim_config_delta: Dict[str, Any]

    # --- Environment persistence ---
    map_json: Dict[str, Any]
    map_path: str
    map_gen_attempts: int

    env_runtime_json_path: str

    # --- Algorithm routing/config ---
    algo_route: str  # "select" | "generate" | "optimize"
    algo_config: Dict[str, Any]
    max_iterations: int

    # --- Simulation / optimization ---
    metrics: Dict[str, Any]
    metrics_ran: bool
    optimization_history: List[Dict[str, Any]]
    iteration: int

    # --- Conversation ---
    pending_question: str
    human_response: str

    # --- Output / control ---
    error: str
    output_path: str  # optional map output override


def _project_dirs() -> Dict[str, str]:
    from mapf_agent.config import PROJECT_ROOT

    map_dir = os.path.join(PROJECT_ROOT, "config", "maps", "generated")
    env_runtime_dir = os.path.join(PROJECT_ROOT, "config", "envs", "runtime")
    env_fallback_dir = os.path.join(PROJECT_ROOT, "config", "envs")
    return {
        "map_dir": map_dir,
        "env_runtime_dir": env_runtime_dir,
        "env_fallback_dir": env_fallback_dir,
    }


def _ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def _default_map_path(attempts: int) -> str:
    dirs = _project_dirs()
    ts = time.strftime("%Y%m%d_%H%M%S")
    suffix = f"_{attempts}" if attempts > 0 else ""
    _ensure_dir(dirs["map_dir"])
    return os.path.join(dirs["map_dir"], f"map_user_{ts}{suffix}.json")


def route_input(state: MAPFState) -> Dict[str, Any]:
    """Classify the current turn into map_only / algorithm_only / both."""
    # Resume safety: if route and both texts already exist, don't overwrite.
    if state.get("route") in ("map_only", "algorithm_only", "both") and state.get("map_text") is not None and state.get(
        "algorithm_text"
    ) is not None:
        return {}

    user_input = state.get("user_input", "") or ""
    hint = (state.get("route_hint") or "").strip()
    if hint in ("map_only", "algorithm_only", "both"):
        if hint == "map_only":
            return {"route": "map_only", "map_text": user_input, "algorithm_text": ""}
        if hint == "algorithm_only":
            return {"route": "algorithm_only", "map_text": "", "algorithm_text": user_input}
        return {"route": "both", "map_text": user_input, "algorithm_text": user_input}

    use_llm = state.get("use_llm", True)
    if use_llm:
        try:
            from mapf_agent.llm import chat_completion_json
            from mapf_agent.config import agent_config

            prompt_path = os.path.join(agent_config.prompts_dir, "router.txt")
            with open(prompt_path, "r", encoding="utf-8") as f:
                system_prompt = f.read()

            result = chat_completion_json(
                [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_input},
                ]
            )
            raw_route = result.get("route", "map_only")
            if raw_route in ("map_only", "algorithm_only", "both"):
                route = raw_route
            elif raw_route == "map":
                route = "map_only"
            elif raw_route == "algorithm":
                route = "algorithm_only"
            else:
                route = "map_only"

            map_text = result.get("map_text", "") or (user_input if route != "algorithm_only" else "")
            algo_text = result.get("algorithm_text", "") or (user_input if route != "map_only" else "")
            return {"route": route, "map_text": map_text, "algorithm_text": algo_text}
        except Exception:
            pass

    # Fallback keyword heuristic
    text_lower = user_input.lower()
    has_map = any(k in text_lower for k in ("地图", "map", "agv", "货架", "shelf"))
    has_algo = any(k in text_lower for k in ("算法", "algorithm", "planner", "cbs", "astar", "优化"))
    if has_map and has_algo:
        return {"route": "both", "map_text": user_input, "algorithm_text": user_input}
    if has_algo:
        return {"route": "algorithm_only", "map_text": "", "algorithm_text": user_input}
    return {"route": "map_only", "map_text": user_input, "algorithm_text": ""}


def env_extract(state: MAPFState) -> Dict[str, Any]:
    """Parse environment description into map_config + sim_config_delta."""
    from mapf_agent.agents.input_parser import InputParserAgent

    attempts = state.get("env_extract_attempts", 0) + 1
    use_llm = state.get("use_llm", True)
    parser = InputParserAgent()

    text = (state.get("human_response") or state.get("map_text") or "").strip()
    if not text:
        return {"env_extract_attempts": attempts, "map_config": {}, "sim_config_delta": {}, "parse_result": {}}

    if state.get("parse_result") is not None and state.get("human_response"):
        # Multi-turn merge
        result = parser.parse(text, use_llm=use_llm)
        prev = state["parse_result"]

        prev_mc = prev.get("map_config", {}) or {}
        result_mc = result.get("map_config", {}) or {}

        # Guard against overwriting required fields with invalid defaults (e.g., width/height=0)
        merged_mc = dict(prev_mc)
        for k, v in result_mc.items():
            if k in ("width", "height"):
                try:
                    if int(v) < 1:
                        continue
                except Exception:
                    continue
            if k == "agvs" and isinstance(v, dict):
                prev_agvs = prev_mc.get("agvs", {}) or {}
                merged_agvs = dict(prev_agvs)
                for ak, av in v.items():
                    if ak == "count":
                        try:
                            if int(av) < 1:
                                continue
                        except Exception:
                            continue
                    merged_agvs[ak] = av
                merged_mc[k] = merged_agvs
            else:
                merged_mc[k] = v

        prev_sc = prev.get("sim_config", {}) or {}
        result_sc = result.get("sim_config", {}) or {}
        merged_sc = dict(prev_sc)
        for k, v in result_sc.items():
            # If follow-up returns null/empty for a key, keep previous value.
            if v is None:
                continue
            merged_sc[k] = v

        result["map_config"] = merged_mc
        result["sim_config"] = merged_sc
    else:
        result = parser.parse(text, use_llm=use_llm)

    return {
        "env_extract_attempts": attempts,
        "parse_result": result,
        "map_config": result.get("map_config", {}) or {},
        "sim_config_delta": result.get("sim_config", {}) or {},
        "human_response": "",
    }


def env_validate(state: MAPFState) -> Dict[str, Any]:
    """
    Validate map_config completeness and SimConfig field correctness.
    When invalid, return pending_question for human follow-up.
    """
    from mapf_agent.tools.sim_config_validator import validate_sim_config_delta

    attempts = state.get("env_validation_attempts", 0) + 1
    max_attempts = int(state.get("env_validation_max_attempts", 5))

    map_config = state.get("map_config") or {}
    sim_delta = state.get("sim_config_delta") or {}

    # Map required fields
    missing: List[str] = []
    try:
        w = int(map_config.get("width"))
        h = int(map_config.get("height"))
        agv_count = int((map_config.get("agvs") or {}).get("count"))
    except Exception:
        w = h = agv_count = 0

    if w < 1:
        missing.append("map_config.width")
    if h < 1:
        missing.append("map_config.height")
    if agv_count < 1:
        missing.append("map_config.agvs.count")

    if missing:
        if attempts > max_attempts:
            return {"env_validation_attempts": attempts, "error": "地图信息补全次数超出上限。", "pending_question": ""}
        return {
            "env_validation_attempts": attempts,
            "pending_question": f"请补充地图配置信息：{', '.join(missing)}。",
        }

    # SimConfig validation
    sim_validation = validate_sim_config_delta(sim_delta)
    if not sim_validation.get("ok", False):
        if attempts > max_attempts:
            return {"env_validation_attempts": attempts, "error": "仿真配置修正次数超出上限。", "pending_question": ""}
        return {
            "env_validation_attempts": attempts,
            "pending_question": sim_validation.get("pending_question", "仿真配置有误，请按提示修正。"),
        }

    return {
        "env_validation_attempts": attempts,
        "pending_question": "",
        "sim_config_delta": sim_validation.get("cleaned_delta", {}) or {},
    }


def generate_and_save_map(state: MAPFState) -> Dict[str, Any]:
    """Generate map JSON from map_config and persist it."""
    from mapf_agent.agents.env_config_agent import EnvConfigAgent

    if state.get("map_json") and state.get("map_path"):
        return {}

    agent = EnvConfigAgent()
    use_llm = state.get("use_llm", True)
    attempts = state.get("map_gen_attempts", 0) + 1
    result = agent.generate(state.get("map_config", {}), use_llm=use_llm)

    if not result.get("ok"):
        return {"map_gen_attempts": attempts, "error": result.get("error", "Map generation failed")}

    map_json = result["map_json"]
    out_override = (state.get("output_path") or "").strip()
    map_path = out_override or _default_map_path(attempts)

    os.makedirs(os.path.dirname(map_path) or ".", exist_ok=True)
    with open(map_path, "w", encoding="utf-8") as f:
        json.dump(map_json, f, indent=2, ensure_ascii=False)

    return {"map_gen_attempts": attempts, "map_json": map_json, "map_path": map_path}


def build_and_save_env_runtime_json(state: MAPFState) -> Dict[str, Any]:
    """Persist runtime_meta env override JSON and apply it to runtime classes."""
    from mapf_agent.tools.env_runtime_config_io import (
        apply_runtime_meta_to_sim_classes,
        build_runtime_meta_payload,
        save_env_runtime_meta_json,
    )

    if state.get("env_runtime_json_path"):
        return {}

    map_path = state.get("map_path") or ""
    if not map_path or not os.path.isfile(map_path):
        return {"error": "地图文件不存在，无法生成环境参数 JSON。"}

    payload = build_runtime_meta_payload(map_file=map_path, sim_overrides=state.get("sim_config_delta") or {})
    out_path = save_env_runtime_meta_json(payload)
    applied = apply_runtime_meta_to_sim_classes(out_path)
    return {"env_runtime_json_path": out_path, "sim_config_applied": applied}


def ensure_env_runtime_json_default(state: MAPFState) -> Dict[str, Any]:
    """For algorithm_only route: create runtime_meta env json referencing existing map_path."""
    from mapf_agent.tools.env_runtime_config_io import (
        apply_runtime_meta_to_sim_classes,
        build_runtime_meta_payload,
        save_env_runtime_meta_json,
    )

    if state.get("env_runtime_json_path"):
        return {}

    map_path = (state.get("map_path") or "").strip()
    if not map_path or not os.path.isfile(map_path):
        return {"error": "algorithm_only 模式需要提供有效的 map_path（--map-file）。"}

    payload = build_runtime_meta_payload(map_file=map_path, sim_overrides=state.get("sim_config_delta") or {})
    out_path = save_env_runtime_meta_json(payload)
    applied = apply_runtime_meta_to_sim_classes(out_path)
    return {"env_runtime_json_path": out_path, "sim_config_applied": applied}


def route_algorithm(state: MAPFState) -> Dict[str, Any]:
    """Classify algorithm request: select / generate / optimize."""
    text = (state.get("algorithm_text") or "").lower()
    route = "select"
    if any(k in text for k in ("优化", "optimize", "演化", "迭代", "evolution")):
        route = "optimize"
    elif any(k in text for k in ("生成", "新算法", "实现", "code", "planner", "scheduler")) and any(
        k in text for k in ("算法", "algorithm")
    ):
        route = "generate"
    return {"algo_route": route}


def algorithm_select_apply_env(state: MAPFState) -> Dict[str, Any]:
    """Select algorithm from NL and apply it to env runtime json + runtime SimConfig."""
    from config.settings import PlannerType, SchedulerType
    from config.settings import SimConfig
    from mapf_agent.agents.algorithm_agent import AlgorithmAgent
    from mapf_agent.tools.env_runtime_config_io import update_env_runtime_meta_sim

    agent = AlgorithmAgent()
    use_llm = state.get("use_llm", True)
    nl = state.get("algorithm_text") or ""
    map_info = (state.get("map_json") or {}).get("map") if state.get("map_json") else None

    result = agent.select(nl, map_info=map_info, use_llm=use_llm)
    algo_config = result or {}

    env_path = state.get("env_runtime_json_path") or ""
    if env_path and os.path.isfile(env_path):
        update_env_runtime_meta_sim(
            env_runtime_json_path=env_path,
            sim_updates={
                "planner_type": algo_config.get("planner_type"),
                "scheduler_type": algo_config.get("scheduler_type"),
            },
        )

    try:
        if algo_config.get("planner_type") is not None:
            SimConfig.planner_type = PlannerType(algo_config["planner_type"])
        if algo_config.get("scheduler_type") is not None:
            SimConfig.scheduler_type = SchedulerType(algo_config["scheduler_type"])
    except Exception:
        # Conversion errors will surface in later simulation.
        pass

    return {"algo_config": algo_config, "max_iterations": int(algo_config.get("max_iterations", 3))}


def algorithm_generate_loop_placeholder(state: MAPFState) -> Dict[str, Any]:
    """
    Placeholder for "generate new algorithm" loop.

    Current repo doesn't support planner/scheduler codegen. We fallback to:
    1) AlgorithmAgent.select to infer planner/scheduler
    2) run simulation quickly; if fails, try alternate planners
    """
    from mapf_agent.config import agent_config
    from mapf_agent.tools.run_simulation import run_simulation

    from mapf_agent.agents.algorithm_codegen_agent import AlgorithmCodegenAgent

    baseline = algorithm_select_apply_env(state)
    algo_config = baseline.get("algo_config") or {}
    map_path = (state.get("map_path") or "").strip()
    if not map_path:
        return {**baseline, "error": "没有可用于仿真的地图文件。", "metrics": {}, "metrics_ran": True}

    codegen_agent = AlgorithmCodegenAgent()
    plan_preview = codegen_agent.propose_code_changes(
        state.get("algorithm_text") or "", map_info=(state.get("map_json") or {}).get("map") if state.get("map_json") else None
    )

    gen_history: List[Dict[str, Any]] = []
    try_planners = codegen_agent.get_planner_candidates(algo_config.get("planner_type"))
    scheduler = algo_config.get("scheduler_type")

    max_gen_attempts = int(state.get("max_iterations", 3))
    attempted = 0
    last_err: Optional[str] = None

    for planner in try_planners:
        if attempted >= max_gen_attempts:
            break
        if not planner:
            continue
        attempted += 1
        sim_result = run_simulation(
            map_file=map_path,
            planner_type=planner,
            scheduler_type=scheduler,
            seed=agent_config.default_simulation_seed,
            num_runs=1,
        )
        if sim_result.get("ok"):
            gen_history.append(
                {
                    "attempt": attempted,
                    "planner_type": planner,
                    "scheduler_type": scheduler,
                    "ok": True,
                }
            )
            return {
                **baseline,
                "algorithm_codegen_plan": plan_preview,
                "algorithm_codegen_history": gen_history,
                "metrics": sim_result.get("metrics", {}) or {},
                "metrics_ran": True,
            }
        last_err = sim_result.get("error", "Simulation failed")
        gen_history.append(
            {
                "attempt": attempted,
                "planner_type": planner,
                "scheduler_type": scheduler,
                "ok": False,
                "error": last_err,
            }
        )

    return {
        **baseline,
        "algorithm_codegen_plan": plan_preview,
        "algorithm_codegen_history": gen_history,
        "error": last_err or "Simulation failed",
        "metrics": {},
        "metrics_ran": True,
    }


def run_simulation_node(state: MAPFState) -> Dict[str, Any]:
    """Run the simulation with current map and algorithm config."""
    if state.get("metrics_ran") and state.get("metrics") is not None:
        return {}

    from mapf_agent.config import agent_config
    from mapf_agent.tools.run_simulation import run_simulation

    algo = state.get("algo_config") or {}
    map_path = (state.get("map_path") or "").strip()

    if not map_path:
        return {"error": "No map file available for simulation", "metrics": {}, "metrics_ran": False}

    result = run_simulation(
        map_file=map_path,
        planner_type=algo.get("planner_type"),
        scheduler_type=algo.get("scheduler_type"),
        seed=agent_config.default_simulation_seed,
        num_runs=1,
    )

    if result.get("ok"):
        return {"metrics": result.get("metrics", {}) or {}, "metrics_ran": True}
    return {"error": result.get("error", "Simulation failed"), "metrics": {}, "metrics_ran": False}


def analyze_and_optimize(state: MAPFState) -> Dict[str, Any]:
    """Analyze metrics and decide whether to continue optimization."""
    if state.get("error"):
        return {}

    from mapf_agent.agents.optimizer_agent import OptimizerAgent

    agent = OptimizerAgent()
    use_llm = state.get("use_llm", True)
    metrics = state.get("metrics", {}) or {}
    algo_config = state.get("algo_config") or {}
    history = list(state.get("optimization_history", []))
    iteration = int(state.get("iteration", 0)) + 1

    current_config = {
        "planner_type": algo_config.get("planner_type", "astar"),
        "scheduler_type": algo_config.get("scheduler_type", "ta"),
    }

    result = agent.suggest(metrics, current_config, history, use_llm=use_llm)
    history.append(
        {
            "iteration": iteration,
            "planner_type": current_config["planner_type"],
            "scheduler_type": current_config["scheduler_type"],
            "metrics": metrics,
            "suggestion": result.get("suggestion", {}) or {},
        }
    )

    updates: Dict[str, Any] = {"optimization_history": history, "iteration": iteration}
    suggestion = result.get("suggestion", {}) or {}
    should_continue = bool(result.get("should_continue", False))
    max_iter = int(state.get("max_iterations", 3))

    if should_continue and iteration < max_iter:
        if suggestion.get("action") == "change_algorithm":
            new_algo = dict(algo_config)
            if suggestion.get("new_planner_type"):
                new_algo["planner_type"] = suggestion["new_planner_type"]
            if suggestion.get("new_scheduler_type"):
                new_algo["scheduler_type"] = suggestion["new_scheduler_type"]
            updates["algo_config"] = new_algo
        elif suggestion.get("action") == "adjust_params":
            param_changes = suggestion.get("param_changes", {}) or {}
            if param_changes.get("max_steps") is not None:
                from config.settings import SimConfig

                SimConfig.max_steps = int(param_changes["max_steps"])

    return updates


# ---------------------------------------------------------------------------
# Conditional edges
# ---------------------------------------------------------------------------


def after_route(state: MAPFState) -> str:
    route = state.get("route", "map_only")
    if route == "algorithm_only":
        return "ensure_env_runtime_json_default"
    return "env_extract"


def after_env_validate(state: MAPFState) -> str:
    if state.get("pending_question"):
        return "wait_for_human"
    return "generate_and_save_map"


def after_map_and_env(state: MAPFState) -> str:
    if not (state.get("algorithm_text") or "").strip():
        return "end_success"
    return "route_algorithm"


def after_route_algorithm(state: MAPFState) -> str:
    route = state.get("algo_route", "select")
    if route == "generate":
        return "algorithm_generate_loop_placeholder"
    return "algorithm_select_apply_env"


def check_optimization(state: MAPFState) -> str:
    algo_config = state.get("algo_config") or {}
    if not algo_config.get("optimize", False):
        return "end_success"

    history = state.get("optimization_history", [])
    if not history:
        return "end_success"

    last = history[-1]
    suggestion = last.get("suggestion", {}) or {}
    iteration = int(state.get("iteration", 0))
    max_iter = int(state.get("max_iterations", 3))

    if suggestion.get("action") == "satisfied":
        return "end_success"
    if iteration >= max_iter:
        return "end_success"
    if suggestion.get("action") in ("change_algorithm", "adjust_params"):
        return "run_simulation"
    return "end_success"


def build_graph() -> StateGraph:
    graph = StateGraph(MAPFState)

    graph.set_entry_point("route_input")

    # Nodes
    graph.add_node("route_input", route_input)
    graph.add_node("env_extract", env_extract)
    graph.add_node("env_validate", env_validate)
    graph.add_node("generate_and_save_map", generate_and_save_map)
    graph.add_node("build_and_save_env_runtime_json", build_and_save_env_runtime_json)
    graph.add_node("ensure_env_runtime_json_default", ensure_env_runtime_json_default)
    graph.add_node("route_algorithm", route_algorithm)
    graph.add_node("algorithm_select_apply_env", algorithm_select_apply_env)
    graph.add_node("algorithm_generate_loop_placeholder", algorithm_generate_loop_placeholder)
    graph.add_node("run_simulation", run_simulation_node)
    graph.add_node("analyze_and_optimize", analyze_and_optimize)

    # Routing
    graph.add_conditional_edges(
        "route_input",
        after_route,
        {"ensure_env_runtime_json_default": "ensure_env_runtime_json_default", "env_extract": "env_extract"},
    )

    graph.add_edge("env_extract", "env_validate")
    graph.add_conditional_edges(
        "env_validate",
        after_env_validate,
        {"wait_for_human": END, "generate_and_save_map": "generate_and_save_map"},
    )

    graph.add_edge("generate_and_save_map", "build_and_save_env_runtime_json")
    graph.add_conditional_edges(
        "build_and_save_env_runtime_json",
        after_map_and_env,
        {"route_algorithm": "route_algorithm", "end_success": END},
    )

    graph.add_edge("ensure_env_runtime_json_default", "route_algorithm")

    graph.add_conditional_edges(
        "route_algorithm",
        after_route_algorithm,
        {
            "algorithm_select_apply_env": "algorithm_select_apply_env",
            "algorithm_generate_loop_placeholder": "algorithm_generate_loop_placeholder",
        },
    )

    graph.add_edge("algorithm_select_apply_env", "run_simulation")
    graph.add_edge("algorithm_generate_loop_placeholder", "run_simulation")

    graph.add_edge("run_simulation", "analyze_and_optimize")
    graph.add_conditional_edges(
        "analyze_and_optimize",
        check_optimization,
        {"run_simulation": "run_simulation", "end_success": END},
    )

    return graph

