
# ---------------------------------------------------------------------------
# Interrupt/Resume rewrite (your node document)
# ---------------------------------------------------------------------------
import os
import json
import time
from langgraph.types import interrupt
from typing import Any, Dict, List, Optional, TypedDict
from langgraph.graph import END, StateGraph

class MAPFState(TypedDict, total=False):
    # --- Global turn inputs ---
    user_input: str
    last_user_response: str
    conversation_history: List[Dict[str, Any]]

    # --- Intent parsing (this turn) ---
    map_intent_flag: bool
    map_intent_content: str

    sim_intent_flag: bool
    sim_intent_content: str

    algorithm_text: str

    algo_generate_flag: bool
    algo_generate_content: str

    algo_optimize_flag: bool
    algo_optimize_content: str

    # --- Map config (stage1) ---
    map_config: Dict[str, Any]
    map_valid: bool

    # --- Environment persistence ---
    map_path: str
    map_json: Dict[str, Any]
    env_config_path: str
    sim_config_delta: Dict[str, Any]

    # --- Algorithm routing/config ---
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


def route_input(state: MAPFState) -> Dict[str, Any]:
    """四意向解析：地图/改配置/生成算法/优化算法。"""
    user_input = (state.get("user_input") or "").strip()

    if user_input.lower() in ("quit", "exit", "q", "stop", "end", "结束", "退出"):
        return {"terminate": True}

    use_llm = bool(state.get("use_llm", True))
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

    if use_llm:
        try:
            from mapf_agent.llm import chat_completion_json
            from mapf_agent.config import agent_config

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
        except Exception:
            # Fallback to keyword heuristics below.
            pass

    if not (map_intent_flag or sim_intent_flag or algo_generate_flag or algo_optimize_flag):
        # Heuristic fallback (helps when LLM is disabled or fails).
        text_lower = user_input.lower()
        map_intent_flag = any(k in text_lower for k in ("地图", "map", "仓库", "warehouse", "货架", "shelf", "agv", "receiver", "obstacle"))
        sim_intent_flag = any(
            k in text_lower
            for k in (
                "配置",
                "config",
                "sim",
                "speed",
                "max_steps",
                "time_step",
                "timeout",
                "订单",
                "order",
                "log",
                "planner_type",
                "scheduler_type",
                "force_replan",
            )
        )
        algo_generate_flag = any(k in text_lower for k in ("生成算法", "generate algorithm", "新算法", "实现算法", "代码", "planner", "scheduler", "cbs", "astar", "dhc"))
        algo_optimize_flag = any(k in text_lower for k in ("优化", "optimize", "reduce conflict", "冲突", "迭代", "performance", "success rate", "成功率"))

    # If a flag is true but content is empty, fall back to the whole user_input.
    if map_intent_flag and not map_intent_content:
        map_intent_content = user_input
    if sim_intent_flag and not sim_intent_content:
        sim_intent_content = user_input
    if algo_generate_flag and not algo_generate_content:
        algo_generate_content = user_input
    if algo_optimize_flag and not algo_optimize_content:
        algo_optimize_content = user_input

    parts = [p for p in (algo_generate_content, algo_optimize_content) if p]
    algorithm_text = "\n".join(parts).strip()

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
        "algorithm_text": algorithm_text,
        "conversation_history": history,
        "pending_question": "",
        "pending_type": "",
        "need_user_input": False,
    }


def env_parse(state: MAPFState) -> Dict[str, Any]:
    """将自然语言环境描述 -> map_config + sim_config_delta。"""
    from mapf_agent.agents.map_config_parser import InputParserAgent

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


