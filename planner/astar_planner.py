import heapq
from typing import Dict, Tuple, List, Set
from collections import defaultdict
from planner.base_planner import BasePlanner
from utils.simulation_context import SimulationContext

MAX_ASTAR_NODES = 800


class AStarPlanner(BasePlanner):
    def __init__(self, ctx: SimulationContext):
        super().__init__(ctx)
        self.env = ctx.env
        self.agv_manager = ctx.agv_manager
        self.warehouse_map = ctx.warehouse_map
        self.max_time = 100

    def plan(self, targets: Dict[int, Tuple[Tuple[int, int], Tuple[int, int]]], scheduler) -> Dict[int, List[Tuple[int, int]]]:
        if not targets:
            return {}

        # Group targets by floor and plan per-floor
        floor_targets: Dict[int, Dict[int, Tuple]] = defaultdict(dict)
        for agv_id, (start, goal) in targets.items():
            fid = self.agv_manager.get_agv_floor(agv_id)
            floor_targets[fid][agv_id] = (start, goal)

        all_paths = {}
        for fid, ftargets in floor_targets.items():
            floor_paths = self._plan_floor(fid, ftargets)
            all_paths.update(floor_paths)
        return all_paths

    def _plan_floor(self, floor_id: int, targets: Dict[int, Tuple]) -> Dict[int, List[Tuple[int, int]]]:
        env_info = self.env.get_env_info_for_floor(floor_id)
        current_paths = env_info['action_queues']
        carrying_status = env_info['carrying_status']
        agv_sizes = env_info['agv_sizes']

        reservation_table = self._build_reservation_table(current_paths, agv_sizes)

        paths = {}
        for agv_id, (start, goal) in targets.items():
            carrying = carrying_status.get(agv_id, False)
            path = self._a_star_with_reservation(
                agv_id, start, goal, carrying, reservation_table, agv_sizes
            )
            if path:
                paths[agv_id] = path[1:] if len(path) > 1 else []
                self._add_to_reservation_table(agv_id, reservation_table, path, agv_sizes)
            else:
                paths[agv_id] = [start]
        return paths

    def _build_reservation_table(
        self, current_paths: Dict[int, List[Tuple[int, int]]],
        agv_sizes: Dict[int, int]
    ) -> Dict[int, Set[Tuple[int, int]]]:
        table = defaultdict(set)
        for agv_id, path in current_paths.items():
            for t, pos in enumerate(path):
                for cell in self._get_occupied_cells(agv_id, pos, agv_sizes):
                    table[t].add(cell)
        return table

    def _add_to_reservation_table(
        self, agv_id: int,
        table: Dict[int, Set[Tuple[int, int]]],
        path: List[Tuple[int, int]],
        agv_sizes: Dict[int, int]
    ):
        for t, pos in enumerate(path):
            for cell in self._get_occupied_cells(agv_id, pos, agv_sizes):
                table[t].add(cell)

    def _a_star_with_reservation(self, agv_id: int, start: Tuple[int, int], goal: Tuple[int, int],
                                 carrying: bool, reservation_table: Dict[int, Set[Tuple[int, int]]],
                                 agv_sizes: Dict[int, int]) -> List[Tuple[int, int]]:
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

            if current == goal and self._is_free(agv_id, current, g + 1, reservation_table, agv_sizes) and self._is_free(agv_id, current, g + 2, reservation_table, agv_sizes):
                return path + [goal] * 2

            for neighbor in self.env.get_walkable_neighbors(agv_id, current, carrying):
                if not self._is_free(agv_id, neighbor, g + 1, reservation_table, agv_sizes):
                    continue
                if self._is_edge_conflict(agv_id, current, neighbor, g + 1, reservation_table, agv_sizes):
                    continue
                new_path = path + [neighbor]
                heapq.heappush(open_set, (g + 1 + self._heuristic(neighbor, goal), g + 1, neighbor, new_path))

            if g > self.max_time:
                break
        return None

    def _heuristic(self, a: Tuple[int, int], b: Tuple[int, int]) -> int:
        return abs(a[0] - b[0]) + abs(a[1] - b[1])

    def _is_free(self, agv_id: int, pos: Tuple[int, int],
                 t: int, reservation_table: Dict[int, Set[Tuple[int, int]]],
                 agv_sizes: Dict[int, int]) -> bool:
        for cell in self._get_occupied_cells(agv_id, pos, agv_sizes):
            if cell in reservation_table.get(t, set()):
                return False
        return True

    def _is_edge_conflict(self, agv_id: int, from_pos: Tuple[int, int], to_pos: Tuple[int, int],
                          t: int, reservation_table: Dict[int, Set[Tuple[int, int]]],
                          agv_sizes: Dict[int, int]) -> bool:
        occ_from_t = self._get_occupied_cells(agv_id, from_pos, agv_sizes)
        occ_to_tminus1 = self._get_occupied_cells(agv_id, to_pos, agv_sizes)
        conflict_now = any(cell in reservation_table.get(t, set()) for cell in occ_from_t)
        conflict_prev = any(cell in reservation_table.get(t - 1, set()) for cell in occ_to_tminus1)
        return conflict_now and conflict_prev

    def _get_occupied_cells(self, agv_id: int, top_left: Tuple[int, int],
                            agv_sizes: Dict[int, int]) -> set[Tuple[int, int]]:
        size = agv_sizes.get(agv_id, 1)
        row, col = top_left
        return {(row + dr, col + dc) for dr in range(size) for dc in range(size)}
