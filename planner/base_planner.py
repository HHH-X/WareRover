from abc import ABC, abstractmethod
from typing import Dict, Tuple, List, Set
from collections import defaultdict
from core.env import Env

class BasePlanner(ABC):
    def __init__(self, env_instance:Env):
        self.env = env_instance
        self.max_time = 100

    @abstractmethod
    def plan(self, targets: Dict[int, Tuple[Tuple[int, int], Tuple[int, int]]]) -> Dict[int, List[Tuple[int, int]]]:
        """
        对需要重规划路径的 AGV 进行集中式路径规划，返回路径列表
        参数:
            targets: dict {agv_id: (start_pos, target_pos)}
        返回:
            paths: dict {agv_id: List[path]}
        """
        pass