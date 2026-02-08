# 文件名: map_editor_final_auto_agv_beautified.py
import pygame
from datetime import datetime

# ──────────── 配置 ────────────
W, H       = 20, 15
CELL       = 48           # 稍微加大一点，更舒适
SW         = W * CELL
SH         = H * CELL + 100

BG_COLOR   = (16, 18, 28)       # 深邃夜空蓝灰
GRID_BG    = (28, 30, 45)       # 格子背景
GRID_LINE  = (60, 65, 90)       # 细网格线
HOVER      = (80, 90, 140, 80)  # 半透明白青色悬停

# 类型颜色（更现代、饱和度适中、有区分度）
COLORS = {
    0: (GRID_BG),                     # empty
    1: (90, 180, 255),                # shelf       明亮蓝
    2: (255, 110, 100),               # receiver    温暖红
    3: (100, 100, 115),               # obstacle    暗灰
    4: (120, 255, 160),               # wait zone   鲜亮绿
}

# ──────────── 初始化 ────────────
pygame.init()
screen = pygame.display.set_mode((SW, SH))
pygame.display.set_caption("Warehouse Map Editor  •  AGV count = Wait Zones")
clock  = pygame.time.Clock()

# 字体（建议系统有该字体，否则可换成 "arial" 或 "consolas"）
font_lg = pygame.font.SysFont("microsoftyahei", 22, bold=True)
font_md = pygame.font.SysFont("microsoftyahei", 18)
font_sm = pygame.font.SysFont("microsoftyahei", 16)

grid = [[0] * W for _ in range(H)]
mode = 1
last_msg = ""
last_msg_timer = 0

# ──────────── 导出函数（逻辑不变） ────────────
def export_perfect():
    boxes, recvs, waits, obsts = [], [], [], []

    for y in range(H):
        for x in range(W):
            t = grid[y][x]
            if t == 1:   boxes.append((len(boxes), x, y))
            elif t == 2: recvs.append((len(recvs), x, y))
            elif t == 3: obsts.append((x, y))
            elif t == 4: waits.append((len(waits), x, y))

    agv_count = len(waits)
    filename = f"map_{datetime.now():%m%d_%H%M%S}.json"

    with open(filename, "w", encoding="utf-8") as f:
        f.write("{\n")
        f.write(f'  "map": {{"width": {W}, "height": {H}}},\n\n')
        f.write('  "boxes": [\n')
        for i, (bid, x, y) in enumerate(boxes):
            comma = "," if i < len(boxes)-1 else ""
            f.write(f'    {{"box_id": {bid}, "position": [{x},{y}], "goods_ids": [{bid}]}}{comma}\n')
        f.write('  ],\n\n' if boxes else '  ],\n\n')

        f.write('  "receivers": [\n')
        for i, (rid, x, y) in enumerate(recvs):
            comma = "," if i < len(recvs)-1 else ""
            f.write(f'    {{"receiver_id": {rid}, "position": [{x},{y}]}}{comma}\n')
        f.write('  ],\n\n' if recvs else '  ],\n\n')

        f.write('  "wait_zones": [\n')
        for i, (wid, x, y) in enumerate(waits):
            comma = "," if i < len(waits)-1 else ""
            f.write(f'    {{"wait_zone_id": {wid}, "position": [{x},{y}]}}{comma}\n')
        f.write('  ],\n\n' if waits else '  ],\n\n')

        f.write('  "agvs": [\n')
        for i in range(agv_count):
            comma = "," if i < agv_count-1 else ""
            f.write(f'    {{"agv_id": {i}}}{comma}\n')
        f.write('  ],\n\n')

        f.write('  "obstacles": [\n')
        for i, (x, y) in enumerate(obsts):
            comma = "," if i < len(obsts)-1 else ""
            f.write(f'    [{x},{y}]{comma}\n')
        f.write('  ]\n')
        f.write("}\n")

    print(f"Export successful → {filename}  (AGVs: {agv_count})")
    return filename, agv_count

