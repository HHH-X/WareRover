from typing import Dict, Tuple, List
import heapq
from collections import defaultdict
from planner.base_planner import BasePlanner
from utils.simulation_context import SimulationContext

MAX_CBS_NODES = 800


class FixedWindowCBSPlanner(BasePlanner):
    def __init__(self, ctx: SimulationContext):
        super().__init__(ctx)
        self.window_size = 10
        self.env = ctx.env
        self.agv_manager = ctx.agv_manager
        self.warehouse_map = ctx.warehouse_map

    def plan(
        self,
        targets: Dict[int, Tuple[Tuple[int, int], Tuple[int, int]]],
        scheduler
    ) -> Dict[int, List[Tuple[int, int]]]:
        if not targets:
            return {}

        # Group by floor
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
        carrying_status = env_info["carrying_status"]
        action_queues = env_info["action_queues"]
        current_pos = env_info["current_grid_pos"]
        self.agv_sizes = env_info["agv_sizes"]

        full_paths = {
            agv_id: [current_pos[agv_id]] + path
            for agv_id, path in action_queues.items()
        }
        fixed_agents = {
            agv_id: path for agv_id, path in full_paths.items() if agv_id not in targets
        }
        window_paths = self._cbs_window(targets, carrying_status, fixed_agents)
        planned_paths = {}
        for agv_id, path in window_paths.items():
            if agv_id in targets:
                planned_paths[agv_id] = path[1:] if len(path) > 1 else []
        return planned_paths

    def _cbs_window(self, targets, carrying_status, fixed_agents):
        planning_agents = set(targets.keys())
        root = {'constraints': [], 'paths': {}, 'cost': 0}
        for agv_id, (start, goal) in targets.items():
            path = self._a_star_with_constraints(
                agv_id, start, goal, carrying_status.get(agv_id, False), [], goal
            )
            if path is None:
                path = [start]
            if len(path) == 1 and start == goal:
                if self._is_vertex_free(agv_id, start, 1, root['constraints']):
                    path = [start, start]
            root['paths'][agv_id] = path
            root['cost'] += len(path) - 1
        for agv_id, path in fixed_agents.items():
            root['paths'][agv_id] = path[:self.window_size + 1]

        open_list = []
        heapq.heappush(open_list, (root['cost'], 0, root))
        node_id = 1
        expanded_nodes = 0
        while open_list:
            expanded_nodes += 1
            if expanded_nodes >= MAX_CBS_NODES:
                break
            cost, _, node = heapq.heappop(open_list)
            conflict = self._detect_conflict(node['paths'], planning_agents, set(fixed_agents.keys()))
            if conflict is None:
                return node['paths']
            a1, a2, time, loc = conflict
            for agent, constraint in zip((a1, a2), self._build_constraints(a1, a2, time, loc)):
                if agent not in planning_agents:
                    continue
                child = {
                    'constraints': node['constraints'] + [constraint],
                    'paths': dict(node['paths']),
                    'cost': 0
                }
                start, goal = targets[agent]
                new_path = self._a_star_with_constraints(
                    agent, start, goal, carrying_status.get(agent, False), child['constraints'], goal
                )
                if new_path is None:
                    continue
                if len(new_path) == 1 and start == goal:
                    if self._is_vertex_free(agent, start, 1, child['constraints']):
                        new_path = [start, start]
                child['paths'][agent] = new_path
                child['cost'] = sum(len(p) - 1 for p in child['paths'].values() if p)
                heapq.heappush(open_list, (child['cost'], node_id, child))
                node_id += 1

        fallback = {}
        for agv_id, (start, goal) in targets.items():
            path = self._a_star_with_constraints(
                agv_id, start, goal, carrying_status.get(agv_id, False), [], goal
            )
            if path is None:
                path = [start]
            if len(path) == 1 and start == goal:
                if self._is_vertex_free(agv_id, start, 1, []):
                    path = [start, start]
            fallback[agv_id] = path
        return fallback

    def _a_star_with_constraints(self, agv_id, start, goal, carrying, constraints, true_goal):
        vertex_cons = defaultdict(set)
        edge_cons = defaultdict(set)
        for c in constraints:
            if c['agent'] != agv_id:
                continue
            t = c['time']
            if len(c['loc']) == 1:
                vertex_cons[t].add(tuple(c['loc'][0]))
            else:
                edge_cons[t].add((tuple(c['loc'][0]), tuple(c['loc'][1])))
        if self._occupied_cells(agv_id, start) & vertex_cons.get(0, set()):
            return None

        start_state = (start, 0)
        open_heap = []
        gscore = {start_state: 0}
        heapq.heappush(open_heap, (self._h(start, goal), 0, start_state, None))
        parents = {}
        closed = set()
        INF = 10**9
        while open_heap:
            f, g, (pos, t), parent = heapq.heappop(open_heap)
            if g > gscore.get((pos, t), INF):
                continue
            if self._occupied_cells(agv_id, pos) & vertex_cons.get(t, set()):
                continue
            parents[(pos, t)] = parent
            closed.add((pos, t))
            if pos == goal or t >= self.window_size:
                return self._reconstruct_path((pos, t), parents)

            if not (self._occupied_cells(agv_id, pos) & vertex_cons.get(t + 1, set())):
                succ = (pos, t + 1)
                ng = g + 1
                if gscore.get(succ, INF) > ng:
                    gscore[succ] = ng
                    heapq.heappush(open_heap, (ng + self._h(pos, goal), ng, succ, (pos, t)))

            for nb in self.env.get_walkable_neighbors(agv_id, pos, carrying):
                if self._occupied_cells(agv_id, nb) & vertex_cons.get(t + 1, set()):
                    continue
                if (pos, nb) in edge_cons.get(t, set()):
                    continue
                succ = (nb, t + 1)
                ng = g + 1
                if gscore.get(succ, INF) > ng:
                    gscore[succ] = ng
                    heapq.heappush(open_heap, (ng + self._h(nb, goal), ng, succ, (pos, t)))
        return None

    def _h(self, a, b):
        return abs(a[0] - b[0]) + abs(a[1] - b[1])

    def _reconstruct_path(self, state, parents):
        path = []
        cur = state
        while cur is not None:
            pos, t = cur
            path.append(pos)
            cur = parents.get(cur)
        path.reverse()
        return path

    def _detect_conflict(self, paths, planning_agents, fixed_agents):
        agents = set(paths.keys())
        max_len = max((len(paths[aid]) for aid in agents), default=0)
        for t in range(max_len):
            occupied_by = defaultdict(list)
            for agv_id, path in paths.items():
                if t >= len(path):
                    continue
                pos = path[t]
                for cell in self._occupied_cells(agv_id, pos):
                    occupied_by[cell].append(agv_id)
            for cell, agvs in occupied_by.items():
                if len(agvs) > 1:
                    conflicting = [a for a in agvs if a in planning_agents]
                    fixed_conflicting = [a for a in agvs if a in fixed_agents]
                    if len(conflicting) >= 2:
                        return conflicting[0], conflicting[1], t, [cell]
                    elif len(conflicting) == 1 and fixed_conflicting:
                        return conflicting[0], fixed_conflicting[0], t, [cell]
            if t > 0:
                ids = list(agents)
                for i in range(len(ids)):
                    for j in range(i + 1, len(ids)):
                        ai, aj = ids[i], ids[j]
                        if t >= len(paths[ai]) or t >= len(paths[aj]):
                            continue
                        prev_i, cur_i = paths[ai][t - 1], paths[ai][t]
                        prev_j, cur_j = paths[aj][t - 1], paths[aj][t]
                        if prev_i == cur_j and prev_j == cur_i and cur_i != cur_j:
                            if ai in fixed_agents and aj in fixed_agents:
                                continue
                            return ai, aj, t - 1, [prev_i, cur_i]
        return None

    def _build_constraints(self, a1, a2, time, loc):
        if len(loc) == 1:
            c1 = {'agent': a1, 'loc': [loc[0]], 'time': time}
            c2 = {'agent': a2, 'loc': [loc[0]], 'time': time}
        else:
            u, v = loc
            c1 = {'agent': a1, 'loc': [u, v], 'time': time}
            c2 = {'agent': a2, 'loc': [v, u], 'time': time}
        return c1, c2

    def _is_vertex_free(self, agv_id, pos, time, constraints):
        forbidden = set()
        for c in constraints:
            if c.get('agent') != agv_id:
                continue
            if c.get('time') == time and len(c.get('loc', [])) == 1:
                forbidden.add(tuple(c['loc'][0]))
        return self._occupied_cells(agv_id, pos) & forbidden == set()

    def _occupied_cells(self, agv_id, pos):
        size = self.agv_sizes.get(agv_id, 1)
        row, col = pos
        return {(row + dr, col + dc) for dr in range(size) for dc in range(size)}
