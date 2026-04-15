# algorithm/DHC/dhc_env.py
import numpy as np
from typing import List, Dict, Tuple
from config.settings import SimConfig, SystemConfig
from core.agv import StepInfo
from core.elevator import ElevatorManager
from core.env import Env
from core.warehouse_map import WarehouseMap
from core.ordermanager import OrderManager
from core.agvmanager import AGVManager
from core.simulator import Simulator
from core.data_generator import generate_send_data
from core.fault_manager import FaultManager
from scheduler.random_scheduler import RandomScheduler
from utils.logger import GlobalLogger
from utils.simulation_clock import SimulationClock
from utils.simulation_context import SimulationContext
from .dhc_converter import DHCCompatibleConverter
from . import configs

# Action deltas in (drow, dcol) convention
ACTION_DELTA = {
    0: (0,  0),   # stay
    1: (-1, 0),   # up    (row decreases)
    2: (1,  0),   # down  (row increases)
    3: (0, -1),   # left  (col decreases)
    4: (0,  1)    # right (col increases)
}

DHC_REWARD = {
    'move':          -0.075,
    'collision':     -0.5,
    'stay_off_goal': -0.075,
    'stay_on_goal':   0.0,
    'finish':        +5.0,
    'other':         -0.075,
}

DIST_REWARD_SCALE = 0.1

