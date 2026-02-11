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
        One simulation step: order manager step, assign tasks to idle AGVs,
        assign rest areas, replan paths for AGVs that need it, then run env step (conflict detection and movement).
        """
        if SimConfig.log_to_console and clock.now() % 30 == 0:
            print(f"\n--- Simulator Step {clock.now()} ---")
            global_logger.add_runtime_log(f"Simulator Step {clock.now()}")
        self.order_manager.step()
        idle_agv_set = self.agv_manager.get_idle_agv_ids()

        with global_logger.computation_timer("scheduler"):
            agv_tasks = self.scheduler.assign_tasks(idle_agv_set, self.planner)
        if agv_tasks:
            self.agv_manager.assign_tasks(agv_tasks)

        agvs_needing_rest = self.agv_manager.get_need_rest_agv_ids()
        if agvs_needing_rest:
            rest_assignments = self.scheduler.assign_rest_areas(agvs_needing_rest)
            self.agv_manager.assign_rest_zones(rest_assignments)

        replanning_targets = self.agv_manager.get_replan_targets()
        with global_logger.computation_timer("planner"):
            new_paths = self.planner.plan(replanning_targets, self.scheduler)
        self.agv_manager.replan_paths(new_paths)

        self.env.step()
        clock.tick()

        if self.order_all_finished():
            print("All orders have been completed.")

    def order_all_finished(self) -> bool:
        """Check if all orders are completed (placeholder; should use OrderManager)."""
        return False  # TODO: integrate with OrderManager