def env_validate(state: MAPFState) -> Dict[str, Any]:
    """校验 map_config + sim_config_delta；不通过时填 pending_question。"""
    from mapf_agent.tools.sim_config_validator import validate_sim_config_delta

    attempts = int(state.get("env_validation_attempts", 0)) + 1
    max_attempts = int(state.get("env_validation_max_attempts", 5))

    map_config = state.get("map_config") or {}
    sim_delta = state.get("sim_config_delta") or {}

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
            return {
                "env_validation_attempts": attempts,
                "error": "地图信息补全次数超出上限。",
                "need_user_input": False,
                "terminate": True,
            }
        return {
            "env_validation_attempts": attempts,
            "pending_type": "env_missing",
            "pending_question": f"请补充地图配置信息：{', '.join(missing)}。",
            "need_user_input": True,
            "env_ready": False,
        }

    sim_validation = validate_sim_config_delta(sim_delta)
    if not sim_validation.get("ok", False):
        if attempts > max_attempts:
            return {
                "env_validation_attempts": attempts,
                "error": "仿真配置修正次数超出上限。",
                "need_user_input": False,
                "terminate": True,
            }
        return {
            "env_validation_attempts": attempts,
            "pending_type": "sim_error",
            "pending_question": sim_validation.get("pending_question", "仿真配置有误，请按提示修正。"),
            "need_user_input": True,
            "env_ready": False,
        }

    return {
        "env_validation_attempts": attempts,
        "env_ready": True,
        "need_user_input": False,
        "pending_question": "",
        "pending_type": "",
        "sim_config_delta": sim_validation.get("cleaned_delta", {}) or {},
    }


def wait_for_human(state: MAPFState) -> Dict[str, Any]:
    """中断点：将 pending_question 抛给用户。"""
    payload = {
        "question": state.get("pending_question", ""),
        "pending_type": state.get("pending_type", ""),
        "type": "user_question",
    }
    answer = interrupt(payload)
    answer_str = str(answer).strip()
    return {"last_user_response": answer_str, "need_user_input": False}


def handle_user_response(state: MAPFState) -> Dict[str, Any]:
    """把用户补充内容回填到对应意向文本，并清理 pending 状态。"""
    resp = (state.get("last_user_response") or "").strip()
    ptype = (state.get("pending_type") or "").strip()

    map_intent_content = state.get("map_intent_content") or ""
    sim_intent_content = state.get("sim_intent_content") or ""
    algorithm_text = state.get("algorithm_text") or ""

    if ptype in ("map_missing", "map_info_missing"):
        if resp:
            map_intent_content = f"{map_intent_content}\n{resp}".strip()
    elif ptype in ("sim_missing", "sim_error"):
        if resp:
            sim_intent_content = f"{sim_intent_content}\n{resp}".strip()
    elif ptype in ("optimize_missing", "optimize_target_missing"):
        if resp:
            algorithm_text = f"{algorithm_text}\n{resp}".strip()
    else:
        # 保守兜底：默认补到地图意向文本里。
        if resp:
            map_intent_content = f"{map_intent_content}\n{resp}".strip()

    return {
        "map_intent_content": map_intent_content,
        "sim_intent_content": sim_intent_content,
        "algorithm_text": algorithm_text,
        "pending_question": "",
        "need_user_input": False,
    }


def _abs_path(path: str) -> str:
    path = (path or "").strip()
    if not path:
        return ""
    if os.path.isabs(path):
        return path
    from mapf_agent.config import PROJECT_ROOT

    return os.path.normpath(os.path.join(PROJECT_ROOT, path))


