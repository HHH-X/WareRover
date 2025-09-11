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
        只规划窗口内的部分路径，确保规划结果在窗口内无冲突，
        同时参考其他AGV已有的action_queues，避免与它们发生冲突。
        """
        env_info = self.env.get_env_info()
        carrying_status = env_info["carrying_status"]
        action_queues = env_info["action_queues"]

        # 只对需要规划的AGV进行规划，其他AGV的路径固定为它们的action_queue
        fixed_agents = {
            agv_id: path for agv_id, path in action_queues.items() if agv_id not in targets
        }

        # 初始化返回结果
        planned_paths = {}

        # 运行一次窗口内的CBS
        window_paths = self._cbs_window(targets, carrying_status, fixed_agents)

        for agv_id, path in window_paths.items():
            planned_paths[agv_id] = path

        return planned_paths

    # ---------------- CBS for one window -----------------

    def _cbs_window(
        self,
        targets: Dict[int, Tuple[Tuple[int, int], Tuple[int, int]]],
        carrying_status: Dict[int, bool],
        fixed_agents: Dict[int, List[Tuple[int, int]]],
    ) -> Dict[int, List[Tuple[int, int]]]:
        # 初始化根节点：无约束，目标agent单独规划
        root = {
            'constraints': [],
            'paths': {},
            'cost': 0
        }
        for agv_id, (start, goal) in targets.items():
            path = self._a_star_with_constraints(agv_id, start, goal, carrying_status[agv_id], [], goal)
            if path is None:
                raise ValueError(f"Agent {agv_id} cannot find path")
            root['paths'][agv_id] = path
            root['cost'] += len(path) - 1

        # 加入固定agents的路径（来自action_queue，不做重规划）
        for agv_id, path in fixed_agents.items():
            root['paths'][agv_id] = path[: self.window_size + 1]

        open_list = []
        heapq.heappush(open_list, (root['cost'], 0, root))
        node_id = 1

        while open_list:
            cost, _, node = heapq.heappop(open_list)
            conflict = self._detect_conflict(node['paths'])
            if conflict is None:
                # 裁剪路径：只返回窗口大小的部分
                clipped = {}
                for agv_id, path in node['paths'].items():
                    clipped[agv_id] = path[: self.window_size + 1]
                return clipped

            a1, a2, time, loc = conflict
            for agent, constraint in zip((a1, a2), self._build_constraints(a1, a2, time, loc)):
                if agent in fixed_agents:
                    continue  # 不对固定AGV加约束
                child = {
                    'constraints': node['constraints'] + [constraint],
                    'paths': dict(node['paths']),
                    'cost': 0
                }
                start, goal = targets[agent]
                new_path = self._a_star_with_constraints(agent, start, goal, carrying_status[agent], child['constraints'], goal)
                if new_path is None:
                    continue
                child['paths'][agent] = new_path
                child['cost'] = sum(len(p) - 1 for p in child['paths'].values() if p)
                heapq.heappush(open_list, (child['cost'], node_id, child))
                node_id += 1

        raise ValueError("No conflict-free solution found in window")

    # ---------------- A* with constraints -----------------

    def _a_star_with_constraints(self, agv_id: int, start: Tuple[int, int], goal: Tuple[int, int], carrying: bool, constraints: List[Dict], true_goal: Tuple[int, int]) -> List[Tuple[int, int]]:
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
                return self._reconstruct_path((pos, t), parents)

            # 等待
            if pos not in vertex_cons.get(t + 1, set()):
                succ = (pos, t + 1)
                if succ not in closed:
                    ng = g + 1
                    if gscore.get(succ, 1e9) > ng:
                        gscore[succ] = ng
                        heapq.heappush(open_heap, (ng + self._h(pos, goal), ng, succ, (pos, t)))

            # 移动
            for nb in self.env.get_walkable_neighbors(pos, carrying):
                if nb in vertex_cons.get(t + 1, set()):
                    continue
                if (pos, nb) in edge_cons.get(t + 1, set()):
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

    def _detect_conflict(self, paths: Dict[int, List[Tuple[int, int]]]):
        max_len = max(len(p) for p in paths.values())
        ids = list(paths.keys())
        for t in range(max_len):
            positions = {}
            for agv_id in ids:
                pos = paths[agv_id][t] if t < len(paths[agv_id]) else paths[agv_id][-1]
                if pos in positions:
                    return positions[pos], agv_id, t, [pos]
                positions[pos] = agv_id

            if t > 0:
                for i in range(len(ids)):
                    for j in range(i + 1, len(ids)):
                        ai, aj = ids[i], ids[j]
                        prev_i = paths[ai][t - 1] if t - 1 < len(paths[ai]) else paths[ai][-1]
                        cur_i = paths[ai][t] if t < len(paths[ai]) else paths[ai][-1]
                        prev_j = paths[aj][t - 1] if t - 1 < len(paths[aj]) else paths[aj][-1]
                        cur_j = paths[aj][t] if t < len(paths[aj]) else paths[aj][-1]
                        if prev_i == cur_j and prev_j == cur_i and cur_i != cur_j:
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
