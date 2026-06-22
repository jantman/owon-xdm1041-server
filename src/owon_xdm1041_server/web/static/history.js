// History page: fetch recorded readings, draw a simple canvas line chart, and
// offer a CSV download. No external charting library, so it works offline.
(function () {
  const canvas = document.getElementById("chart");
  const ctx = canvas.getContext("2d");
  const empty = document.getElementById("empty");
  const csv = document.getElementById("csv");

  function draw(data) {
    const w = canvas.width;
    const h = canvas.height;
    const pad = 40;
    ctx.clearRect(0, 0, w, h);

    const xs = data.map((d) => d.timestamp);
    const ys = data.map((d) => d.value);
    const minX = Math.min(...xs);
    const maxX = Math.max(...xs);
    const minY = Math.min(...ys);
    const maxY = Math.max(...ys);
    const sx = (t) => pad + (maxX === minX ? 0 : (t - minX) / (maxX - minX)) * (w - 2 * pad);
    const sy = (v) => h - pad - (maxY === minY ? 0.5 * (h - 2 * pad) : ((v - minY) / (maxY - minY)) * (h - 2 * pad));

    ctx.strokeStyle = "#3d444d";
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(pad, pad);
    ctx.lineTo(pad, h - pad);
    ctx.lineTo(w - pad, h - pad);
    ctx.stroke();

    ctx.strokeStyle = "#4f9cf9";
    ctx.lineWidth = 2;
    ctx.beginPath();
    data.forEach((d, i) => {
      const x = sx(d.timestamp);
      const y = sy(d.value);
      if (i === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    });
    ctx.stroke();
  }

  function toCsv(data) {
    const header = "timestamp,function,value,unit";
    const rows = data.map((d) => [d.timestamp, d.function, d.value, d.unit].join(","));
    return header + "\n" + rows.join("\n") + "\n";
  }

  async function load() {
    const res = await fetch("/api/history?limit=1000");
    const data = await res.json();
    if (!data.length) {
      empty.style.display = "block";
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      csv.removeAttribute("href");
      return;
    }
    empty.style.display = "none";
    draw(data);
    csv.href = URL.createObjectURL(new Blob([toCsv(data)], { type: "text/csv" }));
  }

  document.getElementById("refresh").addEventListener("click", load);
  load();
})();