def resolve_map_source(state: MAPFState) -> Dict[str, Any]:
    """
    Stage1：仅生成/加载 map_json + 落盘 map_path。

    - 若用户给了 `map_path`：直接加载。
    - 否则若有 `map_intent_content`：用 InputParserAgent + EnvConfigAgent 生成并保存。
    - 否则用默认 `SimConfig.map_file`。
    """
    from mapf_agent.agents.map_builder import MapBuilder
    from mapf_agent.agents.map_config_parser import InputParserAgent
    from config.settings import SimConfig
    from mapf_agent.config import PROJECT_ROOT

    map_path = _abs_path(state.get("map_path") or "")
    map_valid_value = state.get("map_valid")

    # If previous stage1 map validation failed and we have map intent, regenerate from NL.
    # Only retry regeneration after we have explicitly failed validation.
    if state.get("map_intent_flag") and map_valid_value is False:
        map_path = ""

    if map_path and os.path.isfile(map_path):
        with open(map_path, "r", encoding="utf-8") as f:
            map_json = json.load(f)
        return {"map_json": map_json, "map_path": map_path}

    use_llm = bool(state.get("use_llm", True))
    map_intent_flag = bool(state.get("map_intent_flag"))
    map_intent_content = state.get("map_intent_content") or ""

    if map_intent_flag and map_intent_content.strip():
        attempts = int(state.get("map_gen_attempts", 0)) + 1
        max_attempts = int(state.get("map_gen_max_attempts", 3))
        if attempts > max_attempts:
            return {
                "terminate": True,
                "error": "地图生成/校验失败次数超出上限。",
            }

        parser = InputParserAgent()
        if use_llm:
            parsed = parser.parse(map_intent_content)
        else:
            parsed = parser._parse_regex(map_intent_content)

        if not parsed.get("complete", False):
            return {
                "need_user_input": True,
                "pending_type": "map_missing",
                "pending_question": parsed.get("follow_up_question", "请补充地图信息。"),
            }

        map_config = parsed.get("map_config", {}) or {}
        agent = MapBuilder()
        result = agent.generate(map_config, use_llm=use_llm)
        if not result.get("ok", False):
            return {"error": result.get("error", "Map generation failed"), "terminate": True}

        map_json = result["map_json"]

        out_override = (state.get("output_path") or "").strip()
        if out_override:
            map_path_out = _abs_path(out_override)
        else:
            map_dir = os.path.join(PROJECT_ROOT, "config", "maps", "generated")
            os.makedirs(map_dir, exist_ok=True)
            ts = time.strftime("%Y%m%d_%H%M%S")
            map_path_out = os.path.join(map_dir, f"map_user_{ts}_{attempts}.json")

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

    # NOTE: stage1 不强制落盘 map_path（否则会污染文件）；只在需要时更新 map_path。
    return {"map_json": map_json, "map_path": default_path}


def sim_parse_validate_build(state: MAPFState) -> Dict[str, Any]:
    """
    Stage2：解析/验证 modify_sim_config 意向并保存 runtime_meta，覆盖内存 SimConfig。
    """
    from mapf_agent.tools.env_runtime_config_io import (
        apply_runtime_meta_to_sim_classes,
        build_runtime_meta_payload,
        save_env_runtime_meta_json,
    )
    from mapf_agent.agents.sim_config_delta_parser import SimConfigDeltaParserAgent
    from mapf_agent.tools.sim_config_validator import validate_sim_config_delta

    map_path = _abs_path(state.get("map_path") or "")
    if not map_path or not os.path.isfile(map_path):
        return {"terminate": True, "error": "map_path 不存在，无法生成 runtime_meta。"}

    sim_config_delta: Dict[str, Any] = {}
    if state.get("sim_intent_flag"):
        use_llm = bool(state.get("use_llm", True))
        parser = SimConfigDeltaParserAgent()
        sim_text = state.get("sim_intent_content") or ""
        sim_config_delta = parser.parse(sim_text, use_llm=use_llm) or {}

    validation = validate_sim_config_delta(sim_config_delta)
    if not validation.get("ok", False):
        return {
            "need_user_input": True,
            "pending_type": "sim_error",
            "pending_question": validation.get("pending_question", "仿真配置有误，请按提示修正。"),
        }

    cleaned_delta = validation.get("cleaned_delta", {}) or {}
    payload = build_runtime_meta_payload(map_file=map_path, sim_overrides=cleaned_delta)
    env_config_path = save_env_runtime_meta_json(payload)
    apply_runtime_meta_to_sim_classes(env_config_path)
    return {
        "sim_config_delta": cleaned_delta,
        "env_config_path": env_config_path,
        "need_user_input": False,
    }


def _after_resolve_map_source(state: MAPFState) -> str:
    if state.get("terminate"):
        return "end"
    if state.get("need_user_input"):
        return "wait_for_human"
    return "map_validate"


def _after_stage1_map_validate(state: MAPFState) -> str:
    if state.get("terminate"):
        return "end"
    if state.get("map_valid"):
        return "sim_parse_validate_build"
    # Retry only when we generated from NL.
    if state.get("map_intent_flag") and int(state.get("map_gen_attempts", 0)) < int(state.get("map_gen_max_attempts", 3)):
        return "resolve_map_source"
    return "end"


