let debugEnabled = false;

function initDebugFlag() {
  const params = new URLSearchParams(window.location.search);
  debugEnabled = params.get("debug") === "1";
  return { enabled: debugEnabled, source: debugEnabled ? "url" : "default" };
}

function isDebugEnabled() {
  return debugEnabled;
}

function debugLog(...args) {
  if (!isDebugEnabled()) return;
  console.log(...args);
}

function debugWarn(...args) {
  if (!isDebugEnabled()) return;
  console.warn(...args);
}

export { initDebugFlag, isDebugEnabled, debugLog, debugWarn };
