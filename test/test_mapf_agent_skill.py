from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mapf_agent import invoke as invoke_module


class FakeSession:
    def __init__(self, thread_id=None):
        self.thread_id = thread_id or "fake-thread"

    def submit(self, message):
        print("internal progress log")
        if message == "needs more":
            return {
                "thread_id": self.thread_id,
                "waiting_for_input": True,
                "question": "missing info?",
                "response": "",
                "error": "",
            }
        return {
            "thread_id": self.thread_id,
            "waiting_for_input": False,
            "question": None,
            "response": f"done: {message}",
            "error": "",
            "run_metrics": {"sim_steps": 10},
        }

    def resume(self, answer):
        return {
            "thread_id": self.thread_id,
            "waiting_for_input": False,
            "question": None,
            "response": f"resumed: {answer}",
            "error": "",
        }


def test_invoke_agent_returns_session_snapshot(monkeypatch):
    monkeypatch.setattr(invoke_module, "AgentSession", FakeSession)

    state = invoke_module.invoke_agent("run once", thread_id="skill-test")

    assert state["thread_id"] == "skill-test"
    assert state["waiting_for_input"] is False
    assert state["response"] == "done: run once"
    assert state["run_metrics"]["sim_steps"] == 10


def test_invoke_agent_keeps_question_when_answers_missing(monkeypatch):
    monkeypatch.setattr(invoke_module, "AgentSession", FakeSession)

    state = invoke_module.invoke_agent("needs more")

    assert state["waiting_for_input"] is True
    assert state["question"] == "missing info?"


def test_invoke_agent_consumes_answers(monkeypatch):
    monkeypatch.setattr(invoke_module, "AgentSession", FakeSession)

    state = invoke_module.invoke_agent("needs more", answers=["20x20, 4 AGV"])

    assert state["waiting_for_input"] is False
    assert state["response"] == "resumed: 20x20, 4 AGV"


def test_main_writes_json_to_stdout_and_logs_to_stderr(monkeypatch, capsys):
    monkeypatch.setattr(invoke_module, "AgentSession", FakeSession)

    exit_code = invoke_module.main(["--message", "run once"])

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert exit_code == 0
    assert payload["response"] == "done: run once"
    assert "internal progress log" not in captured.out
    assert "internal progress log" in captured.err
