from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from enum import Enum, auto
from typing import Deque, Dict, Optional, TYPE_CHECKING, Tuple, List

if TYPE_CHECKING:
    from core.agv import AGV
    from core.agvmanager import AGVManager
    from core.warehouse_map import WarehouseMap
    from utils.logger import GlobalLogger
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
    TRANSPORTING = auto()


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

        self.agv_id: Optional[int] = None
        self.target_floor: Optional[int] = None
        self.timer: int = 0

    @property
    def is_available(self) -> bool:
        return self.state == ElevatorState.IDLE and self.agv_id is None

    def reset(self):
        self.state = ElevatorState.IDLE
        self.current_floor = self.connected_floors[0]
        self.task_queue.clear()
        self.current_task = None
        self.wait_timer = 0
        self.agv_id = None
        self.target_floor = None
        self.timer = 0


class ElevatorManager:
    """Manages all elevators. Encapsulates boarding, transit, and arrival logic.

    Simulator only needs to call step(); all AGV state transitions are handled internally.
    """

    def __init__(
        self,
        ctx: SimulationContext
    ):
        self.warehouse_map = ctx.warehouse_map
        self.agv_manager = ctx.agv_manager
        self.logger = ctx.logger
        self.wait_timeout_steps = max(1, int(ctx.system_config.sim_config.elevator_wait_timeout_steps))
        self.elevators: Dict[int, Elevator] = {}
        for eid, edef in self.warehouse_map.elevator_defs.items():
            self.elevators[eid] = Elevator(edef)

    def step(self):
        self._advance_state_machine()
        self._process_boarding_requests()

    def enqueue_task(self, elevator_id: int, agv_id: int, from_floor: int, to_floor: int) -> bool:
        elev = self.elevators.get(elevator_id)
        if elev is None:
            return False
        if from_floor not in elev.connected_floors or to_floor not in elev.connected_floors:
            return False
        if from_floor == to_floor:
            return False
        agv = self.agv_manager.get_agv(agv_id)
        if agv.size > elev.size:
            return False

        for task in elev.task_queue:
            if task.agv_id == agv_id and task.from_floor == from_floor and task.to_floor == to_floor:
                return True
        if (elev.current_task is not None
                and elev.current_task.agv_id == agv_id
                and elev.current_task.from_floor == from_floor
                and elev.current_task.to_floor == to_floor):
            return True

        elev.task_queue.append(ElevatorTask(agv_id=agv_id, from_floor=from_floor, to_floor=to_floor))
        return True

    def can_agv_enter(self, agv_id: int, elevator_id: int, floor_id: int) -> bool:
        elev = self.elevators.get(elevator_id)
        if elev is None or elev.state != ElevatorState.WAITING_FOR_AGV:
            return False
        task = elev.current_task
        if task is None:
            return False
        if task.agv_id != agv_id or task.from_floor != floor_id:
            return False
        if elev.current_floor != floor_id:
            return False
        agv = self.agv_manager.get_agv(agv_id)
        if agv.floor_id != floor_id or agv.size > elev.size:
            return False
        if agv.elevator_pending == (elevator_id, task.to_floor):
            return True
        return self._is_agv_heading_to_elevator_task(agv, elevator_id)

    def _is_agv_heading_to_elevator_task(self, agv: AGV, elevator_id: int) -> bool:
        if not agv.task_queue:
            return False
        task_pos, action, extra = agv.task_queue[0]
        if getattr(action, "name", None) != "ENTER_ELEVATOR":
            return False
        if not isinstance(extra, tuple) or len(extra) != 2:
            return False
        planned_eid, _ = extra
        if planned_eid != elevator_id:
            return False
        elevator_pos = self.warehouse_map.get_elevator_position(elevator_id)
        if elevator_pos is None:
            return False
        return task_pos == elevator_pos

    def _advance_state_machine(self):
        for elev in self.elevators.values():
            if elev.state == ElevatorState.IDLE:
                self._try_start_next_task(elev)
            elif elev.state == ElevatorState.MOVING_TO_PICKUP:
                self._advance_move_to_pickup(elev)
            elif elev.state == ElevatorState.WAITING_FOR_AGV:
                self._advance_waiting(elev)
            elif elev.state == ElevatorState.TRANSPORTING:
                self._advance_transport(elev)

    def _try_start_next_task(self, elev: Elevator):
        if not elev.task_queue:
            return
        elev.current_task = elev.task_queue.popleft()
        task = elev.current_task
        if elev.current_floor == task.from_floor:
            elev.state = ElevatorState.WAITING_FOR_AGV
            elev.wait_timer = self.wait_timeout_steps
        else:
            elev.state = ElevatorState.MOVING_TO_PICKUP
            elev.timer = abs(elev.current_floor - task.from_floor) * elev.travel_time_per_floor
            if elev.timer <= 0:
                elev.timer = 1

    def _advance_move_to_pickup(self, elev: Elevator):
        elev.timer -= 1
        if elev.timer > 0:
            return
        task = elev.current_task
        if task is None:
            elev.state = ElevatorState.IDLE
            return
        elev.current_floor = task.from_floor
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
                f"[Elevator {elev.id}] Wait timeout for AGV {task.agv_id} on F{task.from_floor}, task requeued.")
        elev.current_task = None
        elev.state = ElevatorState.IDLE

    def _advance_transport(self, elev: Elevator):
        elev.timer -= 1
        if elev.timer > 0:
            return

        agv_id = elev.agv_id
        target_floor = elev.target_floor
        if agv_id is None or target_floor is None:
            elev.state = ElevatorState.IDLE
            elev.agv_id = None
            elev.target_floor = None
            elev.current_task = None
            return
        agv = self.agv_manager.get_agv(agv_id)
        self.agv_manager.transfer_agv_to_floor(agv_id, target_floor)
        agv.in_elevator = False
        self.agv_manager.need_replan_agvs.add(agv_id)

        self.logger.add_runtime_log(
            f"[Elevator {elev.id}] AGV {agv_id} arrived at F{target_floor}")

        elev.current_floor = target_floor
        elev.state = ElevatorState.IDLE
        elev.agv_id = None
        elev.target_floor = None
        elev.current_task = None

    def _process_boarding_requests(self):
        for agv in self.agv_manager.all_agvs():
            if agv.elevator_pending is None:
                continue
            elev_id, target_floor = agv.elevator_pending
            if not self.can_agv_enter(agv.id, elev_id, agv.floor_id):
                continue

            elev = self.elevators[elev_id]
            task = elev.current_task
            if task is None or task.to_floor != target_floor:
                continue

            travel_time = abs(task.from_floor - task.to_floor) * elev.travel_time_per_floor
            if travel_time <= 0:
                agv.elevator_pending = None
                elev.current_task = None
                elev.state = ElevatorState.IDLE
                continue

            elev.state = ElevatorState.TRANSPORTING
            elev.agv_id = agv.id
            elev.target_floor = task.to_floor
            elev.timer = travel_time

            agv.in_elevator = True
            agv.elevator_pending = None
            self.agv_manager.remove_agv_from_floor(agv.id)

            self.logger.add_runtime_log(
                f"[Elevator {elev_id}] AGV {agv.id} boarded on F{agv.floor_id}, "
                f"heading to F{task.to_floor} (ETA: {travel_time} steps)")

    def find_elevator(self, from_floor: int, to_floor: int,
                      agv_size: int = 1) -> Optional[int]:
        """Find a suitable elevator by queue/load and floor distance."""
        candidates: list[tuple[int, int, int]] = []
        for eid, elev in self.elevators.items():
            if (from_floor in elev.connected_floors
                    and to_floor in elev.connected_floors
                    and agv_size <= elev.size):
                pending = len(elev.task_queue) + (1 if elev.current_task is not None else 0)
                floor_distance = abs(elev.current_floor - from_floor)
                candidates.append((pending, floor_distance, eid))
        if not candidates:
            return None
        candidates.sort()
        return candidates[0][2]

    def get_elevator(self, elevator_id: int) -> Optional[Elevator]:
        return self.elevators.get(elevator_id)

    def reset(self):
        for elev in self.elevators.values():
            elev.reset()
