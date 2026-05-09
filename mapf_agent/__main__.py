"""REPL entry: python -m mapf_agent"""
from __future__ import annotations

from mapf_agent.session import AgentSession


def main() -> None:
    session = AgentSession(thread_id="session-1")
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

        state = session.submit(user_input)

        while state.get("waiting_for_input"):
            question = state.get("question", "")
            print(f"\n[需要补充信息] {question}")
            try:
                answer = input(">> ").strip()
            except (EOFError, KeyboardInterrupt):
                break
            state = session.resume(answer)

        response = state.get("response", "")
        if response:
            print(f"\n{response}")


if __name__ == "__main__":
    main()
