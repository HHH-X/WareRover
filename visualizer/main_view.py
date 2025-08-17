# visualizer/main_view.py
import pygame
import sys
import json
from config.settings import SimConfig
from core.gridmap import GridMap
from core.agvmanager import AGVManager
from visualizer.visualizer import MapVisualizer
from visualizer.control_panel import ControlPanel

class MainView:
    def __init__(self, cfg: SimConfig, gridmap: GridMap, agv_manager: AGVManager):
        cell_size = cfg.cell_size
        self.map_width = cfg.width * cell_size
        self.map_height = cfg.height * cell_size
        self.panel_width = cfg.panel_width
        self.fps = 10

        pygame.init()
        self.screen = pygame.display.set_mode((self.map_width + self.panel_width, self.map_height))
        pygame.display.set_caption("AGV 仿真平台")
        self.clock = pygame.time.Clock()
        self.map_visualizer = MapVisualizer(self.screen, cfg, gridmap, agv_manager, cell_size)
        self.panel = ControlPanel(cfg)
    def render(self):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()
            elif event.type == pygame.MOUSEBUTTONDOWN:
                self.panel.handle_click(event.pos)

        self.screen.fill((255, 255, 255))
        self.map_visualizer.draw()
        self.panel.draw(self.screen)

        pygame.display.flip()
        self.clock.tick(self.fps)

    def close(self):
        pygame.quit()

    def is_paused(self):
        return self.panel.is_paused
    def consume_step_trigger(self) -> bool:
        if self.panel.step_triggered:
            self.panel.step_triggered = False
            return True
        return False