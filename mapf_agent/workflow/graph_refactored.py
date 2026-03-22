
# ---------------------------------------------------------------------------
# Interrupt/Resume rewrite (your node document)
# ---------------------------------------------------------------------------
import os
import json
from langgraph.types import interrupt
from typing import Any, Dict, List, Optional, TypedDict
from langgraph.graph import END, StateGraph

class MAPFState(TypedDict, total=False):
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


def _append_history(state: MAPFState, role: str, content: str) -> List[Dict[str, Any]]:
    history = list(state.get("conversation_history") or [])
    if content:
        history.append({"role": role, "content": content})
    return history


def route_input(state: MAPFState) -> Dict[str, Any]:
    """路由：env_only / algorithm_only / both；并拆分 map_text/algorithm_text。"""
    user_input = (state.get("user_input") or "").strip()

    if user_input.lower() in ("quit", "exit", "q", "stop", "end", "结束", "退出"):
        return {"terminate": True}

    use_llm = bool(state.get("use_llm", True))
    route: str = "env_only"
    map_text = ""
    algorithm_text = ""

    # Optional bias from caller (backward compatibility with Coordinator wrappers).
    hint = (state.get("route_hint") or "").strip()
    if hint in ("env_only", "algorithm_only", "both", "map_only", "algorithm", "map"):
        if hint in ("map_only", "map"):
            route = "env_only"
        elif hint == "algorithm":
            route = "algorithm_only"
        else:
            route = hint

        if route == "env_only":
            map_text = user_input
            algorithm_text = ""
        elif route == "algorithm_only":
            map_text = ""
            algorithm_text = user_input
        else:
            map_text = user_input
            algorithm_text = user_input

        history = _append_history(state, "user", user_input)
        return {
            "route": route,
            "map_text": map_text,
            "algorithm_text": algorithm_text,
            "conversation_history": history,
            "pending_question": "",
            "pending_type": "",
            "need_user_input": False,
        }

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

            raw_route = str(result.get("route") or "")
            if raw_route in ("env_only", "algorithm_only", "both"):
                route = raw_route
            elif raw_route in ("map_only", "map"):
                route = "env_only"
            elif raw_route in ("algorithm_only", "algorithm"):
                route = "algorithm_only"
            else:
                route = "env_only"

            map_text = result.get("map_text", "") or (user_input if route != "algorithm_only" else "")
            algorithm_text = result.get("algorithm_text", "") or (user_input if route != "env_only" else "")
        except Exception:
            # Fallback to heuristic below.
            route = "env_only"

    if not route:
        route = "env_only"

    if not use_llm or (not map_text and not algorithm_text):
        # Keyword heuristic fallback
        text_lower = user_input.lower()
        has_env = any(k in text_lower for k in ("地图", "map", "agv", "货架", "shelf", "仓库", "warehouse"))
        has_algo = any(k in text_lower for k in ("算法", "algorithm", "planner", "cbs", "astar", "优化", "optimize", "调度"))
        if has_env and has_algo:
            route = "both"
        elif has_algo and not has_env:
            route = "algorithm_only"
        else:
            route = "env_only"

        if route == "env_only":
            map_text = user_input
            algorithm_text = ""
        elif route == "algorithm_only":
            map_text = ""
            algorithm_text = user_input
        else:
            map_text = user_input
            algorithm_text = user_input

    history = _append_history(state, "user", user_input)
    return {
        "route": route,
        "map_text": map_text,
        "algorithm_text": algorithm_text,
        "conversation_history": history,
        "pending_question": "",
        "pending_type": "",
        "need_user_input": False,
    }


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
    """合并用户回答到 map_text/algorithm_text，并清理 pending 状态。"""
    resp = (state.get("last_user_response") or "").strip()
    ptype = (state.get("pending_type") or "").strip()

    map_text = state.get("map_text") or ""
    algorithm_text = state.get("algorithm_text") or ""

    if ptype in ("env_missing", "sim_error"):
        if resp:
            map_text = f"{map_text}\n{resp}".strip()
    elif ptype in ("optimize_missing", "optimize_target_missing"):
        if resp:
            algorithm_text = f"{algorithm_text}\n{resp}".strip()
    else:
        # 默认把补充内容当作环境文本的一部分（更保守，更符合你文档的 flow）。
        if resp:
            map_text = f"{map_text}\n{resp}".strip()

    return {
        "map_text": map_text,
        "algorithm_text": algorithm_text,
        "pending_question": "",
        "need_user_input": False,
    }


