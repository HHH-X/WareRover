import os
import json
from langgraph.types import interrupt
from typing import Any, Dict, List, Optional, TypedDict
from langgraph.graph import END, StateGraph
from mapf_agent.config import agent_config
from mapf_agent.llm import chat_completion_json

class MAPFState(TypedDict, total=False):
    user_input: str

    intent_generate_map: bool
    intent_generate_map_content: Optional[str]

    intent_modify_simconfig: bool
    intent_modify_simconfig_content: Optional[str]

    intent_generate_algorithm: bool
    intent_generate_algorithm_content: Optional[str]

    intent_optimize_algorithm: bool
    intent_optimize_algorithm_content: Optional[str]

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

def route_input(state: MAPFState) -> Dict[str, Any]:
    """检测用户输入的意图"""
    user_input = (state.get("user_input") or "").strip()

    if user_input.lower() in ("quit", "exit", "q", "stop", "end", "结束", "退出"):
        return {"terminate": True}
    
    prompt_path = os.path.join(agent_config.prompts_dir, "intent_parser.txt")
    with open(prompt_path, "r", encoding="utf-8") as f:
        system_prompt = f.read()

    result = chat_completion_json(
        [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_input},
        ]
    )
    intent_map = {
        "intent_generate_map": result.get("intent_generate_map", "").strip().lower() == "true",
        "intent_generate_map_content": result.get("intent_generate_map_content", "").strip(),
        "intent_modify_simconfig": result.get("intent_modify_simconfig", "").strip().lower() == "true",
        "intent_modify_simconfig_content": result.get("intent_modify_simconfig_content", "").strip(),
        "intent_generate_algorithm": result.get("intent_generate_algorithm", "").strip().lower() == "true",
        "intent_generate_algorithm_content": result.get("intent_generate_algorithm_content", "").strip(),
        "intent_optimize_algorithm": result.get("intent_optimize_algorithm", "").strip().lower() == "true",
        "intent_optimize_algorithm_content": result.get("intent_optimize_algorithm_content", "").strip(),
    }
    return intent_map


def _after_route_input(state: MAPFState) -> str:

    if state.get("intent_generate_map"):
        return "env_only"

def env_parse(state: MAPFState) -> Dict[str, Any]:
    """将自然语言环境描述 -> map_config + sim_config_delta。"""
    from mapf_agent.agents.input_parser import InputParserAgent

    text = (state.get("map_text") or "").strip()
    if not text:
        return {"map_config": {}, "sim_config_delta": {}, "env_ready": False}

    parser = InputParserAgent()
    use_llm = bool(state.get("use_llm", True))
    parsed = parser.parse(text, use_llm=use_llm)

    return {
        "map_config": parsed.get("map_config", {}) or {},
        # InputParserAgent puts sim fields under sim_config as "sim_config"
        "sim_config_delta": parsed.get("sim_config", {}) or parsed.get("sim_config_delta", {}) or {},
        "env_ready": False,
    }
