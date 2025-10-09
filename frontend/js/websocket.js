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
          world.addBox(new Box(parseInt(boxId), pos, size));
          world.addShelf(new Shelf(parseInt(boxId), pos, size));
          
        }
      }

      if (data.receivers) {
        for (const key in data.receivers) {
          const receiver = data.receivers[key];
          world.addReceiveArea(new ReceiveArea(receiver.pos, receiver.size));
        }
      }

      if (data.agvs) {
        for (const agvId in data.agvs) {
          const agv = data.agvs[agvId];
          world.addAGV(new AGV(parseInt(agvId), agv.pos, agv.size));
        }
      }

      if (data.wait_zones) {
        for (const key in data.wait_zones) {
          const wait_zone = data.wait_zones[key];
          world.addRestArea(new RestArea(wait_zone.pos, wait_zone.size));
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
      if (data.agvs) {
        for (const key in data.agvs) {
          const pos = data.agvs[key];
          const agv = world.agvs.get(parseInt(key));
          if (agv) agv.update(pos);
        }
      }

      // 直接更新 Box 坐标（AGV 上和 shelf 上分开处理）
      if (data.boxes_on_agv) {
        for (const [boxId, pos] of Object.entries(data.boxes_on_agv)) {
          const box = world.boxes.get(parseInt(boxId));
          if (box) box.update(pos, 0.55); // y = 0.5 高度
        }
      }

      if (data.boxes_on_shelf) {
        for (const [boxId, pos] of Object.entries(data.boxes_on_shelf)) {
          const box = world.boxes.get(parseInt(boxId));
          if (box) box.update(pos, 0.7); // y = 0.5 高度
        }
      }
    }
  };
}

export { connectWebSocket, ws };