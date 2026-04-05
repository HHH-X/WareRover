# simulation_clock.py
from typing import Optional
from utils.simulation_context import SimulationContext

class SimulationClock:
    def __init__(self, ctx: SimulationContext):
        self._step = 0
        self._logger = ctx.logger

    def tick(self, n: int = 1):
        self._step += n

    def now(self) -> int:
        return self._step

    def reset(self):
        self._step = 0
        self._logger.add_runtime_log("[SimClock] Clock has been reset.")
