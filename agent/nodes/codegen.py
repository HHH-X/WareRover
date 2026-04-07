"""Code generation node: LLM generates planner/scheduler implementations."""
from __future__ import annotations

import copy
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional

from config.settings import SystemConfig
from agent.llm import chat
from agent.run_sim import run_simulation
from agent.state import AgentState
from utils.algorithm_registry import load_generated_planner, load_generated_scheduler

_PROMPT_PATH = Path(__file__).resolve().parent.parent / "prompts" / "codegen.txt"
_PLANNER_BASE = Path(__file__).resolve().parent.parent.parent / "planner" / "base_planner.py"
_SCHEDULER_BASE = Path(__file__).resolve().parent.parent.parent / "scheduler" / "base_scheduler.py"
_SKILLS_DIR = Path(__file__).resolve().parent.parent / "skills"

_MAX_RETRIES = 3
_SMOKE_TEST_STEPS = 50


def _read_interface(algo_type: str) -> str:
    path = _PLANNER_BASE if algo_type == "planner" else _SCHEDULER_BASE
    return path.read_text(encoding="utf-8")


def _read_skill(skill_name: str) -> Optional[str]:
    if not skill_name:
        return None
    p = _SKILLS_DIR / f"{skill_name}.md"
    if p.exists():
        return p.read_text(encoding="utf-8")
    return None


def _extract_code(raw: str) -> str:
    """Strip markdown code fences if present."""
    if "```python" in raw:
        raw = raw.split("```python", 1)[1]
        raw = raw.split("```", 1)[0]
    elif "```" in raw:
        raw = raw.split("```", 1)[1]
        raw = raw.split("```", 1)[0]
    return raw.strip()


def _build_prompt(algo_type: str, user_request: str, skill_name: str = "") -> str:
    tpl = _PROMPT_PATH.read_text(encoding="utf-8")
    interface_code = _read_interface(algo_type)
    skill_content = _read_skill(skill_name)
    skill_section = ""
    if skill_content:
        skill_section = f"## 参考论文/技术 Skill\n\n{skill_content}"

    return tpl.format(
        algo_type="Planner (路径规划器)" if algo_type == "planner" else "Scheduler (任务调度器)",
        interface_code=f"```python\n{interface_code}\n```",
        skill_section=skill_section,
        user_request=user_request,
    )


def _try_load(code: str, algo_type: str, name: str):
    if algo_type == "planner":
        load_generated_planner(code, name)
    else:
        load_generated_scheduler(code, name)


def _smoke_test(algo_type: str, name: str, state: AgentState) -> Optional[str]:
    """Run a short simulation to verify the generated code doesn't crash."""
    cfg = copy.deepcopy(state.get("system_config") or SystemConfig())
    cfg.sim_config.max_steps = _SMOKE_TEST_STEPS
    if state.get("map_file_path"):
        cfg.sim_config.map_file = state["map_file_path"]
    if algo_type == "planner":
        cfg.sim_config.planner_type = name
    else:
        cfg.sim_config.scheduler_type = name
    try:
        run_simulation(config=cfg, max_steps=_SMOKE_TEST_STEPS)
        return None
    except Exception as exc:
        return str(exc)


def codegen_node(state: AgentState) -> Dict:
    intents = state.get("intents") or []
    idx = state.get("intent_index", 0)
    intent = intents[idx] if idx < len(intents) else {}

    algo_type = intent.get("algo_type", "planner")
    algo_name = intent.get("algo_name", "")
    skill_name = intent.get("skill_name", "")
    detail = intent.get("detail", "")

    reg_name = f"agent_gen_{algo_name or algo_type}"
    system_prompt = _build_prompt(algo_type, detail, skill_name)
    messages = [{"role": "system", "content": system_prompt}, {"role": "user", "content": detail}]

    last_error = ""
    for attempt in range(_MAX_RETRIES):
        if last_error:
            messages.append({"role": "user", "content": f"上次生成的代码运行报错:\n{last_error}\n请修复并重新生成完整代码。"})

        raw = chat(messages, max_tokens=8192)
        code = _extract_code(raw)

        try:
            _try_load(code, algo_type, reg_name)
        except Exception as exc:
            last_error = f"加载失败: {exc}"
            continue

        smoke_err = _smoke_test(algo_type, reg_name, state)
        if smoke_err:
            last_error = f"运行测试失败: {smoke_err}"
            continue

        # Save to file
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        target_dir = Path(__file__).resolve().parent.parent.parent / algo_type
        filename = f"generated_{algo_name or algo_type}_{timestamp}.py"
        out_path = target_dir / filename
        out_path.write_text(code, encoding="utf-8")

        gen = dict(state.get("generated_code") or {})
        gen[algo_type] = str(out_path)
        return {"generated_code": gen, "error": ""}

    return {"error": f"代码生成失败（{_MAX_RETRIES}次重试后仍有错误）: {last_error}"}
