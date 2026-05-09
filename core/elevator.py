from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from enum import Enum, auto
from typing import Deque, Dict, List, Optional, Set, TYPE_CHECKING, Tuple

if TYPE_CHECKING:
    from utils.simulation_context import SimulationContext


@dataclass
class ElevatorDef:
    """Static elevator definition from map JSON."""

    elevator_id: int
    position: Tuple[int, int]
    connected_floors: List[int]
    travel_time: int = 5
    size: int = 1


class ElevatorState(Enum):
    IDLE = auto()
    MOVING_TO_PICKUP = auto()
    WAITING_FOR_AGV = auto()
    BOARDING = auto()
    TRANSPORTING = auto()
    WAITING_AGV_EXIT = auto()


@dataclass
class ElevatorTask:
    agv_id: int
    from_floor: int
    to_floor: int


class Elevator:
    """Runtime state of a single elevator that carries AGVs between floors."""

    def __init__(self, definition: ElevatorDef):
        self.id = definition.elevator_id
        self.position = definition.position
        self.connected_floors = definition.connected_floors
        self.travel_time_per_floor = definition.travel_time
        self.size = definition.size

        self.state = ElevatorState.IDLE
        self.current_floor: int = definition.connected_floors[0]
        self.task_queue: Deque[ElevatorTask] = deque()
        self.current_task: Optional[ElevatorTask] = None

        self.wait_timer: int = 0
        self.timer: int = 0
        self.agv_id: Optional[int] = None
        self.target_floor: Optional[int] = None
        self.move_from_floor: Optional[int] = None
        self.move_to_floor: Optional[int] = None
        self.move_direction: str = "idle"

    @property
    def is_available(self) -> bool:
        return self.state == ElevatorState.IDLE and self.current_task is None and self.agv_id is None

    @property
    def display_floor(self) -> float:
        if self.move_from_floor is None or self.move_to_floor is None:
            return float(self.current_floor)
        travel_time = max(1, self.travel_time_per_floor)
        remaining = max(0, min(self.timer, travel_time))
        progress = (travel_time - remaining) / travel_time
        return self.move_from_floor + (self.move_to_floor - self.move_from_floor) * progress

    def reset(self):
        self.state = ElevatorState.IDLE
        self.current_floor = self.connected_floors[0]
        self.task_queue.clear()
        self.current_task = None
        self.wait_timer = 0
        self.timer = 0
        self.agv_id = None
        self.target_floor = None
        self.move_from_floor = None
        self.move_to_floor = None
        self.move_direction = "idle"


