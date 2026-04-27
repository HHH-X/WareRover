from __future__ import annotations

from collections import deque
from typing import Deque, List, Tuple, Optional, Dict, Set, Generator, TYPE_CHECKING
from enum import Enum, auto
from core.gridmap import GridMap
from config.settings import SimConfig

if TYPE_CHECKING:
    from core.ordermanager import OrderManager
    from utils.simulation_context import SimulationContext

epsilon = 1e-4


class Direction(Enum):
    UP = auto()
    DOWN = auto()
    LEFT = auto()
    RIGHT = auto()


class AGVAction(Enum):
    PICK = "pick"
    PLACE = "place"
    HANDOVER = "handover"
    ENTER_ELEVATOR = "enter_elevator"


class StepInfo(Enum):
    MOVE = auto()
    COLLISION = auto()
    STAY_OFF_GOAL = auto()
    STAY_ON_GOAL = auto()
    FINISH = auto()
    TURNING = auto()
    OTHER = auto()


class ElevatorPhase(Enum):
    NORMAL = auto()
    BOARDING_ELEVATOR = auto()
    IN_ELEVATOR = auto()


class AGV:
    """AGV entity. All grid positions use (row, col) convention."""

    def __init__(
        self,
        sim_config: SimConfig,
        ctx: SimulationContext,
        agv_id: int,
        size: int,
        floor_id: int,
        init_grid_pos: Tuple[int, int],
        map_inst: GridMap,
        order_manager: OrderManager,
    ):
        self.id: int = agv_id
        self.ctx = ctx
        self.size: int = size
        self.floor_id: int = floor_id
        self.init_floor_id: int = floor_id
        self.init_grid_pos: Tuple[int, int] = init_grid_pos
        self.grid_pos: Tuple[int, int] = init_grid_pos
        self.real_pos: Tuple[float, float] = (init_grid_pos[0] + 0.5, init_grid_pos[1] + 0.5)
        self.map = map_inst
        self.order_manager = order_manager
        self.task_queue: Deque[Tuple[Tuple[int, int], AGVAction, Optional[int]]] = deque()
        self.rest_target: Optional[Tuple[int, int]] = None
        self.action_queue: Deque[Tuple[int, int]] = deque()
        self.speed: float = 0.0
        self.max_speed: float = sim_config.agv_max_speed
        self.time_step: float = sim_config.time_step
        self.direction: Optional[Direction] = Direction.LEFT
        turning_time_90: float = sim_config.agv_turn_time_90
        self.turning_steps_90: int = int(round(turning_time_90 / self.time_step))
        self.turning_timer: int = 0
        self.target_direction: Optional[Direction] = None

        self.carried_box_id: int = None
        self.is_working: bool = True
        self.last_completed_task_pos: Tuple[int, int] = init_grid_pos

        self.in_elevator: bool = False
        self.elevator_phase: ElevatorPhase = ElevatorPhase.NORMAL

    @property
    def is_idle(self) -> bool:
        return len(self.task_queue) == 0

    @property
    def is_resting(self) -> bool:
        return self.rest_target is not None and self.grid_pos == self.rest_target

    @property
    def is_aligned(self) -> bool:
        gr, gc = self.grid_pos
        expected_r, expected_c = gr + 0.5, gc + 0.5
        rr, rc = self.real_pos
        return abs(rr - expected_r) < epsilon and abs(rc - expected_c) < epsilon

    def step(self, next_grid: Tuple[int, int]) -> Tuple[bool, StepInfo]:
        if not self.is_working or self.in_elevator:
            return False, StepInfo.OTHER

        if self.turning_timer > 0:
            self.turning_timer -= 1
            if self.turning_timer == 0:
                self.direction = self.target_direction
            return False, StepInfo.TURNING

        _, step_info = self.update_position(next_grid)
        replan_required = False
        if self.action_queue and self.grid_pos == self.action_queue[0]:
            self.action_queue.popleft()
            if self.task_queue and self.grid_pos == self.task_queue[0][0]:
                task_pos, action, extra = self.task_queue.popleft()
                self.last_completed_task_pos = task_pos
                self._execute_action(action, extra)
                self._maybe_enqueue_next_elevator_task()
                replan_required = True
                step_info = StepInfo.FINISH
        elif not self.action_queue and self.task_queue and self.grid_pos == self.task_queue[0][0]:
            task_pos, action, extra = self.task_queue.popleft()
            self.last_completed_task_pos = task_pos
            self._execute_action(action, extra)
            self._maybe_enqueue_next_elevator_task()
            replan_required = True
            step_info = StepInfo.FINISH
        if not self.action_queue and not self.is_resting:
            replan_required = True

        return replan_required, step_info

    def update_position(self, next_grid: Tuple[int, int]) -> tuple[bool, StepInfo]:
        dr = next_grid[0] - self.grid_pos[0]
        dc = next_grid[1] - self.grid_pos[1]

        step_info = StepInfo.MOVE
        if dc == 1:
            self.target_direction = Direction.RIGHT
        elif dc == -1:
            self.target_direction = Direction.LEFT
        elif dr == 1:
            self.target_direction = Direction.DOWN
        elif dr == -1:
            self.target_direction = Direction.UP
        else:
            self.target_direction = None
            step_info = StepInfo.STAY_OFF_GOAL
        self.turning_timer = self._calculate_turn_time(self.direction, self.target_direction)
        if self.turning_timer > 0:
            self.turning_timer -= 1
            if self.turning_timer == 0:
                self.direction = self.target_direction
            return False, StepInfo.TURNING

        self.speed = self.max_speed
        offset = self.speed * self.time_step
        r, c = self.real_pos

        moved = False
        if dr != 0:
            target_r = next_grid[0] + 0.5
            if abs(target_r - r) <= offset + epsilon:
                r = target_r
                moved = True
            else:
                r += offset * dr
        if dc != 0:
            target_c = next_grid[1] + 0.5
            if abs(target_c - c) <= offset + epsilon:
                c = target_c
                moved = True
            else:
                c += offset * dc

        self.real_pos = (r, c)
        if moved:
            self.grid_pos = next_grid
        return moved, step_info

    def _pick_box(self):
        box_id = self.map.pick_box_at(self.grid_pos)
        box_size = self.map.box_sizes.get(box_id, 1)
        if box_id is not None and box_size != self.size:
            raise ValueError(
                f"AGV {self.id} cannot pick box {box_id}: size mismatch (AGV={self.size}, box={box_size})")
        if box_id is not None:
            self.carried_box_id = int(box_id)

    def _place_box(self):
        if self.carried_box_id is not None:
            success = self.map.place_box_at(self.grid_pos, self.carried_box_id)
            if success:
                self.carried_box_id = None

    def _handover_box(self, order_id: Optional[int]):
        if self.carried_box_id is None or order_id is None:
            return
        self.order_manager.complete_order(
            order_id=order_id,
            agv_id=self.id,
            box_id=self.carried_box_id,
            agv_pos=self.grid_pos
        )

    def _enter_elevator(self, extra):
        if not isinstance(extra, tuple) or len(extra) != 2:
            return
        elevator_id, target_floor = int(extra[0]), int(extra[1])
        elevator_manager = self.ctx.elevator_manager
        if elevator_manager is None:
            return
        # agv = self.agv_manager.get_agv(agv_id)
        self.set_elevator_phase_name("IN_ELEVATOR")
        self.ctx.agv_manager.remove_agv_from_floor(self.id)

        elevator_manager.mark_boarding_completed(
            agv_id=self.id,
            elevator_id=elevator_id,
            target_floor=target_floor,
            from_floor=int(self.floor_id),
        )

    def assign_task(self, task_positions: List[Tuple[Tuple[int, int], AGVAction, Optional[int]]]):
        self.task_queue = deque(task_positions)
        self.rest_target = None

    def assign_rest_zone(self, rest_pos: Tuple[int, int]):
        self.rest_target = rest_pos

    def set_new_plan(self, path: List[Tuple[int, int]]):
        self.action_queue = deque(path)

    def get_next_pos(self) -> Tuple[int, int]:
        return self.action_queue[0] if self.action_queue else self.grid_pos

    def _execute_action(self, action: AGVAction, extra):
        if action == AGVAction.PICK:
            self._pick_box()
        elif action == AGVAction.PLACE:
            self._place_box()
        elif action == AGVAction.HANDOVER:
            self._handover_box(extra)
        elif action == AGVAction.ENTER_ELEVATOR:
            self._enter_elevator(extra)

    def _maybe_enqueue_next_elevator_task(self):
        if not self.task_queue:
            return
        _, action, extra = self.task_queue[0]
        if action != AGVAction.ENTER_ELEVATOR:
            return
        elevator_id, target_floor = extra
        elevator_manager = self.ctx.elevator_manager
        elevator_manager.enqueue_task(
            elevator_id=int(elevator_id),
            agv_id=self.id,
            from_floor=int(self.floor_id),
            to_floor=int(target_floor),
        )

    def reset(self):
        self.grid_pos = self.init_grid_pos
        self.real_pos = (self.init_grid_pos[0] + 0.5, self.init_grid_pos[1] + 0.5)
        self.task_queue.clear()
        self.action_queue.clear()
        self.rest_target = None
        self.carried_box_id = None
        self.is_working = True
        self.direction = None
        self.last_completed_task_pos = self.init_grid_pos
        self.set_elevator_phase(ElevatorPhase.NORMAL)

    def set_elevator_phase(self, phase: ElevatorPhase):
        self.elevator_phase = phase
        self.in_elevator = phase == ElevatorPhase.IN_ELEVATOR

    def set_elevator_phase_name(self, phase_name: str):
        self.set_elevator_phase(ElevatorPhase[phase_name])

    def is_elevator_phase(self, phase_name: str) -> bool:
        return self.elevator_phase.name == phase_name

    def _calculate_turn_time(self, current_direction: Direction,
                             target_direction: Optional[Direction]) -> int:
        if target_direction is None or current_direction == target_direction:
            return 0
        opposites = {
            Direction.UP: Direction.DOWN,
            Direction.DOWN: Direction.UP,
            Direction.LEFT: Direction.RIGHT,
            Direction.RIGHT: Direction.LEFT,
        }
        if opposites.get(current_direction) == target_direction:
            return self.turning_steps_90 * 2
        return self.turning_steps_90
