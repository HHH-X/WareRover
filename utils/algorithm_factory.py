from config.settings import SimConfig, SchedulerType, PlannerType

from scheduler.random_scheduler import RandomScheduler
from scheduler.TA_scheduler import TAScheduler

from planner.astar_planner import AStarPlanner
from planner.cbs_fw_planner import FixedWindowCBSPlanner
from planner.dhc_planner import DHCPlanner


def build_scheduler(ordermanager, grid_map, agv_manager):
    if SimConfig.scheduler_type == SchedulerType.RANDOM:
        return RandomScheduler(ordermanager, grid_map, agv_manager)
    elif SimConfig.scheduler_type == SchedulerType.TA:
        return TAScheduler(ordermanager, grid_map, agv_manager)
    else:
        raise ValueError(f"Unknown scheduler: {SimConfig.scheduler_type}")


def build_planner(env):
    if SimConfig.planner_type == PlannerType.ASTAR:
        return AStarPlanner(env)

    elif SimConfig.planner_type == PlannerType.CBS_FW:
        return FixedWindowCBSPlanner(env)

    elif SimConfig.planner_type == PlannerType.DHC:
        # 自动联动配置
        SimConfig.force_replan_every_step = True

        return DHCPlanner(
            env,
            model_path=SimConfig.dhc_model_path,
            forward_steps=1,
            device="cuda"
        )

    else:
        raise ValueError(f"Unknown planner: {SimConfig.planner_type}")
