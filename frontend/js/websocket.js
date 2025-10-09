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
    // try {
    //   const data = JSON.parse(event.data);
    //   console.log("收到数据:", data);
    // } catch (err) {
    //   console.error("JSON 解析失败:", event.data, err);
    // }
    const data = JSON.parse(event.data);
    console.log("get data: ",data)
    if (data.type === "init") {
      // 初始化地图和对象 ...
      world.addMap(data.map_size);
      
      if (data.boxes) {
        for (const boxId in data.boxes) {
          const box = data.boxes[boxId];
          const pos = box.pos;
          const size = box.size;
          world.addBox(new Box(parseInt(key), pos[0], pos[1]));
          world.addShelf(new Shelf(parseInt(key), pos[0], pos[1]));
          
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
      // 更新 AGV 位置
      if (data.agv_pos) {
        for (const key in data.agv_pos) {
          const pos = data.agv_pos[key];
          const agv = world.agvs.get(parseInt(key));
          if (agv) agv.update(pos);
        }
      }

      // 直接更新 Box 坐标（AGV 上和 shelf 上分开处理）
      if (data.boxes_on_agv) {
        for (const [boxId, pos] of Object.entries(data.boxes_on_agv)) {
          const box = world.boxes.get(parseInt(boxId));
          if (box) box.setXYZ(pos[0], 0.55, pos[1]); // y = 0.5 高度
        }
      }

      if (data.boxes_on_shelf) {
        for (const [boxId, pos] of Object.entries(data.boxes_on_shelf)) {
          const box = world.boxes.get(parseInt(boxId));
          if (box) box.setXYZ(pos[0], 0.7, pos[1]); // y = 0.5 高度
        }
      }
    }
  };
}

export { connectWebSocket, ws };