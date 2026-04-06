from __future__ import annotations

import re
import time
from pathlib import Path
from typing import Literal, Tuple

from mapf_agent_v2.llm.client import chat_completion
from utils.algorithm_registry import load_generated_planner, load_generated_scheduler

AlgoType = Literal["planner", "scheduler"]


def _safe_name(name: str, fallback: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9_]+", "_", name).strip("_").lower()
    return s or fallback


def _planner_prompt(user_text: str, class_name: str) -> str:
    return f"""
生成 Python 代码，只返回代码，不要解释。
实现一个类 `{class_name}` 继承 `planner.base_planner.BasePlanner`。
必须实现:
def plan(self, targets, scheduler)
返回 Dict[int, List[Tuple[int, int]]].
策略可简单但要可运行，避免依赖第三方库。
务必包含必要 import，例如 typing、planner.base_planner.BasePlanner。
用户需求:
{user_text}
"""


def _scheduler_prompt(user_text: str, class_name: str) -> str:
    return f"""
生成 Python 代码，只返回代码，不要解释。
实现一个类 `{class_name}` 继承 `scheduler.base_scheduler.BaseScheduler`。
必须实现:
def assign_tasks(self, idle_agv_ids, planner)
返回 Dict[int, List[Tuple[Tuple[int, int], AGVAction, int]]]
策略可简单但要可运行，避免依赖第三方库。
务必包含必要 import，例如 typing、core.agv.AGVAction、scheduler.base_scheduler.BaseScheduler。
用户需求:
{user_text}
"""


def _strip_fence(code: str) -> str:
    text = code.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        return "\n".join(lines).strip()
    return text


def generate_algorithm_code(algorithm_type: AlgoType, algorithm_name: str, user_text: str) -> Tuple[str, str]:
    base_name = _safe_name(algorithm_name, f"generated_{algorithm_type}")
    class_name = "".join(x.capitalize() for x in base_name.split("_"))
    if not class_name.endswith("Planner") and algorithm_type == "planner":
        class_name += "Planner"
    if not class_name.endswith("Scheduler") and algorithm_type == "scheduler":
        class_name += "Scheduler"

    prompt = _planner_prompt(user_text, class_name) if algorithm_type == "planner" else _scheduler_prompt(user_text, class_name)
    raw_code = chat_completion([{"role": "user", "content": prompt}], temperature=0.1, max_tokens=5000)
    code = _strip_fence(raw_code)

    ts = time.strftime("%Y%m%d_%H%M%S")
    if algorithm_type == "planner":
        path = Path("planner/generated")
        path.mkdir(parents=True, exist_ok=True)
        file_path = path / f"{base_name}_{ts}.py"
    else:
        path = Path("scheduler/generated")
        path.mkdir(parents=True, exist_ok=True)
        file_path = path / f"{base_name}_{ts}.py"

    file_path.write_text(code + "\n", encoding="utf-8")

    registry_name = f"{base_name}_{ts}".lower()
    if algorithm_type == "planner":
        load_generated_planner(code, registry_name)
    else:
        load_generated_scheduler(code, registry_name)

    return registry_name, str(file_path)

