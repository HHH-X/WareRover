function initPanel() {
  const panel = document.getElementById('panel');
  panel.innerHTML = `
    <h2>Control Panel</h2>
    <button id="pauseBtn">Pause</button>
    <button id="stepBtn">Step</button>
    <div id="logs"><h3>Logs</h3></div>
    <div id="metrics"><h3>Metrics</h3></div>
  `;

  document.getElementById('pauseBtn').onclick = () => {
    console.log("Pause clicked");
  };

  document.getElementById('stepBtn').onclick = () => {
    console.log("Step clicked");
  };
}

export { initPanel };
