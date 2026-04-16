from __future__ import annotations

from enum import Enum, auto
from typing import Dict, List, Tuple, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from core.agvmanager import AGVManager
    from core.warehouse_map import WarehouseMap, ElevatorDef
    from utils.logger import GlobalLogger


class ElevatorState(Enum):
    IDLE = auto()
    TRANSPORTING = auto()


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
        self.agv_id: Optional[int] = None
        self.target_floor: Optional[int] = None
        self.timer: int = 0

    @property
    def is_available(self) -> bool:
        return self.state == ElevatorState.IDLE and self.agv_id is None

    def reset(self):
        self.state = ElevatorState.IDLE
        self.current_floor = self.connected_floors[0]
        self.agv_id = None
        self.target_floor = None
        self.timer = 0


class ElevatorManager:
    """Manages all elevators. Encapsulates boarding, transit, and arrival logic.

    Simulator only needs to call step(); all AGV state transitions are handled internally.
    """

    def __init__(self, warehouse_map: WarehouseMap, agv_manager: AGVManager,
                 logger: GlobalLogger):
        self.warehouse_map = warehouse_map
        self.agv_manager = agv_manager
        self.logger = logger
        self.elevators: Dict[int, Elevator] = {}
        for eid, edef in warehouse_map.elevator_defs.items():
            self.elevators[eid] = Elevator(edef)

    def step(self):
        """Single entry point called by Simulator each step.

        1. Process AGV boarding requests (elevator_pending).
        2. Advance elevator timers.
        3. Handle arrivals (floor transfer + unlock AGV).
        """
        self._process_boarding()
        self._advance_timers()

    def _process_boarding(self):
        """Scan all AGVs for elevator_pending and attempt boarding."""
        for agv in self.agv_manager.all_agvs():
            if agv.elevator_pending is None:
                continue

            elev_id, target_floor = agv.elevator_pending
            elev = self.elevators.get(elev_id)
            if elev is None:
                agv.elevator_pending = None
                continue

            if not elev.is_available:
                continue

            if agv.size > elev.size:
                self.logger.add_runtime_log(
                    f"[Elevator {elev_id}] AGV {agv.id} size {agv.size} exceeds elevator size {elev.size}")
                agv.elevator_pending = None
                continue

            travel_time = abs(agv.floor_id - target_floor) * elev.travel_time_per_floor
            if travel_time <= 0:
                agv.elevator_pending = None
                continue

            elev.state = ElevatorState.TRANSPORTING
            elev.agv_id = agv.id
            elev.target_floor = target_floor
            elev.timer = travel_time

            agv.in_elevator = True
            agv.elevator_pending = None
            self.agv_manager.remove_agv_from_floor(agv.id)

            self.logger.add_runtime_log(
                f"[Elevator {elev_id}] AGV {agv.id} boarded on F{agv.floor_id}, "
                f"heading to F{target_floor} (ETA: {travel_time} steps)")

    def _advance_timers(self):
        """Advance timers and handle arrivals."""
        for elev in self.elevators.values():
            if elev.state != ElevatorState.TRANSPORTING:
                continue

            elev.timer -= 1
            if elev.timer > 0:
                continue

            agv_id = elev.agv_id
            target_floor = elev.target_floor
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

    def find_elevator(self, from_floor: int, to_floor: int,
                      agv_size: int = 1) -> Optional[int]:
        """Find an available elevator connecting two floors that fits the AGV size."""
        for eid, elev in self.elevators.items():
            if (from_floor in elev.connected_floors
                    and to_floor in elev.connected_floors
                    and agv_size <= elev.size):
                return eid
        return None

    def get_elevator(self, elevator_id: int) -> Optional[Elevator]:
        return self.elevators.get(elevator_id)

    def reset(self):
        for elev in self.elevators.values():
            elev.reset()
