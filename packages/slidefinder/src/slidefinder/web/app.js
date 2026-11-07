// SlideFinder web app: upload a session, tune detection, line slides up with video clips.
(() => {
  const $ = id => document.getElementById(id);
  const SPEED = { mph: { factor: 2.23694, label: "mph" }, kmh: { factor: 3.6, label: "km/h" } };

  const state = {
    config: null, session: null, preset: "strict", custom: {}, method: "steering", note: "",
    events: [], hidden: new Set(), showHidden: false, units: "mph", seq: 0, timer: null,
  };

  const store = {
    get(key, fallback) { try { const v = localStorage.getItem(key); return v === null ? fallback : v; } catch { return fallback; } },
    set(key, value) { try { localStorage.setItem(key, value); } catch { /* storage can be blocked */ } },
  };

  async function api(path, options) {
    const res = await fetch(path, options);
    if (!res.ok) {
      let msg = res.statusText;
      try { msg = (await res.json()).detail || msg; } catch { /* not JSON */ }
      throw new Error(msg);
    }
    return res.json();
  }
  function text(tag, value, className) {
    const el = document.createElement(tag);
    el.textContent = value;
    if (className) el.className = className;
    return el;
  }

  // ---------- upload ----------
  function setupDrop() {
    const drop = $("drop"), input = $("file");
    drop.onclick = () => input.click();
    drop.onkeydown = e => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); input.click(); } };
    input.onchange = () => input.files[0] && upload(input.files[0]);
    ["dragenter", "dragover"].forEach(t => drop.addEventListener(t, e => { e.preventDefault(); drop.classList.add("over"); }));
    ["dragleave", "drop"].forEach(t => drop.addEventListener(t, e => { e.preventDefault(); drop.classList.remove("over"); }));
    drop.addEventListener("drop", e => e.dataTransfer.files[0] && upload(e.dataTransfer.files[0]));
  }

  function upload(file) {
    const msg = $("drop-msg"), progress = $("progress"), bar = $("bar");
    msg.className = "msg"; msg.textContent = `Uploading ${file.name}…`;
    progress.hidden = false; progress.classList.remove("busy"); bar.style.width = "0";
    const xhr = new XMLHttpRequest();
    xhr.open("POST", "/api/sessions");
    xhr.upload.onprogress = e => {
      if (!e.lengthComputable) return;
      bar.style.width = (100 * e.loaded / e.total) + "%";
      if (e.loaded === e.total) { progress.classList.add("busy"); msg.textContent = "Reading the session…"; }
    };
    xhr.onerror = () => fail("Couldn't reach the SlideFinder server. Is it still running?");
    xhr.onload = () => {
      progress.classList.remove("busy");
      let body = {};
      try { body = JSON.parse(xhr.responseText); } catch { /* leave empty */ }
      if (xhr.status !== 200) return fail(body.detail || `Upload failed (${xhr.status}).`);
      progress.hidden = true;
      startSession(body);
    };
    const form = new FormData(); form.append("file", file);
    xhr.send(form);
    function fail(message) { progress.hidden = true; msg.className = "msg error"; msg.textContent = message; }
  }

  // ---------- session ----------
  function startSession(summary) {
    if (state.session) fetch(`/api/sessions/${state.session.id}`, { method: "DELETE" });
    state.session = summary; state.custom = {}; state.preset = state.config.default_preset;
    state.showHidden = false;
    history.replaceState(null, "", `#session=${summary.id}`);
    state.hidden = new Set(JSON.parse(store.get(hiddenKey(), "[]")));
    $("tstart").value = ""; $("tstart").placeholder = `auto (${summary.t_start_s})`;
    $("drop").hidden = true; $("workspace").hidden = false;
    renderSummary(); renderSensitivity();
    requestSlides(0);
  }
  const hiddenKey = () => `slidefinder:hidden:${state.session.filename}:${state.session.part}:${state.session.duration_s}`;

  function renderSummary() {
    const s = state.session, box = $("summary");
    box.innerHTML = "";
    const chips = document.createElement("div"); chips.className = "chips";
    const pill = (label, value, cls = "") => {
      const p = document.createElement("span"); p.className = "pill " + cls;
      p.append(label + " ", text("b", value)); return p;
    };
    chips.append(pill("File", s.filename));
    if (s.parts.length > 1) {                    // a session .rcz can hold several drives
      const label = document.createElement("label"); label.className = "pill";
      label.append("Part ");
      const sel = document.createElement("select"); sel.setAttribute("aria-label", "Which part of the session to analyse");
      s.parts.forEach(p => { const o = document.createElement("option"); o.value = p.index; o.textContent = p.label; sel.append(o); });
      sel.value = s.part; sel.onchange = () => choosePart(+sel.value);
      label.append(sel); chips.append(label);
    } else {
      chips.append(pill("Laps", String(s.laps)));
    }
    chips.append(pill("Length", `${Math.floor(s.duration_s / 60)} min`));
    if (s.track) chips.append(pill("Track", s.track.name));
    else {
      const warn = document.createElement("span"); warn.className = "pill warn";
      warn.append(s.track_name ? `No track file for “${s.track_name}”, so sectors are off. ` : "No track in this file. ");
      const add = text("button", "Add a track file (.rcz)", "link"); add.type = "button";
      add.onclick = chooseTrack; warn.append(add); chips.append(warn);
    }
    const other = text("button", "Open another session", "plain"); other.type = "button";
    other.onclick = () => { $("drop").hidden = false; $("file").value = ""; $("drop-msg").textContent = ""; };
    chips.append(other);
    box.append(chips);
  }

  async function choosePart(index) {
    try {
      const summary = await api(`/api/sessions/${state.session.id}/part/${index}`, { method: "POST" });
      state.session = summary; state.custom = {}; state.showHidden = false;
      state.hidden = new Set(JSON.parse(store.get(hiddenKey(), "[]")));
      $("tstart").value = ""; $("tstart").placeholder = `auto (${summary.t_start_s})`;
      renderSummary(); renderSensitivity(); renderAdvanced();
      requestSlides(0);
    } catch (err) { alert(err.message); renderSummary(); }
  }

  function chooseTrack() {
    const input = document.createElement("input"); input.type = "file"; input.accept = ".rcz";
    input.onchange = async () => {
      if (!input.files[0]) return;
      const form = new FormData(); form.append("file", input.files[0]);
      try {
        state.session = await api(`/api/sessions/${state.session.id}/track`, { method: "POST", body: form });
        renderSummary(); requestSlides(0);
      } catch (err) { alert(err.message); }
    };
    input.click();
  }

  // ---------- sensitivity + advanced ----------
  function renderSensitivity() {
    const seg = $("sens"); seg.innerHTML = "";
    Object.entries(state.config.presets).forEach(([key, p]) => {
      const b = text("button", p.label); b.type = "button"; b.setAttribute("role", "radio"); b.title = p.summary;
      b.setAttribute("aria-checked", String(key === state.preset && !Object.keys(state.custom).length));
      b.onclick = () => { state.preset = key; state.custom = {}; renderSensitivity(); renderAdvanced(); requestSlides(0); };
      seg.append(b);
    });
  }

  const speedFactor = () => SPEED[state.units].factor;
  const presetValue = key => state.config.presets[state.preset][state.method][key];
  const currentValue = key => (key in state.custom ? state.custom[key] : presetValue(key));
  const toDisplay = (info, si) => info.unit === "speed" ? si * speedFactor() : si;
  const fromDisplay = (info, v) => info.unit === "speed" ? v / speedFactor() : v;
  const unitLabel = info => info.unit === "speed" ? SPEED[state.units].label : info.unit;
  const round = (v, step) => Math.round(v / step) * step;

  function renderAdvanced() {
    const grid = $("adv-fields"); grid.innerHTML = "";
    state.config.params.filter(p => p.methods.includes(state.method)).forEach(info => {
      const factor = info.unit === "speed" ? speedFactor() : 1;
      const step = info.unit === "speed" ? 1 : info.step;
      const label = document.createElement("label");
      const range = document.createElement("input"); range.type = "range";
      range.min = Math.floor(info.minimum * factor); range.max = Math.ceil(info.maximum * factor); range.step = step;
      const out = document.createElement("output");
      const sync = () => { out.textContent = `${(+range.value).toFixed(step < 1 ? 2 : 0)} ${unitLabel(info)}`; };
      range.value = round(toDisplay(info, currentValue(info.key)), step); sync();
      range.setAttribute("aria-label", info.label);
      range.oninput = () => {
        sync();
        const si = fromDisplay(info, +range.value);
        if (+range.value === round(toDisplay(info, presetValue(info.key)), step)) delete state.custom[info.key];
        else state.custom[info.key] = si;
        renderSensitivity(); requestSlides();
      };
      const ctl = document.createElement("div"); ctl.className = "ctl"; ctl.append(range, out);
      label.append(info.label, ctl); grid.append(label);
    });
  }

  // ---------- slides ----------
  const clipLengths = () => $("cliplen").value.trim() || state.config.default_clip_length;

  function requestSlides(delay = 150) {
    clearTimeout(state.timer);
    state.timer = setTimeout(fetchSlides, delay);
  }

  async function fetchSlides() {
    if (!state.session) return;
    const seq = ++state.seq;
    const q = new URLSearchParams({ preset: state.preset, offset: String(+$("offset").value || 0), clip_lengths: clipLengths() });
    Object.entries(state.custom).forEach(([k, v]) => q.set(k, v));
    if ($("tstart").value !== "") q.set("t_start", $("tstart").value);
    try {
      const data = await api(`/api/sessions/${state.session.id}/slides?${q}`);
      if (seq !== state.seq) return;                     // a newer request is already on its way
      const methodChanged = data.method !== state.method;
      state.method = data.method; state.note = data.note; state.events = data.events;
      $("note").textContent = data.note;
      if (methodChanged || !$("adv-fields").children.length) { renderSensitivity(); renderAdvanced(); }
      renderSlides();
    } catch (err) {
      if (seq !== state.seq) return;
      $("count").className = "count msg error"; $("count").textContent = err.message;
    }
  }

  const visibleEvents = () => state.events.filter(e => !state.hidden.has(e.id));

  function renderSlides() {
    const all = state.events, shown = state.showHidden ? all : visibleEvents();
    const countEl = $("count"); countEl.className = "count";
    const custom = Object.keys(state.custom).length ? "Custom · " : "";
    countEl.textContent = `${custom}${visibleEvents().length} slide${visibleEvents().length === 1 ? "" : "s"}`;
    const hiddenN = all.length - visibleEvents().length, toggle = $("toggle-hidden");
    toggle.hidden = hiddenN === 0;
    toggle.textContent = state.showHidden ? "Hide the hidden ones" : `Show ${hiddenN} hidden`;

    const table = $("slides-table"); table.innerHTML = "";
    const empty = $("empty");
    if (!shown.length) {
      empty.hidden = false;
      empty.textContent = all.length ? "Everything is hidden." : "No slides found. Try a looser sensitivity.";
    } else empty.hidden = true;
    if (!shown.length) { renderSync(); return; }

    const hasSector = shown.some(e => e.sector_name), hasClip = shown.some(e => e.clip !== undefined);
    const maxSev = Math.max(...shown.map(e => e.severity));
    const head = table.createTHead().insertRow();
    ["#", "Where", hasClip ? "Find it in your video" : "Video time", "Severity", "Length", "Detail", ""].forEach((h, i) => {
      const th = text("th", h); if ([3, 4].includes(i)) th.className = "num"; head.append(th);
    });
    const body = table.createTBody();
    shown.forEach(e => {
      const tr = body.insertRow(); const isHidden = state.hidden.has(e.id);
      if (isHidden) tr.className = "hidden-row";
      tr.insertCell().textContent = e.rank;
      const where = tr.insertCell();
      where.append(text("div", `Lap ${e.lap === "" ? "-" : e.lap}${place(e) ? " · " + place(e) : ""}`));
      where.append(text("div", `data ${e.session_time}${e.turn && hasSector && e.sector_name ? " · sector " + e.sector_name : ""}`, "muted small"));
      const find = tr.insertCell();
      if (hasClip && e.clip !== "" && e.clip != null) {
        const d = document.createElement("div"); d.className = "clip";
        d.append(`Clip ${e.clip} `, text("small", `at ${e.clip_time}`)); find.append(d);
      } else if (hasClip) find.append(text("div", "Before the video starts", "muted"));
      else find.append(text("div", e.video_time));
      const sev = tr.insertCell(); sev.className = "num";
      const wrap = document.createElement("span"); wrap.className = "sev";
      const bar = document.createElement("span"); bar.className = "bar"; const fill = document.createElement("i");
      fill.style.width = `${Math.max(4, 100 * e.severity / maxSev)}%`; bar.append(fill);
      wrap.append(bar, text("span", String(e.severity))); sev.append(wrap);
      const len = tr.insertCell(); len.className = "num"; len.textContent = `${e.duration_s.toFixed(1)} s`;
      tr.insertCell().textContent = detailText(e);
      const act = tr.insertCell();
      const hide = text("button", isHidden ? "Restore" : "Not a slide", "rowbtn"); hide.type = "button";
      hide.onclick = () => toggleHidden(e.id); act.append(hide);
    });
    renderSync();
  }

  // the turn ("T7", "after T7") when the track has a turn map, otherwise the sector
  function place(e) { return e.turn || e.sector_name || ""; }

  function detailText(e) {
    const speed = `${Math.round(e.min_speed_mph / 2.23694 * speedFactor())} ${SPEED[state.units].label} min`;
    if (e.peak_slip_deg !== undefined) return `${e.peak_slip_deg}° slip · ${speed}`;
    return `${e.peak_steer_deg}° steering · ${speed}`;
  }

  function toggleHidden(id) {
    state.hidden.has(id) ? state.hidden.delete(id) : state.hidden.add(id);
    store.set(hiddenKey(), JSON.stringify([...state.hidden]));
    renderSlides();
  }

  function exportCsv() {
    const rows = visibleEvents(); if (!rows.length) return;
    const keys = Object.keys(rows[0]).filter(k => k !== "id");
    const cell = v => { const s = v == null ? "" : String(v); return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s; };
    const csv = [keys.join(","), ...rows.map(r => keys.map(k => cell(r[k])).join(","))].join("\n");
    const a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob([csv], { type: "text/csv" }));
    a.download = "slides.csv"; a.click(); URL.revokeObjectURL(a.href);
  }

  // ---------- video sync ----------
  function renderSync() {
    const sel = $("sync-slide"), keep = sel.value; sel.innerHTML = "";
    visibleEvents().forEach(e => {
      const o = document.createElement("option"); o.value = e.id;
      o.textContent = `#${e.rank} · Lap ${e.lap}${place(e) ? " · " + place(e) : ""} · data ${e.session_time}`;
      sel.append(o);
    });
    if ([...sel.options].some(o => o.value === keep)) sel.value = keep;
  }

  async function lineUp() {
    const msg = $("sync-msg"); msg.className = "msg"; msg.textContent = "";
    const ev = state.events.find(e => String(e.id) === $("sync-slide").value);
    if (!ev) { msg.className = "msg error"; msg.textContent = "Pick a slide first."; return; }
    try {
      const res = await api("/api/sync/solve", { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_time_s: ev.session_time_s, clip_lengths: clipLengths(),
                               clip: +$("sync-clip").value, clip_time: $("sync-time").value || "0" }) });
      $("offset").value = res.offset;
      msg.textContent = `Offset set to ${res.offset} s. Every slide now points at the right clip.`;
      requestSlides(0);
    } catch (err) { msg.className = "msg error"; msg.textContent = err.message; }
  }

  // ---------- wiring ----------
  async function init() {
    state.config = await api("/api/config");
    state.units = store.get("slidefinder:units", "mph"); $("units").value = state.units;
    $("cliplen").value = store.get("slidefinder:cliplen", state.config.default_clip_length);
    setupDrop();
    $("units").onchange = () => { state.units = $("units").value; store.set("slidefinder:units", state.units); renderAdvanced(); renderSlides(); };
    $("reset").onclick = () => { state.custom = {}; renderSensitivity(); renderAdvanced(); requestSlides(0); };
    $("tstart").oninput = () => requestSlides();
    $("offset").oninput = () => requestSlides();
    $("cliplen").oninput = () => { store.set("slidefinder:cliplen", $("cliplen").value); requestSlides(); };
    $("sync-go").onclick = lineUp;
    $("export").onclick = exportCsv;
    $("toggle-hidden").onclick = () => { state.showHidden = !state.showHidden; renderSlides(); };
  }
  async function resume() {                      // reopen the session named in the URL, if the server still has it
    const m = location.hash.match(/session=([0-9a-f]+)/);
    if (!m) return;
    try { startSession(await api(`/api/sessions/${m[1]}`)); } catch { history.replaceState(null, "", location.pathname); }
  }
  init().then(resume).catch(err => { $("drop-msg").className = "msg error"; $("drop-msg").textContent = err.message; });
})();
