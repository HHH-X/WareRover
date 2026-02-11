import heapq
from typing import Dict, Tuple, List, Set
from collections import defaultdict
from core.env import Env
from core.gridmap import GridMap
from core.ordermanager import OrderManager
from core.fault_manager import FaultManager
from core.agvmanager import AGVManager
from planner.base_planner import BasePlanner

MAX_ASTAR_NODES = 800

class AStarPlanner(BasePlanner):
    def __init__(
        self, 
        env: Env,
        agv_manager: AGVManager,
        order_manager: OrderManager, 
        map: GridMap,
        fault_manager: FaultManager
    ):
        super().__init__(env, agv_manager, order_manager, map, fault_manager)
        self.max_time = 100
        env_info = self.env.get_env_info()
        self.agv_sizes = env_info['agv_sizes']

    def plan(self, targets: Dict[int, Tuple[Tuple[int, int], Tuple[int, int]]], scheduler) -> Dict[int, List[Tuple[int, int]]]:
        """
        Centralized path planning using A* with a reservation table (avoids vertex and edge conflicts).
        Args: targets {agv_id: (start_pos, target_pos)}. Returns: {agv_id: path} (path excludes start).
        """
        if not targets:
            return {}
        env_info = self.env.get_env_info()
        current_paths = env_info['action_queues']
        carrying_status = env_info['carrying_status']
        reservation_table = self._build_reservation_table(current_paths)

        paths = {}
        for agv_id, (start, goal) in targets.items():
            carrying = carrying_status.get(agv_id, False)
            path = self._a_star_with_reservation(
                agv_id, start, goal, carrying, reservation_table
            )
            if path:
                paths[agv_id] = path[1:] if len(path) > 1 else []
                self._add_to_reservation_table(agv_id, reservation_table, path)
            else:
                paths[agv_id] = [start]
        return paths

    def _build_reservation_table(
        self, current_paths: Dict[int, List[Tuple[int, int]]],
    ) -> Dict[int, Set[Tuple[int, int]]]:
        """Build reservation table: time step -> set of occupied cells (AGV size-aware)."""
        table = defaultdict(set)
        for agv_id, path in current_paths.items():
            for t, pos in enumerate(path):
                occupied = self._get_occupied_cells(agv_id, pos)
                for cell in occupied:
                    table[t].add(cell)
        return table

    def _add_to_reservation_table(
        self, agv_id: int,
        table: Dict[int, Set[Tuple[int, int]]],
        path: List[Tuple[int, int]]
    ):
        """Add a new path to the reservation table (AGV size-aware)."""
        for t, pos in enumerate(path):
            occupied = self._get_occupied_cells(agv_id, pos)
            for cell in occupied:
                table[t].add(cell)

    def _a_star_with_reservation(self, agv_id: int, start: Tuple[int, int], goal: Tuple[int, int],
                                 carrying: bool, reservation_table: Dict[int, Set[Tuple[int, int]]]
                                 ) -> List[Tuple[int, int]]:
        """A* with reservation table to avoid vertex and swap conflicts."""
        open_set = []
        heapq.heappush(open_set, (0 + self._heuristic(start, goal), 0, start, [start]))
        closed_set = set()
        expanded_nodes = 0
        while open_set:
            expanded_nodes += 1
            if expanded_nodes >= MAX_ASTAR_NODES:
                break
            f, g, current, path = heapq.heappop(open_set)
            if (current, g) in closed_set:
                continue
            closed_set.add((current, g))

            if current == goal and self._is_free(agv_id, current, g + 1, reservation_table) and self._is_free(agv_id, current, g + 2, reservation_table):
                return path + [goal] * 2

            for neighbor in self.env.get_walkable_neighbors(agv_id, current, carrying):
                if not self._is_free(agv_id, neighbor, g + 1, reservation_table):
                    continue
                if self._is_edge_conflict(agv_id, current, neighbor, g + 1, reservation_table):
                    continue

                new_path = path + [neighbor]
                heapq.heappush(open_set, (g + 1 + self._heuristic(neighbor, goal), g + 1, neighbor, new_path))

            if g > self.max_time:
                break
        return None

    def _heuristic(self, a: Tuple[int, int], b: Tuple[int, int]) -> int:
        """Manhattan distance heuristic."""
        return abs(a[0] - b[0]) + abs(a[1] - b[1])

    def _is_free(self, agv_id: int, pos: Tuple[int, int],
                 t: int, reservation_table: Dict[int, Set[Tuple[int, int]]]
                 ) -> bool:
        """True if at time t the AGV at top-left pos and its occupied cells are all free in the table."""
        for cell in self._get_occupied_cells(agv_id, pos):
            if cell in reservation_table.get(t, set()):
                return False
        return True

    def _is_edge_conflict(self, agv_id: int, from_pos: Tuple[int, int], to_pos: Tuple[int, int], t: int,
                      reservation_table: Dict[int, Set[Tuple[int, int]]]
                      ) -> bool:
        """Edge/swap conflict: from_pos occupied at t and to_pos occupied at t-1 overlap with table."""
        occ_from_t = self._get_occupied_cells(agv_id, from_pos)
        occ_to_tminus1 = self._get_occupied_cells(agv_id, to_pos)
        conflict_now = any(cell in reservation_table.get(t, set()) for cell in occ_from_t)
        conflict_prev = any(cell in reservation_table.get(t - 1, set()) for cell in occ_to_tminus1)
        return conflict_now and conflict_prev

    def _get_occupied_cells(self, agv_id: int, top_left: Tuple[int, int]) -> set[Tuple[int, int]]:
        """Return set of grid cells occupied by this AGV given its top-left and size."""
        size = self.agv_sizes.get(agv_id, 1)
        x, y = top_left
        return {(x + dx, y + dy) for dx in range(size) for dy in range(size)}

