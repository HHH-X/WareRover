"""Web entry point for the MAPF Agent UI."""
from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
import os
import sys
import threading
import webbrowser
from functools import partial
from http.server import SimpleHTTPRequestHandler
from socketserver import TCPServer
from typing import Any, Awaitable, Callable, TextIO

from mapf_agent.evolve_visualizer import EvolveVisualizerHub
from mapf_agent.paths import PROJECT_ROOT
from mapf_agent.session import AgentSession
from mapf_agent.visualizer import VisualizerHub, set_active_visualizer


DEFAULT_HTTP_PORT = 8010
DEFAULT_WS_PORT = 8766
_VISUALIZER_HUB = VisualizerHub()
_EVOLVE_VISUALIZER_HUB = EvolveVisualizerHub()
set_active_visualizer(_VISUALIZER_HUB)
_SHUTDOWN_EVENT: asyncio.Event | None = None


class _ReusableTCPServer(TCPServer):
    allow_reuse_address = True


class _LineBufferedWriter:
    """Mirror stdout/stderr and forward complete lines to a callback."""

    def __init__(self, mirror: TextIO, emit: Callable[[str], None]) -> None:
        self._mirror = mirror
        self._emit = emit
        self._buffer = ""

    def write(self, text: str) -> int:
        self._mirror.write(text)
        self._mirror.flush()
        self._buffer += text

        while "\n" in self._buffer:
            line, self._buffer = self._buffer.split("\n", 1)
            line = line.rstrip("\r")
            if line:
                self._emit(line)
        return len(text)

    def flush(self) -> None:
        self._mirror.flush()
        if self._buffer:
            line = self._buffer.rstrip("\r")
            self._buffer = ""
            if line:
                self._emit(line)


def _start_static_server(port: int) -> None:
    handler = partial(SimpleHTTPRequestHandler, directory=str(PROJECT_ROOT))
    with _ReusableTCPServer(("", port), handler) as httpd:
        print(f"MAPF Agent HTTP server: http://localhost:{port}")
        httpd.serve_forever()


async def _send(websocket: Any, message_type: str, **payload: Any) -> None:
    await websocket.send(json.dumps({"type": message_type, **payload}, ensure_ascii=False))


async def _run_with_log_stream(
    send: Callable[..., Awaitable[None]],
    action: Callable[[], dict[str, Any]],
) -> dict[str, Any]:
    loop = asyncio.get_running_loop()
    log_queue: asyncio.Queue[str] = asyncio.Queue()

    def emit(line: str) -> None:
        loop.call_soon_threadsafe(log_queue.put_nowait, line)

    def run_action() -> dict[str, Any]:
        stdout = _LineBufferedWriter(sys.stdout, emit)
        stderr = _LineBufferedWriter(sys.stderr, emit)
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            try:
                return action()
            finally:
                stdout.flush()
                stderr.flush()

    task = asyncio.create_task(asyncio.to_thread(run_action))
    while True:
        if task.done():
            while not log_queue.empty():
                await send("log", message=log_queue.get_nowait())
            return await task
        try:
            line = await asyncio.wait_for(log_queue.get(), timeout=0.1)
            await send("log", message=line)
        except asyncio.TimeoutError:
            pass


async def _handle_agent_message(
    session: AgentSession,
    send: Callable[..., Awaitable[None]],
    message: dict[str, Any],
) -> dict[str, Any]:
    message_type = message.get("type") or message.get("cmd")

    if message_type == "start":
        return await _run_with_log_stream(
            send,
            lambda: session.submit(str(message.get("message", ""))),
        )
    if message_type == "resume":
        return await _run_with_log_stream(
            send,
            lambda: session.resume(str(message.get("answer", ""))),
        )
    if message_type == "reset":
        return session.reset()

    raise ValueError(f"不支持的消息类型: {message_type}")


def _launch_simulator_sync() -> dict[str, Any]:
    return _VISUALIZER_HUB.open()


def _launch_evolve_visualizer_sync() -> dict[str, Any]:
    return _EVOLVE_VISUALIZER_HUB.open()


def _request_shutdown(force: bool = False) -> None:
    _EVOLVE_VISUALIZER_HUB.stop()
    if _SHUTDOWN_EVENT is not None:
        _SHUTDOWN_EVENT.set()
    if force:
        threading.Timer(0.5, lambda: os._exit(0)).start()


def _state_event_type(state: dict[str, Any]) -> str:
    if state.get("waiting_for_input"):
        return "question"
    if state.get("response") or state.get("error"):
        return "final"
    return "state"


async def ws_handler(websocket: Any, *_: Any) -> None:
    session = AgentSession()
    send_lock = asyncio.Lock()
    agent_task: asyncio.Task[None] | None = None

    async def send(message_type: str, **payload: Any) -> None:
        async with send_lock:
            await _send(websocket, message_type, **payload)

    async def run_agent_request(message: dict[str, Any]) -> None:
        nonlocal agent_task
        try:
            await send("running", label="Agent 正在处理...")
            state = await _handle_agent_message(session, send, message)
            await send(_state_event_type(state), state=state)
        except Exception as exc:
            await send("error", error=str(exc))
        finally:
            agent_task = None

    await send("ready", state=session.snapshot())

    async for raw_message in websocket:
        try:
            message = json.loads(raw_message)
            if not isinstance(message, dict):
                raise ValueError("消息必须是 JSON 对象。")

            message_type = message.get("type") or message.get("cmd")
            if message_type == "shutdown":
                await send("shutdown", message="Agent 服务正在关闭。")
                _request_shutdown(force=True)
                break

            if message_type == "launch_simulator":
                result = await asyncio.to_thread(_launch_simulator_sync)
                await send("simulator", **result)
                continue

            if message_type == "launch_evolve_visualizer":
                result = await asyncio.to_thread(_launch_evolve_visualizer_sync)
                await send("evolve_visualizer", **result)
                continue

            if message_type not in {"start", "resume", "reset"}:
                raise ValueError(f"不支持的消息类型: {message_type}")
            if agent_task and not agent_task.done():
                await send("error", error="Agent 正在处理上一条请求。")
                continue

            agent_task = asyncio.create_task(run_agent_request(message))
        except Exception as exc:
            await send("error", error=str(exc))


async def main(http_port: int, ws_port: int, open_browser: bool = True) -> None:
    global _SHUTDOWN_EVENT
    try:
        import websockets  # type: ignore[import-not-found]
    except ModuleNotFoundError as exc:
        raise RuntimeError("缺少依赖 websockets，请先安装项目运行依赖。") from exc

    _SHUTDOWN_EVENT = asyncio.Event()

    threading.Thread(
        target=_start_static_server,
        args=(http_port,),
        daemon=True,
    ).start()

    frontend_url = f"http://localhost:{http_port}/mapf_agent/web/index.html"
    if open_browser:
        webbrowser.open(frontend_url)
    print(f"MAPF Agent UI: {frontend_url}")

    async with websockets.serve(ws_handler, "localhost", ws_port):
        print(f"MAPF Agent WebSocket server: ws://localhost:{ws_port}")
        await _SHUTDOWN_EVENT.wait()


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Start the MAPF Agent web UI.")
    parser.add_argument("--http-port", type=int, default=DEFAULT_HTTP_PORT)
    parser.add_argument("--ws-port", type=int, default=DEFAULT_WS_PORT)
    parser.add_argument("--no-browser", action="store_true")
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    try:
        asyncio.run(
            main(
                http_port=args.http_port,
                ws_port=args.ws_port,
                open_browser=not args.no_browser,
            )
        )
    except KeyboardInterrupt:
        print("MAPF Agent server stopped.")
