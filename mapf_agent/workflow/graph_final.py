from __future__ import annotations

import json
import os
import time
from typing import Any, Dict, List, Optional, TypedDict

from langgraph.graph import END, StateGraph
from langgraph.types import interrupt

from config.settings import SimConfig

from mapf_agent.agents.algorithm_agent import AlgorithmAgent
from mapf_agent.agents.map_builder import MapBuilder
from mapf_agent.agents.map_config_parser import MapConfigParser
from mapf_agent.agents.optimizer_agent import OptimizerAgent
from mapf_agent.agents.sim_config_delta_parser import SimConfigDeltaParserAgent
from mapf_agent.config import PACKAGE_DIR, PROJECT_ROOT
from mapf_agent.llm import chat_completion_json
from mapf_agent.tools.env_runtime_config_io import (
    apply_runtime_meta_to_sim_classes,
    build_runtime_meta_payload,
    save_env_runtime_meta_json,
)
from mapf_agent.tools.run_simulation import run_simulation
from mapf_agent.tools.sim_config_validator import validate_sim_config_delta
from mapf_agent.config import agent_config


class MAPFState(TypedDict, total=False):
    # ===== 输入 =====
    user_input: str
    user_response: str

    # ===== 意图 =====
    # intent_generate_map: bool
    # intent_modify_config: bool
    # intent_generate_algo: bool
    # intent_optimize_algo: bool

    intent_run_simulation: bool

    map_intent_flag: bool
    map_intent_content: str

    sim_intent_flag: bool
    sim_intent_content: str

    algorithm_text: str

    algo_generate_flag: bool
    algo_generate_content: str

    algo_optimize_flag: bool
    algo_optimize_content: str
    # ===== 地图 =====
    map_config: dict
    map_file_path: str

    # ===== 配置 =====
    sim_config: dict

    # ===== 算法 =====
    algo_spec: str
    algo_code: str

    # ===== 仿真结果 =====
    metrics: dict
    error: str

    # ===== 人机交互 =====
    need_user_input: bool
    pending_question: str
    blocking_stage: str

    # ===== pipeline状态（推荐）=====
    map_ready: bool
    config_ready: bool
    algo_ready: bool


def _as_bool(v: Any) -> bool:
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return bool(v)
    if isinstance(v, str):
        s = v.strip().lower()
        return s in ("true", "t", "yes", "y", "1")
    return False


def _term_intent(text: str) -> bool:
    t = (text or "").strip().lower()
    return t in ("quit", "exit", "q", "stop", "end", "结束", "退出")


def request_user_input(question: str, stage_key: str) -> Dict[str, Any]:
    return {
        "need_user_input": True,
        "pending_question": question or "",
        "blocking_stage": stage_key,
    }


def check_need_input(state: MAPFState) -> str:
    if state.get("need_user_input"):
        return "ask_user"
    return "continue"



def intent_parse_node(state: MAPFState) -> Dict[str, Any]:
    user_input = (state.get("user_input") or "").strip()

    if user_input.lower() in ("quit", "exit", "q", "stop", "end", "结束", "退出"):
        return {"terminate": True}
    
    # Compute readiness from existing artifacts
    map_intent_flag = False
    sim_intent_flag = False
    algo_generate_flag = False
    algo_optimize_flag = False
    map_intent_content = ""
    sim_intent_content = ""
    algo_generate_content = ""
    algo_optimize_content = ""
    
    prompt_path = os.path.join(agent_config.prompts_dir, "intent_parser.txt")
    with open(prompt_path, "r", encoding="utf-8") as f:
        system_prompt = f.read()

    result = chat_completion_json(
        [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_input},
        ]
    )

    gmap = result.get("intent_generate_map") or {}
    msim = result.get("intent_modify_simconfig") or {}
    galgo = result.get("intent_generate_algorithm") or {}
    opt = result.get("intent_optimize_algorithm") or {}

    map_intent_flag = _as_bool(gmap.get("flag"))
    map_intent_content = _pick_content(gmap.get("content"))
    sim_intent_flag = _as_bool(msim.get("flag"))
    sim_intent_content = _pick_content(msim.get("content"))
    algo_generate_flag = _as_bool(galgo.get("flag"))
    algo_generate_content = _pick_content(galgo.get("content"))
    algo_optimize_flag = _as_bool(opt.get("flag"))
    algo_optimize_content = _pick_content(opt.get("content"))

    history = _append_history(state, "user", user_input)
    return {
        "map_intent_flag": map_intent_flag,
        "map_intent_content": map_intent_content,
        "sim_intent_flag": sim_intent_flag,
        "sim_intent_content": sim_intent_content,
        "algo_generate_flag": algo_generate_flag,
        "algo_generate_content": algo_generate_content,
        "algo_optimize_flag": algo_optimize_flag,
        "algo_optimize_content": algo_optimize_content,
        "conversation_history": history,
        "pending_question": "",
        "pending_type": "",
        "need_user_input": False,
    }


