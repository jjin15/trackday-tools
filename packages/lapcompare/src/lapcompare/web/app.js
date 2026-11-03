// Lap Compare web app: upload a session, pick a part, compare laps, optionally mark slides.
(() => {
  const $ = id => document.getElementById(id);
  const state = { session: null };

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
    xhr.onerror = () => fail("Couldn't reach the Lap Compare server. Is it still running?");
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
    state.session = summary;
    history.replaceState(null, "", `#session=${summary.id}`);
    $("drop").hidden = true; $("workspace").hidden = false;
    resetSlides(); renderSummary(); loadLaps();
  }

  function renderSummary() {
    const s = state.session, box = $("summary");
    box.innerHTML = "";
    const chips = document.createElement("div"); chips.className = "chips";
    const pill = (label, value) => {
      const p = document.createElement("span"); p.className = "pill";
      p.append(label + " ", text("b", value)); return p;
    };
    chips.append(pill("File", s.filename));
    if (s.parts.length > 1) {                    // a session .rcz can hold several drives
      const label = document.createElement("label"); label.className = "pill";
      label.append("Part ");
      const sel = document.createElement("select"); sel.setAttribute("aria-label", "Which part of the session to compare");
      s.parts.forEach(p => { const o = document.createElement("option"); o.value = p.index; o.textContent = p.label; sel.append(o); });
      sel.value = s.part; sel.onchange = () => choosePart(+sel.value);
      label.append(sel); chips.append(label);
    } else {
      chips.append(pill("Laps", String(s.laps)));
    }
    chips.append(pill("Length", `${Math.floor(s.duration_s / 60)} min`));
    if (s.track_name) chips.append(pill("Track", s.track_name));
    const other = text("button", "Open another session", "plain"); other.type = "button";
    other.onclick = () => { $("drop").hidden = false; $("file").value = ""; $("drop-msg").textContent = ""; };
    chips.append(other);
    box.append(chips);
  }

  async function choosePart(index) {
    try {
      state.session = await api(`/api/sessions/${state.session.id}/part/${index}`, { method: "POST" });
      resetSlides(); renderSummary(); loadLaps();
    } catch (err) { alert(err.message); renderSummary(); }
  }

  async function loadLaps() {
    $("lap-viewer").hidden = true; $("lap-loading").hidden = false;
    $("lap-loading").textContent = "Loading lap data (a few seconds)…";
    try {
      LapViewer.load(await api(`/api/sessions/${state.session.id}/laps`));
      $("lap-loading").hidden = true; $("lap-viewer").hidden = false; LapViewer.redraw();
    } catch (err) { $("lap-loading").textContent = err.message; }
  }

  // ---------- slide markers ----------
  function resetSlides() {
    LapViewer.setMarkers([]);
    $("clear-slides").hidden = true;
    $("slides-msg").className = "muted small";
    $("slides-msg").textContent = "Mark where the slides are: choose the CSV exported from SlideFinder for this session.";
  }

  async function loadSlides(file) {
    const msg = $("slides-msg"); msg.className = "muted small"; msg.textContent = "Reading…";
    const form = new FormData(); form.append("file", file);
    try {
      const res = await api(`/api/sessions/${state.session.id}/slides`, { method: "POST", body: form });
      LapViewer.setMarkers(res.markers);
      $("clear-slides").hidden = res.matched === 0;
      let line = `${res.matched} slide${res.matched === 1 ? "" : "s"} marked`;
      if (res.skipped) line += `, ${res.skipped} not from this session or lap`;
      msg.textContent = line + "." + (res.note ? " " + res.note : "");
      msg.className = res.matched ? "muted small" : "msg error";
    } catch (err) { msg.className = "msg error"; msg.textContent = err.message; }
  }

  // ---------- wiring ----------
  async function resume() {                      // reopen the session named in the URL, if the server still has it
    const m = location.hash.match(/session=([0-9a-f]+)/);
    if (!m) return;
    try { startSession(await api(`/api/sessions/${m[1]}`)); } catch { history.replaceState(null, "", location.pathname); }
  }
  setupDrop();
  $("load-slides").onclick = () => $("slides-file").click();
  $("slides-file").onchange = () => { const f = $("slides-file").files[0]; if (f) loadSlides(f); $("slides-file").value = ""; };
  $("clear-slides").onclick = resetSlides;
  resume();
})();
