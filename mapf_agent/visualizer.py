"""Minimal bridge between Agent simulations and the existing frontend."""
from __future__ import annotations

import asyncio
import json
import socket
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler
from socketserver import ThreadingTCPServer
from typing import Any, Dict
from urllib.parse import quote

from mapf_agent.paths import PROJECT_ROOT


DEFAULT_SIMULATOR_HTTP_PORT = 8000
DEFAULT_SIMULATOR_WS_PORT = 8765

_ACTIVE_VISUALIZER: "VisualizerHub | None" = None


class _ReusableThreadingTCPServer(ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


class VisualizerHub:
    """Starts the simulator frontend and broadcasts frames to connected pages."""

    def __init__(
        self,
        http_port: int = DEFAULT_SIMULATOR_HTTP_PORT,
        ws_port: int = DEFAULT_SIMULATOR_WS_PORT,
    ) -> None:
        self.http_port = http_port
        self.ws_port = ws_port
        self._cache_lock = threading.Lock()
        self._last_init: Dict[str, Any] | None = None
        self._last_update: Dict[str, Any] | None = None

        self._http_started = False
        self._ws_started = False
        self._ws_ready = threading.Event()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._clients: set[Any] = set()

    @property
    def url(self) -> str:
        ws_url = quote(f"ws://localhost:{self.ws_port}", safe="")
        return f"http://localhost:{self.http_port}/frontend/index.html?ws={ws_url}"

    def ensure_started(self) -> None:
        """Start frontend HTTP and visualization WebSocket services if needed."""
        if not self._http_started:
            if not _is_port_open(self.http_port):
                threading.Thread(target=self._serve_http, daemon=True).start()
            self._http_started = True

        if self._ws_started:
            return
        if _is_port_open(self.ws_port):
            raise RuntimeError(
                f"可视化 WebSocket 端口 {self.ws_port} 已被占用，请先停止已有仿真器。"
            )

        threading.Thread(target=self._serve_ws, daemon=True).start()
        if not self._ws_ready.wait(timeout=8):
            raise RuntimeError("可视化 WebSocket 服务启动超时。")
        self._ws_started = True

    def open(self) -> Dict[str, Any]:
        self.ensure_started()
        return {
            "url": self.url,
            "status": "ready",
            "message": "已打开仿真可视化页面。Agent 执行仿真时会在该页面显示过程。",
        }

    def start_run(self) -> None:
        with self._cache_lock:
            self._last_init = None
            self._last_update = None

    def has_clients(self) -> bool:
        return bool(self._clients)

    def publish(self, payload: Dict[str, Any]) -> None:
        if not self.has_clients():
            return

        with self._cache_lock:
            if payload.get("type") == "init":
                self._last_init = payload
                self._last_update = None
            elif payload.get("type") == "update":
                self._last_update = payload

        loop = self._loop
        if loop and loop.is_running():
            asyncio.run_coroutine_threadsafe(self._broadcast(payload), loop)

    def _serve_http(self) -> None:
        handler = partial(SimpleHTTPRequestHandler, directory=str(PROJECT_ROOT))
        with _ReusableThreadingTCPServer(("", self.http_port), handler) as httpd:
            print(f"Simulator HTTP server: http://localhost:{self.http_port}")
            httpd.serve_forever()

    def _serve_ws(self) -> None:
        loop = asyncio.new_event_loop()
        self._loop = loop
        asyncio.set_event_loop(loop)
        loop.run_until_complete(self._run_ws_server())

    async def _run_ws_server(self) -> None:
        try:
            import websockets  # type: ignore[import-not-found]
        except ModuleNotFoundError as exc:
            raise RuntimeError("缺少依赖 websockets，请先安装项目运行依赖。") from exc

        async with websockets.serve(self._ws_handler, "localhost", self.ws_port):
            print(f"Simulator WebSocket server: ws://localhost:{self.ws_port}")
            self._ws_ready.set()
            await asyncio.Future()

    async def _ws_handler(self, websocket: Any, *_: Any) -> None:
        self._clients.add(websocket)
        try:
            for payload in self._cached_payloads():
                await websocket.send(json.dumps(payload, ensure_ascii=False))

            async for _ in websocket:
                pass
        finally:
            self._clients.discard(websocket)

    def _cached_payloads(self) -> list[Dict[str, Any]]:
        with self._cache_lock:
            return [
                payload
                for payload in (self._last_init, self._last_update)
                if payload is not None
            ]

    async def _broadcast(self, payload: Dict[str, Any]) -> None:
        text = json.dumps(payload, ensure_ascii=False)
        stale = []
        for client in list(self._clients):
            try:
                await client.send(text)
            except Exception:
                stale.append(client)
        for client in stale:
            self._clients.discard(client)


def set_active_visualizer(visualizer: VisualizerHub | None) -> None:
    global _ACTIVE_VISUALIZER
    _ACTIVE_VISUALIZER = visualizer


def get_active_visualizer() -> VisualizerHub | None:
    return _ACTIVE_VISUALIZER


def _is_port_open(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.25)
        return sock.connect_ex(("localhost", port)) == 0
