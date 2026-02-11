from config.settings import SimConfig, SchedulerType, PlannerType

from scheduler.random_scheduler import RandomScheduler
from scheduler.TA_scheduler import TAScheduler

from planner.astar_planner import AStarPlanner
from planner.cbs_fw_planner import FixedWindowCBSPlanner
from planner.dhc_planner import DHCPlanner
from core.env import Env
from core.ordermanager import OrderManager
from core.gridmap import GridMap
from core.agvmanager import AGVManager
from core.fault_manager import FaultManager

def build_scheduler(
    env: Env,
    agv_manager: AGVManager,
    ordermanager: OrderManager,
    grid_map: GridMap,
    fault_manager: FaultManager
):
    if SimConfig.scheduler_type == SchedulerType.RANDOM:
        return RandomScheduler(env, agv_manager, ordermanager, grid_map, fault_manager)
    elif SimConfig.scheduler_type == SchedulerType.TA:
        return TAScheduler(env, agv_manager, ordermanager, grid_map, fault_manager)
    else:
        raise ValueError(f"Unknown scheduler: {SimConfig.scheduler_type}")


def build_planner(
    env: Env,
    agv_manager: AGVManager,
    ordermanager: OrderManager,
    grid_map: GridMap,
    fault_manager: FaultManager
):
    if SimConfig.planner_type == PlannerType.ASTAR:
        SimConfig.force_replan_every_step = False
        return AStarPlanner(env, agv_manager, ordermanager, grid_map, fault_manager)

    elif SimConfig.planner_type == PlannerType.CBS_FW:
        SimConfig.force_replan_every_step = False
        return FixedWindowCBSPlanner(env, agv_manager, ordermanager, grid_map, fault_manager)

    elif SimConfig.planner_type == PlannerType.DHC:
        SimConfig.force_replan_every_step = True

        return DHCPlanner(
            env,
            agv_manager=agv_manager,
            order_manager=ordermanager,
            map=grid_map,
            fault_manager=fault_manager,
            model_path=SimConfig.dhc_model_path,
            forward_steps=1,
            device="cuda"
        )

    else:
        raise ValueError(f"Unknown planner: {SimConfig.planner_type}")
