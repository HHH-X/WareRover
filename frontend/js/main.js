import { createScene, renderLoop } from './scene.js';
import { initPanel } from './panel.js';
import { connectWebSocket } from './websocket.js';

// 创建场景
const { scene, camera, renderer, world, controls, labelRenderer } = createScene();

// 初始化控制面板
initPanel();

// 启动 WebSocket，并传 world 用于更新 AGV、Box 等实体
connectWebSocket(world);

// 启动渲染循环
renderLoop(renderer, labelRenderer, scene, camera, controls);
