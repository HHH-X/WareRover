import { AGV } from './entities/agv.js';
import { Shelf } from './entities/shelf.js';
import { Box } from './entities/box.js';
import { Obstacle } from './entities/obstacle.js';
import { RestArea } from './entities/restArea.js';
import { ReceiveArea } from './entities/receiveArea.js';
import { Elevator } from './entities/elevator.js';
import { FLOOR_HEIGHT } from './scene.js';
import { updateMetrics } from './panel.js';
import { updateOrderPanel } from './orderPanel.js';

let ws = null;

function connectWebSocket(world) {
  ws = new WebSocket("ws://localhost:8765");

  ws.onmessage = (event) => {
    const data = JSON.parse(event.data);
    console.log("get data: ", data);

    if (data.type === "init") {
      const numFloors = data.num_floors || 1;
      world.addMap(data.map_size, numFloors);

      // Per-floor entities
      if (data.floors) {
        for (const [fid, floorData] of Object.entries(data.floors)) {
          const floorId = parseInt(fid);

          if (floorData.boxes) {
            for (const boxId in floorData.boxes) {
              const box = floorData.boxes[boxId];
              world.addBox(new Box(parseInt(boxId), box.pos, box.size), floorId);
              world.addShelf(new Shelf(parseInt(boxId), box.pos, box.size), floorId);
            }
          }

          if (floorData.receivers) {
            for (const rid in floorData.receivers) {
              const recv = floorData.receivers[rid];
              world.addReceiveArea(new ReceiveArea(rid, recv.pos, recv.size), floorId);
            }
          }

          if (floorData.wait_zones) {
            for (const key in floorData.wait_zones) {
              const wz = floorData.wait_zones[key];
              world.addRestArea(new RestArea(wz.pos, wz.size), floorId);
            }
          }

          if (floorData.obstacles) {
            floorData.obstacles.forEach(pos => {
              world.addObstacle(new Obstacle(pos), floorId);
            });
          }
        }
      }

      // AGVs
      if (data.agvs) {
        for (const agvId in data.agvs) {
          const agvData = data.agvs[agvId];
          const floorId = agvData.floor || 0;
          world.addAGV(new AGV(parseInt(agvId), agvData.pos, agvData.size), floorId);
        }
      }

      // Elevators
      if (data.elevators) {
        for (const eid in data.elevators) {
          const eData = data.elevators[eid];
          world.addElevator(new Elevator(
            parseInt(eid), eData.pos, eData.floors || [0], FLOOR_HEIGHT
          ));
        }
      }

      // Build floor toggle controls
      if (window.buildFloorToggles) {
        window.buildFloorToggles(numFloors);
      }
    }

    if (data.type === "update") {
      // Update AGV positions and floor transitions
      if (data.agvs) {
        for (const key in data.agvs) {
          const agvData = data.agvs[key];
          const pos = agvData.pos || agvData;
          const agv = world.agvs.get(parseInt(key));
          if (!agv) continue;

          if (agvData.in_elevator) {
            agv.setVisible(false);
          } else {
            agv.setVisible(true);
            if (agvData.floor != null && agvData.floor !== agv.floorId) {
              agv.moveToFloor(agvData.floor, world);
            }
            agv.update(pos);
          }
        }
      }

      // Box updates
      if (data.boxes_on_agv) {
        for (const [boxId, boxData] of Object.entries(data.boxes_on_agv)) {
          const pos = boxData.pos || boxData;
          const box = world.boxes.get(parseInt(boxId));
          if (box) box.update(pos, 0.55);
        }
      }

      if (data.boxes_on_shelf) {
        for (const [boxId, boxData] of Object.entries(data.boxes_on_shelf)) {
          const pos = boxData.pos || boxData;
          const box = world.boxes.get(parseInt(boxId));
          if (box) box.update(pos, 0.7);
        }
      }

      // Safe paths
      if (data.safe_paths) {
        // Flatten to simple format for safePathRenderer
        const flatPaths = {};
        for (const [key, pathData] of Object.entries(data.safe_paths)) {
          flatPaths[key] = pathData.path || pathData;
        }
        world.safePathRenderer.updatePaths(flatPaths);
      }

      // Elevator status
      if (data.elevators) {
        for (const [eid, eStatus] of Object.entries(data.elevators)) {
          const elev = world.elevators.get(parseInt(eid));
          if (elev) {
            elev.updateState(eStatus);
          }
        }
      }

      if (data.metrics) {
        updateMetrics(data.metrics);
      }

      if (data.orders) {
        updateOrderPanel(data.orders);
      }
    }

    if (data.type === "init" && data.orders) {
      updateOrderPanel(data.orders);
    }
  };
}

export { connectWebSocket, ws };