def map_generate(state: MAPFState) -> Dict[str, Any]:
    """根据 map_config 生成 map_json 并落地到 map_path（可失败循环）。"""
    from mapf_agent.agents.env_config_agent import EnvConfigAgent

    attempts = int(state.get("map_gen_attempts", 0)) + 1
    max_attempts = int(state.get("map_gen_max_attempts", 3))

    if attempts > max_attempts:
        return {"error": "地图生成/校验失败次数超出上限。", "map_gen_attempts": attempts, "terminate": True}

    agent = EnvConfigAgent()
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
    if suggestion.get("action") == "change_algorithm":
        if suggestion.get("new_planner_type"):
            algo_cfg["planner_type"] = suggestion["new_planner_type"]
        if suggestion.get("new_scheduler_type"):
            algo_cfg["scheduler_type"] = suggestion["new_scheduler_type"]
    elif suggestion.get("action") == "adjust_params":
        param_changes = suggestion.get("param_changes", {}) or {}
        if param_changes.get("max_steps") is not None:
            from config.settings import SimConfig

            SimConfig.max_steps = int(param_changes["max_steps"])

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

    apply_runtime_meta_to_sim_classes(state.get("out_path"))
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
    graph.add_node("env_parse", env_parse)
    graph.add_node("env_validate", env_validate)
    graph.add_node("wait_for_human", wait_for_human)
    graph.add_node("handle_user_response", handle_user_response)
    graph.add_node("map_generate", map_generate)
    graph.add_node("map_validate", map_validate)
    graph.add_node("env_build", env_build)
    graph.add_node("algo_route", algo_route)
    graph.add_node("algo_select", algo_select)
    graph.add_node("algo_generate_loop", algo_generate_loop)
    graph.add_node("optimize_validate", optimize_validate)
    graph.add_node("optimize_loop", optimize_loop)
    graph.add_node("run_simulation", run_simulation)
    graph.add_node("result_interrupt", result_interrupt)

    # --- Routing after route_input ---
    graph.add_conditional_edges(
        "route_input",
        _after_route_input,
        {"end": END, "env_parse": "env_parse", "algo_route": "algo_route"},
    )

    # --- Environment flow ---
    graph.add_edge("env_parse", "env_validate")
    graph.add_conditional_edges(
        "env_validate",
        _after_env_validate,
        {"end": END, "wait_for_human": "wait_for_human", "map_generate": "map_generate"},
    )
    graph.add_edge("wait_for_human", "handle_user_response")

    # Re-route handle_user_response depending on pending_type
    graph.add_conditional_edges(
        "handle_user_response",
        _after_handle_user_response,
        {"env_parse": "env_parse", "optimize_validate": "optimize_validate"},
    )

    graph.add_edge("map_generate", "map_validate")
    graph.add_conditional_edges(
        "map_validate",
        _after_map_validate,
        {"end": END, "env_build": "env_build", "map_generate": "map_generate"},
    )
    # env_only uses result_interrupt
    graph.add_conditional_edges("env_build", _after_env_build, {"result_interrupt": "result_interrupt", "algo_route": "algo_route"})

    # --- Algorithm flow ---
    graph.add_conditional_edges(
        "algo_route",
        _after_algo_route,
        {
            "wait_for_human": "wait_for_human",
            "algo_select": "algo_select",
            "algo_generate_loop": "algo_generate_loop",
            "optimize_validate": "optimize_validate",
        },
    )

    graph.add_edge("algo_select", "run_simulation")
    graph.add_edge("algo_generate_loop", "run_simulation")
    graph.add_edge("optimize_loop", "run_simulation")
    graph.add_edge("run_simulation", "result_interrupt")

    graph.add_conditional_edges(
        "optimize_validate",
        _after_optimize_validate,
        {"wait_for_human": "wait_for_human", "optimize_loop": "optimize_loop"},
    )

    graph.add_edge("result_interrupt", "route_input")

    return graph

