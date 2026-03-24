import os
import json
from langgraph.types import interrupt
from typing import Any, Dict, List, Optional, TypedDict
from langgraph.graph import END, StateGraph
from mapf_agent.config import agent_config
from mapf_agent.llm import chat_completion_json
from mapf_agent.config import PROJECT_ROOT, PACKAGE_DIR
import time
from mapf_agent.tools.env_runtime_config_io import (
    apply_runtime_meta_to_sim_classes,
    build_runtime_meta_payload,
    save_env_runtime_meta_json,
)

class MAPFState(TypedDict, total=False):
    user_input: str

    map_intent_flag: bool
    map_intent_content: str

    sim_intent_flag: bool
    sim_intent_content: str

    algorithm_text: str

    algo_generate_flag: bool
    algo_generate_content: str

    algo_optimize_flag: bool
    algo_optimize_content: str
    # --- Global turn inputs ---
    user_input: str
    last_user_response: str
    conversation_history: List[Dict[str, Any]]

    # --- Routing (this turn) ---
    route: str  # "env_only" | "algorithm_only" | "both"
    map_text: str
    algorithm_text: str

    # --- Environment parsing/validation ---
    map_config: Dict[str, Any]
    sim_config_delta: Dict[str, Any]
    map_valid: bool
    env_ready: bool

    # --- Environment persistence ---
    map_output_path: str
    
    map_path: str
    map_json: Dict[str, Any]
    env_config_path: str

    # --- Algorithm routing/config ---
    algo_route: str  # "select" | "generate" | "optimize"
    algo_config: Dict[str, Any]
    algo_ready: bool

    # --- Simulation / optimization ---
    metrics: Dict[str, Any]
    pending_question: str
    pending_type: str  # "env_missing" | "sim_error" | "optimize_missing" | ...
    need_user_input: bool
    algo_code: str
    algo_attempts: int
    algo_history: List[Dict[str, Any]]
    optimization_history: List[Dict[str, Any]]
    iteration: int

    # --- Output / control ---
    output_path: str
    sim_config_path: str
    use_llm: bool
    error: str

    # --- Retry limits ---
    env_validation_attempts: int
    env_validation_max_attempts: int
    map_gen_attempts: int
    map_gen_max_attempts: int
    max_iterations: int
    metrics_ran: bool

    # --- Termination ---
    terminate: bool

def _append_history(state: MAPFState, role: str, content: str) -> List[Dict[str, Any]]:
    history = list(state.get("conversation_history") or [])
    if content:
        history.append({"role": role, "content": content})
    return history

def _abs_path(path: str) -> str:
    path = (path or "").strip()
    if not path:
        return ""
    if os.path.isabs(path):
        return path
    from mapf_agent.config import PROJECT_ROOT

    return os.path.normpath(os.path.join(PROJECT_ROOT, path))


def route_input(state: MAPFState) -> Dict[str, Any]:
    """检测用户输入的意图"""
    user_input = (state.get("user_input") or "").strip()

    if user_input.lower() in ("quit", "exit", "q", "stop", "end", "结束", "退出"):
        return {"terminate": True}
    
    def _as_bool(v: Any) -> bool:
        if isinstance(v, bool):
            return v
        if isinstance(v, (int, float)):
            return bool(v)
        if isinstance(v, str):
            s = v.strip().lower()
            return s in ("true", "t", "yes", "y", "1")
        return False

    def _pick_content(obj: Any) -> str:
        if isinstance(obj, str):
            return obj.strip()
        if obj is None:
            return ""
        return str(obj).strip()
    
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


def generate_map(state: MAPFState) -> Dict[str, Any]:
    """根据 map_config 生成 map_json 并落地到 map_path（可失败循环）。"""
    from mapf_agent.agents.map_builder import MapBuilder
    from mapf_agent.agents.map_config_parser import MapConfigParser
    from config.settings import SimConfig
    map_path = agent_config.map_path

    if state.get("map_intent_flag") and state.get("map_intent_content"):
        attempts = int(state.get("map_gen_attempts", 0)) + 1
        max_attempts = int(state.get("map_gen_max_attempts", 3))
        if attempts > max_attempts:
            return {
                "terminate": True,
                "error": "地图生成/校验失败次数超出上限。",
            }
        parser = MapConfigParser()
        parsed = parser.parse(state.get("map_intent_content"))
        if not parsed.get("complete", False):
            return {
                "need_user_input": True,
                "pending_type": "map_missing",
                "pending_question": parsed.get("follow_up_question", "请补充地图信息。"),
            }
        map_config = parsed.get("map_config", {}) or {}
        agent = MapBuilder()
        result = agent.generate(map_config)
        if not result.get("ok", False):
            return {"error": result.get("error", "Map generation failed"), "terminate": True}
        map_json = result["map_json"]

        map_output_path = (state.get("map_output_path") or "").strip()
        if map_output_path:
            map_path_out = _abs_path(map_output_path)
        else:
            map_dir = os.path.join(PACKAGE_DIR, "generated", "envs")
            os.makedirs(map_dir, exist_ok=True)
            ts = time.strftime("%Y%m%d_%H%M%S")
            map_path_out = os.path.join(map_dir, f"map_generated_{ts}_{attempts}.json")

        os.makedirs(os.path.dirname(map_path_out) or ".", exist_ok=True)
        with open(map_path_out, "w", encoding="utf-8") as f:
            json.dump(map_json, f, indent=2, ensure_ascii=False)

        return {
            "map_gen_attempts": attempts,
            "map_config": map_config,
            "map_json": map_json,
            "map_path": map_path_out,
        }

    # Default map: use current SimConfig.map_file.
    default_map = getattr(SimConfig, "map_file", "")
    default_path = _abs_path(str(default_map))
    if not default_path or not os.path.isfile(default_path):
        return {"terminate": True, "error": f"默认地图不存在：{default_path}"}

    with open(default_path, "r", encoding="utf-8") as f:
        map_json = json.load(f)

    return {"map_json": map_json, "map_path": default_path}


def sim_parse_validate_build(state: MAPFState) -> Dict[str, Any]:
    """将自然语言环境描述 -> map_config + sim_config_delta。"""
    from mapf_agent.agents.sim_config_delta_parser import SimConfigDeltaParserAgent
    from mapf_agent.tools.sim_config_validator import validate_sim_config_delta

    sim_config_delta: Dict[str, Any] = {}
    if state.get("sim_intent_flag"):
        parser = SimConfigDeltaParserAgent()
        sim_text = state.get("sim_intent_content") or ""
        sim_config_delta = parser.parse(sim_text) or {}
    validation = validate_sim_config_delta(sim_config_delta)
    if not validation.get("ok", False):
        return {
            "need_user_input": True,
            "pending_type": "sim_error",
            "pending_question": validation.get("pending_question", "仿真配置有误，请按提示修正。"),
        }
    
    sim_output_dir = os.path.join(PACKAGE_DIR, "generated", "envs")
    os.makedirs(sim_output_dir, exist_ok=True)
    ts = time.strftime("%Y%m%d_%H%M%S")
    sim_config_path = os.path.join(sim_output_dir, f"sim_config_{ts}.json")

    cleaned_delta = validation.get("cleaned_delta", {}) or {}
    payload = build_runtime_meta_payload(map_file=state.get("map_path"), sim_overrides=cleaned_delta)
    env_config_path = save_env_runtime_meta_json(payload)
    apply_runtime_meta_to_sim_classes(env_config_path)
    return {
        "sim_config_delta": cleaned_delta,
        "env_config_path": env_config_path,
        "need_user_input": False,
    }