def _after_stage2(state: MAPFState) -> str:
    if state.get("terminate"):
        return "end"
    if state.get("need_user_input"):
        return "wait_for_human"
    if state.get("algo_optimize_flag"):
        return "optimize_validate"
    if state.get("algo_generate_flag"):
        return "algo_generate_loop"
    # Only map/config stage: ask user whether to run algorithms.
    return "result_interrupt"


def _after_handle_user_response_stage12(state: MAPFState) -> str:
    ptype = (state.get("pending_type") or "").strip()
    if ptype in ("map_missing", "map_info_missing"):
        return "resolve_map_source"
    if ptype in ("sim_missing", "sim_error"):
        return "sim_parse_validate_build"
    if ptype in ("optimize_missing", "optimize_target_missing"):
        return "optimize_validate"
    return "resolve_map_source"


def map_generate(state: MAPFState) -> Dict[str, Any]:
    """根据 map_config 生成 map_json 并落地到 map_path（可失败循环）。"""
    from mapf_agent.agents.map_builder import MapBuilder

    attempts = int(state.get("map_gen_attempts", 0)) + 1
    max_attempts = int(state.get("map_gen_max_attempts", 3))

    if attempts > max_attempts:
        return {"error": "地图生成/校验失败次数超出上限。", "map_gen_attempts": attempts, "terminate": True}

    agent = MapBuilder()
    use_llm = bool(state.get("use_llm", True))

    result = agent.generate(state.get("map_config", {}) or {}, use_llm=use_llm)
    if not result.get("ok", False):
        return {"error": result.get("error", "Map generation failed"), "map_gen_attempts": attempts}

    map_json = result["map_json"]

    out_override = (state.get("output_path") or "").strip()
    if not out_override:
        dirs = _project_dirs()
        _ensure_dir(dirs["map_dir"])
        ts = time.strftime("%Y%m%d_%H%M%S")
        out_override = os.path.join(dirs["map_dir"], f"map_user_{ts}_{attempts}.json")

    map_path = out_override
    os.makedirs(os.path.dirname(map_path) or ".", exist_ok=True)
    with open(map_path, "w", encoding="utf-8") as f:
        json.dump(map_json, f, indent=2, ensure_ascii=False)

    return {"map_gen_attempts": attempts, "map_json": map_json, "map_path": map_path}


def map_validate(state: MAPFState) -> Dict[str, Any]:
    """校验 map_json 是否符合 schema + 语义约束。"""
    from mapf_agent.tools.validate_map import validate_map

    map_json = state.get("map_json") or {}
    trial_steps = 0
    res = validate_map(map_json, trial_steps=trial_steps)
    if not res.get("ok", False):
        return {"error": res.get("error", "Map validation failed"), "map_valid": False}

    return {"map_valid": True, "error": ""}


def env_build(state: MAPFState) -> Dict[str, Any]:
    """将 map_json 写入文件并生成 env_runtime_json（env_config_path）。"""
    from mapf_agent.tools.env_runtime_config_io import (
        apply_runtime_meta_to_sim_classes,
        build_runtime_meta_payload,
        save_env_runtime_meta_json,
    )

    map_path = (state.get("map_path") or "").strip()
    if not map_path or not os.path.isfile(map_path):
        return {"error": "地图文件不存在，无法生成环境参数 JSON。", "env_ready": False}

    payload = build_runtime_meta_payload(map_file=map_path, sim_overrides=state.get("sim_config_delta") or {})
    out_path = save_env_runtime_meta_json(payload)
    apply_runtime_meta_to_sim_classes(out_path)

    return {"env_ready": True, "env_config_path": out_path}


def algo_route(state: MAPFState) -> Dict[str, Any]:
    """判断算法意图：select / generate / optimize。"""
    text = (state.get("algorithm_text") or "").lower()

    route = "select"
    if any(k in text for k in ("优化", "optimize", "演化", "迭代", "evolution")):
        route = "optimize"
    elif any(k in text for k in ("生成", "新算法", "实现", "code", "planner", "scheduler", "代码")) and any(
        k in text for k in ("算法", "algorithm")
    ):
        route = "generate"

    # prerequisites: algorithm stage needs env_config_path/map_path
    if route != "select" and route != "optimize" and route != "generate":
        route = "select"

    if not (state.get("env_config_path") or "").strip() and not (state.get("map_path") or "").strip():
        # algorithm-only (or both) but no env yet -> ask user for env.
        return {
            "algo_route": route,
            "need_user_input": True,
            "pending_type": "env_missing",
            "pending_question": "要运行算法/仿真需要地图环境。请补充地图描述或提供环境信息。",
        }

    # For resume safety, don't overwrite existing algo_config here.
    return {"algo_route": route}


