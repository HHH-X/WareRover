# core/fault_manager.py
from __future__ import annotations

from typing import Optional, Dict, Tuple, List, TYPE_CHECKING
import random

from core.gridmap import CellType

if TYPE_CHECKING:
    from utils.simulation_context import SimulationContext


class FaultManager:
    def __init__(self, ctx: SimulationContext):
        assert (
            ctx.system_config is not None
            and ctx.agv_manager is not None
            and ctx.env is not None
            and ctx.warehouse_map is not None
        )
        self.fault_config = ctx.system_config.fault_config
        self.agv_manager = ctx.agv_manager
        self.warehouse_map = ctx.warehouse_map
        self.env = ctx.env
        self.logger = ctx.logger
        self.clock = ctx.clock
        self.reset()

    def _get_floor_grid(self, agv_id: int):
        fid = self.agv_manager.get_agv_floor(agv_id)
        return self.warehouse_map.get_floor(fid)

    def step(self):
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
        cmd = msg.get("cmd")
        agv_id = msg.get("agv_id")
        print(f"[FaultManager] Handling command: {msg}")
        if cmd == "damage":
            self.simulate_fault(agv_id)
        elif cmd == "repair":
            self.repair_agv(agv_id)
        print("Command processed.")

    def simulate_fault(self, agv_id: int):
        self.agv_manager.set_agv_status(agv_id, False)
        gridmap = self._get_floor_grid(agv_id)
        agv_grid_pos = self.agv_manager.get_agv(agv_id).grid_pos
        border_cell = self._find_nearest_border_free_cell(agv_grid_pos, gridmap)
        path = self._plan_repair_path(agv_grid_pos, border_cell, gridmap)
        gridmap.add_dynamic_occupancy(str(agv_id), path)
        self.logger.add_runtime_log(f"[FaultManager] AGV {agv_id} failed at step {self.clock.now()}")

    def repair_agv(self, agv_id: int):
        self.agv_manager.set_agv_status(agv_id, True)
        gridmap = self._get_floor_grid(agv_id)
        gridmap.remove_dynamic_occupancy(str(agv_id))
        self.logger.add_runtime_log(f"[FaultManager] AGV {agv_id} repaired at step {self.clock.now()}")

    def _find_nearest_border_free_cell(self, start, gridmap):
        h, w = gridmap.type_grid.shape
        visited = set()
        queue = [start]
        receiver_set = set(gridmap.receiver_zones.values())

        while queue:
            row, col = queue.pop(0)
            if (row, col) in visited:
                continue
            visited.add((row, col))
            if (gridmap.type_grid[row, col] == CellType.FREE and
                    (row == 0 or col == 0 or row == h - 1 or col == w - 1)):
                if (row, col) not in receiver_set:
                    return (row, col)
            for dr, dc in [(1, 0), (-1, 0), (0, 1), (0, -1)]:
                nr, nc = row + dr, col + dc
                if (0 <= nr < h and 0 <= nc < w and
                        gridmap.type_grid[nr, nc] == CellType.FREE and
                        (nr, nc) not in visited and
                        (nr, nc) not in receiver_set):
                    queue.append((nr, nc))
        return None

    def _plan_repair_path(self, start, goal, gridmap):
        h, w = gridmap.type_grid.shape
        queue = [(start, [start])]
        visited = set()
        receiver_set = set(gridmap.receiver_zones.values())

        while queue:
            (row, col), path = queue.pop(0)
            if (row, col) == goal:
                return path
            if (row, col) in visited:
                continue
            visited.add((row, col))
            for dr, dc in [(1, 0), (-1, 0), (0, 1), (0, -1)]:
                nr, nc = row + dr, col + dc
                if (0 <= nr < h and 0 <= nc < w and
                        gridmap.type_grid[nr, nc] == CellType.FREE and
                        (nr, nc) not in visited and
                        (nr, nc) not in receiver_set):
                    queue.append(((nr, nc), path + [(nr, nc)]))
        return None

    def reset(self):
        self.rng = random.Random(self.fault_config.fault_seed)
        self.enable_faults = self.fault_config.enable_faults
        self.fault_prob = self.fault_config.fault_prob
        self.mean_repair_time = self.fault_config.mean_repair_time
        self.allow_multiple_faults = self.fault_config.allow_multiple_faults
        self.active_faults: Dict[int, int] = {}
