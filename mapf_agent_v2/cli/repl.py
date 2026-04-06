from __future__ import annotations

import argparse
import dataclasses
import json
from typing import Any, Dict

from langgraph.types import Command

from mapf_agent_v2.session.state import new_initial_state
from mapf_agent_v2.workflow.graph import build_graph


def run_repl() -> None:
    graph = build_graph()
    state = new_initial_state()
    config = {"configurable": {"thread_id": "mapf-agent-v2-repl"}}
    print("MAPF Agent V2 (LangGraph) 启动。输入 exit/quit 退出。")
    while True:
        text = input("\nuser> ").strip()
        if not text:
            continue
        state["user_input"] = text
        out = graph.invoke(state, config=config)
        if "__interrupt__" in out:
            payload = out["__interrupt__"][0].value
            question = payload.get("question", "请补充信息")
            answer = input(f"\nassistant(question)> {question}\nuser> ").strip()
            out = graph.invoke(Command(resume=answer), config=config)
        state.update(out)
        history = state.get("conversation_history") or []
        if history:
            print(f"assistant> {history[-1].get('content', '')}")
        if state.get("terminate"):
            break


def run_once(text: str) -> Dict[str, Any]:
    graph = build_graph()
    state = new_initial_state()
    state["user_input"] = text
    config = {"configurable": {"thread_id": "mapf-agent-v2-once"}}
    out = graph.invoke(state, config=config)
    if "__interrupt__" in out:
        # Non-interactive mode returns pending question.
        payload = out["__interrupt__"][0].value
        return {"ok": False, "need_user_input": True, "question": payload.get("question", "")}
    state.update(out)
    exported: Dict[str, Any] = dict(state)
    if "system_config" in exported:
        exported["system_config"] = dataclasses.asdict(exported["system_config"])
    return {"ok": True, "state": exported}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", type=str, default="")
    args = parser.parse_args()
    if args.once:
        print(json.dumps(run_once(args.once), ensure_ascii=False, indent=2))
        return
    run_repl()


if __name__ == "__main__":
    main()

