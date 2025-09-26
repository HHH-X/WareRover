from abc import ABC
from typing import Dict, Tuple, List, Optional, Any
import heapq
from collections import defaultdict, deque
import math
import copy
from planner.base_planner import BasePlanner
from core.env import Env
import time

# ---------------------------------------------------------------------
# Helper datatypes:
# Action representation:
# - MoveAction: ('move', from_pos, to_pos, start_time, duration)
# - WaitAction: ('wait', pos, start_time, duration)
# Trajectory (per agent) is List[action], actions are executed sequentially.
# For external compatibility we also provide to_timed_waypoints(traj) -> List[(pos, t)]
# ---------------------------------------------------------------------


def euclid(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def clamp(x, a, b):
    return max(a, min(b, x))


class ContinuousCBSPlanner(BasePlanner):
    def __init__(
        self,
        env_instance: Env,
        time_horizon: float = 20.0,
        time_resolution: float = 0.25,
        unsafe_search_step: float = 0.05,
        max_ccbs_nodes: int = 10000
    ):
        """
        env_instance: 你的 Env 实例（需要提供下面使用的方法）
        time_horizon: 在单次 plan 中搜索的最大时间（秒）
        time_resolution: SIPP 的时间离散化精度（用于 safe interval 划分与 A* 的启发）
        unsafe_search_step: 在计算 unsafe interval 时的采样步长（数值搜索）
        """
        super().__init__(env_instance)
        self.time_horizon = time_horizon
        self.dt = time_resolution
        self.unsafe_step = unsafe_search_step
        self.max_ccbs_nodes = max_ccbs_nodes

    # ---------------- 主入口 ----------------
    def plan(self, targets: Dict[int, Tuple[Tuple[float, float], Tuple[float, float]]]) -> Dict[int, List[Tuple[Tuple[float, float], float]]]:
        """
        targets: {agv_id: (start_pos, goal_pos)}, positions are floats (x,y) in roadmap vertices
        返回: {agv_id: [(pos, t), (pos, t), ...] } — 每个为时间标注的路径点（pos: (x,y), t: float）
        """
        env_info = self.env.get_env_info()
        carrying_status = env_info.get("carrying_status", {})
        current_pos = env_info.get("current_grid_pos")  # assume dict agv->(x,y) (can be float)
        # for agents not in targets we treat as fixed (their planned trajectories are respected)
        # assume env provides method to get existing action_queues as timed trajectories (best-effort)
        existing_queues = env_info.get("action_queues_timed", {})  # prefer timed format
        fixed_agents = {}
        for agv_id, traj in existing_queues.items():
            if agv_id not in targets:
                fixed_agents[agv_id] = traj  # already timed actions expected

        planning_agents = set(targets.keys())

        # Root: compute initial SIPP plan for each planning agent ignoring others (but respecting fixed agents as dynamic obstacles)
        root = {
            'constraints': [],   # list of constraints: dict with keys ('agent','action','start','end') - action encoded as ('move',u,v) or ('wait',v)
            'plans': {},         # agent -> trajectory (list of actions)
            'cost': 0.0
        }

        # Prebuild dynamic obstacles from fixed_agents as timed segment trajectories to compute safe intervals
        dynamic_obs = fixed_agents  # use as-is

        for agv_id, (start, goal) in targets.items():
            # agent model: try to get speed and radius from env
            spd = self._get_agent_speed(agv_id)
            rad = self._get_agent_radius(agv_id)
            traj = self._sipp_for_agent(
                agv_id, start, goal, spd, rad, dynamic_obs, constraints=[]
            )
            if traj is None:
                # fallback: immediate wait at start for dt increments until horizon
                traj = [('wait', start, 0.0, self.dt)]
            root['plans'][agv_id] = traj
            root['cost'] += self._traj_cost(traj)

        # include fixed agents' plans in root
        for agv_id, traj in fixed_agents.items():
            root['plans'][agv_id] = traj

        # CT search (best-first by cost)
        open_heap = []
        heapq.heappush(open_heap, (root['cost'], 0, root))
        node_counter = 1
        expanded = 0

        while open_heap and expanded < self.max_ccbs_nodes:
            _, _, node = heapq.heappop(open_heap)
            expanded += 1

            conflict = self._detect_conflict_in_plans(node['plans'])
            if conflict is None:
                # success: convert each plan to timed waypoints
                result = {}
                for agv, traj in node['plans'].items():
                    result[agv] = self._trajectory_to_waypoints(traj)
                return result

            # conflict: (ag1, act1, t1), (ag2, act2, t2)  where act is ('move',u,v) or ('wait',v)
            (a1, act1, t1), (a2, act2, t2) = conflict

            # compute unsafe intervals for each action w.r.t other action (numerical)
            tui_1 = self._compute_unsafe_interval(a1, act1, t1, a2, act2, t2)
            tui_2 = self._compute_unsafe_interval(a2, act2, t2, a1, act1, t1)

            # two child nodes: forbid a1 in its unsafe interval, or forbid a2 in its unsafe interval
            children = []
            for agent, act, (st, ed) in [(a1, act1, tui_1), (a2, act2, tui_2)]:
                # build a constraint record
                constraint = {
                    'agent': agent,
                    'action': act,  # the action signature to be forbidden
                    'start': st,
                    'end': ed
                }
                child = {
                    'constraints': node['constraints'] + [constraint],
                    'plans': dict(node['plans']),
                    'cost': 0.0
                }
                # replan only for the constrained agent
                # build dynamic obstacles from other agents' current plans
                dynamic_obs_child = {}
                for other, p in child['plans'].items():
                    if other == agent:
                        continue
                    dynamic_obs_child[other] = p

                spd = self._get_agent_speed(agent)
                rad = self._get_agent_radius(agent)
                start_pos, goal_pos = targets[agent]
                # collect relevant constraints for this agent
                cons_for_agent = [c for c in child['constraints'] if c['agent'] == agent]

                new_traj = self._sipp_for_agent(agent, start_pos, goal_pos, spd, rad, dynamic_obs_child, cons_for_agent)
                if new_traj is None:
                    # infeasible child
                    continue
                child['plans'][agent] = new_traj
                child['cost'] = sum(self._traj_cost(tr) for tr in child['plans'].values())
                children.append(child)

            for ch in children:
                heapq.heappush(open_heap, (ch['cost'], node_counter, ch))
                node_counter += 1

        # failure -> return best-effort current root plans (timed waypoints)
        fallback = {}
        for agv, traj in root['plans'].items():
            fallback[agv] = self._trajectory_to_waypoints(traj)
        return fallback

    # ---------------- SIPP-like low-level planner ----------------
    def _sipp_for_agent(
        self,
        agv_id: int,
        start: Tuple[float, float],
        goal: Tuple[float, float],
        speed: float,
        radius: float,
        dynamic_obstacles: Dict[int, List[Any]],
        constraints: List[Dict]
    ) -> Optional[List[Tuple]]:
        """
        A simplified SIPP on roadmap vertices (obtained from env).
        - dynamic_obstacles: other agents' current planned trajectories, used to compute safe intervals
        - constraints: list of constraints for this agent (forbidden action+time-intervals)
        Return: trajectory = list of actions: ('move', u, v, start_time, duration) or ('wait', v, start_time, duration)
        NOTE: For simplicity we run a time-augmented A* that uses safe-intervals sampled every dt.
        """
        # get roadmap neighbors (assume env.get_neighbors returns geometric neighbors)
        # We'll run SIPP on vertices provided by env.get_roadmap_vertices() or env.get_all_vertices()
        try:
            vertices = self.env.get_all_vertices()
        except Exception:
            # fallback: use start and goal + neighbors
            vertices = [start, goal]

        # prepare safe intervals per vertex (sample on [0, time_horizon] with step dt and mark times when vertex is safe)
        samples = int(math.ceil(self.time_horizon / self.dt)) + 1
        time_samples = [i * self.dt for i in range(samples)]

        vertex_safe = {}  # vertex -> list of (t_start, t_end) safe intervals
        # for each vertex, mark unsafe times if any dynamic obstacle occupies it (or collides while waiting)
        for v in vertices:
            unsafe_marks = [False] * samples
            # check dynamic obstacles for collisions with a wait action at v at time t
            for other_id, other_traj in dynamic_obstacles.items():
                for t_idx, t in enumerate(time_samples):
                    # represent wait at exact time t as point pos v at time t
                    if self._point_collides_with_trajectory_point(v, t, other_traj, radius, self._get_agent_radius(other_id)):
                        unsafe_marks[t_idx] = True
            # apply own constraints that ban waiting at v during intervals
            for c in constraints:
                if c['action'][0] == 'wait' and self._same_pos(c['action'][1], v):
                    # constraint forbids waits in [start,end)
                    s_idx = int(math.floor(c['start'] / self.dt))
                    e_idx = int(math.ceil(c['end'] / self.dt))
                    for k in range(max(0, s_idx), min(samples, e_idx)):
                        unsafe_marks[k] = True
            # convert unsafe_marks to safe intervals
            safe_intervals = []
            i = 0
            while i < samples:
                if not unsafe_marks[i]:
                    j = i
                    while j + 1 < samples and not unsafe_marks[j + 1]:
                        j += 1
                    safe_intervals.append((time_samples[i], min(self.time_horizon, time_samples[j] + self.dt)))
                    i = j + 1
                else:
                    i += 1
            vertex_safe[v] = safe_intervals

        # low-level nodes: (vertex, interval_index, entry_time)
        # initial possible intervals at start: any safe interval that includes t=0
        start_intervals = []
        for idx, (s, e) in enumerate(vertex_safe.get(start, [(0.0, self.time_horizon)])):
            if s <= 0.0 < e:
                start_intervals.append((start, idx, 0.0))

        if not start_intervals:
            # cannot occupy start at t=0
            return None

        # A* over (v, interval_idx, time)
        def heuristic(v):
            # Euclidean / speed
            return euclid(v, goal) / max(1e-6, speed)

        open_heap = []
        gscore = {}  # key: (v, idx, entry_t) simplified to (v, idx) -> best_entry_time
        parents = {}

        # push starts (choose earliest entry time 0)
        for (v, idx, entry_t) in start_intervals:
            key = (v, idx)
            gscore[key] = 0.0
            f = heuristic(v) + 0.0
            heapq.heappush(open_heap, (f, 0.0, v, idx, entry_t, None))  # store parent as None

        max_expansions = 100000
        expansions = 0
        while open_heap and expansions < max_expansions:
            f, g, v, idx, entry_t, parent = heapq.heappop(open_heap)
            key = (v, idx)
            if g > gscore.get(key, 1e18):
                continue
            # record parent
            parents[(v, idx, entry_t)] = parent

            # check goal: if we can be at vertex==goal within this safe interval
            s_int, e_int = vertex_safe.get(v, [(0.0, self.time_horizon)])[idx]
            # if vertex is goal, we can finish at earliest entry time
            if self._same_pos(v, goal):
                # build path by reconstructing and turning into actions
                return self._reconstruct_trajectory_from_parents((v, idx, entry_t), parents, vertex_safe, speed)

            # expand: two kinds of transitions:
            # 1) wait inside this interval until some tnext (but respecting any wait-forbidden constraints)
            # We'll consider waiting to the end of this safe interval, then transitions.
            expansions += 1

            # try moving to neighbors in roadmap
            neighbors = self.env.get_walkable_neighbors(v, carrying=False)  # assume returns list of neighbor vertices (positions)
            for nb in neighbors:
                # compute travel time
                dist = euclid(v, nb)
                travel_t = dist / max(1e-6, speed)
                # we try earliest departure time >= entry_t such that:
                # - departure_time in [s_int, e_int)
                # - arrival_time = departure_time + travel_t falls into some safe interval of nb
                # - no constraint forbids performing ('move', v, nb) at departure time
                # We'll scan departure_time candidates from entry_t to e_int step dt
                departure = max(entry_t, s_int)
                feasible_found = False
                arrival_candidate = None
                while departure + travel_t <= self.time_horizon and departure < e_int + 1e-9:
                    # check forbidden move constraints
                    if self._violates_move_constraints(constraints, ('move', v, nb), departure):
                        departure += self.dt
                        continue
                    arrival = departure + travel_t
                    # check collision with dynamic obstacles along this continuous segment
                    if self._segment_collides_with_dynamic(nb, v, departure, arrival, dynamic_obstacles, radius, agv_id):
                        departure += self.dt
                        continue
                    # check nb safe intervals: arrival must be inside some safe interval
                    nb_intervals = vertex_safe.get(nb, [])
                    found_idx = None
                    for nb_idx, (ns, ne) in enumerate(nb_intervals):
                        if ns - 1e-9 <= arrival <= ne + 1e-9:
                            found_idx = nb_idx
                            break
                    if found_idx is not None:
                        # accept
                        ng = g + (departure - entry_t) + travel_t
                        key2 = (nb, found_idx)
                        prev_best = gscore.get(key2, 1e18)
                        if ng + 1e-9 < prev_best:
                            gscore[key2] = ng
                            parents[(nb, found_idx, arrival)] = (v, idx, entry_t)
                            heapq.heappush(open_heap, (ng + heuristic(nb), ng, nb, found_idx, arrival, (v, idx, entry_t)))
                        feasible_found = True
                        break
                    # else try later departure
                    departure += self.dt
                # end while scanning departure

            # also consider waiting until end of safe interval and staying there (if not forbidden)
            # if waiting is not forbidden by a constraint
            if not self._violates_wait_constraints(constraints, ('wait', v), entry_t, e_int):
                # waiting to end of interval then we can attempt transitions at time e_int
                # push state (v, same or next interval) with entry time = e_int (if e_int < horizon)
                next_time = e_int
                # find interval index for v that contains next_time (it might be same if e_int slightly less than next sample)
                intervals = vertex_safe.get(v, [])
                chosen_idx = None
                for idx2, (s2, e2) in enumerate(intervals):
                    if s2 - 1e-9 <= next_time <= e2 + 1e-9:
                        chosen_idx = idx2
                        break
                if chosen_idx is not None:
                    key2 = (v, chosen_idx)
                    ng = g + (next_time - entry_t)
                    if ng + 1e-9 < gscore.get(key2, 1e18):
                        gscore[key2] = ng
                        parents[(v, chosen_idx, next_time)] = (v, idx, entry_t)
                        heapq.heappush(open_heap, (ng + heuristic(v), ng, v, chosen_idx, next_time, (v, idx, entry_t)))

        # no path found
        return None

    def _reconstruct_trajectory_from_parents(self, end_key, parents, vertex_safe, speed):
        # climb parents back to start and build action list
        seq = []
        cur = end_key  # (v, idx, entry_t)
        while True:
            parent = parents.get(cur)
            if parent is None:
                # root
                v, idx, entry_t = cur
                # if no parent, there's no prior action (start)
                seq.append(('wait', v, entry_t, 0.0))
                break
            # parent is another key (pv, pidx, pentry)
            pv, pidx, pentry = parent
            v, idx, entry_t = cur
            # if pv == v -> we waited from pentry to entry_t
            if self._same_pos(pv, v):
                wait_dur = entry_t - pentry
                if wait_dur > 1e-9:
                    seq.append(('wait', v, pentry, wait_dur))
            else:
                # a move from pv to v starting at p_depart = ???; our parents stored arrival time as entry_t for child
                # We don't have precise departure recorded for move; approximate departure = entry_t - travel_time
                travel_t = euclid(pv, v) / max(1e-6, speed)
                depart = entry_t - travel_t
                seq.append(('move', pv, v, depart, travel_t))
            cur = parent
        seq.reverse()
        return seq

    # ---------------- Collision utilities ----------------
    def _point_collides_with_trajectory_point(self, point, t, other_traj, my_radius, other_radius):
        """
        Check whether a point at time t (agent located at `point`) collides with other_traj at time t.
        other_traj is list of actions: ('move'/'wait', ... , start_time, duration)
        We'll find other agent position at time t (linear interpolation) and compare distance.
        """
        pos = self._pos_of_trajectory_at_time(other_traj, t)
        if pos is None:
            return False
        return euclid(point, pos) <= (my_radius + other_radius + 1e-9)

    def _pos_of_trajectory_at_time(self, traj, t):
        # return interpolated position or None if t outside traj coverage
        for act in traj:
            if act[0] == 'move':
                _, u, v, st, dur = act
                if st - 1e-9 <= t <= st + dur + 1e-9:
                    if dur < 1e-9:
                        return v
                    frac = clamp((t - st) / dur, 0.0, 1.0)
                    return (u[0] + (v[0] - u[0]) * frac, u[1] + (v[1] - u[1]) * frac)
            else:
                _, p, st, dur = act
                if st - 1e-9 <= t <= st + dur + 1e-9:
                    return p
        # t not covered -> assume agent stationary at last known point if t > last
        if len(traj) > 0:
            last = traj[-1]
            if last[0] == 'move':
                _, u, v, st, dur = last
                if t >= st + dur - 1e-9:
                    return v
            else:
                _, p, st, dur = last
                if t >= st + dur - 1e-9:
                    return p
        return None

    def _segment_collides_with_dynamic(self, v_to, v_from, depart, arrive, dynamic_obstacles, my_radius, my_id):
        """
        Check collision between moving segment (from v_from->v_to during [depart,arrive]) and any other agent's trajectory.
        We'll sample times at self.unsafe_step and check point-to-point distance (sufficient for disk models and small dt)
        """
        steps = max(1, int(math.ceil((arrive - depart) / self.unsafe_step)))
        for k in range(steps + 1):
            t = depart + (arrive - depart) * (k / float(steps))
            # pos of self at t
            frac = clamp((t - depart) / (arrive - depart), 0.0, 1.0) if arrive - depart > 1e-9 else 1.0
            self_pos = (v_from[0] + (v_to[0] - v_from[0]) * frac, v_from[1] + (v_to[1] - v_from[1]) * frac)
            for other_id, oth_traj in dynamic_obstacles.items():
                pos_o = self._pos_of_trajectory_at_time(oth_traj, t)
                if pos_o is None:
                    continue
                if euclid(self_pos, pos_o) <= (my_radius + self._get_agent_radius(other_id) + 1e-9):
                    return True
        return False

    def _violates_move_constraints(self, constraints, move_action, depart_time):
        # constraints forbid performing action within [start,end)
        for c in constraints:
            if c['action'][0] != 'move':
                continue
            if self._same_pos(c['action'][1], move_action[1]) and self._same_pos(c['action'][2], move_action[2]):
                if c['start'] - 1e-9 <= depart_time < c['end'] - 1e-9:
                    return True
        return False

    def _violates_wait_constraints(self, constraints, wait_action, t_entry, t_exit):
        # if any constraint forbids wait at this vertex overlapping [t_entry, t_exit)
        for c in constraints:
            if c['action'][0] != 'wait':
                continue
            if self._same_pos(c['action'][1], wait_action[1]):
                if not (t_exit <= c['start'] + 1e-9 or t_entry >= c['end'] - 1e-9):
                    return True
        return False

    def _compute_unsafe_interval(self, aid, act_a, t_a, bid, act_b, t_b):
        """
        Numerical search for maximal interval [t_a, t_a_u) such that performing act_a at any t in [t_a, t_a_u) with act_b fixed at t_b collides.
        We sample forward starting at t_a in steps self.unsafe_step until collision no longer holds and then expand via small binary search.
        Returns (start, end)
        """
        # If act_b is shiftable? we treat act_b time fixed at t_b according to the conflict detection
        # We'll test times t = t_a + k*step
        max_t = self.time_horizon
        step = self.unsafe_step
        # first check that at t_a there is conflict (should be, if given by detection); if not, return empty interval
        if not self._actions_conflict(aid, act_a, t_a, bid, act_b, t_b):
            return (t_a, t_a)  # empty
        t = t_a
        last_conflict = t_a
        while t <= max_t:
            t_test = t + step
            if not self._actions_conflict(aid, act_a, t_test, bid, act_b, t_b):
                # binary search between t and t_test to refine end time
                lo = t
                hi = t_test
                for _ in range(10):
                    mid = 0.5 * (lo + hi)
                    if self._actions_conflict(aid, act_a, mid, bid, act_b, t_b):
                        lo = mid
                    else:
                        hi = mid
                return (t_a, hi)
            t += step
            last_conflict = t
        return (t_a, max_t)

    def _actions_conflict(self, aid, act_a, t_a, bid, act_b, t_b):
        """
        Return True if agent aid executing act_a at start t_a collides with bid executing act_b at start t_b.
        We check using sampling along the overlapping time range.
        """
        # Build segments for each action: (pos_start, pos_end, t_start, t_end)
        segs_a = self._action_to_segments(act_a, t_a)
        segs_b = self._action_to_segments(act_b, t_b)
        # check pairwise segment collision by sampling
        for (ua, va, sa, ea) in segs_a:
            for (ub, vb, sb, eb) in segs_b:
                # overlap window
                s_overlap = max(sa, sb)
                e_overlap = min(ea, eb)
                if e_overlap < s_overlap:
                    continue
                # sample inside overlap
                steps = max(1, int(math.ceil((e_overlap - s_overlap) / self.unsafe_step)))
                for k in range(steps + 1):
                    tt = s_overlap + (e_overlap - s_overlap) * (k / float(steps))
                    posa = self._interp(ua, va, sa, ea, tt)
                    posb = self._interp(ub, vb, sb, eb, tt)
                    if euclid(posa, posb) <= (self._get_agent_radius(aid) + self._get_agent_radius(bid) + 1e-9):
                        return True
        return False

    def _action_to_segments(self, action, start_time):
        """
        Convert action into one or more time-parameterized segments:
        ('move', u, v, start_time, dur) -> [(u,v,start_time,start_time+dur)]
        ('wait', v, start_time, dur) -> [(v,v,start_time,start_time+dur)]
        Note: if action has no explicit duration given in the signature passed, caller must ensure
        """
        if action[0] == 'move':
            # action = ('move', u, v) or may be ('move',u,v,dur) depending on how called
            if len(action) >= 5:
                _, u, v, st, dur = action
                return [(u, v, st, st + dur)]
            else:
                _, u, v = action
                # caller provided start_time separately
                # To compute duration we need speed -> we cannot here; but in our use-cases we pass actions in normalized forms.
                # For safety assume small duration:
                return [(u, v, start_time, start_time + self.dt)]
        else:
            # wait
            if len(action) >= 4:
                _, v, st, dur = action
                return [(v, v, st, st + dur)]
            else:
                _, v = action
                return [(v, v, start_time, start_time + self.dt)]

    def _interp(self, u, v, st, et, t):
        if et - st < 1e-9:
            return v
        frac = clamp((t - st) / (et - st), 0.0, 1.0)
        return (u[0] + (v[0] - u[0]) * frac, u[1] + (v[1] - u[1]) * frac)

    # ---------------- Conflict detection ----------------
    def _detect_conflict_in_plans(self, plans: Dict[int, List[Tuple]]) -> Optional[Tuple[Tuple[int, Tuple], Tuple[int, Tuple]]]:
        """
        Given plans: agent->list of timed actions, detect first conflict.
        Returns ((a1, action1, t1), (a2, action2, t2)) or None
        We'll pairwise check actions and use sampling.
        """
        agents = list(plans.keys())
        for i in range(len(agents)):
            for j in range(i + 1, len(agents)):
                a1 = agents[i]
                a2 = agents[j]
                traj1 = plans[a1]
                traj2 = plans[a2]
                # iterate actions in trajs
                for act1 in traj1:
                    for act2 in traj2:
                        # get action times
                        if act1[0] == 'move':
                            st1 = act1[3]
                            dur1 = act1[4]
                        else:
                            st1 = act1[2]
                            dur1 = act1[3]
                        if act2[0] == 'move':
                            st2 = act2[3]
                            dur2 = act2[4]
                        else:
                            st2 = act2[2]
                            dur2 = act2[3]
                        if st1 + dur1 < st2 - 1e-9 or st2 + dur2 < st1 - 1e-9:
                            continue  # disjoint in time
                        # test conflict
                        if self._actions_conflict(a1, act1, st1, a2, act2, st2):
                            return ((a1, (act1[0], act1[1], act1[2]) if act1[0]=='wait' else (act1[0], act1[1], act1[2]), st1),
                                    (a2, (act2[0], act2[1], act2[2]) if act2[0]=='wait' else (act2[0], act2[1], act2[2]), st2))
        return None

    # ---------------- utilities ----------------
    def _traj_cost(self, traj):
        c = 0.0
        for a in traj:
            if a[0] == 'move':
                c += a[4]
            else:
                c += a[3]
        return c

    def _trajectory_to_waypoints(self, traj):
        """
        Convert action list to list of (pos, t) pairs by sampling at action boundaries (start and end).
        """
        waypts = []
        for a in traj:
            if a[0] == 'move':
                _, u, v, st, dur = a
                waypts.append((u, st))
                waypts.append((v, st + dur))
            else:
                _, v, st, dur = a
                waypts.append((v, st))
                waypts.append((v, st + dur))
        # compress duplicates and sort
        filtered = []
        last = None
        for p, t in sorted(waypts, key=lambda x: (x[1], x[0][0], x[0][1])):
            if last is None or (euclid(last[0], p) > 1e-9 or abs(last[1] - t) > 1e-9):
                filtered.append((p, t))
                last = (p, t)
        return filtered

    def _same_pos(self, a, b):
        return euclid(a, b) < 1e-6

    # agent parameters retrieval (best-effort)
    def _get_agent_speed(self, agv_id):
        try:
            return float(self.env.get_agent_speed(agv_id))
        except Exception:
            return 1.0

    def _get_agent_radius(self, agv_id):
        try:
            return float(self.env.get_agent_radius(agv_id))
        except Exception:
            return 0.25

