(function () {
  const params = new URLSearchParams(window.location.search);
  const wsUrl = params.get("ws") || `ws://${window.location.hostname || "localhost"}:8766`;

  const elements = {
    artifacts: document.getElementById("artifacts"),
    connectionStatus: document.getElementById("connection-status"),
    currentTask: document.getElementById("current-task"),
    evolveVisualizerButton: document.getElementById("evolve-visualizer-button"),
    form: document.getElementById("chat-form"),
    input: document.getElementById("message-input"),
    messages: document.getElementById("messages"),
    metrics: document.getElementById("metrics"),
    progressText: document.getElementById("progress-text"),
    resetButton: document.getElementById("reset-button"),
    sendButton: document.getElementById("send-button"),
    simulatorButton: document.getElementById("simulator-button"),
    stopButton: document.getElementById("stop-button"),
  };

  let socket = null;
  let waitingForInput = false;
  let running = false;
  let pendingEvolveVisualizerWindow = null;
  let pendingSimulatorWindow = null;
  let shuttingDown = false;

  function connect() {
    socket = new WebSocket(wsUrl);
    setConnection("连接中");

    socket.addEventListener("open", () => setConnection("已连接"));
    socket.addEventListener("close", () => {
      setConnection(shuttingDown ? "已停止" : "已断开，3 秒后重连");
      setBusy(false);
      if (!shuttingDown) {
        setTimeout(connect, 3000);
      }
    });
    socket.addEventListener("error", () => setConnection("连接异常"));
    socket.addEventListener("message", (event) => {
      const message = JSON.parse(event.data);
      handleServerMessage(message);
    });
  }

  function handleServerMessage(message) {
    if (message.type === "ready") {
      renderState(message.state);
      return;
    }
    if (message.type === "running") {
      setBusy(true, message.label || "Agent 正在处理，请稍候...");
      return;
    }
    if (message.type === "log") {
      appendMessage("log", message.message || "");
      return;
    }
    if (message.type === "simulator") {
      openSimulatorWindow(message.url);
      appendMessage("agent", message.message || "仿真可视化页面已打开。");
      return;
    }
    if (message.type === "evolve_visualizer") {
      openEvolveVisualizerWindow(message.url);
      appendMessage("agent", message.message || "优化进度可视化页面已打开。");
      return;
    }
    if (message.type === "error") {
      setBusy(false);
      closePendingSimulatorWindow();
      closePendingEvolveVisualizerWindow();
      appendMessage("error", message.error || "请求失败");
      return;
    }
    if (message.type === "shutdown") {
      shuttingDown = true;
      setBusy(false);
      appendMessage("system", message.message || "Agent 服务正在关闭。");
      setConnection("正在停止");
      return;
    }

    if (message.state) {
      setBusy(false);
      renderState(message.state);
    }
  }

  function renderState(state) {
    waitingForInput = Boolean(state.waiting_for_input);
    elements.input.placeholder = waitingForInput
      ? "请输入 Agent 需要补充的信息"
      : "例如：生成一个 20x15、4 台 AGV 的地图，并运行仿真";
    elements.sendButton.textContent = waitingForInput ? "补充信息" : "发送";

    renderProgress(state);
    renderArtifacts(state);
    renderMetrics(state.run_metrics || {});

    if (state.question) {
      appendMessage("agent", `需要补充信息：${state.question}`);
      return;
    }
    if (state.response) {
      appendMessage("agent", state.response);
    }
    if (state.error && !state.response) {
      appendMessage("error", state.error);
    }
  }

  function renderProgress(state) {
    const intents = state.intents || [];
    const current = state.current_intent;
    elements.currentTask.textContent = current
      ? `${current.label}: ${current.detail || "无详情"}`
      : waitingForInput
        ? "等待补充信息"
        : "尚未开始";
    elements.progressText.textContent = `${Math.min(state.intent_index || 0, intents.length)} / ${intents.length}`;
  }

  function renderArtifacts(state) {
    const items = [];
    if (state.map_file_path) {
      items.push(["地图文件", state.map_file_path]);
    }
    Object.entries(state.generated_code || {}).forEach(([kind, path]) => {
      items.push([`生成算法 (${kind})`, path]);
    });
    if (state.optimize_result && state.optimize_result.run_dir) {
      items.push(["优化结果", state.optimize_result.run_dir]);
    }

    if (!items.length) {
      elements.artifacts.className = "empty";
      elements.artifacts.textContent = "暂无产物";
      return;
    }

    elements.artifacts.className = "artifact-list";
    elements.artifacts.innerHTML = items
      .map(([label, value]) => `<div><strong>${escapeHtml(label)}</strong><code>${escapeHtml(String(value))}</code></div>`)
      .join("");
  }

  function renderMetrics(metrics) {
    const cards = [
      ["步数", metrics.sim_steps],
      ["是否完成", formatBoolean(metrics.finished)],
      ["完成率", metrics.task_success_rate],
      ["完成任务数", metrics.tasks_completed],
    ].filter(([, value]) => value !== undefined && value !== null && value !== "");

    if (!cards.length) {
      elements.metrics.className = "empty";
      elements.metrics.textContent = "暂无指标";
      return;
    }

    elements.metrics.className = "metric-grid";
    elements.metrics.innerHTML = cards
      .map(([label, value]) => `<div><span>${escapeHtml(label)}</span><strong>${escapeHtml(String(value))}</strong></div>`)
      .join("");
  }

  function appendMessage(role, text) {
    const item = document.createElement("article");
    item.className = `message ${role}`;
    item.textContent = text;
    elements.messages.appendChild(item);
    elements.messages.scrollTop = elements.messages.scrollHeight;
  }

  function sendPayload(payload) {
    if (!socket || socket.readyState !== WebSocket.OPEN) {
      appendMessage("error", "WebSocket 尚未连接。");
      return;
    }
    socket.send(JSON.stringify(payload));
  }

  elements.form.addEventListener("submit", (event) => {
    event.preventDefault();
    const text = elements.input.value.trim();
    if (!text || running) {
      return;
    }
    appendMessage("user", text);
    sendPayload(waitingForInput ? { type: "resume", answer: text } : { type: "start", message: text });
    elements.input.value = "";
  });

  elements.resetButton.addEventListener("click", () => {
    if (running) {
      return;
    }
    elements.messages.innerHTML = "";
    sendPayload({ type: "reset" });
  });

  elements.simulatorButton.addEventListener("click", () => {
    pendingSimulatorWindow = window.open("about:blank", "warerover-simulator");
    sendPayload({ type: "launch_simulator" });
  });

  elements.evolveVisualizerButton.addEventListener("click", () => {
    pendingEvolveVisualizerWindow = window.open("about:blank", "mapf-agent-evolve-visualizer");
    sendPayload({ type: "launch_evolve_visualizer" });
  });

  elements.stopButton.addEventListener("click", () => {
    if (shuttingDown) {
      return;
    }
    shuttingDown = true;
    elements.stopButton.disabled = true;
    appendMessage("system", "正在停止 Agent 服务...");
    sendPayload({ type: "shutdown" });
  });

  function setConnection(text) {
    elements.connectionStatus.textContent = text;
  }

  function setBusy(value, label) {
    running = value;
    elements.sendButton.disabled = value;
    elements.resetButton.disabled = value;
    elements.input.disabled = value;
    if (value) {
      appendMessage("system", label || "正在处理，请稍候...");
    }
  }

  function openSimulatorWindow(url) {
    if (!url) {
      return;
    }
    if (pendingSimulatorWindow && !pendingSimulatorWindow.closed) {
      pendingSimulatorWindow.location.href = url;
      pendingSimulatorWindow.focus();
      pendingSimulatorWindow = null;
      return;
    }
    window.open(url, "warerover-simulator");
  }

  function openEvolveVisualizerWindow(url) {
    if (!url) {
      return;
    }
    if (pendingEvolveVisualizerWindow && !pendingEvolveVisualizerWindow.closed) {
      pendingEvolveVisualizerWindow.location.href = url;
      pendingEvolveVisualizerWindow.focus();
      pendingEvolveVisualizerWindow = null;
      return;
    }
    window.open(url, "mapf-agent-evolve-visualizer");
  }

  function closePendingSimulatorWindow() {
    if (pendingSimulatorWindow && !pendingSimulatorWindow.closed) {
      pendingSimulatorWindow.close();
    }
    pendingSimulatorWindow = null;
  }

  function closePendingEvolveVisualizerWindow() {
    if (pendingEvolveVisualizerWindow && !pendingEvolveVisualizerWindow.closed) {
      pendingEvolveVisualizerWindow.close();
    }
    pendingEvolveVisualizerWindow = null;
  }

  function formatBoolean(value) {
    if (value === true) {
      return "是";
    }
    if (value === false) {
      return "否";
    }
    return value;
  }

  function escapeHtml(value) {
    return value.replace(/[&<>"']/g, (char) => ({
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      "\"": "&quot;",
      "'": "&#39;",
    }[char]));
  }

  connect();
}());
