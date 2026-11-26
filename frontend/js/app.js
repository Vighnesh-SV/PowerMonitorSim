const el = (id) => document.getElementById(id);

let isCharging = false;
const maxPoints = 60;
const labels = [];
const levelData = [];
const currentData = [];

const ctx = el("liveChart").getContext("2d");
const liveChart = new Chart(ctx, {
  type: "line",
  data: {
    labels,
    datasets: [
      { label: "Battery (%)", data: levelData, borderColor: "#22c55e", yAxisID: "y", tension: 0.2, pointRadius: 0 },
      { label: "Current (mA)", data: currentData, borderColor: "#3b82f6", yAxisID: "y1", tension: 0.2, pointRadius: 0 },
    ],
  },
  options: {
    animation: false,
    scales: {
      y: { type: "linear", position: "left", min: 0, max: 100 },
      y1: { type: "linear", position: "right", grid: { drawOnChartArea: false } },
    },
  },
});

function updateUI(snap) {
  el("sim-clock").textContent = snap.sim_clock;
  const b = snap.battery;
  el("val-level").textContent = `${b.level_pct.toFixed(1)}%`;
  el("val-status").textContent = b.charging_state;
  el("val-current").textContent = `${b.current_ma.toFixed(0)} mA`;
  el("val-eta").textContent = b.eta_minutes != null ? `ETA: ${b.eta_minutes} min` : "ETA: --";
  el("val-voltage").textContent = `${b.voltage_mv} mV`;
  el("val-cap").textContent = `${b.remaining_mah.toFixed(0)} / ${b.capacity_mah.toFixed(0)} mAh`;
  el("val-temp").textContent = `${b.temperature_c.toFixed(1)} °C`;
  el("val-health").textContent = `Health: ${b.health_pct}%`;

  isCharging = b.charging_state === "CHARGING" || b.charging_state === "FULL";
  el("btn-charger").textContent = isCharging ? "Unplug Charger" : "Plug Charger";

  if (snap.device) {
    const d = snap.device;
    el("device-state-bar").textContent =
      `Screen: ${d.screen_on ? "ON" : "OFF"} (${Math.round(d.brightness * 100)}%) | Doze: ${d.doze_active ? "ACTIVE" : "INACTIVE"} | CPU: ${d.cpu_freq_mhz} MHz | WiFi: ${d.wifi_connected ? "ON" : "OFF"} | GPS: ${d.gps_active ? "ACTIVE" : "OFF"}`;
    el("btn-screen").textContent = d.screen_on ? "Turn Screen Off" : "Turn Screen On";
    window._screenOn = d.screen_on;
  }

  if (snap.processes) {
    renderProcessTable(snap.processes);
  }
  if (snap.attribution) {
    renderAppsTab(snap.attribution);
  }
  if (snap.scheduler && snap.device) {
    el("internals-live").innerHTML = `
      <div class="card"><div class="card-label">Context Switches</div><div class="card-value">${snap.scheduler.total_context_switches}</div></div>
      <div class="card"><div class="card-label">CPU Frequency</div><div class="card-value">${snap.device.cpu_freq_mhz} MHz</div></div>
      <div class="card"><div class="card-label">Doze State</div><div class="card-value">${snap.device.doze_active ? "ACTIVE" : "INACTIVE"}</div></div>
      <div class="card"><div class="card-label">Active Processes</div><div class="card-value">${snap.processes.filter((p) => p.state !== "STOPPED" && p.state !== "CACHED").length}</div></div>
    `;
  }

  labels.push(snap.sim_clock.split("·")[1]?.trim() || snap.tick);
  levelData.push(b.level_pct);
  currentData.push(b.current_ma);
  if (labels.length > maxPoints) {
    labels.shift(); levelData.shift(); currentData.shift();
  }
  liveChart.update();
}

async function post(url, body = {}) {
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return res.json();
}

el("btn-play").onclick = () => post("/api/sim/play");
el("btn-pause").onclick = () => post("/api/sim/pause");
el("sel-speed").onchange = (e) => post("/api/sim/speed", { speed: Number(e.target.value) });
el("btn-reset").onclick = () => {
  labels.length = 0; levelData.length = 0; currentData.length = 0;
  post("/api/sim/reset", { seed: Number(el("inp-seed").value) || 42 });
};
el("btn-charger").onclick = () => post("/api/device/charger", { charging: !isCharging });
el("btn-theme").onclick = () => {
  const html = document.documentElement;
  html.dataset.theme = html.dataset.theme === "dark" ? "light" : "dark";
};
el("btn-screen").onclick = () => post("/api/device/screen", { screen_on: !window._screenOn });

