import { createScene, renderLoop } from './scene.js';
import { initPanel } from './panel.js';
import { connectWebSocket } from './websocket.js';

console.log("开始调试");
const { scene, camera, renderer, world, controls } = createScene();
initPanel();   // 初始化控制面板
connectWebSocket(world);  // 启动 WebSocket，传 world 以便更新实体

renderLoop(renderer, scene, camera, controls);