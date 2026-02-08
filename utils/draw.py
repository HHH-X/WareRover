# 文件名: map_editor_final_auto_agv.py  ← Ultimate version: AGV count auto follows wait zones
import pygame
from datetime import datetime

W, H = 20, 15
CELL = 45
SW = W * CELL
SH = H * CELL + 80

pygame.init()
screen = pygame.display.set_mode((SW, SH))
pygame.display.set_caption("Warehouse Map Editor")
clock = pygame.time.Clock()
font = pygame.font.SysFont("microsoftyahei", 20, bold=True)

grid = [[0]*W for _ in range(H)]
mode = 1  # 1=shelf 2=receiver 3=obstacle 4=wait zone (AGV spawn point)

def export_perfect():
    boxes, recvs, waits, obsts = [], [], [], []

    for y in range(H):
        for x in range(W):
            t = grid[y][x]
            if t == 1:   # shelf
                bid = len(boxes)
                boxes.append((bid, x, y))
            elif t == 2: # receiver
                recvs.append((len(recvs), x, y))
            elif t == 3: # obstacle
                obsts.append((x, y))
            elif t == 4: # wait zone → determines AGV count!
                waits.append((len(waits), x, y))

    # Key feature: AGV count = number of wait zones
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

        # agvs → count automatically equals wait zones count!
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

    print(f"Export successful! AGV count = Wait zones count = {agv_count} → {filename}")
    return filename, agv_count

# Main loop
running = True
last_msg = ""
while running:
    for e in pygame.event.get():
        if e.type == pygame.QUIT:
            running = False

        if e.type == pygame.KEYDOWN:
            if pygame.K_1 <= e.key <= pygame.K_4:
                mode = e.key - pygame.K_0
            if e.key in (pygame.K_s, pygame.K_RETURN):
                filename, count = export_perfect()
                last_msg = f"Exported {filename}   AGV×{count}"

        if e.type == pygame.MOUSEBUTTONDOWN and e.pos[1] < H*CELL:
            x = e.pos[0] // CELL
            y = e.pos[1] // CELL
            if 0 <= x < W and 0 <= y < H:
                grid[y][x] = mode if e.button == 1 else 0

    # Drawing
    screen.fill((18, 18, 35))
    for y in range(H):
        for x in range(W):
            rect = pygame.Rect(x*CELL, y*CELL, CELL, CELL)
            color = [
                (40,40,60),      # 0 empty
                (80,160,255),    # 1 shelf
                (255,80,80),     # 2 receiver
                (70,70,70),      # 3 obstacle
                (100,255,140)    # 4 wait zone (AGV spawn)
            ][grid[y][x]]
            pygame.draw.rect(screen, color, rect)
            pygame.draw.rect(screen, (140,140,180), rect, 1)

    # Bottom info bar
    pygame.draw.rect(screen, (30,35,65), (0, H*CELL, SW, 80))
    mode_name = ["", "Shelf", "Receiver", "Obstacle", "Wait Zone (determines AGV count)"][mode]
    screen.blit(font.render(f"Current mode: {mode_name}    (1~4 to switch)", True, (255,255,200)), (20, H*CELL + 15))
    screen.blit(font.render("Left click to place    Right click to remove    Press S or Enter to export", True, (180,255,220)), (20, H*CELL + 45))
    if last_msg:
        screen.blit(font.render(last_msg, True, (0, 255, 120)), (SW//2 - 200, H*CELL + 45))

    # Real-time wait zone count display
    wait_count = sum(row.count(4) for row in grid)
    text = font.render(f"Wait zones: {wait_count} → Will generate {wait_count} AGVs", True, (255, 220, 100))
    screen.blit(text, (SW - text.get_width() - 20, 15))

    pygame.display.flip()
    clock.tick(60)

pygame.quit()