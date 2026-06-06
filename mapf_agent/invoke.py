"""Machine-readable entry point for external agents.

Example:
    python -m mapf_agent.invoke --message "生成一个 20x20 地图并运行仿真"
"""
from __future__ import annotations

import argparse
import contextlib
import json
import sys
from pathlib import Path
from typing import Any, Sequence

from mapf_agent.session import AgentSession


def invoke_agent(
    message: str,
    *,
    answers: Sequence[str] | None = None,
    thread_id: str | None = None,
) -> dict[str, Any]:
    """Run one MAPF Agent request and return the JSON-serializable state."""
    if not message.strip():
        raise ValueError("message 不能为空。")

    session = AgentSession(thread_id=thread_id)
    state = session.submit(message)
    for answer in answers or ():
        if not state.get("waiting_for_input"):
            break
        state = session.resume(str(answer))
    return state


def _parse_answers(raw: str | None) -> list[str]:
    if not raw:
        return []
    value = json.loads(raw)
    if not isinstance(value, list):
        raise ValueError("--answers 必须是 JSON 数组。")
    return [str(item) for item in value]


def _read_payload(path: str) -> dict[str, Any]:
    text = sys.stdin.read() if path == "-" else Path(path).read_text(encoding="utf-8")
    value = json.loads(text)
    if not isinstance(value, dict):
        raise ValueError("输入 JSON 必须是对象。")
    return value


def _payload_from_args(args: argparse.Namespace) -> dict[str, Any]:
    if args.input:
        payload = _read_payload(args.input)
    else:
        payload = {
            "message": args.message,
            "answers": _parse_answers(args.answers),
        }
    if args.thread_id:
        payload["thread_id"] = args.thread_id
    return payload


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Invoke MAPF Agent once and emit a JSON state snapshot.",
    )
    parser.add_argument("--message", "-m", help="Natural-language MAPF Agent request.")
    parser.add_argument(
        "--answers",
        default=None,
        help='JSON array of answers for follow-up questions, e.g. \'["20x20, 4 AGV"]\'.',
    )
    parser.add_argument(
        "--input",
        "-i",
        help="Read request JSON from a file, or '-' for stdin. Keys: message, answers, thread_id.",
    )
    parser.add_argument("--thread-id", help="Optional LangGraph checkpoint thread id.")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON output.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if not args.input and not args.message:
        parser.error("请提供 --message，或通过 --input 传入 JSON 请求。")

    try:
        payload = _payload_from_args(args)
        message = str(payload.get("message", ""))
        raw_answers = payload.get("answers", [])
        if not isinstance(raw_answers, list):
            raise ValueError("answers 必须是数组。")

        with contextlib.redirect_stdout(sys.stderr):
            state = invoke_agent(
                message,
                answers=[str(item) for item in raw_answers],
                thread_id=payload.get("thread_id"),
            )

        indent = 2 if args.pretty else None
        print(json.dumps(state, ensure_ascii=False, indent=indent))
        return 0
    except Exception as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stdout)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
