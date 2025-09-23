from abc import ABC
from typing import Dict, Tuple, List
import heapq
from collections import defaultdict
from planner.base_planner import BasePlanner
from core.env import Env


class FixedWindowCBSPlanner(BasePlanner):
    def __init__(self, env_instance: Env, window_size: int = 10):
        super().__init__(env_instance)
        self.window_size = window_size

    def plan(self, targets: Dict[int, Tuple[Tuple[int, int], Tuple[int, int]]]) -> Dict[int, List[Tuple[int, int]]]:
        """
        使用固定窗口 CBS 进行集中式路径规划。
        """
        env_info = self.env.get_env_info()
        carrying_status = env_info["carrying_status"]
        action_queues = env_info["action_queues"]
        current_pos = env_info["current_grid_pos"]

        # 拼接 start + action_queue，得到完整路径
        full_paths = {
            agv_id: [current_pos[agv_id]] + path
            for agv_id, path in action_queues.items()
        }

        # 非目标AGV的路径固定为 full_paths
        fixed_agents = {
            agv_id: path for agv_id, path in full_paths.items() if agv_id not in targets
        }

        # 运行一次窗口内的CBS
        window_paths = self._cbs_window(targets, carrying_status, fixed_agents)

        # 返回结果时去掉 start（保证只返回 action_queues 风格）
        planned_paths = {}
        for agv_id, path in window_paths.items():
            if agv_id in targets:
                planned_paths[agv_id] = path[1:] if len(path) > 1 else []

        return planned_paths

    # ---------------- CBS for one window -----------------

    def _cbs_window(
        self,
        targets: Dict[int, Tuple[Tuple[int, int], Tuple[int, int]]],
        carrying_status: Dict[int, bool],
        fixed_agents: Dict[int, List[Tuple[int, int]]],
    ) -> Dict[int, List[Tuple[int, int]]]:
        planning_agents = set(targets.keys())

        # 初始化根节点
        root = {
            'constraints': [],
            'paths': {},
            'cost': 0
        }
        for agv_id, (start, goal) in targets.items():
            path = self._a_star_with_constraints(
                agv_id, start, goal, carrying_status[agv_id], [], goal
            )
            if path is None:
                path = [start]  # 退化路径
            root['paths'][agv_id] = path
            root['cost'] += len(path) - 1

        # 加入固定agents的路径（截取窗口大小）
        for agv_id, path in fixed_agents.items():
            root['paths'][agv_id] = path[: self.window_size + 1]

        open_list = []
        heapq.heappush(open_list, (root['cost'], 0, root))
        node_id = 1

        while open_list:
            cost, _, node = heapq.heappop(open_list)
            conflict = self._detect_conflict(node['paths'], planning_agents, set(fixed_agents.keys()))
            if conflict is None:
                return node['paths']  # 直接返回完整路径

            a1, a2, time, loc = conflict

            # 只给 planning_agents 加约束
            for agent, constraint in zip((a1, a2), self._build_constraints(a1, a2, time, loc)):
                if agent not in planning_agents:
                    continue  # fixed_agents 永远不加约束
                child = {
                    'constraints': node['constraints'] + [constraint],
                    'paths': dict(node['paths']),
                    'cost': 0
                }
                start, goal = targets[agent]
                new_path = self._a_star_with_constraints(
                    agent, start, goal, carrying_status[agent], child['constraints'], goal
                )
                if new_path is None:
                    continue
                child['paths'][agent] = new_path
                child['cost'] = sum(len(p) - 1 for p in child['paths'].values() if p)
                heapq.heappush(open_list, (child['cost'], node_id, child))
                node_id += 1

        # CBS 搜索失败，退化返回独立路径
        fallback = {}
        for agv_id, (start, goal) in targets.items():
            path = self._a_star_with_constraints(
                agv_id, start, goal, carrying_status[agv_id], [], goal
            )
            if path is None:
                path = [start]
            fallback[agv_id] = path
        return fallback

    # ---------------- A* with constraints -----------------

    def _a_star_with_constraints(
        self,
        agv_id: int,
        start: Tuple[int, int],
        goal: Tuple[int, int],
        carrying: bool,
        constraints: List[Dict],
        true_goal: Tuple[int, int]
    ) -> List[Tuple[int, int]]:
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

        start_state = (start, 0)
        open_heap = []
        gscore = {start_state: 0}
        heapq.heappush(open_heap, (self._h(start, goal), 0, start_state, None))
        parents = {}

        closed = set()
        while open_heap:
            f, g, (pos, t), parent = heapq.heappop(open_heap)
            if (pos, t) in closed:
                continue
            parents[(pos, t)] = parent
            closed.add((pos, t))

            if pos == goal or t >= self.window_size:
                path = self._reconstruct_path((pos, t), parents)
                return path

            # 等待
            if pos not in vertex_cons.get(t, set()):
                succ = (pos, t + 1)
                if succ not in closed:
                    ng = g + 1
                    if gscore.get(succ, 1e9) > ng:
                        gscore[succ] = ng
                        heapq.heappush(open_heap, (ng + self._h(pos, goal), ng, succ, (pos, t)))

            # 移动
            for nb in self.env.get_walkable_neighbors(pos, carrying):
                if nb in vertex_cons.get(t, set()):
                    continue
                if (pos, nb) in edge_cons.get(t, set()):
                    continue
                succ = (nb, t + 1)
                if succ not in closed:
                    ng = g + 1
                    if gscore.get(succ, 1e9) > ng:
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

    # ---------------- Conflict detection -----------------
    def _detect_conflict(self, paths: Dict[int, List[Tuple[int, int]]], planning_agents: set, fixed_agents: set):
        agents = set(paths.keys())
        max_len = max((len(paths[aid]) for aid in agents), default=0)

        for t in range(max_len):
            positions = {}
            for agv_id, path in paths.items():
                if t >= len(path):
                    continue
                pos = path[t]
                if pos in positions:
                    other = positions[pos]
                    if agv_id in fixed_agents and other in fixed_agents:
                        continue
                    return other, agv_id, t, [pos]
                positions[pos] = agv_id

            # 边冲突
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
                            return ai, aj, t, [prev_i, cur_i]
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
