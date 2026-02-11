# core/fault_manager.py
from typing import Optional, Dict, Tuple, List
import random
from core.agvmanager import AGVManager
from core.env import Env
from core.gridmap import GridMap
from config.settings import FaultConfig
from utils.logger import global_logger
from utils.simulation_clock import clock

class FaultManager:
    def __init__(self, agv_manager: AGVManager, env: Env, gridmap: GridMap):
        self.agv_manager = agv_manager
        self.gridmap = gridmap
        self.env = env
        env_info = env.get_env_info()
        self.static_grid = env_info['static_grid']
        self.reset()

    def step(self):
        """
        Called once per simulation step.
        Handles random fault injection and repair.
        """
        if not self.enable_faults:
            return

        self._maybe_trigger_fault()
        self._update_repairs()

    def _maybe_trigger_fault(self):
        if not self.allow_multiple_faults and self.active_faults:
            return
        for agv_id in self.agv_manager.all_agv_ids:

            if agv_id in self.active_faults:
                continue

            if self.rng.random() < self.fault_prob:
                self._trigger_fault(agv_id)
                if not self.allow_multiple_faults:
                    break

    def _trigger_fault(self, agv_id: int):
        repair_time = self.rng.randint(
            self.mean_repair_time // 2,
            self.mean_repair_time * 2,
        )

        self.active_faults[agv_id] = repair_time
        self.simulate_fault(agv_id)

    def _update_repairs(self):
        recovered = []

        for agv_id in self.active_faults:
            self.active_faults[agv_id] -= 1
            if self.active_faults[agv_id] <= 0:
                recovered.append(agv_id)

        for agv_id in recovered:
            self.repair_agv(agv_id)
            del self.active_faults[agv_id]


    def handle_message(self, msg: dict):
        """Handle frontend commands, e.g. {"cmd": "damage", "agv_id": 2} or {"cmd": "repair", "agv_id": 2}."""
        cmd = msg.get("cmd")
        agv_id = msg.get("agv_id")
        print(f"[FaultManager] Handling command: {msg}")
        if cmd == "damage":
            self.simulate_fault(agv_id)
        elif cmd == "repair":
            self.repair_agv(agv_id)
        print("Command processed.")
        # else:
        #     print(f"[FaultManager] 未知命令: {cmd}")

    def simulate_fault(self, agv_id: int):
        self.agv_manager.set_agv_status(agv_id, False)
        agv_grid_pos = self.agv_manager.get_agv(agv_id).grid_pos
        border_cell = self._find_nearest_border_free_cell(agv_grid_pos)
        path = self.plan_repair_path(agv_grid_pos, border_cell)
        self.gridmap.add_dynamic_occupancy(str(agv_id), path)
        global_logger.add_runtime_log(f"[FaultManager] AGV {agv_id} failed at step {clock.now()}")

    def repair_agv(self, agv_id: int):
        self.agv_manager.set_agv_status(agv_id, True)
        self.gridmap.remove_dynamic_occupancy(str(agv_id))
        global_logger.add_runtime_log(f"[FaultManager] AGV {agv_id} repaired at step {clock.now()}")

    def assign_replacement(self, faulty_agv_id: int, replacement_agv_id: int):
        """Assign a replacement AGV for a faulty one (re-dispatch tasks)."""
        pass

    def _find_nearest_border_free_cell(self, start: Tuple[int, int]) -> Optional[Tuple[int, int]]:
        """Find nearest traversable border cell (-1) from start without crossing receiver zones."""
        h, w = self.static_grid.shape
        visited = set()
        queue = [start]
        receiver_set = set(self.gridmap.receiver_zones.values())

        while queue:
            x, y = queue.pop(0)
            if (x, y) in visited:
                continue
            visited.add((x, y))
            if self.static_grid[y, x] == -1 and (x == 0 or y == 0 or x == w - 1 or y == h - 1):
                if (x, y) not in receiver_set:
                    return (x, y)

            for dx, dy in [(1, 0), (-1, 0), (0, 1), (0, -1)]:
                nx, ny = x + dx, y + dy
                if (
                    0 <= nx < w and 0 <= ny < h and
                    self.static_grid[ny, nx] == -1 and
                    (nx, ny) not in visited and
                    (nx, ny) not in receiver_set
                ):
                    queue.append((nx, ny))

        return None

    def plan_repair_path(self, start: Tuple[int, int], goal: Tuple[int, int]) -> Optional[List[Tuple[int, int]]]:
        """Plan traversable path from start to goal on static_grid, avoiding receiver zones."""
        h, w = self.static_grid.shape
        queue = [(start, [start])]
        visited = set()
        receiver_set = set(self.gridmap.receiver_zones.values())

        while queue:
            (x, y), path = queue.pop(0)
            if (x, y) == goal:
                return path

            if (x, y) in visited:
                continue
            visited.add((x, y))

            for dx, dy in [(1, 0), (-1, 0), (0, 1), (0, -1)]:
                nx, ny = x + dx, y + dy
                if (
                    0 <= nx < w and 0 <= ny < h and
                    self.static_grid[ny, nx] == -1 and
                    (nx, ny) not in visited and
                    (nx, ny) not in receiver_set
                ):
                    queue.append(((nx, ny), path + [(nx, ny)]))

        return None

    def reset(self):
        self.rng = random.Random(FaultConfig.fault_seed)
        # ---------- Sync from FaultConfig ----------
        self.enable_faults = FaultConfig.enable_faults
        self.fault_prob = FaultConfig.fault_prob
        self.mean_repair_time = FaultConfig.mean_repair_time
        self.allow_multiple_faults = FaultConfig.allow_multiple_faults

        # ---------- Runtime State ----------
        self.active_faults: Dict[int, int] = {}
