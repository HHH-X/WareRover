# visualizer/visualizer.py
import pygame
from typing import Tuple
from core.gridmap import GridMap
from core.agvmanager import AGVManager
from config.settings import SimConfig
import json

OBSTACLE_COLOR = (80, 80, 80)
RECEIVER_COLOR = (0, 128, 0)
REST_COLOR = (70, 130, 180)
SHELF_COLOR = (139, 69, 19)
AGV_COLOR = (255, 165, 0)
GRID_LINE_COLOR = (200, 200, 200)
BLACK_TEXT = (0, 0, 0)

class MapVisualizer:
    def __init__(self, screen, cfg:SimConfig, gridmap: GridMap, agv_manager: AGVManager, cell_size: int):
        self.screen = screen
        self.gridmap = gridmap
        self.agv_manager = agv_manager
        self.cell_size = cell_size

        self.font_small = pygame.font.SysFont("Arial", 10)
        self.font_medium = pygame.font.SysFont("Arial", 12)
        self.font_large = pygame.font.SysFont("Arial", 16)

        # 从 JSON 文件读取地图元素
        with open(cfg.map_file, 'r') as f:
            data = json.load(f)

        self.width = data['map']['width'] * cell_size
        self.height = data['map']['height'] * cell_size

        self.obstacle_coords = set(tuple(pos) for pos in data.get('obstacles', []))
        self.box_coords = set(tuple(box['position']) for box in data.get('boxes', []))
        self.receiver_coords = set(tuple(receiver['position']) for receiver in data.get('receivers', []))
        self.rest_coords = set(tuple(wait_zone['position']) for wait_zone in data.get('wait_zones', []))

    def draw_grid(self):
        for x in range(0, self.width, self.cell_size):
            pygame.draw.line(self.screen, GRID_LINE_COLOR, (x, 0), (x, self.height))
        for y in range(0, self.height, self.cell_size):
            pygame.draw.line(self.screen, GRID_LINE_COLOR, (0, y), (self.width, y))

    def draw_map_elements(self):
        for (x, y) in self.obstacle_coords:
            self._draw_cell((x, y), OBSTACLE_COLOR)

        for (x, y) in self.receiver_coords:
            self._draw_cell((x, y), RECEIVER_COLOR)

        for (x, y) in self.rest_coords:
            self._draw_cell((x, y), REST_COLOR)

    def draw_shelves(self):
        for (x, y) in self.box_coords:
            self._draw_cell((x, y), SHELF_COLOR)  # 棕色
            box_id = self.gridmap.get_box_id_at((x, y))
            if box_id is not None:
                # 居中显示 box id
                pos = (x * self.cell_size + self.cell_size // 2, y * self.cell_size + self.cell_size // 2)
                self._draw_text(str(box_id), pos, self.font_large, BLACK_TEXT, center=True)

    def draw_agvs(self):
        for agv in self.agv_manager.all_agvs():
            x, y = agv.real_pos   # size=1: 格子中心; size=2: 左上格子中心
            size = getattr(agv, "size", 1)

            if size == 1:
                # 单格 AGV（中心点）
                screen_x = int(x * self.cell_size)
                screen_y = int(y * self.cell_size)
                center = (screen_x, screen_y)

                pygame.draw.circle(self.screen, AGV_COLOR, center, self.cell_size // 3)
                self._draw_text(str(agv.id), center, self.font_medium, BLACK_TEXT, center=True)

                if agv.carried_box_id is not None:
                    pos = (center[0], center[1] - self.cell_size // 2 - 6)
                    self._draw_text(str(agv.carried_box_id), pos, self.font_medium, BLACK_TEXT, center=True)

            else:
                # size>=2 的 AGV (左上格子中心)
                rect_size = size * self.cell_size

                # 左上角像素坐标 = 左上格子中心 - 半格
                rect_left = int(x * self.cell_size - self.cell_size / 2)
                rect_top = int(y * self.cell_size - self.cell_size / 2)

                rect = pygame.Rect(rect_left, rect_top, rect_size, rect_size)
                pygame.draw.rect(self.screen, AGV_COLOR, rect)

                center = rect.center
                self._draw_text(str(agv.id), center, self.font_medium, BLACK_TEXT, center=True)

                if agv.carried_box_id is not None:
                    pos = (center[0], rect.top - 10)
                    self._draw_text(str(agv.carried_box_id), pos, self.font_medium, BLACK_TEXT, center=True)

    def _draw_cell(self, pos: Tuple[int, int], color: Tuple[int, int, int]):
        x, y = pos
        rect = pygame.Rect(x * self.cell_size, y * self.cell_size, self.cell_size, self.cell_size)
        pygame.draw.rect(self.screen, color, rect)

    def _draw_text(self, text: str, pos: Tuple[int, int], font: pygame.font.Font, color: Tuple[int, int, int], center: bool = True):
        text_surface = font.render(text, True, color)
        text_rect = text_surface.get_rect(center=pos if center else None)
        if not center:
            text_rect.topleft = pos
        self.screen.blit(text_surface, text_rect)

    def draw(self):
        self.draw_grid()
        self.draw_map_elements()
        self.draw_shelves()
        self.draw_agvs()