def _ensure_env_runtime(state: MAPFState) -> Dict[str, Any]:
    """If env_config_path is missing but map_path exists, build runtime_meta on demand."""
    from mapf_agent.tools.env_runtime_config_io import (
        apply_runtime_meta_to_sim_classes,
        build_runtime_meta_payload,
        save_env_runtime_meta_json,
    )

    if state.get("env_config_path"):
        return {}

    map_path = (state.get("map_path") or "").strip()
    if not map_path or not os.path.isfile(map_path):
        return {"error": "algorithm stage requires a valid map_path."}

    payload = build_runtime_meta_payload(map_file=map_path, sim_overrides=state.get("sim_config_delta") or {})
    out_path = save_env_runtime_meta_json(payload)
    apply_runtime_meta_to_sim_classes(out_path)
    return {"env_config_path": out_path, "env_ready": True}


def algo_select(state: MAPFState) -> Dict[str, Any]:
    """从算法 NL 中选择 planner/scheduler，并写入 env_runtime + SimConfig。"""
    from config.settings import PlannerType, SchedulerType
    from config.settings import SimConfig
    from mapf_agent.agents.algorithm_agent import AlgorithmAgent
    from mapf_agent.tools.env_runtime_config_io import update_env_runtime_meta_sim

    env_up = _ensure_env_runtime(state)
    if env_up.get("error"):
        return env_up
    env_config_path = env_up.get("env_config_path") or state.get("env_config_path") or ""

    agent = AlgorithmAgent()
    use_llm = bool(state.get("use_llm", True))
    nl = state.get("algorithm_text") or ""

    map_info = (state.get("map_json") or {}).get("map") if state.get("map_json") else None
    result = agent.select(nl, map_info=map_info, use_llm=use_llm)
    algo_cfg = result or {}

    if env_config_path and os.path.isfile(env_config_path):
        update_env_runtime_meta_sim(
            env_runtime_json_path=env_config_path,
            sim_updates={
                "planner_type": algo_cfg.get("planner_type"),
                "scheduler_type": algo_cfg.get("scheduler_type"),
            },
        )

    return {"algo_config": algo_cfg, "algo_ready": True, "max_iterations": int(algo_cfg.get("max_iterations", 3))}


def algo_generate_loop(state: MAPFState) -> Dict[str, Any]:
    """
    "生成新算法" 的落地：仓库当前不支持真正 codegen planner/scheduler。
    这里实现可扩展的尝试/回退策略：从现有算法推断 baseline，然后尝试候选 planners 做快速验证。
    """
    from mapf_agent.config import agent_config
    from mapf_agent.agents.algorithm_codegen_agent import AlgorithmCodegenAgent
    from mapf_agent.tools.run_simulation import run_simulation

    env_up = _ensure_env_runtime(state)
    if env_up.get("error"):
        return env_up

    baseline = algo_select(state)
    algo_cfg = baseline.get("algo_config") or {}
    map_path = (state.get("map_path") or "").strip()

    if not map_path:
        return {
            "algo_ready": False,
            "algo_history": state.get("algo_history") or [],
            "metrics": {},
            "metrics_ran": True,
            "error": "没有可用于仿真的地图文件。",
        }

    codegen_agent = AlgorithmCodegenAgent()
    plan_preview = codegen_agent.propose_code_changes(
        state.get("algorithm_text") or "",
        map_info=(state.get("map_json") or {}).get("map") if state.get("map_json") else None,
    )

    gen_history: List[Dict[str, Any]] = list(state.get("algo_history") or [])
    algo_attempts = int(state.get("algo_attempts", 0))
    scheduler = algo_cfg.get("scheduler_type")
    try_planners = codegen_agent.get_planner_candidates(algo_cfg.get("planner_type"))

    max_gen_attempts = int(state.get("max_iterations", 3))
    last_err: Optional[str] = None

    for planner in try_planners:
        if algo_attempts >= max_gen_attempts:
            break
        algo_attempts += 1

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
                    "attempt": algo_attempts,
                    "planner_type": planner,
                    "scheduler_type": scheduler,
                    "ok": True,
                }
            )
            return {
                "algo_code": plan_preview,
                "algo_history": gen_history,
                "algo_attempts": algo_attempts,
                "algo_ready": True,
                "metrics": sim_result.get("metrics", {}) or {},
                "metrics_ran": True,
                "optimization_history": state.get("optimization_history") or [],
                "error": "",
            }

        last_err = sim_result.get("error", "Simulation failed")
        gen_history.append(
            {
                "attempt": algo_attempts,
                "planner_type": planner,
                "scheduler_type": scheduler,
                "ok": False,
                "error": last_err,
            }
        )

    return {
        "algo_code": plan_preview,
        "algo_history": gen_history,
        "algo_attempts": algo_attempts,
        "algo_ready": False,
        "metrics": {},
        "metrics_ran": True,
        "error": last_err or "Simulation failed",
    }


