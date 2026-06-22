// Live dashboard: stream readings over the WebSocket and update the readout.
// Auto-reconnects with a short backoff so the page recovers from drops.
(function () {
  const valueEl = document.getElementById("value");
  const unitEl = document.getElementById("unit");
  const funcEl = document.getElementById("function");
  const statusEl = document.getElementById("status");

  function formatValue(v) {
    const a = Math.abs(v);
    if (a !== 0 && (a < 1e-3 || a >= 1e6)) return v.toExponential(4);
    return v.toPrecision(6);
  }

  function setStatus(text, connected) {
    statusEl.textContent = text;
    statusEl.className = "status " + (connected ? "connected" : "disconnected");
  }

  function connect() {
    const proto = location.protocol === "https:" ? "wss" : "ws";
    const ws = new WebSocket(proto + "://" + location.host + "/ws/live");
    ws.onopen = () => setStatus("live", true);
    ws.onclose = () => {
      setStatus("disconnected", false);
      setTimeout(connect, 1000);
    };
    ws.onmessage = (event) => {
      const d = JSON.parse(event.data);
      valueEl.textContent = formatValue(d.value);
      unitEl.textContent = d.unit;
      funcEl.textContent = d.function;
    };
  }

  connect();
})();
