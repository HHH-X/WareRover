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
        self.height =  cfg.height * cfg.cell_size
        self.order_list: List[dict] = []

        self.pause_button_rect = pygame.Rect(20, 20, 100, 40)
        self.is_paused = False

        self.step_button_rect = pygame.Rect(20, 70, 100, 40)
        self.step_triggered = False

        self.font_small = pygame.font.SysFont("Arial", 10)
        self.font_medium = pygame.font.SysFont("Arial", 12)
        self.font_large = pygame.font.SysFont("Arial", 16)

    def draw(self, surface: pygame.Surface):
        panel_rect = pygame.Rect(self.left_offset, 0, self.panel_width, self.height)
        pygame.draw.rect(surface, BG_COLOR, panel_rect)

        pygame.draw.rect(surface, BUTTON_COLOR, self.pause_button_rect.move(self.left_offset, 0))
        label = "Resume" if self.is_paused else "Pause"
        text_surf = self.font_medium.render(label, True, BLACK_TEXT)
        surface.blit(text_surf, self.pause_button_rect.move(self.left_offset + 10, 10))

        pygame.draw.rect(surface, BUTTON_COLOR, self.step_button_rect.move(self.left_offset, 0))
        step_text_surf = self.font_medium.render("Step", True, BLACK_TEXT)
        surface.blit(step_text_surf, self.step_button_rect.move(self.left_offset + 10, 10))

        y_offset = 80
        for idx, order in enumerate(self.order_list[:10]):
            order_text = f"Order {order['id']}: {order['status']}"
            surface.blit(self.font_medium.render(order_text, True, BLACK_TEXT), (self.left_offset + 10, y_offset))
            y_offset += 20

    def handle_click(self, pos: Tuple[int, int]):
        relative_pos = (pos[0] - self.left_offset, pos[1])
        if self.pause_button_rect.collidepoint(relative_pos):
            self.is_paused = not self.is_paused
        elif self.step_button_rect.collidepoint(relative_pos):
            if not self.is_paused:
                self.is_paused = True  # 自动暂停
            self.step_triggered = True