def _extract_optimize_target(text: str) -> str:
    t = text.lower()
    if any(k in t for k in ("成功率", "success", "task success", "task success rate")):
        return "success_rate"
    if any(k in t for k in ("总步", "总步数", "步数", "sim_steps", "makespan", "总耗时")):
        return "total_steps"
    if any(k in t for k in ("冲突", "collision", "冲突次数", "conflict")):
        return "conflicts"
    return ""


def optimize_validate(state: MAPFState) -> Dict[str, Any]:
    """检查优化目标是否明确；缺失则 interrupt。"""
    # Ensure algo_config exists.
    algo_cfg = state.get("algo_config") or {}
    if not algo_cfg:
        sel = algo_select(state)
        algo_cfg = sel.get("algo_config") or {}

    # If user didn't ask for optimize, just proceed (tolerant).
    # We'll rely on algo_cfg["optimize"] if present.
    algo_cfg_optimize = bool(algo_cfg.get("optimize", True))

    optimize_target = str(algo_cfg.get("optimize_target") or "").strip()
    if not optimize_target:
        optimize_target = _extract_optimize_target(state.get("algorithm_text") or "")

    if not optimize_target:
        return {
            "pending_type": "optimize_missing",
            "pending_question": "你想优化哪项指标？（例如：成功率、总步数、冲突次数……）",
            "need_user_input": True,
            "algo_config": {**algo_cfg, "optimize": algo_cfg_optimize, "optimize_target": ""},
        }

    algo_cfg["optimize"] = algo_cfg_optimize
    algo_cfg["optimize_target"] = optimize_target
    return {"algo_config": algo_cfg, "algo_ready": True, "need_user_input": False, "pending_question": "", "pending_type": ""}


