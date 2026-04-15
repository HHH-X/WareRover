from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto
from collections import deque
from typing import Dict, List, Tuple, Optional, Deque, TYPE_CHECKING

if TYPE_CHECKING:
    from core.warehouse_map import WarehouseMap, ElevatorDef
    from utils.logger import GlobalLogger


class ElevatorState(Enum):
    IDLE = auto()
    TRANSPORTING = auto()


@dataclass
class TransportRequest:
    """A request to move a box between floors via elevator."""
    box_id: int
    from_floor: int
    to_floor: int
    order_id: Optional[int] = None


class Elevator:
    """Runtime state of a single elevator."""

    def __init__(self, definition: ElevatorDef):
        self.id = definition.elevator_id
        self.position = definition.position
        self.connected_floors = definition.connected_floors
        self.travel_time = definition.travel_time
        self.capacity = definition.capacity

        self.state = ElevatorState.IDLE
        self.current_box_id: Optional[int] = None
        self.from_floor: Optional[int] = None
        self.to_floor: Optional[int] = None
        self.timer: int = 0
        self.queue: Deque[TransportRequest] = deque()

        # Box waiting at elevator port on each floor (delivered but not yet picked up)
        self.pending_boxes: Dict[int, int] = {}  # floor_id -> box_id

    def has_pending_box(self, floor_id: int) -> bool:
        return floor_id in self.pending_boxes

    def get_pending_box(self, floor_id: int) -> Optional[int]:
        return self.pending_boxes.get(floor_id)

    def reset(self):
        self.state = ElevatorState.IDLE
        self.current_box_id = None
        self.from_floor = None
        self.to_floor = None
        self.timer = 0
        self.queue.clear()
        self.pending_boxes.clear()


class ElevatorManager:
    """Manages all elevators: accepts transport requests, steps timers, delivers boxes."""

    def __init__(self, warehouse_map: WarehouseMap, logger: GlobalLogger):
        self.warehouse_map = warehouse_map
        self.logger = logger
        self.elevators: Dict[int, Elevator] = {}
        for eid, edef in warehouse_map.elevator_defs.items():
            self.elevators[eid] = Elevator(edef)

    def request_transport(self, elevator_id: int, box_id: int,
                          from_floor: int, to_floor: int,
                          order_id: Optional[int] = None) -> bool:
        """Queue a transport request. Returns True if accepted."""
        elev = self.elevators.get(elevator_id)
        if elev is None:
            return False
        if from_floor not in elev.connected_floors or to_floor not in elev.connected_floors:
            return False
        elev.queue.append(TransportRequest(box_id, from_floor, to_floor, order_id))
        self.logger.add_runtime_log(
            f"[Elevator {elevator_id}] Transport queued: box {box_id} from F{from_floor} to F{to_floor}")
        return True

    def load_box(self, elevator_id: int, box_id: int, floor_id: int) -> bool:
        """AGV loads a box onto the elevator at the given floor. Starts transport if request matches."""
        elev = self.elevators.get(elevator_id)
        if elev is None or elev.state != ElevatorState.IDLE:
            return False
        if not elev.queue:
            return False
        req = elev.queue[0]
        if req.box_id != box_id or req.from_floor != floor_id:
            return False
        elev.queue.popleft()
        elev.state = ElevatorState.TRANSPORTING
        elev.current_box_id = box_id
        elev.from_floor = floor_id
        elev.to_floor = req.to_floor
        elev.timer = elev.travel_time
        self.logger.add_runtime_log(
            f"[Elevator {elevator_id}] Loaded box {box_id} on F{floor_id}, transporting to F{req.to_floor}")
        return True

    def unload_box(self, elevator_id: int, floor_id: int) -> Optional[int]:
        """AGV picks up a pending box from elevator at the given floor. Returns box_id or None."""
        elev = self.elevators.get(elevator_id)
        if elev is None:
            return None
        box_id = elev.pending_boxes.pop(floor_id, None)
        if box_id is not None:
            self.logger.add_runtime_log(
                f"[Elevator {elevator_id}] Box {box_id} unloaded on F{floor_id}")
        return box_id

    def step(self):
        """Advance all elevator timers by one step."""
        for elev in self.elevators.values():
            if elev.state == ElevatorState.TRANSPORTING:
                elev.timer -= 1
                if elev.timer <= 0:
                    elev.pending_boxes[elev.to_floor] = elev.current_box_id
                    self.logger.add_runtime_log(
                        f"[Elevator {elev.id}] Box {elev.current_box_id} arrived at F{elev.to_floor}")
                    elev.current_box_id = None
                    elev.state = ElevatorState.IDLE
                    elev.from_floor = None
                    elev.to_floor = None

    def find_elevator_for_floors(self, from_floor: int, to_floor: int) -> Optional[int]:
        """Find an available elevator connecting two floors."""
        for eid, elev in self.elevators.items():
            if from_floor in elev.connected_floors and to_floor in elev.connected_floors:
                return eid
        return None

    def get_elevator(self, elevator_id: int) -> Optional[Elevator]:
        return self.elevators.get(elevator_id)

    def reset(self):
        for elev in self.elevators.values():
            elev.reset()