class ElevatorManager:
    """Manages all elevators and encapsulates elevator/AGV state transitions."""

    def __init__(self, ctx: SimulationContext):
        self.warehouse_map = ctx.warehouse_map
        self.agv_manager = ctx.agv_manager
        self.logger = ctx.logger
        self.wait_timeout_steps = max(1, int(ctx.system_config.sim_config.elevator_wait_timeout_steps))
        self.elevators: Dict[int, Elevator] = {}
        for eid, edef in self.warehouse_map.elevator_defs.items():
            self.elevators[eid] = Elevator(edef)

    def step(self):
        self._advance_state_machine()

    def enqueue_task(self, elevator_id: int, agv_id: int, from_floor: int, to_floor: int) -> bool:
        elev = self.elevators.get(elevator_id)
        if elev is None:
            return False
        if from_floor not in elev.connected_floors or to_floor not in elev.connected_floors:
            return False
        if from_floor == to_floor:
            return False

        agv = self.agv_manager.get_agv(agv_id)
        if agv.size != elev.size:
            return False

        # for task in elev.task_queue:
        #     if task.agv_id == agv_id and task.from_floor == from_floor and task.to_floor == to_floor:
        #         return True
        # if elev.current_task is not None:
        #     task = elev.current_task
        #     if task.agv_id == agv_id and task.from_floor == from_floor and task.to_floor == to_floor:
        #         return True

        elev.task_queue.append(ElevatorTask(agv_id=agv_id, from_floor=from_floor, to_floor=to_floor))
        return True

    def can_agv_enter(self, agv_id: int, elevator_id: int, floor_id: int) -> bool:
        elev = self.elevators.get(elevator_id)
        if elev is None:
            return False           
        task = elev.current_task
        if task is None:
            return False
        if task.agv_id != agv_id:
            return False
        if task.from_floor != floor_id or elev.current_floor != floor_id:
            return False

        if elev.state == ElevatorState.WAITING_FOR_AGV:
            return True
        if elev.state == ElevatorState.BOARDING and elev.agv_id == agv_id:
            return True
        return False

    def start_boarding(self, agv_id: int, elevator_id: int, floor_id: int) -> bool:
        if not self.can_agv_enter(agv_id=agv_id, elevator_id=elevator_id, floor_id=floor_id):
            return False

        elev = self.elevators[elevator_id]
        if elev.state == ElevatorState.BOARDING and elev.agv_id == agv_id:
            return True

        if elev.state != ElevatorState.WAITING_FOR_AGV:
            return False
        task = elev.current_task
        if task is None:
            return False

        # agv = self.agv_manager.get_agv(agv_id)
        # agv.set_elevator_phase_name("BOARDING_ELEVATOR")
        elev.state = ElevatorState.BOARDING
        elev.agv_id = agv_id
        elev.target_floor = task.to_floor
        self._clear_move_segment(elev)

        self.logger.add_runtime_log(
            f"[Elevator {elevator_id}] AGV {agv_id} starts boarding on F{floor_id}."
        )
        return True

    def mark_boarding_completed(
        self,
        agv_id: int,
        elevator_id: int,
        target_floor: int,
        from_floor: int,
    ) -> bool:
        elev = self.elevators.get(elevator_id)
        if elev is None or elev.state != ElevatorState.BOARDING:
            return False
        task = elev.current_task
        if task is None:
            return False
        if elev.agv_id != agv_id or task.agv_id != agv_id:
            return False
        if task.from_floor != from_floor or task.to_floor != target_floor:
            return False
        if elev.current_floor != from_floor:
            return False

        elev.state = ElevatorState.TRANSPORTING
        elev.target_floor = target_floor
        self._start_move_segment(elev, target_floor)
        return True

    def _advance_state_machine(self):
        for elev in self.elevators.values():
            if elev.state == ElevatorState.IDLE:
                self._try_start_next_task(elev)
            elif elev.state == ElevatorState.MOVING_TO_PICKUP:
                self._advance_move_to_pickup(elev)
            elif elev.state == ElevatorState.WAITING_FOR_AGV:
                self._advance_waiting(elev)
            elif elev.state == ElevatorState.BOARDING:
                self._advance_boarding(elev)
            elif elev.state == ElevatorState.TRANSPORTING:
                self._advance_transport(elev)
            elif elev.state == ElevatorState.WAITING_AGV_EXIT:
                self._advance_wait_agv_exit(elev)

    def _try_start_next_task(self, elev: Elevator):
        if not elev.task_queue:
            return
        elev.current_task = elev.task_queue.popleft()
        self.logger.add_runtime_log(
            f"[Elevator {elev.id}] New task: AGV {elev.current_task.agv_id} from F{elev.current_task.from_floor} to F{elev.current_task.to_floor}."
        )
        elev.agv_id = None
        elev.target_floor = None

        task = elev.current_task
        if elev.current_floor == task.from_floor:
            elev.state = ElevatorState.WAITING_FOR_AGV
            elev.wait_timer = self.wait_timeout_steps
            return

        elev.state = ElevatorState.MOVING_TO_PICKUP
        elev.target_floor = task.from_floor
        self._start_move_segment(elev, task.from_floor)

    def _advance_move_to_pickup(self, elev: Elevator):
        if not self._advance_move_segment(elev):
            return
        task = elev.current_task
        if task is None:
            self._reset_elevator(elev)
            return
        if elev.current_floor != task.from_floor:
            self._start_move_segment(elev, task.from_floor)
            return
        elev.target_floor = None
        elev.state = ElevatorState.WAITING_FOR_AGV
        elev.wait_timer = self.wait_timeout_steps

    def _advance_waiting(self, elev: Elevator):
        elev.wait_timer -= 1
        if elev.wait_timer > 0:
            return

        task = elev.current_task
        if task is not None:
            elev.task_queue.append(task)
            self.logger.add_runtime_log(
                f"[Elevator {elev.id}] wait timeout for AGV {task.agv_id} on F{task.from_floor}, requeued."
            )
        self._reset_elevator(elev)

    def _advance_boarding(self, elev: Elevator):
        task = elev.current_task
        agv_id = elev.agv_id
        if task is None or agv_id is None:
            self._reset_elevator(elev)
            return

        agv = self.agv_manager.get_agv(agv_id)
        if not agv.is_elevator_phase("IN_ELEVATOR"):
            return
        if agv.grid_pos != elev.position:
            return

        # self.agv_manager.remove_agv_from_floor(agv_id)
        # travel_time = abs(task.from_floor - task.to_floor) * elev.travel_time_per_floor
        # elev.state = ElevatorState.TRANSPORTING
        # elev.target_floor = task.to_floor
        # elev.timer = max(1, travel_time)
        self.logger.add_runtime_log(
            f"[Elevator {elev.id}] AGV {agv_id} boarded on F{task.from_floor}, heading to F{task.to_floor}."
        )

    def _clear_move_segment(self, elev: Elevator):
        elev.timer = 0
        elev.move_from_floor = None
        elev.move_to_floor = None
        elev.move_direction = "idle"

    def _start_move_segment(self, elev: Elevator, destination_floor: int) -> bool:
        if elev.current_floor == destination_floor:
            self._clear_move_segment(elev)
            return False

        direction = 1 if destination_floor > elev.current_floor else -1
        elev.move_from_floor = elev.current_floor
        elev.move_to_floor = elev.current_floor + direction
        elev.move_direction = "up" if direction > 0 else "down"
        elev.timer = max(1, elev.travel_time_per_floor)
        return True

    def _advance_move_segment(self, elev: Elevator) -> bool:
        if elev.move_from_floor is None or elev.move_to_floor is None:
            return True

        elev.timer -= 1
        if elev.timer > 0:
            return False

        elev.current_floor = elev.move_to_floor
        self._clear_move_segment(elev)
        return True

    def _advance_transport(self, elev: Elevator):
        if not self._advance_move_segment(elev):
            return

        agv_id = elev.agv_id
        target_floor = elev.target_floor
        if agv_id is None or target_floor is None:
            self._reset_elevator(elev)
            return

        if elev.current_floor != target_floor:
            self._start_move_segment(elev, target_floor)
            return

        agv = self.agv_manager.get_agv(agv_id)
        self.agv_manager.transfer_agv_to_floor(agv_id, target_floor)
        agv.set_elevator_phase_name("NORMAL")
        agv.is_working = True
        self.agv_manager.need_replan_agvs.add(agv_id)

        elev.state = ElevatorState.WAITING_AGV_EXIT
        self.logger.add_runtime_log(f"[Elevator {elev.id}] AGV {agv_id} arrived at F{target_floor}.")

    def _elevator_cell_set(self, elev: Elevator, floor_id: int) -> Set[Tuple[int, int]]:
        floor_grid = self.warehouse_map.get_floor(floor_id)
        return set(floor_grid.get_elevator_cells(elev.id))

    def _advance_wait_agv_exit(self, elev: Elevator):
        agv_id = elev.agv_id
        if agv_id is None:
            self._reset_elevator(elev)
            return

        agv_cells = self.agv_manager.get_agv_footprint_cells(agv_id)
        elevator_cells = self._elevator_cell_set(elev, elev.current_floor)
        if not agv_cells.isdisjoint(elevator_cells):
            return

        self.logger.add_runtime_log(
            f"[Elevator {elev.id}] AGV {agv_id} fully exited on F{elev.current_floor}."
        )
        self._reset_elevator(elev)

    def _reset_elevator(self, elev: Elevator):
        elev.state = ElevatorState.IDLE
        elev.current_task = None
        elev.wait_timer = 0
        elev.timer = 0
        elev.agv_id = None
        elev.target_floor = None
        elev.move_from_floor = None
        elev.move_to_floor = None
        elev.move_direction = "idle"

    def find_elevator(self, from_floor: int, to_floor: int, agv_size: int = 1) -> List[int]:
        """Find suitable elevators, sorted by queue length."""
        candidates: List[Tuple[int, int]] = []
        for eid, elev in self.elevators.items():
            if elev.size != agv_size:
                continue
            if from_floor not in elev.connected_floors or to_floor not in elev.connected_floors:
                continue
            queue_len = len(elev.task_queue) + (1 if elev.current_task is not None else 0)
            candidates.append((queue_len, eid))
        candidates.sort()
        return [eid for _, eid in candidates]

    def get_elevator(self, elevator_id: int) -> Optional[Elevator]:
        return self.elevators.get(elevator_id)

    def get_elevator_ids_by_size(self, size: int) -> List[int]:
        return [eid for eid, elev in self.elevators.items() if elev.size == size]

    def reset(self):
        for elev in self.elevators.values():
            elev.reset()
