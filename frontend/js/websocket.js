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
import { debugLog, debugWarn } from './debug.js';

let ws = null;

function resolveWebSocketUrl() {
  const params = new URLSearchParams(window.location.search);
  return params.get("ws") || "ws://localhost:8765";
}

function applyBoxUpdate(world, boxId, boxData, height) {
  const box = world.boxes.get(parseInt(boxId));
  if (!box) return false;

  if (boxData.in_elevator) {
    box.setVisible(false);
    return true;
  }

  box.setVisible(true);
  if (boxData.floor != null) {
    const floorId = Number(boxData.floor);
    if (Number.isFinite(floorId) && floorId !== box.floorId) {
      box.moveToFloor(floorId, world);
    }
  }

  const pos = boxData.pos || boxData;
  box.update(pos, height);
  return true;
}

function connectWebSocket(world) {
  ws = new WebSocket(resolveWebSocketUrl());

  ws.onopen = () => {
    debugLog("[ws] open", { url: ws.url });
  };

  ws.onclose = (event) => {
    debugWarn("[ws] close", {
      code: event.code,
      reason: event.reason,
      wasClean: event.wasClean
    });
  };

  ws.onerror = (event) => {
    debugWarn("[ws] error", event);
  };

  ws.onmessage = (event) => {
    let data;
    try {
      data = JSON.parse(event.data);
    } catch (error) {
      debugWarn("[ws] invalid json", event.data, error);
      return;
    }
    debugLog("[ws] message", data.type || "unknown", data);

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
            parseInt(eid), eData.pos, eData.floors || [0], FLOOR_HEIGHT, eData.size || 1
          ));
        }
      }

      // Build floor toggle controls
      if (window.buildFloorToggles) {
        window.buildFloorToggles(numFloors);
      }

      debugLog("[ws] init complete", {
        floors: numFloors,
        agvs: data.agvs ? Object.keys(data.agvs).length : 0,
        elevators: data.elevators ? Object.keys(data.elevators).length : 0
      });
    }

    if (data.type === "update") {
      // Update AGV positions and floor transitions
      if (data.agvs) {
        let updated = 0;
        let missing = 0;
        for (const key in data.agvs) {
          const agvData = data.agvs[key];
          const pos = agvData.pos || agvData;
          const agv = world.agvs.get(parseInt(key));
          if (!agv) {
            missing += 1;
            continue;
          }

          if (agvData.in_elevator) {
            agv.setVisible(false);
          } else {
            agv.setVisible(true);
            if (agvData.floor != null && agvData.floor !== agv.floorId) {
              agv.moveToFloor(agvData.floor, world);
            }
            agv.update(pos);
            updated += 1;
          }
        }
        debugLog("[ws] update agvs", { received: Object.keys(data.agvs).length, updated, missing });
      }

      // Box updates
      if (data.boxes_on_agv) {
        let updated = 0;
        let missing = 0;
        for (const [boxId, boxData] of Object.entries(data.boxes_on_agv)) {
          if (applyBoxUpdate(world, boxId, boxData, 0.55)) {
            updated += 1;
          } else {
            missing += 1;
          }
        }
        debugLog("[ws] update boxes_on_agv", { received: Object.keys(data.boxes_on_agv).length, updated, missing });
        debugLog("[ws] boxes_on_agv", data.boxes_on_agv);
      }

      if (data.boxes_on_shelf) {
        let updated = 0;
        let missing = 0;
        for (const [boxId, boxData] of Object.entries(data.boxes_on_shelf)) {
          if (applyBoxUpdate(world, boxId, boxData, 0.7)) {
            updated += 1;
          } else {
            missing += 1;
          }
        }
        debugLog("[ws] update boxes_on_shelf", { received: Object.keys(data.boxes_on_shelf).length, updated, missing });
      }

      // Safe paths
      if (data.safe_paths) {
        // Flatten to simple format for safePathRenderer
        const flatPaths = {};
        for (const [key, pathData] of Object.entries(data.safe_paths)) {
          flatPaths[key] = pathData.path || pathData;
        }
        world.safePathRenderer.updatePaths(flatPaths);
        debugLog("[ws] update safe_paths", { count: Object.keys(flatPaths).length });
      }

      // Elevator status
      if (data.elevators) {
        let updated = 0;
        for (const [eid, eStatus] of Object.entries(data.elevators)) {
          const elev = world.elevators.get(parseInt(eid));
          if (elev) {
            elev.updateState(eStatus);
            updated += 1;
          }
        }
        debugLog("[ws] update elevators", { received: Object.keys(data.elevators).length, updated });
      }

      if (data.metrics) {
        updateMetrics(data.metrics);
        debugLog("[ws] update metrics", data.metrics);
      }

      if (data.orders) {
        updateOrderPanel(data.orders);
        debugLog("[ws] update orders", data.orders);
      }
    }

    if (data.type === "init" && data.orders) {
      updateOrderPanel(data.orders);
    }
  };
}

export { connectWebSocket, ws };
