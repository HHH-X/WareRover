import { ws } from './websocket.js';

function initPanel() {
  const panel = document.getElementById('panel');
  panel.innerHTML = `
    <h2>Control Panel</h2>
    <div>
      <button id="toggleBtn">Pause</button>
      <button id="stepBtn">Step</button>
    </div>
    <div id="metrics">
      <h3>Metrics</h3>
      <div id="metricsContent">
        <p>AGVs: 0</p>
        <p>Tasks: 0</p>
        <p>FPS: 0</p>
      </div>
    </div>
  `;

  let isPaused = false;
  const toggleBtn = document.getElementById('toggleBtn');
  const stepBtn = document.getElementById('stepBtn');

  toggleBtn.onclick = () => {
    if (!ws || ws.readyState !== WebSocket.OPEN) return;

    if (isPaused) {
      ws.send(JSON.stringify({ cmd: "resume" }));
      toggleBtn.textContent = "Pause";
      toggleBtn.classList.remove("paused");
    } else {
      ws.send(JSON.stringify({ cmd: "pause" }));
      toggleBtn.textContent = "Resume";
      toggleBtn.classList.add("paused");
    }
    isPaused = !isPaused;
  };

  stepBtn.onclick = () => {
    if (!ws || ws.readyState !== WebSocket.OPEN) return;

    if (!isPaused) {
      ws.send(JSON.stringify({ cmd: "pause" }));
      toggleBtn.textContent = "Resume";
      toggleBtn.classList.add("paused");
      isPaused = true;
    }
    ws.send(JSON.stringify({ cmd: "step" }));
  };
  makePanelDraggable(panel);
}

// 提供外部接口，便于后端数据传入
function updateMetrics(data) {
  const metricsContent = document.getElementById('metricsContent');
  if (!metricsContent) return;

  metricsContent.innerHTML = `
    <p>AGVs: ${data.agvs ?? 0}</p>
    <p>Tasks: ${data.tasks ?? 0}</p>
    <p>FPS: ${data.fps ?? 0}</p>
  `;
}

function makePanelDraggable(panel) {
  let isDragging = false;
  let offsetX, offsetY;

  panel.addEventListener("mousedown", (e) => {
    isDragging = true;
    offsetX = e.clientX - panel.offsetLeft;
    offsetY = e.clientY - panel.offsetTop;
    panel.style.cursor = "grabbing";
  });

  document.addEventListener("mousemove", (e) => {
    if (!isDragging) return;
    panel.style.left = `${e.clientX - offsetX}px`;
    panel.style.top = `${e.clientY - offsetY}px`;
    panel.style.right = "auto"; // 取消固定 right
  });

  document.addEventListener("mouseup", () => {
    isDragging = false;
    panel.style.cursor = "grab";
  });
}


export { initPanel, updateMetrics };
