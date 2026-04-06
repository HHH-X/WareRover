from __future__ import annotations

from collections import OrderedDict
from typing import Callable, Dict, List, Optional, Tuple

from planner.astar_planner import AStarPlanner
from planner.base_planner import BasePlanner
from utils.simulation_context import SimulationContext

TargetMap = Dict[int, Tuple[Tuple[int, int], Tuple[int, int]]]
RankerFunc = Callable[[List[dict], int], List[int]]

_RANKER_FUNCTION: Optional[RankerFunc] = None


def set_ranker_function(func: Optional[RankerFunc]) -> None:
    global _RANKER_FUNCTION
    _RANKER_FUNCTION = func


def _default_ranker(target_rows: List[dict], current_step: int = 0) -> List[int]:
    scored: List[Tuple[float, int]] = []
    for row in target_rows:
        agv_id = int(row["agv_id"])
        sx, sy = row["start"]
        gx, gy = row["goal"]
        distance = abs(sx - gx) + abs(sy - gy)
        tie_break = ((agv_id * 31 + current_step) % 17) * 1e-4
        score = -float(distance) + tie_break
        scored.append((score, agv_id))

    scored.sort(reverse=True)
    return [agv_id for _, agv_id in scored]


class EvolvedWrapperPlanner(BasePlanner):
    """
    Planner wrapper for OpenEvolve experiments.

    It reorders targets using an evolved ranker function, then delegates
    path generation to the baseline A* planner.
    """

    def __init__(self, ctx: SimulationContext):
        super().__init__(ctx)
        self.ctx = ctx
        self._delegate = AStarPlanner(ctx)

    def _rank_targets(self, targets: TargetMap) -> List[int]:
        rows = [
            {
                "agv_id": agv_id,
                "start": start,
                "goal": goal,
            }
            for agv_id, (start, goal) in targets.items()
        ]
        current_step = int(self.ctx.clock.now()) if self.ctx.clock is not None else 0

        ranker = _RANKER_FUNCTION or _default_ranker
        try:
            ordered_ids = ranker(rows, current_step=current_step)
        except TypeError:
            ordered_ids = ranker(rows, current_step)
        except Exception:
            ordered_ids = _default_ranker(rows, current_step=current_step)

        valid_ids = [agv_id for agv_id in ordered_ids if agv_id in targets]
        unseen = [agv_id for agv_id in targets.keys() if agv_id not in valid_ids]
        return valid_ids + unseen

    def plan(
        self,
        targets: TargetMap,
        scheduler,
    ) -> Dict[int, List[Tuple[int, int]]]:
        if not targets:
            return {}

        ordered_ids = self._rank_targets(targets)
        ordered_targets: "OrderedDict[int, Tuple[Tuple[int, int], Tuple[int, int]]]" = OrderedDict()
        for agv_id in ordered_ids:
            ordered_targets[agv_id] = targets[agv_id]
        return self._delegate.plan(ordered_targets, scheduler)
