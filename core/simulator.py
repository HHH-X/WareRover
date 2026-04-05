# core/simulator.py

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from utils.simulation_context import SimulationContext


class Simulator:
    def __init__(self, ctx: SimulationContext):
        assert (
            ctx.system_config is not None
            and ctx.grid_map is not None
            and ctx.agv_manager is not None
            and ctx.order_manager is not None
            and ctx.env is not None
            and ctx.scheduler is not None
            and ctx.planner is not None
            and ctx.logger is not None
            and ctx.clock is not None
        )
        self.system_config = ctx.system_config
        self.map = ctx.grid_map
        self.agv_manager = ctx.agv_manager
        self.order_manager = ctx.order_manager
        self.env = ctx.env
        self.scheduler = ctx.scheduler
        self.planner = ctx.planner
        self.clock = ctx.clock
        self.logger = ctx.logger

    def step(self):
        """
        One simulation step: order manager step, assign tasks to idle AGVs,
        assign rest areas, replan paths for AGVs that need it, then run env step (conflict detection and movement).
        """
        if self.clock.now() % 30 == 0:
            # print(f"\n--- Simulator Step {clock.now()} ---")
            self.logger.add_runtime_log(f"Simulator Step {self.clock.now()}")
        self.order_manager.step()
        idle_agv_set = self.agv_manager.get_idle_agv_ids()

        with self.logger.computation_timer("scheduler"):
            agv_tasks = self.scheduler.assign_tasks(idle_agv_set, self.planner)
        if agv_tasks:
            self.agv_manager.assign_tasks(agv_tasks)

        agvs_needing_rest = self.agv_manager.get_need_rest_agv_ids()
        if agvs_needing_rest:
            rest_assignments = self.scheduler.assign_rest_areas(agvs_needing_rest)
            self.agv_manager.assign_rest_zones(rest_assignments)

        replanning_targets = self.agv_manager.get_replan_targets()
        with self.logger.computation_timer("planner"):
            new_paths = self.planner.plan(replanning_targets, self.scheduler)
        self.agv_manager.replan_paths(new_paths)

        self.env.step()
        self.clock.tick()

        if self.order_all_finished():
            print("All orders have been completed.")

    def order_all_finished(self) -> bool:
        """Check if all orders are completed (placeholder; should use OrderManager)."""
        return False  # TODO: integrate with OrderManager