class DHCAVGEnv:
    """
    DHC Environment wrapper using the real warehouse AGV environment.
    All positions use (row, col) convention.
    """
    def __init__(
        self,
        curriculum
    ):
        ctx = SimulationContext()
        ctx.system_config = SystemConfig()
        ctx.logger = GlobalLogger(ctx.system_config.sim_config)
        ctx.clock = SimulationClock(ctx.logger)
        bind_context_runtime(ctx)
        ctx.warehouse_map = WarehouseMap(ctx)
        ctx.order_manager = OrderManager(ctx)
        ctx.agv_manager = AGVManager(ctx)
        ctx.elevator_manager = ElevatorManager(ctx.warehouse_map, ctx.logger)
        ctx.env = Env(ctx)
        ctx.fault_manager = FaultManager(ctx)
        ctx.scheduler = RandomScheduler(ctx)

        self._ctx = ctx
        self.ordermanager = ctx.order_manager
        self.agv_manager = ctx.agv_manager
        self.real_env = ctx.env
        self.scheduler = ctx.scheduler

        self.obs_radius = configs.obs_radius
        floor0 = ctx.warehouse_map.get_floor(0)
        self.converter = DHCCompatibleConverter(
            num_agvs=self.agv_manager.num_agvs,
            gridmap=floor0,
            agvmanager=self.agv_manager,
        )
        self.steps = 0
        self.num_agents = self.agv_manager.num_agvs
        self.map_size = (floor0.height, floor0.width)

        self.prev_goal_distances = {}
        SimConfig.force_replan_every_step = True

    def reset(self):
        self.steps = 0
        self.real_env.reset()
        if(self.ordermanager.can_generate_more_orders()):
            self.ordermanager.step()
        self.scheduler.reset()
        self.prev_goal_distances.clear()

        idle_agv_set = self.agv_manager.get_idle_agv_ids()
        if idle_agv_set:
            agv_tasks = self.scheduler.assign_tasks(idle_agv_set)
            if(agv_tasks):
                self.agv_manager.assign_tasks(agv_tasks)

        replanning_targets = self.agv_manager.get_replan_targets()
        for agv_id, (curr_pos, goal_pos) in replanning_targets.items():
            dist = abs(curr_pos[0] - goal_pos[0]) + abs(curr_pos[1] - goal_pos[1])
            self.prev_goal_distances[agv_id] = dist

        return self.observe()

    def step(self, actions: List[int]) -> Tuple:
        replanning_targets = self.agv_manager.get_replan_targets()
        next_pos_dict: Dict[int, List[Tuple[int, int]]] = {}
        for agv_id, (current_pos, goal_pos) in replanning_targets.items():
                if agv_id >= len(actions):
                    raise IndexError(f"AGV {agv_id} action index out of range {len(actions)}")

                action = actions[agv_id]
                if action not in ACTION_DELTA:
                    raise ValueError(f"AGV {agv_id} invalid action {action}")

                drow, dcol = ACTION_DELTA[action]
                next_row = current_pos[0] + drow
                next_col = current_pos[1] + dcol

                next_pos_dict[agv_id] = [(next_row, next_col)]

        self.agv_manager.replan_paths(next_pos_dict)
        step_info = self.real_env.step()

        idle_agv_set = self.agv_manager.get_idle_agv_ids()
        if idle_agv_set:
            agv_tasks = self.scheduler.assign_tasks(idle_agv_set)
            if(agv_tasks):
                self.agv_manager.assign_tasks(agv_tasks)

        agvs_needing_rest = self.agv_manager.get_need_rest_agv_ids()
        if agvs_needing_rest:
            rest_assignments = self.scheduler.assign_rest_areas(agvs_needing_rest)
            self.agv_manager.assign_rest_zones(rest_assignments)

        replanning_targets = self.agv_manager.get_replan_targets()

        env_info = self.real_env.get_env_info_for_floor(0)
        type_grid = env_info['type_grid']
        agv_positions = env_info['current_grid_pos']

        obs, pos = self.converter.convert(
            type_grid=type_grid,
            agv_positions=agv_positions,
            targets=replanning_targets
        )

        self.steps += 1
        if(self.ordermanager.can_generate_more_orders()):
            self.ordermanager.step(self.steps)

        all_agv_ids = self.agv_manager.all_agv_ids

        rewards = []
        for agv_id in all_agv_ids:
            info = step_info[agv_id]

            if info == StepInfo.FINISH:
                r = DHC_REWARD['finish']
            elif info == StepInfo.MOVE:
                r = DHC_REWARD['move']
            elif info == StepInfo.COLLISION:
                r = DHC_REWARD['collision']
            elif info == StepInfo.STAY_OFF_GOAL:
                r = DHC_REWARD['stay_off_goal']
            elif info == StepInfo.STAY_ON_GOAL:
                r = DHC_REWARD['stay_on_goal']
            elif info == StepInfo.OTHER:
                r = DHC_REWARD['other']
            else:
                raise ValueError(f"Unknown StepInfo: {info}")

            if agv_id in replanning_targets:
                curr_pos, goal_pos = replanning_targets[agv_id]
                curr_dist = abs(curr_pos[0] - goal_pos[0]) + abs(curr_pos[1] - goal_pos[1])
                if info == StepInfo.FINISH:
                    self.prev_goal_distances[agv_id] = curr_dist
                else:
                    prev_dist = self.prev_goal_distances.get(agv_id, curr_dist)
                    delta_dist = prev_dist - curr_dist
                    r += DIST_REWARD_SCALE * delta_dist
                    self.prev_goal_distances[agv_id] = curr_dist
            else:
                self.prev_goal_distances.pop(agv_id, None)
            rewards.append(r)

        overall_done = self.ordermanager.is_all_orders_completed() or self.steps >= SimConfig.max_steps
        return (obs, pos), rewards, overall_done, info

    def render(self):
        self.real_env.render()

    def close(self):
        self.real_env.close()

    def observe(self):
        env_info = self.real_env.get_env_info_for_floor(0)
        type_grid = env_info['type_grid']
        agv_positions = env_info['current_grid_pos']
        replanning_targets = self.agv_manager.get_replan_targets()
        obs, pos = self.converter.convert(
            type_grid=type_grid,
            agv_positions=agv_positions,
            targets=replanning_targets
        )
        return obs, pos

    def update_env_settings_set(self, test):
        pass
