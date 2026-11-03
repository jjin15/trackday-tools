// Lap comparison viewer: any logged signals against distance into the lap, laps overlaid.
const LapViewer = (() => {
  const MAX_LAPS = 8;
  const DELTA = "Delta time vs reference";
  const WHEELS = ["wheel speed freq fl", "wheel speed freq fr", "wheel speed freq rl", "wheel speed freq rr"];
  const WHEEL_KEY = "wheel speeds (FL FR RL RR)";
  const WHEEL_NAMES = ["FL", "FR", "RL", "RR"];
  const DEFAULT_SIGNALS = ["speed (gps)", DELTA, "throttle pos", "brake pressure front"];

  const $ = id => document.getElementById(id);
  const css = n => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
  const fmtTime = s => `${Math.floor(s / 60)}:${(s % 60).toFixed(1).padStart(4, "0")}`;

  let D = null, lapByN = {}, allSignals = [], rangeCache = {};
  let markers = [];                       // slides to draw: {lap, time_in_lap_s, rank}
  let state = { laps: new Map(), signals: [], ref: 1 };
  let wired = false, pendingRange = null;

  function load(data) {
    D = data; rangeCache = {};
    lapByN = Object.fromEntries(D.laps.map((l, i) => [l.n, { ...l, idx: i }]));
    const hasWheels = WHEELS.every(k => D.values[k]);
    allSignals = [{ key: DELTA, unit: "s", group: "Derived" },
      ...D.signals.filter(s => !(hasWheels && WHEELS.includes(s.key))),
      ...(hasWheels ? [{ key: WHEEL_KEY, unit: "Hz", group: "CAN bus", members: WHEELS }] : [])];
    const keys = new Set(allSignals.map(s => s.key));
    state = { laps: new Map(), signals: DEFAULT_SIGNALS.filter(k => keys.has(k)),
              ref: D.defaultLaps[0] ?? (D.laps[0] && D.laps[0].n) ?? 1 };
    D.defaultLaps.forEach(selectLap);
    wire();
    refresh();
  }

  function selectLap(n) {
    if (state.laps.has(n)) { state.laps.delete(n); return true; }
    if (state.laps.size >= MAX_LAPS) { say(`Up to ${MAX_LAPS} laps at once. Deselect one first.`); return false; }
    const used = new Set(state.laps.values());
    let slot = 1; while (used.has(slot)) slot++;
    state.laps.set(n, slot);
    return true;
  }
  const say = t => { $("lv-msg").textContent = t; };

  function seriesFor(key, lapN) {
    const i = lapByN[lapN].idx;
    if (key !== DELTA) return D.values[key][i];
    const t = D.time[i], r = D.time[lapByN[state.ref].idx];
    return t.map((v, j) => (j < r.length ? +(v - r[j]).toFixed(3) : null));
  }

  function distAt(lapN, timeInLap) {            // distance into the lap at a time into the lap
    const arr = D.time[lapByN[lapN].idx];
    let lo = 0, hi = arr.length - 1;
    while (lo < hi) { const mid = (lo + hi) >> 1; if (arr[mid] < timeInLap) lo = mid + 1; else hi = mid; }
    return lo * D.step;
  }

  function buildLapChips() {
    const el = $("lv-laps"); el.innerHTML = "";
    D.laps.forEach(l => {
      const b = document.createElement("button");
      b.className = "chip"; b.type = "button";
      const slot = state.laps.get(l.n);
      b.setAttribute("aria-pressed", slot ? "true" : "false");
      if (slot) b.style.setProperty("--c", `var(--series-${slot})`);
      b.innerHTML = `<span class="swatch"></span>Lap ${l.n} <small>${fmtTime(l.time)}</small>`;
      b.onclick = () => { say(""); selectLap(l.n); refresh(); };
      el.appendChild(b);
    });
    const ref = $("lv-ref");
    ref.innerHTML = D.laps.map(l => `<option value="${l.n}">Lap ${l.n} (${fmtTime(l.time)})</option>`).join("");
    ref.value = state.ref;
  }

  function buildSignalList() {
    const q = $("lv-filter").value.toLowerCase();
    const el = $("lv-signals"); el.innerHTML = "";
    const groups = {};
    allSignals.forEach(s => (groups[s.group] ??= []).push(s));
    Object.entries(groups).forEach(([g, list]) => {
      const vis = list.filter(s => s.key.toLowerCase().includes(q));
      if (!vis.length) return;
      const h = document.createElement("h2"); h.textContent = g; el.appendChild(h);
      vis.forEach(s => {
        const lab = document.createElement("label");
        const cb = document.createElement("input"); cb.type = "checkbox";
        cb.checked = state.signals.includes(s.key);
        cb.onchange = () => {
          state.signals = cb.checked ? [...state.signals, s.key] : state.signals.filter(k => k !== s.key);
          refresh(false);
        };
        lab.append(cb, `${s.key}${s.unit ? " [" + s.unit + "]" : ""}`);
        el.appendChild(lab);
      });
    });
  }

  const wheelColor = k => css(`--series-${k + 1}`);
  const lapShade = lapN => Math.max(0.3, 1 - 0.3 * [...state.laps.keys()].indexOf(lapN));

  function drawPlot() {
    const n = state.signals.length, lapNs = [...state.laps.keys()];
    const wrap = $("lv-plot");
    if (!n || !lapNs.length) {
      Plotly.purge(wrap);
      wrap.innerHTML = `<div class="empty">Select at least one lap and one signal.</div>`;
      return;
    }
    const ink = css("--text-secondary"), grid = css("--grid"), muted = css("--muted");
    const traces = [], annotations = [], shapes = [], layout = {
      paper_bgcolor: "rgba(0,0,0,0)", plot_bgcolor: "rgba(0,0,0,0)",
      font: { color: ink, size: 12 }, margin: { l: 70, r: 16, t: 24, b: 48 },
      height: 80 + 200 * n, hovermode: "x unified", showlegend: false, annotations, shapes,
      hoverlabel: { bgcolor: css("--surface-1"), bordercolor: grid, font: { color: css("--text-primary") } },
    };
    const gap = 0.05, h = (1 - gap * (n - 1)) / n;
    const showMarkers = $("lv-markers").checked;
    state.signals.forEach((key, i) => {
      const sig = allSignals.find(s => s.key === key), ax = i + 1;
      const top = 1 - i * (h + gap);
      layout["yaxis" + ax] = { domain: [top - h, top], anchor: "x" + ax, gridcolor: grid, zeroline: key === DELTA,
        zerolinecolor: muted, title: { text: sig.unit ? `${key} [${sig.unit}]` : key, font: { size: 11 } }, automargin: true };
      layout["xaxis" + ax] = { domain: [0, 1], anchor: "y" + ax, matches: ax > 1 ? "x" : undefined, gridcolor: grid,
        showspikes: true, spikemode: "across", spikethickness: 1, spikecolor: muted, spikedash: "solid",
        showticklabels: i === n - 1, title: i === n - 1 ? { text: "Distance into lap [m]", font: { size: 11 } } : undefined };

      if (showMarkers) lapNs.forEach(lapN => markers.filter(m => m.lap === lapN).forEach(m => {
        const x = distAt(lapN, m.time_in_lap_s), color = css(`--series-${state.laps.get(lapN)}`);
        shapes.push({ type: "line", xref: "x" + ax, yref: "paper", x0: x, x1: x, y0: top - h, y1: top,
          line: { color, width: 8 }, opacity: 0.18, layer: "below" });
        if (i === 0) annotations.push({ xref: "x1", yref: "paper", x, y: top, text: `#${m.rank}`, showarrow: false,
          yanchor: "bottom", font: { size: 11, color: ink } });
      }));

      if (sig.members) {                                       // colour = wheel, shade = lap
        annotations.push({ xref: "paper", yref: "paper", x: 0, y: top + 0.012, xanchor: "left", yanchor: "bottom",
          showarrow: false, font: { size: 12, color: ink },
          text: WHEEL_NAMES.map((nm, k) => `<span style="color:${wheelColor(k)}">━━</span> ${nm}`).join("&nbsp;&nbsp;&nbsp;")
            + `&nbsp;&nbsp;&nbsp;&nbsp;shade = lap (strongest to lightest: ${lapNs.map(l => "Lap " + l).join(", ")})` });
        sig.members.forEach((member, k) => lapNs.forEach(lapN => {
          const y = seriesFor(member, lapN);
          traces.push({ type: "scatter", mode: "lines", xaxis: "x" + ax, yaxis: "y" + ax,
            x: y.map((_, j) => j * D.step), y, name: `Lap ${lapN} · ${WHEEL_NAMES[k]}`, opacity: lapShade(lapN),
            line: { color: wheelColor(k), width: 2 }, connectgaps: false, hovertemplate: `%{y:.2f} Hz` });
        }));
        return;
      }
      lapNs.forEach(lapN => {
        const y = seriesFor(key, lapN);
        traces.push({ type: "scatter", mode: "lines", xaxis: "x" + ax, yaxis: "y" + ax,
          x: y.map((_, j) => j * D.step), y, name: `Lap ${lapN}`,
          line: { color: css(`--series-${state.laps.get(lapN)}`), width: 2 }, connectgaps: false,
          hovertemplate: `%{y:.2f}${sig.unit ? " " + sig.unit : ""}` });
      });
    });
    Plotly.react("lv-plot", traces, layout, { responsive: true, displaylogo: false }).then(() => {
      if (pendingRange) { Plotly.relayout("lv-plot", { "xaxis.range": pendingRange }); pendingRange = null; }
    });
  }

  function drawTable() {
    const el = $("lv-tablewrap");
    const lapNs = [...state.laps.keys()];
    const sigs = state.signals.flatMap(k => allSignals.find(s => s.key === k).members ?? [k]).filter(k => k !== DELTA);
    const stat = arr => {
      const v = arr.filter(x => x != null); if (!v.length) return ["-", "-", "-"];
      const avg = v.reduce((a, b) => a + b, 0) / v.length;
      return [Math.min(...v), avg, Math.max(...v)].map(x => x.toFixed(1));
    };
    let html = `<table><thead><tr><th>Lap</th><th>Time</th>`;
    sigs.forEach(k => html += `<th colspan="3">${k}</th>`);
    html += `</tr><tr><th></th><th></th>${sigs.map(() => "<th>min</th><th>avg</th><th>max</th>").join("")}</tr></thead><tbody>`;
    lapNs.forEach(n => {
      html += `<tr><td>Lap ${n}</td><td>${fmtTime(lapByN[n].time)}</td>`;
      sigs.forEach(k => stat(seriesFor(k, n)).forEach(v => html += `<td class="num">${v}</td>`));
      html += `</tr>`;
    });
    el.innerHTML = lapNs.length ? html + "</tbody></table>" : `<div class="empty">Select at least one lap.</div>`;
  }

  function refresh(rebuildSignals = true) {
    if (!D) return;
    buildLapChips();
    if (rebuildSignals) buildSignalList();
    const table = $("lv-table").checked;
    $("lv-plot-wrap").hidden = table;
    $("lv-tablewrap").hidden = !table;
    table ? drawTable() : drawPlot();
  }

  function wire() {
    if (wired) return; wired = true;
    $("lv-fastest").onclick = () => { state.laps.clear(); D.defaultLaps.forEach(selectLap); say(""); refresh(); };
    $("lv-clear").onclick = () => { state.laps.clear(); say(""); refresh(); };
    $("lv-ref").onchange = e => { state.ref = +e.target.value; refresh(false); };
    $("lv-table").onchange = () => refresh(false);
    $("lv-markers").onchange = () => refresh(false);
    $("lv-filter").oninput = buildSignalList;
    matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => refresh(false));
  }

  return {
    load,
    isLoaded: () => !!D,
    setMarkers(list) { markers = list; if (D && !$("lv-plot-wrap").hidden) drawPlot(); },
    redraw: () => refresh(false),
    // Bring a slide into view: make sure its lap is shown and zoom to the stretch around it.
    show(lapN, timeInLap) {
      if (!D || !lapByN[lapN]) return;
      if (!state.laps.has(lapN)) {
        if (state.laps.size >= MAX_LAPS) state.laps.delete(state.laps.keys().next().value);
        selectLap(lapN);
      }
      const x = distAt(lapN, timeInLap);
      pendingRange = [Math.max(0, x - 250), x + 250];
      $("lv-table").checked = false;
      refresh();
    },
  };
})();
