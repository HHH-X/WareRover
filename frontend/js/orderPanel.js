/**
 * Order Panel - Top-right panel for order information display.
 * Contains: collapsible header, order counts, order logs, AGV progress.
 */

function initOrderPanel() {
  const panel = document.getElementById('order-panel');
  panel.innerHTML = `
    <div class="order-panel-wrapper">
      <div class="order-panel-header" id="orderPanelHeader">
        <span class="order-panel-title">▶ Order Panel</span>
      </div>
      <div class="order-panel-content" id="orderPanelContent">
        <div class="order-counts">
          <div class="order-count-item">
            <span class="order-count-label">Unprocessed</span>
            <span class="order-count-value" id="orderCountUnprocessed">0</span>
          </div>
          <div class="order-count-item">
            <span class="order-count-label">Processing</span>
            <span class="order-count-value" id="orderCountProcessing">0</span>
          </div>
          <div class="order-count-item">
            <span class="order-count-label">Completed</span>
            <span class="order-count-value" id="orderCountCompleted">0</span>
          </div>
        </div>

        <div class="order-logs-section">
          <div class="order-log-block">
            <div class="order-log-title">Order Generated</div>
            <div class="order-log-list" id="orderLogGeneration"></div>
          </div>
          <div class="order-log-block">
            <div class="order-log-title">Order Assigned</div>
            <div class="order-log-list" id="orderLogAssignment"></div>
          </div>
          <div class="order-log-block">
            <div class="order-log-title">Order Completed</div>
            <div class="order-log-list" id="orderLogCompletion"></div>
          </div>
        </div>

        <div class="agv-progress-section">
          <div class="agv-progress-title">AGV Progress</div>
          <div class="agv-progress-list" id="agvProgressList"></div>
        </div>
      </div>
    </div>
  `;

  // Collapse toggle logic - collapse entire panel (content + background)
  const header = document.getElementById('orderPanelHeader');
  const content = document.getElementById('orderPanelContent');
  let isExpanded = true;

  header.addEventListener('click', () => {
    isExpanded = !isExpanded;
    content.style.display = isExpanded ? 'flex' : 'none';
    panel.classList.toggle('order-panel-collapsed', !isExpanded);
    header.querySelector('.order-panel-title').textContent =
      isExpanded ? '▼ Order Panel' : '▶ Order Panel';
  });

  header.querySelector('.order-panel-title').textContent = '▼ Order Panel';
}

function formatGenerationLog(entry) {
  const goodsStr = entry.goods_id != null ? ` goods ${entry.goods_id}` : '';
  return `Order ${entry.order_id}${goodsStr} → receiver ${entry.receiver_id}`;
}

function formatAssignmentLog(entry) {
  const boxStr = entry.box_id != null ? `(box ${entry.box_id})` : '';
  return `Order ${entry.order_id} → AGV ${entry.agv_id} ${boxStr}`;
}

function formatCompletionLog(entry) {
  return `AGV ${entry.agv_id} completed Order ${entry.order_id}`;
}

function updateOrderPanel(ordersData) {
  if (!ordersData) return;

  const counts = ordersData.counts || {};
  document.getElementById('orderCountUnprocessed').textContent =
    String(counts.unprocessed ?? 0);
  document.getElementById('orderCountProcessing').textContent =
    String(counts.processing ?? 0);
  document.getElementById('orderCountCompleted').textContent =
    String(counts.completed ?? 0);

  const logs = ordersData.logs || {};
  const genEl = document.getElementById('orderLogGeneration');
  const assignEl = document.getElementById('orderLogAssignment');
  const completeEl = document.getElementById('orderLogCompletion');

  const maxLogItems = 20;
  const scrollToBottom = (el) => {
    if (el) el.scrollTop = el.scrollHeight;
  };
  if (genEl) {
    const items = (logs.generation || []).slice(-maxLogItems);
    genEl.innerHTML = items
      .map((e) => `<div class="order-log-line">${formatGenerationLog(e)}</div>`)
      .join('') || '<div class="order-log-empty">None</div>';
    scrollToBottom(genEl);
  }
  if (assignEl) {
    const items = (logs.assignment || []).slice(-maxLogItems);
    assignEl.innerHTML = items
      .map((e) => `<div class="order-log-line">${formatAssignmentLog(e)}</div>`)
      .join('') || '<div class="order-log-empty">None</div>';
    scrollToBottom(assignEl);
  }
  if (completeEl) {
    const items = (logs.completion || []).slice(-maxLogItems);
    completeEl.innerHTML = items
      .map((e) => `<div class="order-log-line">${formatCompletionLog(e)}</div>`)
      .join('') || '<div class="order-log-empty">None</div>';
    scrollToBottom(completeEl);
  }

  const agvProgress = ordersData.agv_progress || [];
  const progressEl = document.getElementById('agvProgressList');
  if (progressEl) {
    progressEl.innerHTML = agvProgress
      .map((p) => {
        const progress = Math.round((p.progress || 0) * 100);
        let statusStr = '-';
        if (p.task_type === 'pick') {
          statusStr = p.order_id != null ? `Picking Order ${p.order_id}` : 'Picking';
        } else if (p.task_type === 'handover') {
          statusStr = p.order_id != null ? `Delivering Order ${p.order_id}` : 'Delivering';
        } else if (p.task_type === 'place') {
          statusStr = 'Returning';
        }
        return `
          <div class="agv-progress-row">
            <span class="agv-progress-id">AGV ${p.agv_id}</span>
            <div class="agv-progress-bar-wrap">
              <div class="agv-progress-bar">
                <div class="agv-progress-fill" style="width: ${progress}%"></div>
                <div class="agv-progress-dot" style="left: ${progress}%"></div>
              </div>
            </div>
            <span class="agv-progress-order">${statusStr}</span>
          </div>
        `;
      })
      .join('');
  }
}

export { initOrderPanel, updateOrderPanel };
