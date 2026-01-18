from collections import deque
from typing import Deque, List, Tuple, Optional, Dict, Set, Generator
from enum import Enum, auto
from core.gridmap import GridMap
from core.ordermanager import OrderManager
from config.settings import SimConfig
import json

epsilon = 1e-4 
class Direction(Enum):
    UP = auto()
    DOWN = auto()
    LEFT = auto()
    RIGHT = auto()

class AGVAction(Enum):
    PICK = "pick"         # 取货
    PLACE = "place"       # 放置货物
    HANDOVER = "handover" # 交接货物，在接收区等待被拾取

class StepInfo(Enum):
    MOVE = auto()          # 移动一步
    COLLISION = auto()     # 碰撞（墙/障碍/其他AGV）
    STAY_OFF_GOAL = auto() # 非目标点且不动
    STAY_ON_GOAL = auto()  # 在目标点上静止
    FINISH = auto()        # 完成任务
    TURNING = auto()
    OTHER = auto()       # 其他情况

class AGV:
    def __init__(
        self,
        agv_id: int,
        size:int,
        init_grid_pos: Tuple[int, int],
        map_inst: GridMap,
        order_manager: OrderManager,
    ):
        self.id: int = agv_id
        # AGV的大小
        self.size: int  = size
        # AGV 当前网格位置 (x, y)
        self.init_grid_pos: Tuple[int, int] = init_grid_pos
        # 对于size大于1的agv来说，坐标为左上角
        self.grid_pos: Tuple[int, int] = init_grid_pos
        # 精确位置 (x, y)
        self.real_pos: Tuple[float, float] = (init_grid_pos[0] + 0.5, init_grid_pos[1] + 0.5)

        self.map = map_inst
        self.order_manager = order_manager

        # 元素为 (位置, 动作, 附加信息)，其中附加信息用于 HANDOVER 时的订单 ID
        self.task_queue: Deque[Tuple[Tuple[int, int], AGVAction, Optional[int]]] = deque()

        self.rest_target: Optional[Tuple[int, int]] = None
        self.action_queue: Deque[Tuple[int, int]] = deque()

        self.speed: float = 0.0
        self.max_speed: float =  SimConfig.agv_max_speed
        self.time_step: float = SimConfig.time_step

        self.direction: Optional[Direction] = Direction.LEFT # 初始朝向向下
        turning_time_90: float = SimConfig.agv_turn_time_90
        self.turning_steps_90: int = int(round(turning_time_90 / self.time_step))
        self.turning_timer: int = 0
        self.target_direction: Optional[Direction] = None

        self.carried_box_id: int = None

        self.is_working: bool = True 

    @property
    def is_idle(self) -> bool:
        return len(self.task_queue) == 0

    @property
    def is_resting(self) -> bool:
        return self.rest_target is not None and self.grid_pos == self.rest_target
    
    @property
    def is_aligned(self) -> bool:
        """
        判断当前 AGV 的 real_pos 是否与 grid_pos 的中心对齐。
        """
        gx, gy = self.grid_pos
        expected_x, expected_y = gx + 0.5, gy + 0.5
        rx, ry = self.real_pos
        return abs(rx - expected_x) < epsilon and abs(ry - expected_y) < epsilon


    def step(self, next_grid: Tuple[int, int]) -> Tuple[bool, StepInfo]:
        if not self.is_working:
            return False, StepInfo.OTHER
        
        if self.turning_timer > 0:
            self.turning_timer -= 1
            if(self.turning_timer == 0):
                self.direction = self.target_direction
            return False, StepInfo.TURNING
               
        _, step_info = self.update_position(next_grid)
        replan_required = False

        # 情况 1：有路径，正常前进
        if self.action_queue and self.grid_pos == self.action_queue[0]:
            self.action_queue.popleft()

            # 检查是否到达任务点
            if self.task_queue and self.grid_pos == self.task_queue[0][0]:
                _, action, extra = self.task_queue.popleft()
                self._execute_action(action, extra)
                replan_required = True
                step_info = StepInfo.FINISH

        # 情况 2：没有路径，但当前位置刚好是任务点
        elif not self.action_queue and self.task_queue and self.grid_pos == self.task_queue[0][0]:
            _, action, extra = self.task_queue.popleft()
            self._execute_action(action, extra)
            replan_required = True
            step_info = StepInfo.FINISH

        # 没有路径，且不是休息状态 -> 需要重新规划
        if not self.action_queue and not self.is_resting:
            replan_required = True

        return replan_required, step_info


    def update_position(self, next_grid: Tuple[int, int]) -> tuple[bool, StepInfo]:
        dx = next_grid[0] - self.grid_pos[0]
        dy = next_grid[1] - self.grid_pos[1]

        step_info = StepInfo.MOVE
        # 判断方向
        if dx == 1:
            self.target_direction = Direction.RIGHT
        elif dx == -1:
            self.target_direction = Direction.LEFT
        elif dy == 1:
            self.target_direction = Direction.DOWN
        elif dy == -1:
            self.target_direction = Direction.UP
        else:
            self.target_direction = None
            step_info = StepInfo.STAY_OFF_GOAL
        #处理目标方向
        self.turning_timer = self._calculate_turn_time(self.direction, self.target_direction)
        if( self.turning_timer > 0):
            self.turning_timer -= 1
            if(self.turning_timer == 0):
                self.direction = self.target_direction
            return False, StepInfo.TURNING
        
        self.speed = self.max_speed
        offset = self.speed * self.time_step
        x, y = self.real_pos

        moved = False
        if dx != 0:
            target_x = next_grid[0] + 0.5  # 中心点
            if abs(target_x - x) <= offset + epsilon:
                x = target_x
                moved = True
            else:
                x += offset * dx
        if dy != 0:
            target_y = next_grid[1] + 0.5
            if abs(target_y - y) <= offset + epsilon:
                y = target_y
                moved = True
            else:
                y += offset * dy

        self.real_pos = (x, y)

        # 如果移动到了方格中心，则更新grid_pos
        if moved:
            self.grid_pos = next_grid
        return moved, step_info

    def _pick_box(self):
        box_id = self.map.pick_box_at(self.grid_pos)
        box_size = self.map.box_sizes.get(box_id, 1)
        if box_id is not None and box_size != self.size:
            raise ValueError(f"AGV {self.id} 尝试拾取尺寸不匹配的货箱 {box_id}（AGV尺寸：{self.size}，货箱尺寸：{box_size}）")
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
        # 注意：不卸货，carried_box_id 保持不变

    def assign_task(self, task_positions: List[Tuple[Tuple[int, int], AGVAction, Optional[int]]]):
        self.task_queue = deque(task_positions)
        self.rest_target = None  # 有任务时不考虑休息

    def assign_rest_zone(self, rest_pos: Tuple[int, int]):
        self.rest_target = rest_pos

    def set_new_plan(self, path: List[Tuple[int, int]]):
        self.action_queue = deque(path)

    def get_next_pos(self) -> Tuple[int, int]:
        return self.action_queue[0] if self.action_queue else self.grid_pos

    def _execute_action(self, action: AGVAction, extra: Optional[int]):
        if action == AGVAction.PICK:
            self._pick_box()
        elif action == AGVAction.PLACE:
            self._place_box()
        elif action == AGVAction.HANDOVER:
            self._handover_box(extra)

    def reset(self):
        """重置 AGV 到初始状态和位置。
        """
        # 位置复原
        self.grid_pos = self.init_grid_pos
        self.real_pos = (self.init_grid_pos[0] + 0.5, self.init_grid_pos[1] + 0.5)

        # 任务相关全部清空
        self.task_queue.clear()
        self.action_queue.clear()
        self.rest_target = None
        self.carried_box_id = None
        self.is_working = True
        self.direction = None
    
    def _calculate_turn_time(self, current_direction: Direction, target_direction: Optional[Direction],) -> int:
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