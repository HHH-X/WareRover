import random
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Set

from config.settings import SystemConfig
from core.order import Order
from core.warehouse_map import WarehouseMap


class OrderGenerationStrategy(ABC):

    def __init__(self, system_config: SystemConfig, warehouse_map: WarehouseMap):
        self.system_config = system_config
        self.warehouse_map = warehouse_map
        self.rng = random.Random(self.system_config.sim_config.order_seed)
        ratio = self.system_config.sim_config.cross_floor_order_ratio
        self.cross_floor_order_ratio = max(0.0, min(1.0, ratio))

        self._floor_goods_by_size: Dict[int, Dict[int, List[int]]] = {}
        self._floor_receivers_by_size: Dict[int, Dict[int, List[int]]] = {}
        self._goods_floors_by_size: Dict[int, Dict[int, List[int]]] = {}
        self._all_goods_ids_by_size: Dict[int, List[int]] = {}
        self._prepare_floor_indexes()

    @abstractmethod
    def update(self, current_step: int) -> List[Order]:
        pass

    def _prepare_floor_indexes(self) -> None:
        for floor_id in self.warehouse_map.all_floor_ids():
            floor_grid = self.warehouse_map.get_floor(floor_id)
            goods_by_size: Dict[int, Set[int]] = {}
            for box_id in floor_grid.box_id_set:
                size = floor_grid.box_sizes.get(box_id, 1)
                goods_list = floor_grid.get_goods_by_box(box_id)
                if goods_list:
                    goods_by_size.setdefault(size, set()).update(goods_list)

            receivers_by_size: Dict[int, Set[int]] = {}
            for receiver_id in floor_grid.receiver_id_set:
                size = floor_grid.receiver_zones_size.get(receiver_id, 1)
                receivers_by_size.setdefault(size, set()).add(receiver_id)

            self._floor_goods_by_size[floor_id] = {
                size: sorted(list(goods_set))
                for size, goods_set in goods_by_size.items()
            }
            self._floor_receivers_by_size[floor_id] = {
                size: sorted(list(receiver_set))
                for size, receiver_set in receivers_by_size.items()
            }

            for size, goods_ids in self._floor_goods_by_size[floor_id].items():
                goods_floor_map = self._goods_floors_by_size.setdefault(size, {})
                for goods_id in goods_ids:
                    goods_floor_map.setdefault(goods_id, []).append(floor_id)

        for size, goods_floor_map in self._goods_floors_by_size.items():
            for floor_list in goods_floor_map.values():
                floor_list.sort()
            self._all_goods_ids_by_size[size] = sorted(list(goods_floor_map.keys()))

    def _build_order(
        self,
        size: int,
        goods_id: int,
        receiver_id: int,
        source_floor: int,
        target_floor: int,
    ) -> Order:
        return Order(
            order_id=-1,
            goods_id=goods_id,
            receiver_id=receiver_id,
            required_size=size,
            source_floor=source_floor,
            target_floor=target_floor,
            is_cross_floor=source_floor != target_floor,
        )

    def _generate_single_same_floor_order(
        self, size: int, preferred_goods_id: Optional[int] = None
    ) -> Optional[Order]:
        candidate_floors: List[int] = []
        for floor_id in self.warehouse_map.all_floor_ids():
            goods_ids = self._floor_goods_by_size.get(floor_id, {}).get(size, [])
            receiver_ids = self._floor_receivers_by_size.get(floor_id, {}).get(size, [])
            if not goods_ids or not receiver_ids:
                continue
            if preferred_goods_id is not None and preferred_goods_id not in goods_ids:
                continue
            candidate_floors.append(floor_id)

        if not candidate_floors:
            return None

        floor_id = self.rng.choice(candidate_floors)
        floor_goods = self._floor_goods_by_size[floor_id][size]
        goods_id = preferred_goods_id if preferred_goods_id is not None else self.rng.choice(floor_goods)
        if goods_id not in floor_goods:
            return None
        receiver_ids = self._floor_receivers_by_size[floor_id][size]
        receiver_id = self.rng.choice(receiver_ids)
        return self._build_order(size, goods_id, receiver_id, floor_id, floor_id)

    def _generate_single_cross_floor_order(
        self, size: int, preferred_goods_id: Optional[int] = None
    ) -> Optional[Order]:
        floor_ids = self.warehouse_map.all_floor_ids()
        if len(floor_ids) < 2:
            return None

        source_candidates: List[int] = []
        for floor_id in floor_ids:
            goods_ids = self._floor_goods_by_size.get(floor_id, {}).get(size, [])
            if not goods_ids:
                continue
            if preferred_goods_id is not None and preferred_goods_id not in goods_ids:
                continue
            has_receiver_on_other_floor = any(
                other_floor != floor_id
                and self._floor_receivers_by_size.get(other_floor, {}).get(size, [])
                for other_floor in floor_ids
            )
            if has_receiver_on_other_floor:
                source_candidates.append(floor_id)

        if not source_candidates:
            return None

        source_floor = self.rng.choice(source_candidates)
        source_goods = self._floor_goods_by_size[source_floor][size]
        goods_id = preferred_goods_id if preferred_goods_id is not None else self.rng.choice(source_goods)
        if goods_id not in source_goods:
            return None

        target_candidates = [
            floor_id
            for floor_id in floor_ids
            if floor_id != source_floor
            and self._floor_receivers_by_size.get(floor_id, {}).get(size, [])
        ]
        if not target_candidates:
            return None

        target_floor = self.rng.choice(target_candidates)
        receiver_ids = self._floor_receivers_by_size[target_floor][size]
        receiver_id = self.rng.choice(receiver_ids)
        return self._build_order(size, goods_id, receiver_id, source_floor, target_floor)

    def _generate_single_order(
        self, size: int, preferred_goods_id: Optional[int] = None
    ) -> Optional[Order]:
        prefer_cross = self.rng.random() < self.cross_floor_order_ratio
        if prefer_cross:
            order = self._generate_single_cross_floor_order(size, preferred_goods_id)
            if order is not None:
                return order
            return self._generate_single_same_floor_order(size, preferred_goods_id)
        order = self._generate_single_same_floor_order(size, preferred_goods_id)
        if order is not None:
            return order
        return self._generate_single_cross_floor_order(size, preferred_goods_id)

    def _generate_batch_orders(self, batch_size: int) -> List[Order]:
        num_size2 = int(batch_size * self.system_config.sim_config.size2_ratio)
        num_size1 = batch_size - num_size2
        new_orders: List[Order] = []
        for size, count in [(1, num_size1), (2, num_size2)]:
            for _ in range(count):
                order = self._generate_single_order(size)
                if order:
                    new_orders.append(order)
        return new_orders
