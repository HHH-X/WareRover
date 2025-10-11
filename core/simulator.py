# core/simulator.py

from config.settings import SimConfig
from core.gridmap import GridMap
from core.agvmanager import AGVManager
from core.env import Env
from scheduler.base_scheduler import BaseScheduler
from planner.base_planner import BasePlanner


class Simulator:
    def __init__(self, sim_config: SimConfig, map_inst: GridMap,
                 agv_manager: AGVManager, env: Env,
                 scheduler: BaseScheduler, planner: BasePlanner):
        self.config = sim_config
        self.map = map_inst
        self.agv_manager = agv_manager
        self.env = env
        self.scheduler = scheduler
        self.planner = planner
        self.step_count = 0  # 当前仿真步数计数器

    def step(self):
        """
        执行主仿真循环，每一轮包括：
        - 分配任务给空闲AGV
        - 分配休息区给任务完成的AGV
        - 为需要重规划的AGV生成新路径
        - 执行AGV动作与冲突检测
        """
        
        # if self.step_count ==366:
        #     print("Debug: Step 27 reached.")
        print(f"\n--- Simulator Step {self.step_count} ---")

        # 1. 获取空闲AGV并尝试分配任务
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
        if replanning_targets:
            new_paths = self.planner.plan(replanning_targets)       
            self.agv_manager.replan_paths(new_paths)

        # 4. 执行一步环境逻辑（含冲突检测与AGV移动）
        self.env.step()

        self.step_count += 1

        # 5. 检查仿真终止条件（例如订单全部完成）
        if self.order_all_finished():
            print("All orders have been completed.")


    def order_all_finished(self) -> bool:
        """
        判断订单是否全部完成（当前为占位函数）。
        实际应通过 OrderManager 判断是否还有未完成订单。
        """
        return False  # TODO: 实现与订单管理的对接