function renderProcessTable(procs) {
  const tbody = el("process-tbody");
  tbody.innerHTML = procs.map((p) => `
    <tr>
      <td>${p.pid}</td>
      <td>${p.display_name} ${p.is_rogue ? '<span class="badge badge-rogue">ROGUE</span>' : ""}</td>
      <td><span class="badge ${p.state === "FOREGROUND" ? "badge-fg" : ""}">${p.state}</span></td>
      <td>${p.standby_bucket}</td>
      <td>${(p.cpu_time_ms / 1000).toFixed(1)}</td>
      <td>${p.wakelock_held ? "HELD" : "-"} (${Math.round(p.wakelock_duration_s)}s)</td>
      <td>${p.current_power_ma.toFixed(1)} mA</td>
      <td>
        <button class="btn" onclick="appAction('/api/apps/launch','${p.package_name}')">Launch</button>
        <button class="btn" onclick="appAction('/api/apps/kill','${p.package_name}')">Kill</button>
      </td>
    </tr>
  `).join("");
}

window.appAction = (url, pkg) => post(url, { package_name: pkg });

let appsChart = null;
function renderAppsTab(items) {
  const tbody = el("apps-tbody");
  tbody.innerHTML = items.map((a) => `
    <tr>
      <td>${a.display_name}</td>
      <td>${a.total_mah.toFixed(2)}</td>
      <td>${a.pct_of_total.toFixed(1)}%</td>
      <td>${a.fg_mah.toFixed(2)}</td>
      <td>${a.bg_mah.toFixed(2)}</td>
      <td>${a.cpu_mah.toFixed(2)}</td>
      <td>${a.screen_mah.toFixed(2)}</td>
      <td>${a.network_mah.toFixed(2)}</td>
      <td>${a.gps_mah.toFixed(2)}</td>
      <td>${a.wakelock_mah.toFixed(2)}</td>
    </tr>
  `).join("");

  const labelsA = items.map((i) => i.display_name);
  const datasets = [
    { label: "CPU", data: items.map((i) => i.cpu_mah), backgroundColor: "#3b82f6" },
    { label: "Screen", data: items.map((i) => i.screen_mah), backgroundColor: "#f59e0b" },
    { label: "Network", data: items.map((i) => i.network_mah), backgroundColor: "#22c55e" },
    { label: "GPS", data: items.map((i) => i.gps_mah), backgroundColor: "#a855f7" },
    { label: "Wakelock", data: items.map((i) => i.wakelock_mah), backgroundColor: "#ef4444" },
  ];

  if (!appsChart) {
    appsChart = new Chart(el("appsChart").getContext("2d"), {
      type: "bar",
      data: { labels: labelsA, datasets },
      options: {
        animation: false,
        scales: { x: { stacked: true }, y: { stacked: true, title: { display: true, text: "mAh" } } },
      },
    });
  } else {
    appsChart.data.labels = labelsA;
    appsChart.data.datasets.forEach((ds, idx) => { ds.data = datasets[idx].data; });
    appsChart.update();
  }
}

let historyChart = null;
async function loadSessions() {
  const sessions = await (await fetch("/api/history/sessions")).json();
  el("sel-session").innerHTML = sessions.map((s) => `<option value="${s.id}">Session #${s.id} (seed ${s.seed})</option>`).join("");
  if (sessions.length) loadHistory(sessions[0].id);
}

async function loadHistory(sessionId) {
  const [samples, events] = await Promise.all([
    (await fetch(`/api/history/battery?session_id=${sessionId}`)).json(),
    (await fetch(`/api/history/events?session_id=${sessionId}`)).json(),
  ]);
  const hLabels = samples.map((s) => `${Math.floor(s.sim_time_s / 3600)}h${Math.floor((s.sim_time_s % 3600) / 60)}m`);
  const hLevels = samples.map((s) => s.level_pct);
  if (!historyChart) {
    historyChart = new Chart(el("historyChart").getContext("2d"), {
      type: "line",
      data: { labels: hLabels, datasets: [{ label: "Battery (%)", data: hLevels, borderColor: "#22c55e", pointRadius: 0 }] },
      options: { animation: false, scales: { y: { min: 0, max: 100 } } },
    });
  } else {
    historyChart.data.labels = hLabels;
    historyChart.data.datasets[0].data = hLevels;
    historyChart.update();
  }
  el("events-tbody").innerHTML = events.map((e) => `
    <tr><td>${Math.round(e.sim_time_s)}</td><td>${e.package_name}</td><td>${e.old_state}</td><td>${e.new_state}</td></tr>
  `).join("");
}

el("btn-load-history").onclick = () => loadHistory(el("sel-session").value);

