"""AgentState: LangGraph 状态定义."""
from __future__ import annotations

from typing import Any, Dict, List, Literal, TypedDict

from config.settings import SystemConfig


IntentType = Literal["map", "config", "run", "codegen", "optimize"]


class IntentTask(TypedDict, total=False):
    type: IntentType
    detail: str
    algo_type: str       # "planner" / "scheduler"
    algo_name: str
    skill_name: str
    optimize_source: str  # file path or "generated"


class AgentState(TypedDict, total=False):
    # --- conversation ---
    user_input: str
    conversation_history: List[Dict[str, str]]

    # --- intent scheduling ---
    intents: List[IntentTask]
    intent_index: int

    # --- runtime artifacts ---
    system_config: SystemConfig
    map_file_path: str
    generated_code: Dict[str, str]   # {"planner": path, "scheduler": path}
    run_metrics: Dict[str, Any]
    optimize_result: Dict[str, Any]

    # --- output ---
    response: str
    error: str