def optimize_loop(state: MAPFState) -> Dict[str, Any]:
    """基于 metrics + optimization_history 给出一次迭代改进（然后进入 run_simulation）。"""
    from mapf_agent.agents.optimizer_agent import OptimizerAgent
    from mapf_agent.tools.env_runtime_config_io import update_env_runtime_meta_sim
    import os as _os

    history = list(state.get("optimization_history") or [])
    iteration = int(state.get("iteration", 0))
    algo_cfg = state.get("algo_config") or {}

    # First run (no metrics yet) => just prepare and let run_simulation produce metrics.
    if not state.get("metrics_ran") or not state.get("metrics"):
        return {"iteration": iteration, "algo_config": algo_cfg}

    agent = OptimizerAgent()
    use_llm = bool(state.get("use_llm", True))
    current_config = {
        "planner_type": algo_cfg.get("planner_type", "astar"),
        "scheduler_type": algo_cfg.get("scheduler_type", "ta"),
        "optimize_target": algo_cfg.get("optimize_target", ""),
    }

    iteration += 1
    result = agent.suggest(state.get("metrics") or {}, current_config, history, use_llm=use_llm)
    suggestion = result.get("suggestion", {}) or {}

    # Apply suggestion to algo_config / SimConfig.
    env_config_path = _abs_path(state.get("env_config_path") or "")
    sim_updates: Dict[str, Any] = {}
    if suggestion.get("action") == "change_algorithm":
        if suggestion.get("new_planner_type"):
            algo_cfg["planner_type"] = suggestion["new_planner_type"]
            sim_updates["planner_type"] = suggestion["new_planner_type"]
        if suggestion.get("new_scheduler_type"):
            algo_cfg["scheduler_type"] = suggestion["new_scheduler_type"]
            sim_updates["scheduler_type"] = suggestion["new_scheduler_type"]
    elif suggestion.get("action") == "adjust_params":
        param_changes = suggestion.get("param_changes", {}) or {}
        if param_changes.get("max_steps") is not None:
            from config.settings import SimConfig

            SimConfig.max_steps = int(param_changes["max_steps"])
            sim_updates["max_steps"] = int(param_changes["max_steps"])

    history.append(
        {
            "iteration": iteration,
            "planner_type": algo_cfg.get("planner_type"),
            "scheduler_type": algo_cfg.get("scheduler_type"),
            "metrics": state.get("metrics") or {},
            "suggestion": suggestion,
        }
    )

    # Update in-memory SimConfig now; env runtime meta will be updated later on next algo_select if needed.
    from config.settings import PlannerType, SchedulerType, SimConfig

    try:
        if algo_cfg.get("planner_type") is not None:
            SimConfig.planner_type = PlannerType(algo_cfg["planner_type"])
        if algo_cfg.get("scheduler_type") is not None:
            SimConfig.scheduler_type = SchedulerType(algo_cfg["scheduler_type"])
    except Exception:
        pass

    # Persist to runtime_meta so the next run_simulation picks up the new config.
    if sim_updates and env_config_path and _os.path.isfile(env_config_path):
        update_env_runtime_meta_sim(env_runtime_json_path=env_config_path, sim_updates=sim_updates)

    return {
        "algo_config": algo_cfg,
        "optimization_history": history,
        "iteration": iteration,
        "need_user_input": False,
        "pending_question": "",
        "pending_type": "",
    }


def run_simulation(state: MAPFState) -> Dict[str, Any]:
    """调用仿真引擎执行一次实验并填 metrics。"""
    if state.get("metrics_ran") and state.get("metrics") is not None:
        return {}

    from mapf_agent.config import agent_config
    from mapf_agent.tools.run_simulation import run_simulation as sim_run
    from mapf_agent.tools.env_runtime_config_io import (
        apply_runtime_meta_to_sim_classes,
    )

    algo_cfg = state.get("algo_config") or {}
    map_path = (state.get("map_path") or "").strip()
    if not map_path:
        return {"error": "No map file available for simulation", "metrics": {}, "metrics_ran": False}

    env_config_path = _abs_path(state.get("env_config_path") or "")
    if not env_config_path or not os.path.isfile(env_config_path):
        return {"error": "env_config_path 不存在，无法应用 runtime_meta。", "metrics": {}, "metrics_ran": False}

    apply_runtime_meta_to_sim_classes(env_config_path)
    result = sim_run(
        num_runs=1,
    )

    if result.get("ok"):
        return {"metrics": result.get("metrics", {}) or {}, "metrics_ran": True, "error": ""}
    return {"metrics": {}, "metrics_ran": True, "error": result.get("error", "Simulation failed")}


def result_interrupt(state: MAPFState) -> Dict[str, Any]:
    """结果展示 + 决策中断。resume 后把输入重新作为下一轮 user_input。"""
    metrics = state.get("metrics") or {}
    has_error = bool(state.get("error"))
    if has_error and not metrics:
        msg = "仿真失败。你想如何处理？（例如：修改地图/换算法/结束）"
    elif metrics:
        msg = "仿真已完成。是否继续优化或修改？（继续优化/换算法/换地图/结束）"
    else:
        msg = "环境/地图已就绪。是否要继续运行算法？（提供算法需求/结束）"

    payload = {
        "type": "result_decision",
        "metrics": metrics,
        "message": msg,
    }
    decision = interrupt(payload)
    decision_str = str(decision).strip()

    # Route_input will interpret decision_str (including "结束"/"exit").
    return {"user_input": decision_str, "last_user_response": decision_str}


