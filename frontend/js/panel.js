import { ws } from './websocket.js';

function initPanel() {
  const panel = document.getElementById('panel');
  panel.innerHTML = `
    <h2>Control Panel</h2>
    <button id="toggleBtn">Pause</button>
    <button id="stepBtn">Step</button>
    <div id="logs"><h3>Logs</h3></div>
    <div id="metrics"><h3>Metrics</h3></div>
  `;

  let isPaused = false; // 初始状态：运行中

  const toggleBtn = document.getElementById('toggleBtn');
  toggleBtn.onclick = () => {
    if (!ws || ws.readyState !== WebSocket.OPEN) return;

    if (isPaused) {
      // 当前是暂停 → 发送恢复
      ws.send(JSON.stringify({ cmd: "resume" }));
      toggleBtn.textContent = "Pause";
      console.log("Resume clicked");
    } else {
      // 当前是运行 → 发送暂停
      ws.send(JSON.stringify({ cmd: "pause" }));
      toggleBtn.textContent = "Resume";
      console.log("Pause clicked");
    }

    isPaused = !isPaused;
  };

  document.getElementById('stepBtn').onclick = () => {
    if (!ws || ws.readyState !== WebSocket.OPEN) return;

    if (!isPaused) {
      // 如果正在运行，先切换为暂停
      ws.send(JSON.stringify({ cmd: "pause" }));
      toggleBtn.textContent = "Resume";
      isPaused = true;
      console.log("Auto-paused before step");
    }

    // 然后执行一步
    ws.send(JSON.stringify({ cmd: "step" }));
    console.log("Step clicked");
  };
}

export { initPanel };
