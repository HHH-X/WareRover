# run.py
import asyncio
import json
import os
import threading
import webbrowser
from http.server import SimpleHTTPRequestHandler
from socketserver import TCPServer
import random
import numpy as np

from config.settings import SystemConfig
from core.data_generator import generate_send_data
from core.elevator import ElevatorManager
from core.env import Env
from core.fault_manager import FaultManager
from core.warehouse_map import WarehouseMap
from core.agvmanager import AGVManager
from core.ordermanager import OrderManager
from core.simulator import Simulator
import websockets
from utils.algorithm_registry import default_registry
from utils.logger import GlobalLogger
from utils.simulation_clock import SimulationClock
from utils.simulation_context import SimulationContext

STATE = {
    "paused": True,
    "step_trigger": False,
}
RUNNING = True
NEED_RESET = False

def start_http_server(port=18000):
    """Start local HTTP server (avoids file:// CORS issues)."""
    os.chdir(os.path.abspath("."))
    handler = SimpleHTTPRequestHandler
    with TCPServer(("", port), handler) as httpd:
        print(f"HTTP server running at http://localhost:{port}")
        httpd.serve_forever()


async def simulator_loop(websocket, message_queue):
    global RUNNING
    global NEED_RESET
    print("Simulation begin")

    ctx = SimulationContext()
    ctx.system_config = SystemConfig()

    ctx.logger = GlobalLogger(ctx)
    ctx.clock = SimulationClock(ctx)
    ctx.warehouse_map = WarehouseMap(ctx)
    ctx.order_manager = OrderManager(ctx)
    ctx.agv_manager = AGVManager(ctx)
    ctx.elevator_manager = ElevatorManager(ctx)
    ctx.env = Env(ctx)
    ctx.fault_manager = FaultManager(ctx)
    ctx.scheduler = default_registry.build_scheduler(ctx)
    ctx.planner = default_registry.build_planner(ctx)
    ctx.simulator = Simulator(ctx)

    init_data = generate_send_data(
        ctx,
        data_type="init",
    )
    await websocket.send(json.dumps(init_data))

    while RUNNING:
        if NEED_RESET:
            print("Resetting simulation...")
            ctx.clock.reset()
            ctx.env.reset()
            ctx.elevator_manager.reset()
            ctx.scheduler.reset()
            ctx.logger.reset()
            NEED_RESET = False
            print("Reset complete.")
            continue
        while (RUNNING
               and not NEED_RESET
               and not ctx.order_manager.is_all_orders_completed()
               and ctx.clock.now() < ctx.system_config.sim_config.max_steps):

            if not STATE["paused"] or STATE["step_trigger"]:
                ctx.simulator.step()
                STATE["step_trigger"] = False
                step_data = generate_send_data(
                    ctx,
                    data_type="update",
                )
                await websocket.send(json.dumps(step_data))

            while not message_queue.empty():
                msg = await message_queue.get()
                ctx.fault_manager.handle_message(msg)
                print("Message processed.")

            await asyncio.sleep(0.1)

        if not NEED_RESET:
            print("All orders completed or max steps reached; waiting for reset or stop.")
            final = ctx.logger.get_final_metrics(ctx.clock.now())
            ctx.logger.add_runtime_log(str(final))
            print(final)

        while RUNNING and not NEED_RESET:
            await asyncio.sleep(0.1)

    print("Simulation loop ended.")


async def ws_handler(websocket):
    global RUNNING
    message_queue = asyncio.Queue()
    sim_task = asyncio.create_task(simulator_loop(websocket, message_queue))

    try:
        async for message in websocket:
            try:
                msg = json.loads(message)
                print("Received message:", msg)
                cmd = msg.get("cmd")
                if cmd == "pause":
                    STATE["paused"] = True
                elif cmd == "resume":
                    STATE["paused"] = False
                elif cmd == "step":
                    STATE["step_trigger"] = True
                elif cmd == "stop":
                    print("Stop command received, exiting...")
                    RUNNING = False
                    STATE["paused"] = True
                    await websocket.send(json.dumps({"status": "stopping"}))
                    await websocket.close()
                    break
                elif cmd == "reset":
                    print("Reset command received.")
                    global NEED_RESET
                    NEED_RESET = True
                    # await websocket.send(json.dumps({"status": "resetting"}))
                    # continue
                else:
                    await message_queue.put(msg)

            except Exception as e:
                print("Invalid message:", message, e)

    except websockets.exceptions.ConnectionClosed:
        print("WebSocket closed.")

    finally:
        if not sim_task.done():
            sim_task.cancel()
            try:
                await sim_task
            except asyncio.CancelledError:
                pass
        print("WebSocket handler exited.")


async def main():
    """Start visualization: HTTP server + WebSocket + open browser."""
    global RUNNING
    http_port = 8000
    threading.Thread(target=start_http_server, args=(http_port,), daemon=True).start()

    frontend_url = f"http://localhost:{http_port}/frontend/index.html?debug=1"
    webbrowser.open(frontend_url)
    print(f"Opening browser at {frontend_url}")

    ws_port = 8765
    async with websockets.serve(ws_handler, "localhost", ws_port):
        print(f"WebSocket server running at ws://localhost:{ws_port}")
        while RUNNING:
            await asyncio.sleep(0.5)

    print("Main loop ended, exiting.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Interrupted by user.")
    finally:
        print("Exit complete.")
