// Live dashboard: stream readings over the WebSocket and update the readout.
// Auto-reconnects with a short backoff so the page recovers from drops.
//
// "Live" only means the socket is up — not that data is flowing. A watchdog
// flips the badge to "live — no data" when no reading arrives for a few seconds
// (e.g. the meter is off or stuck), so a stalled feed is visible at a glance
// rather than looking healthy with a frozen value.
(function () {
  const valueEl = document.getElementById("value");
  const unitEl = document.getElementById("unit");
  const funcEl = document.getElementById("function");
  const statusEl = document.getElementById("status");

  // No data for this long while connected => show the stale state. The poller
  // samples ~2x/second, so a few seconds is many missed readings, not a blip.
  const STALE_MS = 3000;
  let staleTimer = null;

  function formatValue(v) {
    const a = Math.abs(v);
    if (a !== 0 && (a < 1e-3 || a >= 1e6)) return v.toExponential(4);
    return v.toPrecision(6);
  }

  function setStatus(text, state) {
    statusEl.textContent = text;
    statusEl.className = "status " + state;
  }

  function clearStaleTimer() {
    if (staleTimer !== null) {
      clearTimeout(staleTimer);
      staleTimer = null;
    }
  }

  function armStaleTimer() {
    clearStaleTimer();
    staleTimer = setTimeout(() => setStatus("live — no data", "stale"), STALE_MS);
  }

  function connect() {
    const proto = location.protocol === "https:" ? "wss" : "ws";
    const ws = new WebSocket(proto + "://" + location.host + "/ws/live");
    ws.onopen = () => {
      // Connected but nothing received yet: optimistic "live", but start the
      // watchdog so we surface a silent feed if no reading shows up.
      setStatus("live", "connected");
      armStaleTimer();
    };
    ws.onclose = () => {
      clearStaleTimer();
      setStatus("disconnected", "disconnected");
      setTimeout(connect, 1000);
    };
    ws.onmessage = (event) => {
      const d = JSON.parse(event.data);
      valueEl.textContent = formatValue(d.value);
      unitEl.textContent = d.unit;
      funcEl.textContent = d.function;
      // A reading arrived: feed is healthy; reset the staleness countdown.
      setStatus("live", "connected");
      armStaleTimer();
    };
  }

  connect();
})();
