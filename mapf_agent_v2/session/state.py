from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional, TypedDict

from config.settings import SystemConfig


IntentType = Literal["map", "config", "run", "generate_algo", "optimize"]
AlgoType = Literal["planner", "scheduler"]
OptimizeTarget = Literal["planner", "scheduler", "both"]
BlockingStage = Literal["map", "config", "generate_algo", "optimize", ""]


class IntentTask(TypedDict, total=False):
    type: IntentType
    content: str
    algorithm_type: AlgoType
    algorithm_name: str
    target: OptimizeTarget
    planner_source: str
    scheduler_source: str
    iterations: int
    config_path: str
    output_root: str


class AgentState(TypedDict, total=False):
    # Input / conversation
    user_input: str
    user_response: str
    conversation_history: List[Dict[str, str]]

    # Parsed intents and scheduling
    intents: List[IntentTask]
    intent_index: int

    # Interactive blocking
    need_user_input: bool
    pending_question: str
    blocking_stage: BlockingStage
    terminate: bool

    # Runtime config and artifacts
    system_config: SystemConfig
    map_file_path: str
    config_patch_path: str
    generated_planner_name: str
    generated_planner_path: str
    generated_scheduler_name: str
    generated_scheduler_path: str
    latest_optimize_run_dir: str
    latest_optimize_best_code: str

    # Result and status
    metrics: Dict[str, Any]
    result_summary: str
    error: str


def new_initial_state() -> AgentState:
    return AgentState(
        user_input="",
        user_response="",
        conversation_history=[],
        intents=[],
        intent_index=0,
        need_user_input=False,
        pending_question="",
        blocking_stage="",
        terminate=False,
        system_config=SystemConfig(),
        map_file_path="",
        config_patch_path="",
        generated_planner_name="",
        generated_planner_path="",
        generated_scheduler_name="",
        generated_scheduler_path="",
        latest_optimize_run_dir="",
        latest_optimize_best_code="",
        metrics={},
        result_summary="",
        error="",
    )

