# simulation_clock.py
from utils.logger import global_logger

class SimulationClock:
    def __init__(self):
        self._step = 0

    def tick(self, n: int = 1):
        self._step += n

    def now(self) -> int:
        return self._step

    def reset(self):
        self._step = 0
        global_logger.add_runtime_log("[SimClock] Clock has been reset.")


clock = SimulationClock()
