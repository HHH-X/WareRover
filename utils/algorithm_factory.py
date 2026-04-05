from utils.algorithm_registry import PlannerRegistry, SchedulerRegistry
from utils.simulation_context import SimulationContext


def build_scheduler(ctx: SimulationContext):
    assert ctx.system_config is not None
    name = ctx.system_config.sim_config.scheduler_type
    scheduler_cls = SchedulerRegistry.get(name)
    return scheduler_cls(ctx)


def build_planner(ctx: SimulationContext):
    assert ctx.system_config is not None
    sim_cfg = ctx.system_config.sim_config
    planner_cls = PlannerRegistry.get(sim_cfg.planner_type)
    if sim_cfg.planner_type == "dhc":
        sim_cfg.force_replan_every_step = True
    else:
        sim_cfg.force_replan_every_step = False
    return planner_cls(ctx)