def _after_route_input(state: MAPFState) -> str:
    if state.get("terminate"):
        return "end"
    route = state.get("route") or "env_only"
    if route == "algorithm_only":
        return "algo_route"
    if route == "both":
        return "env_parse"
    return "env_parse"


def _after_env_validate(state: MAPFState) -> str:
    if state.get("terminate"):
        return "end"
    if state.get("need_user_input"):
        return "wait_for_human"
    return "map_generate"


def _after_map_validate(state: MAPFState) -> str:
    if state.get("terminate"):
        return "end"
    if state.get("map_valid"):
        return "env_build"
    # Retry map generation by returning to map_generate
    return "map_generate"


def _after_env_build(state: MAPFState) -> str:
    if (state.get("route") or "env_only") == "env_only":
        return "result_interrupt"
    return "algo_route"


def _after_algo_route(state: MAPFState) -> str:
    if state.get("need_user_input"):
        return "wait_for_human"
    ar = state.get("algo_route") or "select"
    if ar == "generate":
        return "algo_generate_loop"
    if ar == "optimize":
        return "optimize_validate"
    return "algo_select"


def _after_handle_user_response(state: MAPFState) -> str:
    ptype = (state.get("pending_type") or "").strip()
    if ptype in ("env_missing", "sim_error"):
        return "env_parse"
    if ptype in ("optimize_missing", "optimize_target_missing"):
        return "optimize_validate"
    return "env_parse"


def _after_optimize_validate(state: MAPFState) -> str:
    if state.get("need_user_input"):
        return "wait_for_human"
    return "optimize_loop"


def build_graph() -> StateGraph:
    """Construct the LangGraph StateGraph for interrupt/resume workflow."""
    graph = StateGraph(MAPFState)
    graph.set_entry_point("route_input")

    graph.add_node("route_input", route_input)
    graph.add_node("resolve_map_source", resolve_map_source)
    graph.add_node("wait_for_human", wait_for_human)
    graph.add_node("handle_user_response", handle_user_response)
    graph.add_node("map_validate", map_validate)
    graph.add_node("sim_parse_validate_build", sim_parse_validate_build)
    graph.add_node("algo_select", algo_select)
    graph.add_node("algo_generate_loop", algo_generate_loop)
    graph.add_node("optimize_validate", optimize_validate)
    graph.add_node("optimize_loop", optimize_loop)
    graph.add_node("run_simulation", run_simulation)
    graph.add_node("result_interrupt", result_interrupt)

    # --- Stage1: map ---
    graph.add_conditional_edges("route_input", _after_resolve_map_source, {"end": END, "wait_for_human": "wait_for_human", "map_validate": "map_validate"})
    graph.add_edge("wait_for_human", "handle_user_response")

    graph.add_conditional_edges("handle_user_response", _after_handle_user_response_stage12, {"resolve_map_source": "resolve_map_source", "sim_parse_validate_build": "sim_parse_validate_build", "optimize_validate": "optimize_validate"})

    graph.add_conditional_edges("resolve_map_source", _after_resolve_map_source, {"wait_for_human": "wait_for_human", "map_validate": "map_validate", "end": END})
    graph.add_conditional_edges(
        "sim_parse_validate_build",
        _after_stage2,
        {
            "end": END,
            "wait_for_human": "wait_for_human",
            "optimize_validate": "optimize_validate",
            "algo_generate_loop": "algo_generate_loop",
            "result_interrupt": "result_interrupt",
        },
    )

    # Stage1 map validation retry
    graph.add_conditional_edges("map_validate", _after_stage1_map_validate, {"end": END, "resolve_map_source": "resolve_map_source", "sim_parse_validate_build": "sim_parse_validate_build"})

    graph.add_edge("algo_select", "run_simulation")
    graph.add_edge("algo_generate_loop", "run_simulation")
    graph.add_edge("optimize_loop", "run_simulation")
    graph.add_edge("run_simulation", "result_interrupt")
    graph.add_conditional_edges("optimize_validate", _after_optimize_validate, {"wait_for_human": "wait_for_human", "optimize_loop": "optimize_loop"})

    graph.add_edge("result_interrupt", "route_input")

    return graph

