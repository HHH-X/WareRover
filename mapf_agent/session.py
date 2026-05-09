"""Reusable session wrapper for the MAPF Agent graph."""
from __future__ import annotations

from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any, Mapping
from uuid import uuid4

from langgraph.types import Command

from mapf_agent.graph import build_graph


_INTENT_LABELS = {
    "map": "生成地图",
    "config": "修改配置",
    "codegen": "生成算法",
    "optimize": "优化算法",
    "run": "运行仿真",
}


class AgentSession:
    """Owns one LangGraph checkpoint thread and exposes UI-friendly state."""

    def __init__(self, thread_id: str | None = None) -> None:
        self.thread_id = thread_id or f"session-{uuid4().hex}"
        self._thread = {"configurable": {"thread_id": self.thread_id}}
        self._graph = build_graph()

    def submit(self, user_input: str) -> dict[str, Any]:
        """Submit a new user instruction to the graph."""
        text = user_input.strip()
        if not text:
            raise ValueError("请输入指令。")
        self._graph.invoke({"user_input": text}, self._thread)
        return self.snapshot()

    def resume(self, answer: str) -> dict[str, Any]:
        """Resume a graph interrupt with the user's answer."""
        text = answer.strip()
        if not text:
            raise ValueError("请输入补充信息。")
        self._graph.invoke(Command(resume=text), self._thread)
        return self.snapshot()

    def reset(self) -> dict[str, Any]:
        """Clear graph memory for this browser session."""
        self._graph = build_graph()
        self.thread_id = f"session-{uuid4().hex}"
        self._thread = {"configurable": {"thread_id": self.thread_id}}
        return self.snapshot()

    def snapshot(self) -> dict[str, Any]:
        """Return a JSON-serializable view of the current graph state."""
        graph_state = self._graph.get_state(self._thread)
        values = dict(graph_state.values or {})
        question = _get_interrupt_question(graph_state)
        intents = [_to_jsonable(item) for item in values.get("intents", [])]
        intent_index = int(values.get("intent_index", 0) or 0)

        return {
            "thread_id": self.thread_id,
            "waiting_for_input": question is not None,
            "question": question,
            "response": values.get("response", ""),
            "error": values.get("error", ""),
            "intents": intents,
            "intent_index": intent_index,
            "current_intent": _current_intent(intents, intent_index),
            "map_file_path": values.get("map_file_path", ""),
            "generated_code": _to_jsonable(values.get("generated_code", {})),
            "run_metrics": _normalize_metrics(values.get("run_metrics", {})),
            "optimize_result": _to_jsonable(values.get("optimize_result", {})),
        }


def _get_interrupt_question(graph_state: Any) -> str | None:
    if not getattr(graph_state, "next", None):
        return None

    for task in getattr(graph_state, "tasks", []):
        interrupts = getattr(task, "interrupts", None)
        if not interrupts:
            continue
        value = interrupts[0].value
        if isinstance(value, Mapping):
            question = value.get("question")
            return str(question) if question else ""
    return None


def _current_intent(intents: list[Any], intent_index: int) -> dict[str, Any] | None:
    if intent_index < 0 or intent_index >= len(intents):
        return None
    intent = intents[intent_index]
    if not isinstance(intent, Mapping):
        return None
    intent_type = str(intent.get("type", ""))
    return {
        "index": intent_index,
        "type": intent_type,
        "label": _INTENT_LABELS.get(intent_type, intent_type or "未知任务"),
        "detail": intent.get("detail", ""),
    }


def _normalize_metrics(metrics: Any) -> dict[str, Any]:
    if not isinstance(metrics, Mapping):
        return {}

    normalized = {str(key): _to_jsonable(value) for key, value in metrics.items()}
    normalized["sim_steps"] = _first_present(
        metrics, "sim_steps", "Sim Steps", "steps", "step"
    )
    normalized["finished"] = _first_present(metrics, "finished", "Finished")
    normalized["task_success_rate"] = _first_present(
        metrics, "task_success_rate", "Task Success Rate", "success_rate"
    )
    normalized["tasks_completed"] = _first_present(
        metrics, "tasks_completed", "Tasks Completed"
    )
    return {key: value for key, value in normalized.items() if value is not None}


def _first_present(metrics: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in metrics:
            return _to_jsonable(metrics[key])
    return None


def _to_jsonable(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Path):
        return str(value)
    if is_dataclass(value):
        return _to_jsonable(asdict(value))
    if isinstance(value, Mapping):
        return {str(key): _to_jsonable(val) for key, val in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_to_jsonable(item) for item in value]
    return str(value)
