"""REPL entry: python -m agent"""
from __future__ import annotations

from langgraph.types import Command

from agent.graph import build_graph

THREAD = {"configurable": {"thread_id": "session-1"}}


def _get_interrupt_question(graph, config: dict) -> str | None:
    """Check if the graph is paused on an interrupt and return the question."""
    snapshot = graph.get_state(config)
    if not snapshot.next:
        return None
    for task in snapshot.tasks:
        if hasattr(task, "interrupts") and task.interrupts:
            val = task.interrupts[0].value
            if isinstance(val, dict):
                return val.get("question", "")
    return None


def main() -> None:
    graph = build_graph()
    print("MAPF Agent Ready. 输入指令开始操作，输入 quit 退出。\n")

    while True:
        try:
            user_input = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if user_input.lower() in ("quit", "exit", "q"):
            break
        if not user_input:
            continue

        graph.invoke({"user_input": user_input}, THREAD)

        while True:
            question = _get_interrupt_question(graph, THREAD)
            if question is None:
                break
            print(f"\n[需要补充信息] {question}")
            try:
                answer = input(">> ").strip()
            except (EOFError, KeyboardInterrupt):
                break
            graph.invoke(Command(resume=answer), THREAD)

        snapshot = graph.get_state(THREAD)
        response = snapshot.values.get("response", "")
        if response:
            print(f"\n{response}")


if __name__ == "__main__":
    main()
