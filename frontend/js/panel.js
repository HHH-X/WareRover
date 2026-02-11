import { ws } from './websocket.js';

function initPanel() {
  const panel = document.getElementById('panel');
  panel.innerHTML = `
    <h2>Control Panel</h2>

    <!-- === 基础控制按钮 === -->
    <div class="basic-controls">
      <button id="toggleBtn">Resume</button>
      <button id="stepBtn">Step</button>
    </div>

    <!-- === 折叠模块：显示设置 === -->
    <div class="collapsible" id="displaySettings">
      <div class="collapsible-header">▶ Display Settings</div>
      <div class="collapsible-content">
        <label><input type="checkbox" id="showAgvId"> Show AGV IDs</label><br>
        <label><input type="checkbox" id="showBoxId"> Show Box IDs</label><br>
        <label><input type="checkbox" id="showRecvId"> Show Receive Zone IDs</label>
      </div>
    </div>

    <!-- === 折叠模块：事故模拟 === -->
    <div class="collapsible" id="incidentSim">
      <div class="collapsible-header">▶ Failure Simulation</div>
      <div class="collapsible-content">
        <div class="form-group">
          <input type="number" id="damageAgvId" placeholder="AGV ID to damage">
          <button id="damageBtn">Damage</button>
        </div>
        <div class="form-group">
          <input type="number" id="repairAgvId" placeholder="AGV ID to repair">
          <button id="repairBtn">Repair</button>
        </div>
      </div>
    </div>

    <!-- === 折叠模块：性能指标 === -->
    <div class="collapsible" id="metrics">
      <div class="collapsible-header">▶ Metrics</div>
      <div class="collapsible-content" id="metricsContent">
        <p>AGVs: 0</p>
        <p>Tasks: 0</p>
        <p>FPS: 0</p>
      </div>
    </div>

  <!-- === 停止与重置按钮 === -->
    <div class="stop-section">
      <button id="stopBtn" class="stop-btn">Stop</button>
      <button id="resetBtn" class="reset-btn">Reset</button>
    </div>
  `;

  setupCollapsibles();
  makePanelDraggable(panel);

  // === 运行控制按钮 ===
  let isPaused = true;
  const toggleBtn = document.getElementById('toggleBtn');
  const stepBtn = document.getElementById('stepBtn');
  toggleBtn.classList.add("paused");
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

  // === 事故模拟 ===
  const damageBtn = document.getElementById('damageBtn');
  const repairBtn = document.getElementById('repairBtn');

  damageBtn.onclick = () => {
    const id = parseInt(document.getElementById('damageAgvId').value);
    if (!isNaN(id) && ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ cmd: "damage", agv_id: id }));
    }
  };

  repairBtn.onclick = () => {
    const id = parseInt(document.getElementById('repairAgvId').value);
    if (!isNaN(id) && ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ cmd: "repair", agv_id: id }));
    }
  };

  // === 停止模拟 ===
  const stopBtn = document.getElementById('stopBtn');
  stopBtn.onclick = () => {
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ cmd: "stop" }));
    }
  };

  // === 重置仿真按钮 ===
  const resetBtn = document.getElementById('resetBtn');
  resetBtn.onclick = () => {
    if (ws && ws.readyState === WebSocket.OPEN) {
      console.log("发送 reset 命令");
      ws.send(JSON.stringify({ cmd: "reset" }));
      // 可选：给用户一点反馈（按钮变灰 1 秒）
      resetBtn.disabled = true;
      resetBtn.textContent = "Resetting...";
      setTimeout(() => {
        resetBtn.disabled = false;
        resetBtn.textContent = "Reset";
      }, 1500);
    }
  };

  // === 显示设置勾选框逻辑 ===
  const showAgvId = document.getElementById('showAgvId');
  const showBoxId = document.getElementById('showBoxId');
  const showRecvId = document.getElementById('showRecvId');

  showAgvId.addEventListener('change', (e) => {
    window.sceneWorld?.agvs.forEach(agv => agv.setLabelVisible(e.target.checked));
  });

  showBoxId.addEventListener('change', (e) => {
    window.sceneWorld?.boxes.forEach(box => box.setLabelVisible(e.target.checked));
  });

  showRecvId.addEventListener('change', (e) => {
    window.sceneWorld?.receiveAreas.forEach(r => r.setLabelVisible(e.target.checked));
  });
}

function updateMetrics(metrics) {
  const metricsContent = document.getElementById('metricsContent');
  if (!metricsContent) return;

  // 动态生成指标显示
  let html = '';
  for (const [key, value] of Object.entries(metrics)) {
    const formattedKey = key
      .replace(/_/g, ' ')            // 下划线转空格
      .replace(/\b\w/g, c => c.toUpperCase()); // 每个单词首字母大写
    html += `<p>${formattedKey}: ${value.toFixed(2)}</p>`;
  }

  metricsContent.innerHTML = html;
}

// === 折叠逻辑 ===
function setupCollapsibles() {
  const headers = document.querySelectorAll('.collapsible-header');
  headers.forEach(header => {
    header.addEventListener('click', () => {
      const content = header.nextElementSibling;
      const expanded = header.classList.toggle('expanded');
      header.textContent = expanded
        ? '▼ ' + header.textContent.slice(2)
        : '▶ ' + header.textContent.slice(2);
      content.style.display = expanded ? 'block' : 'none';
    });
  });
}

// === 拖动逻辑 ===
function makePanelDraggable(panel) {
  let isDragging = false;
  let offsetX, offsetY;

  panel.addEventListener("mousedown", (e) => {
    if (e.target.classList.contains('collapsible-header')) return;
    isDragging = true;
    offsetX = e.clientX - panel.offsetLeft;
    offsetY = e.clientY - panel.offsetTop;
    panel.style.cursor = "grabbing";
  });

  document.addEventListener("mousemove", (e) => {
    if (!isDragging) return;
    panel.style.left = `${e.clientX - offsetX}px`;
    panel.style.top = `${e.clientY - offsetY}px`;
    panel.style.right = "auto";
  });

  document.addEventListener("mouseup", () => {
    isDragging = false;
    panel.style.cursor = "grab";
  });
}

export { initPanel, updateMetrics };