def router_node(state: MAPFState) -> Dict[str, Any]:
    # Router is a pass-through node; routing decisions are done by route_decision().
    return {}


def route_decision(state: MAPFState) -> str:
    if _term_intent(state.get("user_input") or ""):
        return "end"

    # Resume priority
    if state.get("blocking_stage"):
        return state["blocking_stage"]

    intent_run = bool(state.get("intent_run_simulation"))
    intent_map = bool(state.get("intent_generate_map"))
    intent_cfg = bool(state.get("intent_modify_config"))
    intent_algo = bool(state.get("intent_generate_algo"))
    intent_opt = bool(state.get("intent_optimize_algo"))

    map_ready = bool(state.get("map_ready"))
    config_ready = bool(state.get("config_ready"))
    algo_ready = bool(state.get("algo_ready"))

    # Automatic completion chain (run)
    if intent_run:
        if not map_ready:
            return "map"
        if not config_ready:
            return "config"
        if not algo_ready:
            return "algo_gen"
        return "run"

    # Normal intents: still ensure prerequisites for algo/opt
    if intent_map and not map_ready:
        return "map"
    if intent_cfg and not config_ready:
        return "config"

    if intent_algo or intent_opt:
        if not map_ready:
            return "map"
        if not config_ready:
            return "config"
        if not algo_ready:
            return "algo_gen"
        if intent_opt:
            return "algo_opt"
        return "run"

    return "end"


