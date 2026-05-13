"""Launch OpenEvolve's visualizer for MAPF Agent optimization output."""
from __future__ import annotations

import argparse
import os
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any

from mapf_agent.paths import OUTPUT_ROOT, PROJECT_ROOT


DEFAULT_EVOLVE_VISUALIZER_PORT = 8080
DEFAULT_EVOLVE_OUTPUT_DIR = OUTPUT_ROOT / "evolve"


class EvolveVisualizerHub:
    """Owns a single OpenEvolve visualizer process."""

    def __init__(self, host: str = "127.0.0.1", port: int = DEFAULT_EVOLVE_VISUALIZER_PORT) -> None:
        self.host = host
        self.port = port
        self._lock = threading.Lock()
        self._process: subprocess.Popen[Any] | None = None
        self._path: Path | None = None

    @property
    def url(self) -> str:
        return f"http://localhost:{self.port}/"

    def open(self, path: str | Path = DEFAULT_EVOLVE_OUTPUT_DIR) -> dict[str, Any]:
        visualizer_path = Path(path).expanduser().resolve()
        visualizer_path.mkdir(parents=True, exist_ok=True)

        with self._lock:
            self._ensure_started(visualizer_path)

        return {
            "url": self.url,
            "path": str(visualizer_path),
            "message": "已打开优化进度可视化页面。",
        }

    def stop(self) -> None:
        with self._lock:
            self._stop_locked()

    def _ensure_started(self, visualizer_path: Path) -> None:
        if self._is_running() and self._path == visualizer_path:
            return
        if self._is_running():
            self._stop_locked()

        if _is_port_open(self.host, self.port):
            raise RuntimeError(f"优化进度可视化端口 {self.port} 已被占用。")

        env = os.environ.copy()
        pythonpath = [str(PROJECT_ROOT), str(PROJECT_ROOT / "openevolve")]
        if env.get("PYTHONPATH"):
            pythonpath.append(env["PYTHONPATH"])
        env["PYTHONPATH"] = os.pathsep.join(pythonpath)
        env.setdefault("PYTHONUTF8", "1")

        self._process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "mapf_agent.evolve_visualizer",
                "--serve",
                "--path",
                str(visualizer_path),
                "--host",
                self.host,
                "--port",
                str(self.port),
            ],
            cwd=str(PROJECT_ROOT),
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        self._path = visualizer_path

        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            if self._process.poll() is not None:
                self._process = None
                self._path = None
                raise RuntimeError("OpenEvolve 优化进度可视化服务启动失败。")
            if _is_port_open(self.host, self.port):
                return
            time.sleep(0.1)

        self._stop_locked()
        raise RuntimeError("OpenEvolve 优化进度可视化服务启动超时。")

    def _is_running(self) -> bool:
        return self._process is not None and self._process.poll() is None

    def _stop_locked(self) -> None:
        process = self._process
        self._process = None
        self._path = None
        if process is None or process.poll() is not None:
            return

        process.terminate()
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=3)

def _serve(path: str, host: str, port: int) -> None:
    scripts_dir = PROJECT_ROOT / "openevolve" / "scripts"
    sys.path.insert(0, str(scripts_dir))
    os.environ["EVOLVE_OUTPUT"] = path

    import visualizer as openevolve_visualizer  # type: ignore[import-not-found]

    openevolve_visualizer.app.run(host=host, port=port, debug=False, use_reloader=False)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the OpenEvolve visualizer for MAPF Agent.")
    parser.add_argument("--serve", action="store_true")
    parser.add_argument("--path", default=str(DEFAULT_EVOLVE_OUTPUT_DIR))
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=DEFAULT_EVOLVE_VISUALIZER_PORT)
    return parser.parse_args()


def _is_port_open(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.25)
        return sock.connect_ex((host, port)) == 0


if __name__ == "__main__":
    args = _parse_args()
    if args.serve:
        _serve(args.path, args.host, args.port)
