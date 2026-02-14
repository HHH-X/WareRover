import { createScene, renderLoop } from './scene.js';
import { initPanel } from './panel.js';
import { initOrderPanel } from './orderPanel.js';
import { connectWebSocket } from './websocket.js';

// 创建场景
const { scene, camera, renderer, world, controls, labelRenderer } = createScene();

// 初始化控制面板（左侧）
initPanel();

// 初始化订单面板（右上角）
initOrderPanel();

// 启动 WebSocket，并传 world 用于更新 AGV、Box 等实体
connectWebSocket(world);

// 启动渲染循环
renderLoop(renderer, labelRenderer, scene, camera, controls);
