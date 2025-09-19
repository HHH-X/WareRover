import { AGV } from './entities/agv.js';
import { Shelf } from './entities/shelf.js';
import { Box } from './entities/box.js';
import { Obstacle } from './entities/obstacle.js';
import { RestArea } from './entities/restArea.js';
import { ReceiveArea } from './entities/receiveArea.js';

function connectWebSocket(world) {
  const ws = new WebSocket("ws://localhost:8765");

  ws.onmessage = (event) => {
    const data = JSON.parse(event.data);
    console.log("收到数据:", data);

    if (data.type === "init") {
      // 初始化地图
      world.addMap(data.map_size);

      // 遍历地图网格
      if (data.map_grid) {
        console.log("初始化地图网格");
        const grid = data.map_grid;
        for (let y = 0; y < grid.length; y++) {
          for (let x = 0; x < grid[y].length; x++) {
            const cell = grid[y][x];
            if (cell === -3) {
              // 障碍物
              const obs = new Obstacle(x, y);
              world.addObstacle(obs);
            } else if (cell === -1) {
              // 空货架
              const shelf = new Shelf(`s-${x}-${y}`, x, y, 1, 1);
              world.addShelf(shelf);
            } else if (cell >= 0) {
              // 有货箱（cell 作为货箱 ID）
              const box = new Box(cell, x, y);
              world.addBox(box);
            }
          }
        }
      }

      // 初始化休息区
      if (data.map_elements?.rest_areas) {
        console.log("初始化休息区:", data.map_elements.rest_areas);
        data.map_elements.rest_areas.forEach(r => {
          const rest = new RestArea(r.x, r.y);
          world.addRestArea(rest);
        });
      }

      // 初始化接收区
      if (data.map_elements?.receive_areas) {
        console.log("初始化接收区:", data.map_elements.receive_areas);
        data.map_elements.receive_areas.forEach(r => {
          const recv = new ReceiveArea(r.x, r.y);
          world.addReceiveArea(recv);
        });
      }

      // 初始化货架（带宽高的那种）
      if (data.map_elements?.shelves) {
        data.map_elements.shelves.forEach(s => {
          const shelf = new Shelf(s.id, s.x, s.y, s.width, s.height);
          world.addShelf(shelf);
        });
      }

      // 初始化 AGV
      if (data.agvs) {
        data.agvs.forEach(a => {
          const agv = new AGV(a.id, a.x, a.y);
          world.addAGV(agv);
        });
      }
    }

    if (data.type === "update") {
      // 更新 AGV 状态
      if (data.agvs) {
        data.agvs.forEach(a => {
          const agv = world.agvs.get(a.id);
          if (agv) {
            agv.update(a.pos, a.direction);
          }
        });
      }
    }
  };
}

export { connectWebSocket };
