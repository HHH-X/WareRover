import { AGV } from './entities/agv.js';
import { Shelf } from './entities/shelf.js';
import { Box } from './entities/box.js';
import { Obstacle } from './entities/obstacle.js';
import { RestArea } from './entities/restArea.js';
import { ReceiveArea } from './entities/receiveArea.js';

let ws = null;

function connectWebSocket(world) {
  ws = new WebSocket("ws://localhost:8765");

  ws.onmessage = (event) => {
    const data = JSON.parse(event.data);
    if (data.type === "init") {
      // 初始化地图和对象 ...
      world.addMap(data.map_size);

      if (data.boxes) {
        for (const key in data.boxes) {
          const pos = data.boxes[key];
          world.addBox(new Box(key, pos[0], pos[1]));
        }
      }

      if (data.receivers) {
        for (const key in data.receivers) {
          const pos = data.receivers[key];
          world.addReceiveArea(new ReceiveArea(pos[0], pos[1]));
        }
      }

      if (data.agvs) {
        for (const key in data.agvs) {
          const pos = data.agvs[key];
          world.addAGV(new AGV(parseInt(key), pos[0], pos[1]));
        }
      }

      if (data.wait_zones) {
        for (const key in data.wait_zones) {
          const pos = data.wait_zones[key];
          world.addRestArea(new RestArea(pos[0], pos[1]));
        }
      }

      if (data.obstacles) {
        data.obstacles.forEach(pos => {
          world.addObstacle(new Obstacle(pos[0], pos[1]));
        });
      }
    }

    if (data.type === "update") {
      if (data.agv_pos) {
        for (const key in data.agv_pos) {
          const agv = world.agvs.get(parseInt(key));
          if (agv) {
            agv.update(data.agv_pos[key]);
          }
        }
      }

      if (data.agv_carrying) {
        for (const key in data.agv_carrying) {
          const agv = world.agvs.get(parseInt(key));
          if (agv) {
            agv.setCarryingStatus(data.agv_carrying[key]);
          }
        }
      }
    }
  };
}

export { connectWebSocket, ws };