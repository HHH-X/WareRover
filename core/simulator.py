# core/simulator.py

from config.settings import SimConfig
from core.gridmap import GridMap
from core.agvmanager import AGVManager
from core.env import Env
from core.ordermanager import OrderManager
from scheduler.base_scheduler import BaseScheduler
from planner.base_planner import BasePlanner
from utils.simulation_clock import clock
from utils.logger import global_logger

class Simulator:
    def __init__(self, map_inst: GridMap,
                 agv_manager: AGVManager, order_manager: OrderManager, env: Env,
                 scheduler: BaseScheduler, planner: BasePlanner):
        self.map = map_inst
        self.agv_manager = agv_manager
        self.order_manager = order_manager
        self.env = env
        self.scheduler = scheduler
        self.planner = planner

    def step(self):
        """
        执行主仿真循环，每一轮包括：
        - 分配任务给空闲AGV
        - 分配休息区给任务完成的AGV
        - 为需要重规划的AGV生成新路径
        - 执行AGV动作与冲突检测
        """
        if SimConfig.log_to_console and clock.now() % 30 == 0:
            print(f"\n--- Simulator Step {clock.now()} ---")
            global_logger.add_runtime_log(f"Simulator Step {clock.now()}")
        # 订单管理器执行一步（处理新订单、更新订单状态等）
        self.order_manager.step()
        # 1. 获取空闲AGV并尝试分配任务
        idle_agv_set = self.agv_manager.get_idle_agv_ids()
        if idle_agv_set:
            with global_logger.computation_timer("scheduler"):
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
            with global_logger.computation_timer("planner"):
                new_paths = self.planner.plan(replanning_targets)       
            self.agv_manager.replan_paths(new_paths)

        # 4. 执行一步环境逻辑（含冲突检测与AGV移动）
        step_info_dict = self.env.step()

        clock.tick()

        # 5. 检查仿真终止条件（例如订单全部完成）
        if self.order_all_finished():
            print("All orders have been completed.")


    def order_all_finished(self) -> bool:
        """
        判断订单是否全部完成（当前为占位函数）。
        实际应通过 OrderManager 判断是否还有未完成订单。
        """
        return False  # TODO: 实现与订单管理的对接
