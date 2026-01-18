# 文件名: dhc_agv_wrapper.py
import numpy as np
from typing import List, Dict, Tuple
from config.settings import SimConfig
from core.agv import StepInfo
from core.agvmanager import AGVManager
from core.gridmap import GridMap
from core.ordermanager import OrderManager
from core.env import Env
from core.simulator import Simulator
from core.data_generator import generate_send_data
from core.fault_manager import FaultManager
from utils.logger import global_logger
from scheduler.random_scheduler import RandomScheduler
from scheduler.TA_scheduler import TAScheduler
from planner.astar_planner import AStarPlanner
from planner.cbs_fw_planner import FixedWindowCBSPlanner
from .dhc_converter import DHCCompatibleConverter
from . import configs

# 动作对应的坐标偏移（x右 y下 为正，常见仓库地图坐标系）
ACTION_DELTA = {
    0: (0,  0),   # stay
    1: (0, -1),   # up
    2: (0,  1),   # down
    3: (-1, 0),   # left
    4: (1,  0)    # right
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
    完全模仿 DHC Environment 的接口，但底层使用你的真实仓库 AGV 环境
    可直接替换所有 DHC 训练代码中的 env = Environment(...)
    """
    def __init__(
        self,
        curriculum
    ):
        
        # --- 初始化各组件 ---
        grid_map = GridMap()
        self.ordermanager = OrderManager(grid_map)
        self.agv_manager = AGVManager(grid_map, self.ordermanager)
        self.real_env = Env(self.agv_manager, grid_map, self.ordermanager)
        # self.scheduler = TAScheduler(self.ordermanager, grid_map, self.agv_manager)
        self.scheduler = RandomScheduler(self.ordermanager, grid_map, self.agv_manager)

        self.obs_radius = configs.obs_radius
        # 转换器
        self.converter = DHCCompatibleConverter(num_agvs=self.agv_manager.num_agvs, gridmap=grid_map, agvmanager=self.agv_manager)
        self.steps = 0
        self.num_agents =  self.agv_manager.num_agvs
        self.map_size = (self.real_env.map.height, self.real_env.map.width)

        self.prev_goal_distances = {}  # {agv_id: 上一次到目标的曼哈顿距离}
        SimConfig.force_replan_every_step = True
    def reset(self):
        self.steps = 0
        # self.ordermanager.reset_order()
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

        # 初始化 prev_goal_distances
        replanning_targets = self.agv_manager.get_replan_targets()
        for agv_id, (curr_pos, goal_pos) in replanning_targets.items():
            dist = abs(curr_pos[0] - goal_pos[0]) + abs(curr_pos[1] - goal_pos[1])
            self.prev_goal_distances[agv_id] = dist

        # 返回 DHC 格式的观测
        return self.observe()

    def step(self, actions: List[int]) -> Tuple:
        """
        actions: List[int] 长度 = 当前需要决策的 AGV 数量，值 0~4
        返回: obs, rewards, done, info   （完全和 DHC 一致）
        """

        replanning_targets = self.agv_manager.get_replan_targets()
        next_pos_dict: Dict[int, List[Tuple[int, int]]] = {}
        for agv_id, (current_pos, goal_pos) in replanning_targets.items():
                # 边界检查
                if agv_id >= len(actions):
                    raise IndexError(f"AGV {agv_id} 的动作索引超出 actions 列表长度 {len(actions)}")

                action = actions[agv_id]
                if action not in ACTION_DELTA:
                    raise ValueError(f"AGV {agv_id} 的动作值 {action} 非法")

                dx, dy = ACTION_DELTA[action]
                next_x = current_pos[0] + dx
                next_y = current_pos[1] + dy

                next_pos_dict[agv_id] = [(next_x, next_y)]
        # 执行动作  
        self.agv_manager.replan_paths(next_pos_dict)
        step_info = self.real_env.step()     

        idle_agv_set = self.agv_manager.get_idle_agv_ids()
        if idle_agv_set:
            agv_tasks = self.scheduler.assign_tasks(idle_agv_set)
            if(agv_tasks):
                self.agv_manager.assign_tasks(agv_tasks)
        # 2. 分配休息区给任务完成的AGV
        agvs_needing_rest = self.agv_manager.get_need_rest_agv_ids()
        if agvs_needing_rest:
            rest_assignments = self.scheduler.assign_rest_areas(agvs_needing_rest)
            self.agv_manager.assign_rest_zones(rest_assignments)

        # 3. 获取需要重规划的AGV的当前位置与目标
        replanning_targets = self.agv_manager.get_replan_targets()
        
        env_info = self.real_env.get_env_info()
        static_grid = env_info['static_grid']
        agv_positions = env_info['current_grid_pos']

        obs, pos = self.converter.convert(
            static_grid=static_grid,
            agv_positions_xy=agv_positions,
            targets=replanning_targets
        )
        
            
        self.steps += 1
        if(self.ordermanager.can_generate_more_orders()):
            self.ordermanager.step(self.steps)

        # 所有的agv id
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
                r = DHC_REWARD['other']   # 默认当普通移动处理
            else:
                raise ValueError(f"Unknown StepInfo: {info}")

            # ---------- 曼哈顿距离 shaping reward ----------
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
                # 没有目标的 AGV（理论上很少）
                self.prev_goal_distances.pop(agv_id, None)
            rewards.append(r)

        overall_done = self.ordermanager.is_all_orders_completed() or self.steps >= SimConfig.max_steps
        return (obs, pos) , rewards, overall_done, info

    def render(self):
        # 直接调用你的真实环境渲染，或者自己画
        self.real_env.render()

    def close(self):
        self.real_env.close()

    def observe(self):
        env_info = self.real_env.get_env_info()
        static_grid = env_info['static_grid']
        agv_positions = env_info['current_grid_pos']
        replanning_targets = self.agv_manager.get_replan_targets()
        obs, pos = self.converter.convert(
            static_grid=static_grid,
            agv_positions_xy=agv_positions,
            targets=replanning_targets
        )

        return obs, pos
    
    def update_env_settings_set(self, test):
        pass
