"""Code generation node: ReAct tool-use loop for planner/scheduler generation."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional

from mapf_agent.llm import chat_completion
from mapf_agent.paths import output_dir
from mapf_agent.state import AgentState
from mapf_agent.tools import TOOL_DEFINITIONS, create_executor
from mapf_agent.tools.run_code import _extract_code

_PROMPT_PATH = Path(__file__).resolve().parent.parent / "prompts" / "codegen.txt"
_PLANNER_BASE = Path(__file__).resolve().parent.parent.parent / "planner" / "base_planner.py"
_SCHEDULER_BASE = Path(__file__).resolve().parent.parent.parent / "scheduler" / "base_scheduler.py"
_SKILLS_DIR = Path(__file__).resolve().parent.parent / "skills"
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

_MAX_ROUNDS = 20
_KEY_DIRS = ["core", "planner", "scheduler", "utils", "config", "order_strategies"]


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


def _project_tree() -> str:
    """Generate a brief project directory tree for the system prompt."""
    lines: list[str] = []
    for d in _KEY_DIRS:
        dp = _PROJECT_ROOT / d
        if not dp.is_dir():
            continue
        lines.append(f"{d}/")
        for f in sorted(dp.iterdir()):
            if f.name.startswith((".", "__pycache__")):
                continue
            if f.is_dir():
                lines.append(f"  {f.name}/")
            elif f.suffix == ".py":
                lines.append(f"  {f.name}")
    return "\n".join(lines)


def _build_system_prompt(algo_type: str, user_request: str,
                         skill_name: str = "") -> str:
    tpl = _PROMPT_PATH.read_text(encoding="utf-8")
    interface_code = _read_interface(algo_type)
    skill_content = _read_skill(skill_name)
    skill_section = ""
    if skill_content:
        skill_section = f"## 参考论文/技术 Skill\n\n{skill_content}"

    return tpl.format(
        algo_type="Planner (路径规划器)" if algo_type == "planner"
        else "Scheduler (任务调度器)",
        interface_code=f"```python\n{interface_code}\n```",
        project_tree=_project_tree(),
        skill_section=skill_section,
        user_request=user_request,
    )


def _msg_from_completion(msg) -> dict:
    """Convert a ChatCompletionMessage to a serializable dict for the messages list."""
    d: dict = {"role": "assistant", "content": msg.content or ""}
    if msg.tool_calls:
        d["tool_calls"] = [
            {
                "id": tc.id,
                "type": "function",
                "function": {
                    "name": tc.function.name,
                    "arguments": tc.function.arguments,
                },
            }
            for tc in msg.tool_calls
        ]
    return d


_ALGO_LABELS = {"planner": "路径规划器", "scheduler": "任务调度器"}
_SUCCESS = "测试通过"


def codegen_node(state: AgentState) -> Dict:
    intents = state.get("intents") or []
    idx = state.get("intent_index", 0)
    intent = intents[idx] if idx < len(intents) else {}

    algo_type = intent.get("algo_type", "planner")
    algo_name = intent.get("algo_name", "")
    skill_name = intent.get("skill_name", "")
    detail = intent.get("detail", "")

    label = _ALGO_LABELS.get(algo_type, algo_type)
    parts = [f"[代码生成] 正在生成{label}"]
    if algo_name:
        parts.append(f"({algo_name})")
    if skill_name:
        parts.append(f"[skill: {skill_name}]")
    print(" ".join(parts) + " (ReAct 模式)...")

    reg_name = f"agent_gen_{algo_name or algo_type}"
    system_prompt = _build_system_prompt(algo_type, detail, skill_name)
    messages: list[dict] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": detail},
    ]
    executor = create_executor(algo_type, reg_name, state)

    for round_num in range(1, _MAX_ROUNDS + 1):
        print(f"[代码生成] 轮次 {round_num}/{_MAX_ROUNDS}")
        msg = chat_completion(messages, tools=TOOL_DEFINITIONS, max_tokens=8192)
        messages.append(_msg_from_completion(msg))

        # --- LLM called tools ---
        if msg.tool_calls:
            test_passed_code: Optional[str] = None
            for tc in msg.tool_calls:
                fn_name = tc.function.name
                try:
                    args = json.loads(tc.function.arguments)
                except json.JSONDecodeError:
                    args = {}
                print(f"  [工具] {fn_name}")
                result = executor(fn_name, args)
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": result,
                })
                if fn_name == "test_code" and result == _SUCCESS:
                    test_passed_code = args.get("code", "")
            if test_passed_code is not None:
                return _save_result(
                    _extract_code(test_passed_code), algo_type, algo_name,
                    state,
                )
            continue

        # --- LLM returned plain text (no tool calls) ---
        code = _extract_code(msg.content or "")
        if code:
            print("  [自动测试] LLM 直接输出了代码，自动提交测试...")
            result = executor("test_code", {"code": code})
            if result == _SUCCESS:
                return _save_result(code, algo_type, algo_name, state)
            messages.append({
                "role": "user",
                "content": f"代码测试失败: {result}\n请根据错误信息修复代码，然后使用 test_code 工具重新提交。",
            })

    print(f"[代码生成] 失败 — 达到最大轮次 {_MAX_ROUNDS}")
    return {"error": f"代码生成失败（{_MAX_ROUNDS} 轮后仍未通过测试）"}


def _save_result(code: str, algo_type: str, algo_name: str,
                 state: AgentState) -> Dict:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"generated_{algo_name or algo_type}_{timestamp}.py"
    out_path = output_dir("codegen") / filename
    out_path.write_text(code, encoding="utf-8")

    gen = dict(state.get("generated_code") or {})
    gen[algo_type] = str(out_path)
    print(f"[代码生成] 完成 — 已保存至 {filename}")
    return {"generated_code": gen, "error": ""}
