from config.settings import init_sim_config
from core.agvmanager import load_agvs_from_config
from core.gridmap import load_map_from_config
from core.order import OrderManager
from core.env import Env
from core.simulator import Simulator
from visualizer.main_view import MainView

from scheduler.TA_scheduler import TAScheduler
from scheduler.random_scheduler import RandomScheduler
from planner.astar_planner import AStarPlanner
from planner.cbs_fw_planner import FixedWindowCBSPlanner

import random
def main():
    random.seed(1)  # 固定随机数种子
    cfg = init_sim_config("config/test_map.json")
    grid_map = load_map_from_config(cfg)
    ordermanager = OrderManager(cfg,grid_map)
    agv_manager = load_agvs_from_config(cfg,grid_map,ordermanager)
    env = Env(agv_manager,grid_map, ordermanager)

    scheduler = RandomScheduler(ordermanager,grid_map)
    # scheduler = TAScheduler(ordermanager,grid_map,agv_manager)
    planner = FixedWindowCBSPlanner(env, window_size=8)
    # planner = AStarPlanner(env)

    simulator = Simulator(cfg, grid_map,agv_manager, env,scheduler, planner)

    main_view = MainView(cfg, grid_map, agv_manager)
    while not ordermanager.is_all_orders_completed() and simulator.step_count < cfg.max_steps:
        if not main_view.is_paused() or main_view.consume_step_trigger():
            simulator.step()       
        main_view.render()

if __name__ == "__main__":
    main()