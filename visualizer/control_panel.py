# visualizer/control_panel.py
import pygame
from typing import Tuple, List
from config.settings import SimConfig

BLACK_TEXT = (0, 0, 0)
BUTTON_COLOR = (180, 180, 180)
BG_COLOR = (240, 240, 240)

class ControlPanel:
    def __init__(self, cfg: SimConfig):
        self.left_offset = cfg.width * cfg.cell_size
        self.panel_width = cfg.panel_width
        self.panel_height = cfg.height * cfg.cell_size
        self.order_list: List[dict] = []

        # 按钮
        self.pause_button_rect = pygame.Rect(self.left_offset + 20, 20, 100, 40)
        self.is_paused = False

        self.step_button_rect = pygame.Rect(self.left_offset + 20, 70, 100, 40)
        self.step_triggered = False

        # 字体
        self.font_small = pygame.font.SysFont("Arial", 10)
        self.font_medium = pygame.font.SysFont("Arial", 12)
        self.font_large = pygame.font.SysFont("Arial", 16)

    def draw(self, surface: pygame.Surface):
        # 绘制背景面板
        panel_rect = pygame.Rect(self.left_offset, 0, self.panel_width, self.panel_height)
        pygame.draw.rect(surface, BG_COLOR, panel_rect)

        # 各部分绘制
        self._draw_buttons(surface)
        self._draw_order_info(surface)
        # self._draw_metrics(surface)

    def _draw_buttons(self, surface: pygame.Surface):
        """绘制控制按钮"""
        pygame.draw.rect(surface, BUTTON_COLOR, self.pause_button_rect)
        label = "Resume" if self.is_paused else "Pause"
        text_surf = self.font_medium.render(label, True, BLACK_TEXT)
        surface.blit(text_surf, (self.pause_button_rect.x + 10, self.pause_button_rect.y + 10))

        pygame.draw.rect(surface, BUTTON_COLOR, self.step_button_rect)
        step_text_surf = self.font_medium.render("Step", True, BLACK_TEXT)
        surface.blit(step_text_surf, (self.step_button_rect.x + 10, self.step_button_rect.y + 10))

    def _draw_order_info(self, surface: pygame.Surface):
        """绘制订单完成信息"""
        y_offset = 140  # 按钮下面开始绘制
        surface.blit(self.font_large.render("Orders", True, BLACK_TEXT), (self.left_offset + 10, y_offset))
        y_offset += 25
        for idx, order in enumerate(self.order_list[:10]):
            order_text = f"Order {order['id']}: {order['status']}"
            surface.blit(self.font_medium.render(order_text, True, BLACK_TEXT), (self.left_offset + 10, y_offset))
            y_offset += 20

    def _draw_metrics(self, surface: pygame.Surface):
        """绘制运行指标"""
        y_offset = 400  # 固定在下面
        surface.blit(self.font_large.render("Metrics", True, BLACK_TEXT), (self.left_offset + 10, y_offset))
        y_offset += 25

        # 遍历显示指标（外部赋值 self.metrics = {...}）
        for key, value in self.metrics.items():
            metric_text = f"{key}: {value}"
            surface.blit(self.font_medium.render(metric_text, True, BLACK_TEXT), (self.left_offset + 10, y_offset))
            y_offset += 20

    def handle_click(self, pos: Tuple[int, int]):
        # 直接使用屏幕坐标检测
        if self.pause_button_rect.collidepoint(pos):
            self.is_paused = not self.is_paused
        elif self.step_button_rect.collidepoint(pos):
            if not self.is_paused:
                self.is_paused = True  # 自动暂停
            self.step_triggered = True