def _load_json_if_map(path: str) -> Optional[Dict[str, Any]]:
    path = (path or "").strip()
    if not path or not os.path.isfile(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _default_algo_code() -> str:
    # Store a JSON string in algo_code to match the "algo_code: str" contract.
    default = {
        "planner_type": getattr(SimConfig.planner_type, "value", SimConfig.planner_type),
        "scheduler_type": getattr(SimConfig.scheduler_type, "value", SimConfig.scheduler_type),
    }
    return json.dumps(default, ensure_ascii=False)


def map_generate_node(state: MAPFState) -> Dict[str, Any]:

    # Consume human supplement
    user_text = state.get("user_input") or ""
    if state.get("blocking_stage") == "map" and state.get("user_response"):
        user_text = f"{user_text}\n{state['user_response']}"

    parser = MapConfigParser()
    try:
        parsed = parser.parse(user_text)
    except Exception:
        # Best-effort regex fallback (private API, but stable within this repo)
        parsed = parser._parse_regex(user_text)  # type: ignore[attr-defined]

    complete = bool(parsed.get("complete"))
    if not complete:
        return request_user_input(parsed.get("follow_up_question", "请补充地图信息。"), "map")

    map_config = parsed.get("map_config", {}) or {}

    existing_path = (state.get("map_file_path") or "").strip()
    if existing_path and os.path.isfile(existing_path):
        return {
            "map_config": map_config,
            "map_ready": True,
            "blocking_stage": "",
            "user_response": "",
        }

    map_out_override = (state.get("output_path") or "").strip() or (state.get("map_output_path") or "").strip()
    if map_out_override:
        map_file_path = os.path.abspath(map_out_override)
    else:
        map_dir = os.path.join(PROJECT_ROOT, "config", "maps", "generated")
        os.makedirs(map_dir, exist_ok=True)
        ts = time.strftime("%Y%m%d_%H%M%S")
        map_file_path = os.path.join(map_dir, f"map_user_{ts}.json")

    result = MapBuilder().generate(map_config, use_llm=use_llm)
    if not result.get("ok", False):
        return request_user_input(f"地图生成失败：{result.get('error','')}。请补充/修正地图信息。", "map")

    map_json = result["map_json"]
    os.makedirs(os.path.dirname(map_file_path) or ".", exist_ok=True)
    with open(map_file_path, "w", encoding="utf-8") as f:
        json.dump(map_json, f, indent=2, ensure_ascii=False)

    return {
        "map_config": map_config,
        "map_file_path": map_file_path,
        "map_ready": True,
        "blocking_stage": "",
        "user_response": "",
        "error": "",
    }


def config_update_node(state: MAPFState) -> Dict[str, Any]:
    use_llm = bool(state.get("use_llm", True))

    # Consume human supplement
    user_text = state.get("user_input") or ""
    if state.get("blocking_stage") == "config" and state.get("user_response"):
        user_text = f"{user_text}\n{state['user_response']}"

    sim_delta_parser = SimConfigDeltaParserAgent()
    sim_delta = {}
    try:
        sim_delta = sim_delta_parser.parse(user_text, use_llm=use_llm) or {}
    except Exception:
        sim_delta = sim_delta_parser.parse(user_text, use_llm=False) or {}

    validation = validate_sim_config_delta(sim_delta)
    if not validation.get("ok", False):
        return request_user_input(validation.get("pending_question", "仿真配置有误，请按提示修正。"), "config")

    cleaned = validation.get("cleaned_delta", {}) or {}
    return {
        "sim_config": cleaned,
        "config_ready": True,
        "blocking_stage": "",
        "user_response": "",
        "error": "",
    }


def algo_generate_node(state: MAPFState) -> Dict[str, Any]:
    use_llm = bool(state.get("use_llm", True))

    user_text = state.get("user_input") or ""
    if state.get("blocking_stage") == "algo_gen" and state.get("user_response"):
        user_text = f"{user_text}\n{state['user_response']}"

    map_json = _load_json_if_map(state.get("map_file_path") or "")
    agent = AlgorithmAgent()
    algo_cfg = agent.select(user_text, map_info=(map_json.get("map") if map_json else None), use_llm=use_llm) or {}

    # Contract: algo_code is a string. Store the selected config as JSON.
    algo_code = json.dumps(
        {
            "planner_type": algo_cfg.get("planner_type"),
            "scheduler_type": algo_cfg.get("scheduler_type"),
            "optimize": algo_cfg.get("optimize", False),
            "optimize_target": algo_cfg.get("optimize_target", ""),
            "max_iterations": algo_cfg.get("max_iterations", 3),
        },
        ensure_ascii=False,
    )

    return {
        "algo_spec": user_text,
        "algo_code": algo_code,
        "algo_ready": True,
        "blocking_stage": "",
        "user_response": "",
        "error": "",
    }


def _extract_optimize_target(text: str) -> str:
    t = (text or "").lower()
    if any(k in t for k in ("success", "成功率", "task success", "task success rate", "成功")):
        return "success_rate"
    if any(k in t for k in ("总步", "总步数", "步数", "sim_steps", "makespan", "总耗时")):
        return "total_steps"
    if any(k in t for k in ("冲突", "collision", "冲突次数", "conflict", "conflicts")):
        return "conflicts"
    return ""


def algo_optimize_node(state: MAPFState) -> Dict[str, Any]:
    use_llm = bool(state.get("use_llm", True))

    user_text = state.get("user_input") or ""
    if state.get("blocking_stage") == "algo_opt" and state.get("user_response"):
        user_text = f"{user_text}\n{state['user_response']}"

    algo_code_raw = state.get("algo_code") or ""
    algo_cfg: Dict[str, Any] = {}
    try:
        algo_cfg = json.loads(algo_code_raw) if algo_code_raw else {}
    except Exception:
        algo_cfg = {}

    optimize_target = str(algo_cfg.get("optimize_target") or "").strip() or _extract_optimize_target(user_text)
    if not optimize_target:
        return request_user_input("你想优化哪项指标？（例如：成功率、总步数、冲突次数……）", "algo_opt")

    # If metrics not available yet, keep current config and let simulation run.
    metrics = state.get("metrics") or {}
    if not metrics:
        return {"algo_spec": user_text, "blocking_stage": "", "user_response": "", "algo_ready": True}

    current_config = {
        "planner_type": algo_cfg.get("planner_type", getattr(SimConfig.planner_type, "value", SimConfig.planner_type)),
        "scheduler_type": algo_cfg.get("scheduler_type", getattr(SimConfig.scheduler_type, "value", SimConfig.scheduler_type)),
        "optimize_target": optimize_target,
    }
    suggestion = OptimizerAgent().suggest(metrics=metrics, current_config=current_config, history=None, use_llm=use_llm) or {}
    sugg = suggestion.get("suggestion") or {}

    action = sugg.get("action")
    sim_updates: Dict[str, Any] = {}
    new_planner = sugg.get("new_planner_type")
    new_scheduler = sugg.get("new_scheduler_type")

    if action == "change_algorithm":
        if new_planner:
            algo_cfg["planner_type"] = new_planner
        if new_scheduler:
            algo_cfg["scheduler_type"] = new_scheduler
    elif action == "adjust_params":
        sim_updates = sugg.get("param_changes", {}) or {}

    # Apply sim param updates (sim_config is a validated subset dict)
    next_sim_config = dict(state.get("sim_config") or {})
    if sim_updates:
        # Validate as delta updates (best-effort)
        validation = validate_sim_config_delta(sim_updates)
        if validation.get("ok", False):
            next_sim_config.update(validation.get("cleaned_delta", {}) or {})

    next_algo_code = json.dumps(
        {
            "planner_type": algo_cfg.get("planner_type"),
            "scheduler_type": algo_cfg.get("scheduler_type"),
            "optimize": True,
            "optimize_target": optimize_target,
            "max_iterations": algo_cfg.get("max_iterations", 3),
        },
        ensure_ascii=False,
    )

    return {
        "sim_config": next_sim_config,
        "algo_code": next_algo_code,
        "config_ready": True,
        "algo_ready": True,
        "blocking_stage": "",
        "user_response": "",
        "error": "",
    }


def simulation_node(state: MAPFState) -> Dict[str, Any]:
    map_file_path = (state.get("map_file_path") or "").strip()
    if not map_file_path or not os.path.isfile(map_file_path):
        return {"metrics": {}, "error": "缺少地图文件或地图路径无效。", "algo_ready": False}

    # Resolve algo config from algo_code (fallback to default)
    algo_cfg: Dict[str, Any] = {}
    algo_code_raw = (state.get("algo_code") or "").strip()
    if algo_code_raw:
        try:
            algo_cfg = json.loads(algo_code_raw) or {}
        except Exception:
            algo_cfg = {}

    if not algo_cfg.get("planner_type") or not algo_cfg.get("scheduler_type"):
        if state.get("algo_spec"):
            map_json = _load_json_if_map(map_file_path) or {}
            algo_cfg = AlgorithmAgent().select(
                state.get("algo_spec") or "",
                map_info=(map_json.get("map") if map_json else None),
                use_llm=bool(state.get("use_llm", True)),
            )
        else:
            algo_cfg = json.loads(_default_algo_code())

    # Resolve sim overrides
    sim_delta = state.get("sim_config") or {}
    validation = validate_sim_config_delta(sim_delta if isinstance(sim_delta, dict) else {})
    cleaned = validation.get("cleaned_delta", {}) if validation.get("ok", False) else (sim_delta if isinstance(sim_delta, dict) else {})

    sim_overrides = dict(cleaned or {})
    sim_overrides["planner_type"] = algo_cfg.get("planner_type")
    sim_overrides["scheduler_type"] = algo_cfg.get("scheduler_type")

    payload = build_runtime_meta_payload(map_file=map_file_path, sim_overrides=sim_overrides)
    env_config_path = save_env_runtime_meta_json(payload)
    apply_runtime_meta_to_sim_classes(env_config_path)

    out = run_simulation(num_runs=1)
    if out.get("ok"):
        return {"metrics": out.get("metrics", {}) or {}, "error": ""}
    return {"metrics": {}, "error": out.get("error", "Simulation failed")}


def result_node(state: MAPFState) -> Dict[str, Any]:
    metrics = state.get("metrics") or {}
    error = state.get("error") or ""

    if error:
        msg = f"仿真失败：{error}\n你想如何处理？（修改地图/换算法/继续优化/结束）"
    else:
        msg = f"仿真结果：{metrics}\n你想继续优化或修改吗？（继续优化/换算法/换地图/结束）"

    payload = {
        "question": msg,
        "pending_type": "result_decision",
        "metrics": metrics,
        "type": "result_decision",
    }
    decision = interrupt(payload)
    decision_str = str(decision).strip()

    return {
        "user_input": decision_str,
        "user_response": decision_str,
        "need_user_input": False,
        "pending_question": "",
        "blocking_stage": "",
        # Clear intents to avoid污染；下一轮 intent_parse_node 重新解析 decision_str
        "intent_generate_map": False,
        "intent_modify_config": False,
        "intent_generate_algo": False,
        "intent_optimize_algo": False,
        "intent_run_simulation": False,
    }


def build_graph() -> StateGraph:
    graph = StateGraph(MAPFState)

    # ======================
    # 节点注册
    # ======================
    graph.add_node("intent_parse", intent_parse_node)
    graph.add_node("router", router_node)

    graph.add_node("map_generate", map_generate_node)
    graph.add_node("config_update", config_update_node)

    graph.add_node("algo_generate", algo_generate_node)
    graph.add_node("algo_optimize", algo_optimize_node)

    graph.add_node("simulation", simulation_node)
    graph.add_node("result", result_node)

    graph.add_node("ask_user", _ask_user_node)

    # ======================
    # 主入口
    # ======================
    graph.set_entry_point("intent_parse")
    graph.add_edge("intent_parse", "router")

    # ======================
    # Router 分发
    # ======================
    graph.add_conditional_edges(
        "router",
        route_decision,
        {
            "map": "map_generate",
            "config": "config_update",
            "algo_gen": "algo_generate",
            "algo_opt": "algo_optimize",
            "run": "simulation",
            "end": END,
        },
    )

    # ======================
    # 每个阶段后插入“中断检测”
    # ======================
    def add_stage_flow(node_name: str, next_node: str) -> None:
        graph.add_conditional_edges(
            node_name,
            check_need_input,
            {
                "ask_user": "ask_user",
                "continue": next_node,
            },
        )

    add_stage_flow("map_generate", "config_update")
    add_stage_flow("config_update", "router")
    add_stage_flow("algo_generate", "simulation")
    add_stage_flow("algo_optimize", "simulation")

    # ======================
    # ask_user → 回 router
    # ======================
    graph.add_edge("ask_user", "router")

    # ======================
    # 仿真 → 结果
    # ======================
    graph.add_edge("simulation", "result")

    # ======================
    # 结果 → 下一轮
    # ======================
    graph.add_edge("result", "intent_parse")

    return graph


def _ask_user_node(state: MAPFState) -> Dict[str, Any]:
    question = state.get("pending_question") or ""
    stage_key = state.get("blocking_stage") or ""
    payload = {"question": question, "pending_type": stage_key, "type": "user_question"}
    answer = interrupt(payload)
    answer_str = str(answer).strip()
    return {
        "user_response": answer_str,
        "need_user_input": False,
    }

