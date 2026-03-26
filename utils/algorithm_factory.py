from config.settings import SystemConfig
from core.env import Env
from core.ordermanager import OrderManager
from core.gridmap import GridMap
from core.agvmanager import AGVManager
from core.fault_manager import FaultManager
from utils.algorithm_registry import PlannerRegistry, SchedulerRegistry

def build_scheduler(
    system_config: SystemConfig,
    env: Env,
    agv_manager: AGVManager,
    ordermanager: OrderManager,
    grid_map: GridMap,
    fault_manager: FaultManager
):
    scheduler_name = system_config.sim_config.scheduler_type
    scheduler_cls = SchedulerRegistry.get(scheduler_name)
    return scheduler_cls(env, agv_manager, ordermanager, grid_map, fault_manager)


def build_planner(
    system_config: SystemConfig,
    env: Env,
    agv_manager: AGVManager,
    ordermanager: OrderManager,
    grid_map: GridMap,
    fault_manager: FaultManager
):
    sim_cfg = system_config.sim_config
    planner_name = sim_cfg.planner_type
    planner_cls = PlannerRegistry.get(planner_name)

    if planner_name == "dhc":
        sim_cfg.force_replan_every_step = True
        return planner_cls(
            env,
            agv_manager=agv_manager,
            order_manager=ordermanager,
            map=grid_map,
            fault_manager=fault_manager,
            model_path=sim_cfg.dhc_model_path,
            forward_steps=1,
            device="cuda"
        )

    sim_cfg.force_replan_every_step = False
    return planner_cls(env, agv_manager, ordermanager, grid_map, fault_manager)