async function loadReport() {
  const rep = await (await fetch("/api/reports/summary")).json();
  el("report-summary").innerHTML = `
    <div class="card"><div class="card-label">Simulated Hours</div><div class="card-value">${rep.sim_hours_elapsed} h</div></div>
    <div class="card"><div class="card-label">Total Drain</div><div class="card-value">${rep.total_drain_mah} mAh</div></div>
    <div class="card"><div class="card-label">Screen-On Time</div><div class="card-value">${rep.screen_on_minutes} min</div></div>
    <div class="card"><div class="card-label">Top Drainer</div><div class="card-value">${rep.top_5_drainers[0]?.display_name || "--"}</div></div>
  `;
  const f = (v) => (v ?? 0).toFixed(1);
  el("report-apps").innerHTML = rep.all_apps.map((a) => `
    <tr><td>${a.display_name}</td><td>${f(a.total_mah)}</td><td>${f(a.pct_of_total)}%</td>
    <td>${f(a.fg_mah)}</td><td>${f(a.bg_mah)}</td><td>${f(a.cpu_mah)}</td><td>${f(a.screen_mah)}</td>
    <td>${f(a.network_mah)}</td><td>${f(a.gps_mah)}</td><td>${f(a.wakelock_mah)}</td></tr>`).join("");
  const days = [...new Set(rep.hourly_drain.map((h) => h.day))];
  const max = Math.max(1, ...rep.hourly_drain.map((h) => h.drain_pct));
  const cell = (d, h) => {
    const v = rep.hourly_drain.find((x) => x.day === d && x.hour === h)?.drain_pct || 0;
    return `<div class="hm-cell" title="Day ${d} ${h}:00 - ${v.toFixed(1)}%" style="opacity:${v ? 0.15 + 0.85 * v / max : 0.06}"></div>`;
  };
  el("report-heatmap").innerHTML = days.length
    ? `<div class="hm-row hm-head"><span></span>${[...Array(24).keys()].map((h) => `<span>${h % 3 ? "" : h}</span>`).join("")}</div>` +
      days.map((d) => `<div class="hm-row"><span>Day ${d}</span>${[...Array(24).keys()].map((h) => cell(d, h)).join("")}</div>`).join("")
    : `<div class="muted">Run the simulation to collect hourly data.</div>`;
}

async function loadAlerts() {
  const alerts = await (await fetch("/api/alerts")).json();
  const box = el("alerts-list");
  if (!alerts.length) {
    box.innerHTML = `<div class="card-meta">No anomalies detected yet.</div>`;
    return;
  }
  box.innerHTML = alerts.map((a) => `
    <div class="card" style="margin-bottom:10px; border-color: var(--danger);">
      <div class="card-header-row">
        <strong>[${a.severity}] ${a.display_name}</strong>
        <div class="sim-controls">
          <button class="btn" onclick="post('/api/apps/bucket',{package_name:'${a.package_name}',bucket:'RESTRICTED'}).then(loadAlerts)">Restrict Bucket</button>
          <button class="btn" onclick="post('/api/apps/kill',{package_name:'${a.package_name}'}).then(loadAlerts)">Kill App</button>
        </div>
      </div>
      <div class="card-meta">${a.reason}</div>
    </div>
  `).join("");
}

el("btn-refresh-alerts").onclick = loadAlerts;

let optChart = null;
el("btn-run-opt").onclick = async () => {
  const res = await post("/api/optimizer/run", {
    seed: Number(el("inp-seed").value) || 42,
    battery_saver: el("opt-saver").checked,
    aggressive_doze: el("opt-doze").checked,
    restrict_rogue: el("opt-rogue").checked,
    max_brightness: Number(el("opt-bright").value) || 0.7,
    max_cpu_freq_mhz: Number(el("opt-cpu").value) || 1800,
  });
  el("opt-result").innerHTML = `
    <div class="card"><div class="card-label">Baseline End</div><div class="card-value">${res.baseline.final_level_pct}%</div></div>
    <div class="card"><div class="card-label">Optimized End</div><div class="card-value">${res.optimized.final_level_pct}%</div></div>
    <div class="card"><div class="card-label">Battery Saved</div><div class="card-value" style="color:var(--ok)">+${res.pct_saved}%</div></div>
    <div class="card"><div class="card-label">Energy Saved</div><div class="card-value" style="color:var(--ok)">+${res.mah_saved} mAh</div></div>
  `;
  const oLabels = res.baseline.curve.map((_, i) => `${(i * 0.5).toFixed(1)}h`);
  if (!optChart) {
    optChart = new Chart(el("optChart").getContext("2d"), {
      type: "line",
      data: {
        labels: oLabels,
        datasets: [
          { label: "Baseline (%)", data: res.baseline.curve, borderColor: "#ef4444", pointRadius: 0 },
          { label: "Optimized (%)", data: res.optimized.curve, borderColor: "#22c55e", pointRadius: 0 },
        ],
      },
      options: { animation: false, scales: { y: { min: 0, max: 100 } } },
    });
  } else {
    optChart.data.labels = oLabels;
    optChart.data.datasets[0].data = res.baseline.curve;
    optChart.data.datasets[1].data = res.optimized.curve;
    optChart.update();
  }
};

document.querySelectorAll(".tab").forEach((btn) => {
  btn.onclick = () => {
    document.querySelectorAll(".tab").forEach((t) => t.classList.remove("active"));
    document.querySelectorAll(".tab-panel").forEach((p) => p.classList.remove("active"));
    btn.classList.add("active");
    el(`tab-${btn.dataset.tab}`).classList.add("active");
    if (btn.dataset.tab === "history") loadSessions();
    if (btn.dataset.tab === "reports") loadReport();
    if (btn.dataset.tab === "alerts") loadAlerts();
  };
});

function connectWS() {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  const ws = new WebSocket(`${proto}://${location.host}/ws`);
  ws.onmessage = (ev) => updateUI(JSON.parse(ev.data));
  ws.onclose = () => setTimeout(connectWS, 1500);
}
connectWS();