# ──────────── 主循环 ────────────
running = True
while running:
    mx, my = pygame.mouse.get_pos()
    cx = mx // CELL
    cy = my // CELL
    is_in_grid = (0 <= cx < W and 0 <= cy < H and my < H*CELL)

    for e in pygame.event.get():
        if e.type == pygame.QUIT:
            running = False

        if e.type == pygame.KEYDOWN:
            if pygame.K_1 <= e.key <= pygame.K_4:
                mode = e.key - pygame.K_0
            if e.key in (pygame.K_s, pygame.K_RETURN):
                fn, cnt = export_perfect()
                last_msg = f"Exported → {fn}   (AGV × {cnt})"
                last_msg_timer = 240   # 显示约4秒 (60fps)

        if e.type == pygame.MOUSEBUTTONDOWN and is_in_grid:
            grid[cy][cx] = mode if e.button == 1 else 0

    # ─── 绘制 ───
    screen.fill(BG_COLOR)

    # 绘制网格
    for y in range(H):
        for x in range(W):
            rect = pygame.Rect(x*CELL, y*CELL, CELL, CELL)
            base_color = COLORS[grid[y][x]]

            # 基础填充
            pygame.draw.rect(screen, base_color, rect)

            # 悬停高亮
            if is_in_grid and x == cx and y == cy:
                s = pygame.Surface((CELL, CELL), pygame.SRCALPHA)
                s.fill(HOVER)
                screen.blit(s, rect.topleft)

            # 边框（更细腻的层次感）
            pygame.draw.rect(screen, GRID_LINE, rect, 1)

            # 轻微内发光/高光（可选增强立体感）
            if grid[y][x] != 0:
                highlight = pygame.Surface((CELL, CELL), pygame.SRCALPHA)
                pygame.draw.rect(highlight, (255,255,255,30), (1,1,CELL-2, CELL//3))
                screen.blit(highlight, rect.topleft)

    # 底部控制栏（半透明 + 渐变感）
    bar_rect = pygame.Rect(0, H*CELL, SW, SH - H*CELL)
    bar_surf = pygame.Surface(bar_rect.size, pygame.SRCALPHA)
    bar_surf.fill((25, 28, 50, 240))               # 半透深色
    pygame.draw.rect(bar_surf, (50, 55, 90, 100), bar_rect, border_radius=8)  # 轻微圆角感
    screen.blit(bar_surf, bar_rect.topleft)

    # 当前模式
    mode_names = ["", "Shelf", "Receiver", "Obstacle", "Wait Zone (AGV spawn)"]
    mode_text = font_lg.render(f"Mode: {mode_names[mode]}    (1–4)", True, (220, 230, 255))
    screen.blit(mode_text, (24, H*CELL + 18))

    # 操作提示
    instr = font_md.render("LMB: place    RMB: erase    S / Enter: export", True, (160, 220, 200))
    screen.blit(instr, (24, H*CELL + 52))

    # 导出成功提示（带淡出）
    if last_msg_timer > 0:
        alpha = min(255, last_msg_timer * 3)   # 快速淡入，慢淡出
        txt = font_md.render(last_msg, True, (100, 255, 180))
        txt.set_alpha(alpha)
        screen.blit(txt, (SW//2 - txt.get_width()//2, H*CELL + 52))
        last_msg_timer -= 1

    # 等待区计数器（更醒目的标签风格）
    wait_count = sum(row.count(4) for row in grid)
    count_text = font_lg.render(f"Wait Zones: {wait_count}  →  {wait_count} AGVs", True, (255, 240, 140))
    count_bg = pygame.Surface((count_text.get_width() + 24, count_text.get_height() + 16), pygame.SRCALPHA)
    pygame.draw.rect(count_bg, (60, 70, 40, 220), count_bg.get_rect(), border_radius=6)
    count_bg.blit(count_text, (12, 8))
    screen.blit(count_bg, (SW - count_bg.get_width() - 20, 20))

    pygame.display.flip()
    clock.tick(60)

pygame.quit()