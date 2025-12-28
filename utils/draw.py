# 文件名: map_editor_final_auto_agv.py  ← 终极版：AGV 数量自动跟随等待区
import pygame
from datetime import datetime

W, H = 20, 15
CELL = 45
SW = W * CELL
SH = H * CELL + 80

pygame.init()
screen = pygame.display.set_mode((SW, SH))
pygame.display.set_caption("仓库地图编辑器 - AGV数量自动等于等待区数量")
clock = pygame.time.Clock()
font = pygame.font.SysFont("microsoftyahei", 20, bold=True)

grid = [[0]*W for _ in range(H)]
mode = 1  # 1货架 2接收站 3障碍 4等待区（AGV停靠点）

def export_perfect():
    boxes, recvs, waits, obsts = [], [], [], []

    for y in range(H):
        for x in range(W):
            t = grid[y][x]
            if t == 1:   # 货架
                bid = len(boxes)
                boxes.append((bid, x, y))
            elif t == 2: # 接收站
                recvs.append((len(recvs), x, y))
            elif t == 3: # 障碍
                obsts.append((x, y))
            elif t == 4: # 等待区 → 决定AGV数量！
                waits.append((len(waits), x, y))

    # 关键：AGV 数量 = 等待区数量
    agv_count = len(waits)

    filename = f"map_{datetime.now():%m%d_%H%M%S}.json"
    with open(filename, "w", encoding="utf-8") as f:
        f.write("{\n")
        f.write(f'  "map": {{\n    "width": {W},\n    "height": {H}\n  }},\n\n')

        # boxes
        f.write('  "boxes": [\n')
        for i, (bid, x, y) in enumerate(boxes):
            comma = "," if i < len(boxes)-1 else ""
            f.write(f'    {{ "box_id": {bid}, "position": [{x}, {y}], "goods_ids": [{bid}] }}{comma}\n')
        f.write('  ],\n\n' if boxes else '  ],\n\n')

        # receivers
        f.write('  "receivers": [\n')
        for i, (rid, x, y) in enumerate(recvs):
            comma = "," if i < len(recvs)-1 else ""
            f.write(f'    {{ "receiver_id": {rid}, "position": [{x}, {y}] }}{comma}\n')
        f.write('  ],\n\n' if recvs else '  ],\n\n')

        # wait_zones
        f.write('  "wait_zones": [\n')
        for i, (wid, x, y) in enumerate(waits):
            comma = "," if i < len(waits)-1 else ""
            f.write(f'    {{ "wait_zone_id": {wid}, "position": [{x}, {y}] }}{comma}\n')
        f.write('  ],\n\n' if waits else '  ],\n\n')

        # agvs → 数量自动等于等待区数量！
        f.write('  "agvs": [\n')
        for i in range(agv_count):
            comma = "," if i < agv_count-1 else ""
            f.write(f'    {{ "agv_id": {i} }}{comma}\n')
        f.write('  ],\n\n')

        # obstacles
        f.write('  "obstacles": [\n')
        for i, (x, y) in enumerate(obsts):
            comma = "," if i < len(obsts)-1 else ""
            f.write(f'    [{x}, {y}]{comma}\n')
        f.write('  ]\n')

        f.write("}")

    print(f"导出成功！AGV数量 = 等待区数量 = {agv_count} → {filename}")
    return filename, agv_count

# 主循环
running = True
last_msg = ""
while running:
    for e in pygame.event.get():
        if e.type == pygame.QUIT:
            running = False

        if e.type == pygame.KEYDOWN:
            if pygame.K_1 <= e.key <= pygame.K_4:
                mode = e.key - pygame.K_0  # K_1→1, K_2→4
            if e.key in (pygame.K_s, pygame.K_RETURN):
                filename, count = export_perfect()
                last_msg = f"已导出 {filename}   AGV×{count}"

        if e.type == pygame.MOUSEBUTTONDOWN and e.pos[1] < H*CELL:
            x = e.pos[0] // CELL
            y = e.pos[1] // CELL
            if 0 <= x < W and 0 <= y < H:
                grid[y][x] = mode if e.button == 1 else 0

    # 绘制
    screen.fill((18, 18, 35))
    for y in range(H):
        for x in range(W):
            rect = pygame.Rect(x*CELL, y*CELL, CELL, CELL)
            color = [
                (40,40,60),      # 0 空
                (80,160,255),    # 1 货架
                (255,80,80),     # 2 接收站
                (70,70,70),      # 3 障碍
                (100,255,140)    # 4 等待区（AGV出生点）
            ][grid[y][x]]
            pygame.draw.rect(screen, color, rect)
            pygame.draw.rect(screen, (140,140,180), rect, 1)

    # 底部信息栏
    pygame.draw.rect(screen, (30,35,65), (0, H*CELL, SW, 80))
    mode_name = ["", "货架", "接收站", "障碍", "等待区(决定AGV数量)"][mode]
    screen.blit(font.render(f"当前模式：{mode_name}　　(1~4切换)", True, (255,255,200)), (20, H*CELL + 15))
    screen.blit(font.render("左键放置　右键删除　　按 S 或 Enter 导出", True, (180,255,220)), (20, H*CELL + 45))
    if last_msg:
        screen.blit(font.render(last_msg, True, (0, 255, 120)), (SW//2 - 200, H*CELL + 45))

    # 实时显示当前等待区数量
    wait_count = sum(row.count(4) for row in grid)
    text = font.render(f"等待区数量 = {wait_count} → 将生成 {wait_count} 台 AGV", True, (255, 220, 100))
    screen.blit(text, (SW - text.get_width() - 20, 15))

    pygame.display.flip()
    clock.tick(60)

pygame.quit()