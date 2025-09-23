from typing import Dict, Tuple, Set, List
from core.gridmap import GridMap
from core.agvmanager import AGVManager
epsilon = 1e-4  # 精度容差，可调

class Env:
    def __init__(self, agv_manager: AGVManager, map_inst: GridMap):
        self.agv_manager = agv_manager
        self.map = map_inst

    def get_env_info(self):
        """
        获取当前环境的综合信息，用于状态表示或规划器决策。

        Returns:
            Dict[str, Any]: 包含环境关键信息的字典，具体包含以下键值对：
                - 'grid': np.ndarray
                    地图网格数据，形状为 (height, width) 的整数数组。
                    取值含义：
                        -3: 障碍物（所有情况下都不可通行）
                        -2: 空格（所有情况下都可通行）
                        -1: 空货架（是否可通行取决于AGV的来源方向和载货状态）
                        >=0: 有货箱的货架（载货时不可通行，不载货时可通行）
                
                - 'carrying_status': Dict[int, bool]
                    所有AGV的载货状态字典。
                    键为AGV的ID（整数），值为布尔值：
                        True: 表示该AGV正在携带货箱
                        False: 表示该AGV未携带货箱
                
                - 'action_queues': Dict[int, List[Tuple[int, int]]]
                    所有AGV的动作队列（路径队列）字典。
                    键为AGV的ID（整数），值为坐标元组列表：
                        对于正在休息的AGV：返回包含10个休息目标位置的列表
                        对于活跃的AGV：返回其当前的动作队列（路径点列表）

                - 'current_grid_pos': Dict[int, Tuple[int, int]]
                    所有AGV当前的网格位置字典。
                    键为AGV的ID（整数），值为其当前所在位置的坐标元组 (x, y)
        """
        grid = self.map.map_grid
        carrying_status = self.agv_manager.get_carrying_status()
        action_queues = self.agv_manager.get_all_action_queues()
        current_grid_pos = self.agv_manager.get_all_current_pos()

        return {
            'grid': grid,
            'carrying_status': carrying_status,
            'action_queues': action_queues,
            'current_grid_pos': current_grid_pos
        }
    
    def get_walkable_neighbors(self, pos: Tuple[int, int], carrying_goods: bool) -> List[Tuple[int, int]]:
        """
        获取指定位置在当前载货状态下可通行的相邻位置。

        该方法通过检查当前位置的四个方向（上、下、左、右），判断每个相邻位置是否可通行，
        并返回所有可通行的相邻位置坐标列表。

        Args:
            pos: 当前所在位置的坐标元组 (x, y)
            carrying_goods: AGV当前的载货状态，True表示正在载货，False表示空载

        Returns:
            List[Tuple[int, int]]: 可通行的相邻位置坐标列表，每个元素为 (x, y) 元组
        """
        return self.map.get_walkable_neighbors(pos, carrying_goods)
    
    def is_walkable(self, to_pos: Tuple[int, int], from_pos: Tuple[int, int], carrying_goods: bool) -> bool:
        """
        判断从当前位置移动到目标位置是否可行。

        判断逻辑基于地图网格的单元格类型和AGV的载货状态：
        1. 首先检查目标位置是否在地图边界内
        2. 根据目标位置的单元格类型进行判断：
           - 障碍物(-3): 永远不可通行
           - 空格(-2): 永远可通行
           - 空货架(-1): 空载时可通行；载货时只能从空格走向空货架
           - 有货箱(>=0): 空载时可通行，载货时不可通行

        Args:
            to_pos: 目标位置的坐标元组 (x, y)
            from_pos: 当前位置的坐标元组 (x, y)
            carrying_goods: AGV当前的载货状态，True表示正在载货，False表示空载

        Returns:
            bool: True表示可通行，False表示不可通行
        """
        return self.map.is_walkable(to_pos, from_pos, carrying_goods)

    def step(self):
        next_positions = self.resolve_conflicts()
        self.agv_manager.step_all(next_positions)

    def resolve_conflicts(self) -> Dict[int, Tuple[int, int]]:
        current_pos = self.agv_manager.get_all_current_pos()
        next_pos = self.agv_manager.get_all_next_pos()
        real_pos = self.agv_manager.get_all_real_positions()
        carrying_status = self.agv_manager.get_carrying_status()

        final_next_pos: Dict[int, Tuple[int, int]] = dict(next_pos)

        for agv_id, tgt in next_pos.items():
            cur = current_pos[agv_id]
            dx = abs(tgt[0] - cur[0])
            dy = abs(tgt[1] - cur[1])
            if dx + dy > 1:
                # 超出一步，强制停在原地
                print(f"[Warning] AGV {agv_id} invalid move {cur} -> {tgt}, forced to stay.")
                next_pos[agv_id] = cur

        # 1. 分类 AGV
        in_center, not_in_center = self.classify_by_grid_center(real_pos)

        # 2. 初始化顶点占用字典：格子 -> 占用该位置的 agv_id 集合
        vertex_conflict_dict: Dict[Tuple[int, int], Set[int]] = dict()

        # 3. 固定不在中心的 AGV，并构建初始冲突字典
        for agv_id in not_in_center:
            cur = current_pos[agv_id]
            tgt = final_next_pos[agv_id]
            occ = self._get_next_occupied_positions(agv_id, cur, tgt)

            for pos in occ:
                if pos not in vertex_conflict_dict:
                    vertex_conflict_dict[pos] = set()
                if vertex_conflict_dict[pos]:
                    print("current_pos:", current_pos)
                    print("next_pos:", next_pos)
                    print("real_pos:", real_pos)
                    print("conflict at:", pos, "by agv:", agv_id, "and agv(s):", vertex_conflict_dict[pos])
                    raise ValueError(f"Conflict in static phase for AGV {agv_id} at {pos}")
                vertex_conflict_dict[pos].add(agv_id)

        # 4. 将中心AGV初始设为原地不动
        for agv_id in in_center:
            final_next_pos[agv_id] = current_pos[agv_id]

        # 5. 多轮迭代解决中心AGV冲突
        while True:
            changed = False
            cur_vertex_dict: Dict[Tuple[int, int], Set[int]] = {
                k: set(v) for k, v in vertex_conflict_dict.items()
            }
            edge_conflict_set: Set[Tuple[Tuple[int, int], Tuple[int, int]]] = set()

            # 初始化当前所有已决策的动作占用
            for agv_id in in_center:
                cur = current_pos[agv_id]
                tgt = final_next_pos[agv_id]
                occ = self._get_next_occupied_positions(agv_id, cur, tgt)
                for pos in occ:
                    if pos not in cur_vertex_dict:
                        cur_vertex_dict[pos] = set()
                    cur_vertex_dict[pos].add(agv_id)
                if cur != tgt:
                    edge_conflict_set.add((cur, tgt))

            # 遍历所有中心AGV
            for agv_id in in_center:
                cur = current_pos[agv_id]
                tgt = next_pos[agv_id]
                carrying = carrying_status.get(agv_id, False)

                if tgt == cur:
                    continue

                walkable = self.map.is_walkable(tgt, cur, carrying)
                occ = self._get_next_occupied_positions(agv_id, cur, tgt)

                # 顶点冲突判断：占用区域不能和他人重叠
                has_vertex_conflict = any(
                    (cell in cur_vertex_dict and len(cur_vertex_dict[cell] - {agv_id}) > 0)
                    for cell in occ
                )

                # 交换冲突判断（基于左上角坐标）
                has_edge_conflict = (tgt, cur) in edge_conflict_set

                if walkable and not has_vertex_conflict and not has_edge_conflict:
                    if final_next_pos[agv_id] != tgt:
                        final_next_pos[agv_id] = tgt
                        changed = True
                    for pos in occ:
                        if pos not in cur_vertex_dict:
                            cur_vertex_dict[pos] = set()
                        cur_vertex_dict[pos].add(agv_id)
                    edge_conflict_set.add((cur, tgt))
                else:
                    final_next_pos[agv_id] = cur
                    edge_conflict_set.add((cur, cur))

            if not changed:
                for agv_id in in_center:
                    if final_next_pos[agv_id] != next_pos[agv_id]:
                        self.agv_manager.increment_block_count(agv_id)
                break

        return final_next_pos

    def _get_next_occupied_positions(
        self, agv_id: int, cur: Tuple[int, int], tgt: Tuple[int, int]
    ) -> Set[Tuple[int, int]]:
        """
        返回 AGV 从 cur 移动到 tgt 过程中，所占用的所有格子（考虑 size）
        """
        size = self.agv_manager.get_agv_size(agv_id)  # 新增: 从管理器获取 AGV 的 size

        def footprint(pos: Tuple[int, int]) -> Set[Tuple[int, int]]:
            x, y = pos
            return {(x + dx, y + dy) for dx in range(size) for dy in range(size)}

        if cur == tgt:
            return footprint(cur)

        real_pos = self.agv_manager.get_real_position(agv_id)
        speed = self.agv_manager.get_agv_speed(agv_id)
        time_step = 1

        offset = speed * time_step
        x, y = real_pos
        dx = tgt[0] - cur[0]
        dy = tgt[1] - cur[1]

        # 当前和目标 footprint
        cur_fp = footprint(cur)
        tgt_fp = footprint(tgt)

        occupied: Set[Tuple[int, int]] = set()

        if dx != 0:
            target_x = tgt[0] + 0.5
            if abs(target_x - x) <= offset + epsilon:
                occupied |= tgt_fp
            else:
                occupied |= (cur_fp | tgt_fp)
        elif dy != 0:
            target_y = tgt[1] + 0.5
            if abs(target_y - y) <= offset + epsilon:
                occupied |= tgt_fp
            else:
                occupied |= (cur_fp | tgt_fp)
        else:
            occupied |= cur_fp

        return occupied

    def classify_by_grid_center(self, real_positions: Dict[int, Tuple[float, float]]) -> Tuple[Set[int], Set[int]]:
        """
        根据 AGV 是否在网格中心将其划分为两个集合。
        网格中心定义为坐标的 x 和 y 均为 **.5。
        返回：
            in_center: 在中心的 AGV ID 集合
            not_in_center: 不在中心的 AGV ID 集合
        """
        in_center = set()
        not_in_center = set()

        for agv_id, (x, y) in real_positions.items():
            if abs(x % 1 - 0.5) < epsilon and abs(y % 1 - 0.5) < epsilon:
                in_center.add(agv_id)
            else:
                not_in_center.add(agv_id)

        return in_center, not_in_center

    def reset(self):
        # TODO: 可按需扩展重置逻辑
        pass
