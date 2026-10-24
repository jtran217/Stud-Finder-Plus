// Stud Mapper web page: polls /api/state, sends clicks and commands.
"use strict";

const $ = (id) => document.getElementById(id);
const POLL_MS = 150;
const CORNER_LABELS = ["top-left", "top-right", "bottom-right", "bottom-left"];
const VIEW_LABELS = { "video": "Video", "object mask": "Object mask", "laser mask": "Laser mask" };

let state = null;
let online = true;
const STILL = new URLSearchParams(location.search).has("still");
const videoSrc = () => (STILL ? "/snapshot.jpg?" : "/stream.mjpg?") + Date.now();
$("video").src = videoSrc();

// ------------------------------------------------------------------ server --
async function post(path, body) {
  try {
    await fetch(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    poll();   // show the result right away
  } catch (e) { /* the poll loop reports lost contact */ }
}
const command = (name, arg) => post("/api/command", { name, arg });

async function poll() {
  try {
    const r = await fetch("/api/state", { cache: "no-store" });
    state = await r.json();
    if (!online) {           // reconnected: restart the video stream
      online = true;
      $("video").src = videoSrc();
    }
    $("offline").hidden = true;
    render();
  } catch (e) {
    online = false;
    $("offline").hidden = false;
  }
}
setInterval(poll, POLL_MS);
poll();

// ------------------------------------------------------------------- input --
document.querySelectorAll("button[data-cmd]").forEach((b) =>
  b.addEventListener("click", () => command(b.dataset.cmd)));

const KEYS = {};
document.querySelectorAll("button[data-key]").forEach((b) => { KEYS[b.dataset.key] = b; });

document.addEventListener("keydown", (e) => {
  if (e.metaKey || e.ctrlKey || e.altKey || e.repeat) return;
  if (e.target.closest("input, textarea, select")) return;   // typing in a field
  const key = e.key.length === 1 ? e.key.toLowerCase() : e.key;
  if (key === "m") { command("view"); return; }
  const b = KEYS[key];
  if (!b) return;
  e.preventDefault();          // stop space from scrolling or re-clicking a focused button
  if (!b.disabled) command(b.dataset.cmd);
});

// Clicks on the video, as fractions of the actual picture (ignores letterboxing).
$("video").addEventListener("click", (e) => {
  if (!state || !state.setup_step) return;
  const img = e.currentTarget;
  const box = img.getBoundingClientRect();
  const nw = img.naturalWidth || 16, nh = img.naturalHeight || 9;
  const scale = Math.min(box.width / nw, box.height / nh);
  const w = nw * scale, h = nh * scale;
  const fx = (e.clientX - box.left - (box.width - w) / 2) / w;
  const fy = (e.clientY - box.top - (box.height - h) / 2) / h;
  if (fx < 0 || fx > 1 || fy < 0 || fy > 1) return;
  post("/api/click", { x: fx, y: fy });
});

// ------------------------------------------------------------------ render --
const fmt = (v, d = 1) => (v === null || v === undefined ? "--" : v.toFixed(d));

function setStatus(id, cls, text) {
  const el = $(id);
  el.className = cls;
  el.textContent = text;
}

function render() {
  const s = state;
  const L = s.laser;

  // top bar
  setStatus("st-camera", s.fps > 5 ? "good" : "bad", `Camera ${fmt(s.fps, 0)} fps`);
  setStatus("st-signal", s.signal.source === "serial" ? "good" : "sim",
    s.signal.source === "serial" ? "Stud signal: Pro Micro" : "Stud signal: keyboard");
  setStatus("st-laser", L.simulated ? "sim" : (L.calibrated ? "good" : ""),
    L.simulated ? "Laser: simulated" : (L.calibrated ? "Laser: calibrated" : "Laser: not calibrated"));

  renderSetup(s);
  renderFinder(s);
  renderStuds(s);
  renderLaser(s);
  renderViews(s);
  renderLog(s);
  if (!$("xray-figure").hidden) renderXray(s);
}

// ---- wall size form (setup step 1) ----
let editingWall = false;     // "Change size" pressed after the size was set
let wallPrefilled = false;

$("wall-form").addEventListener("submit", (e) => {
  e.preventDefault();
  const width = parseFloat($("wall-w").value), height = parseFloat($("wall-h").value);
  if (!(width > 0 && height > 0)) return;
  editingWall = false;
  command("set_wall", { width, height });
});
$("btn-wall-change").addEventListener("click", () => {
  editingWall = true;
  $("wall-w").value = state.wall_size[0];
  $("wall-h").value = state.wall_size[1];
  render();
  $("wall-w").focus();
});
$("btn-wall-cancel").addEventListener("click", () => { editingWall = false; render(); });

function renderWallStep(s) {
  const set = s.wall_size_set;
  const editing = !set || editingWall;
  $("step-wall").className = editing ? "current" : "done";
  $("wall-state").textContent = set && !editingWall ? `${s.wall_size[0]} × ${s.wall_size[1]} in` : "";
  $("wall-form").hidden = !editing;
  $("wall-change").hidden = editing;
  $("btn-wall-cancel").hidden = !set;
  if (!set && !wallPrefilled) {       // first visit: suggest the default size
    wallPrefilled = true;
    $("wall-w").value = s.wall_size[0];
    $("wall-h").value = s.wall_size[1];
    $("wall-w").focus();
    $("wall-w").select();
  }
}

function renderSetup(s) {
  renderWallStep(s);
  const wallSet = s.wall_size_set;
  const clicking = wallSet && s.clicks < 4;
  const needObject = s.tracker.mode === "object";
  const objectDone = s.tracker.ready;

  const corners = $("step-corners"), object = $("step-object"), sweep = $("step-sweep");
  corners.className = !wallSet ? "" : clicking ? "current" : "done";
  $("corners-state").textContent = !wallSet ? "" : clicking ? `${s.clicks} of 4` : "done";
  $("btn-undo").hidden = !clicking;
  $("btn-undo").disabled = s.clicks === 0;

  object.className = !needObject ? "skip" : (!wallSet || clicking ? "" : (objectDone ? "done" : "current"));
  $("object-state").textContent = objectDone && needObject ? "locked on" : "";
  $("btn-resample").hidden = !needObject;

  const ready = wallSet && !clicking && objectDone;
  sweep.className = ready ? (s.studs.length ? "done" : "current") : "";
  $("sweep-state").textContent = s.studs.length
    ? `${s.studs.length} stud${s.studs.length > 1 ? "s" : ""} found` : "";

  // banner over the video
  const banner = $("setup-banner");
  banner.hidden = !s.setup_step;
  $("video-frame").classList.toggle("clicking", !!s.setup_step);
  if (s.setup_step) {
    if (!wallSet) {
      $("setup-text").textContent = "Enter the distance between the tape crosses in the Setup panel";
      renderCornerMap(-2);
    } else if (clicking) {
      const c = s.corners_in[s.clicks];
      $("setup-text").textContent =
        `Click the ${CORNER_LABELS[s.clicks]} tape cross (${c[0]}, ${c[1]} in)`;
    } else {
      $("setup-text").textContent = "Click the colored object on the stud finder";
    }
    if (wallSet) renderCornerMap(clicking ? s.clicks : -1);
  }
}

function renderCornerMap(active) {
  const pts = [[6, 6], [58, 6], [58, 34], [6, 34]];
  let svg = `<rect x="6" y="6" width="52" height="28" fill="none" stroke="#26282b" stroke-width="1.5" stroke-dasharray="3 2"/>`;
  if (active === -2) {          // size not entered: dimension arrows
    svg += `<path d="M10 20 H54 M10 17 V23 M54 17 V23" stroke="#26282b" stroke-width="1.5" fill="none"/>`;
  } else if (active < 0) {
    svg += `<rect x="26" y="15" width="12" height="10" rx="2" fill="#26282b"/>`;
  } else {
    pts.forEach(([x, y], i) => {
      const done = i < active, cur = i === active;
      svg += `<circle cx="${x}" cy="${y}" r="${cur ? 5.5 : 3.5}" fill="${done || cur ? "#26282b" : "#f2c524"}" stroke="#26282b" stroke-width="1.5"/>`;
    });
  }
  $("corner-map").innerHTML = svg;
}

function renderFinder(s) {
  const x = s.tracker.x;
  const el = $("finder-x");
  el.textContent = fmt(x, 2);
  el.parentElement.classList.toggle("lost", x === null);
  let sub = "from the left edge";
  if (s.setup_step) sub = "finish setup first";
  else if (x === null) sub = `${s.tracker.name} not in view`;
  else if (s.open_x !== null) sub = `stud started at ${fmt(s.open_x)} in, keep going`;
  $("finder-sub").textContent = sub;

  const sig = $("btn-signal");
  sig.disabled = s.signal.source !== "fake";
  sig.firstChild.textContent = s.signal.on ? "End stud " : "Stud signal ";
}

function renderStuds(s) {
  const list = $("stud-list");
  if (!s.studs.length) {
    list.innerHTML = `<li class="empty">No studs yet. Sweep the stud finder across the wall${
      s.signal.source === "fake" ? ", pressing Space at each edge of a stud" : ""}.</li>`;
    return;
  }
  list.innerHTML = s.studs.map((st, i) => {
    const gap = i > 0 ? `<span class="gap">${fmt(st.center - s.studs[i - 1].center)} in apart</span>` : "<span></span>";
    const aimed = s.laser.aim_index === i ? ' class="aimed"' : "";
    const aim = `<button class="aim-btn" data-i="${i}" ${s.laser.calibrated && !s.laser.calibrating ? "" : "disabled"}
      title="Point the laser at stud ${i + 1}">Aim</button>`;
    return `<li${aimed}><span>Stud ${i + 1}</span><strong>${fmt(st.center)} in</strong>${gap}${aim}</li>`;
  }).join("");
}

// "Aim" buttons in the stud list (the list is redrawn often, so listen on it).
$("stud-list").addEventListener("click", (e) => {
  const b = e.target.closest(".aim-btn");
  if (b && !b.disabled) command("aim", Number(b.dataset.i));
});

function renderLaser(s) {
  const L = s.laser;
  $("laser-x").textContent = fmt(L.x, 2);
  $("laser-x").parentElement.classList.toggle("lost", L.x === null);
  $("laser-status").textContent = L.x === null && !L.calibrating
    ? `Laser line not in view. ${L.status}` : L.status;
  $("aim-status").textContent = L.aim_status || "";
  const btn = $("btn-laser");
  btn.classList.toggle("is-on", L.on);
  btn.firstChild.textContent = L.on ? "Laser off " : "Laser on ";
  document.querySelector('[data-cmd="next_stud"]').disabled =
    !L.calibrated || !s.studs.length || L.calibrating;
  document.querySelector('[data-cmd="laser_calibrate"]').disabled =
    !!s.setup_step || L.calibrating;
}

function renderViews(s) {
  const box = $("views");
  const key = s.views.join("|");
  if (box.dataset.key !== key) {
    box.dataset.key = key;
    box.innerHTML = s.views.map((v) =>
      `<button data-view="${v}">${VIEW_LABELS[v] || v}</button>`).join("");
    box.querySelectorAll("button").forEach((b) =>
      b.addEventListener("click", () => command("view", b.dataset.view)));
  }
  box.querySelectorAll("button").forEach((b) =>
    b.setAttribute("aria-pressed", String(b.dataset.view === s.view)));
}

function renderLog(s) {
  const key = s.messages.length ? s.messages[s.messages.length - 1].t + s.messages.length : 0;
  const log = $("log");
  if (log.dataset.key === String(key)) return;
  log.dataset.key = String(key);
  log.innerHTML = s.messages.slice().reverse().map((m) => {
    const t = new Date(m.t * 1000).toLocaleTimeString([], { hour12: false });
    return `<li><time>${t}</time><span>${escapeHtml(m.text)}</span></li>`;
  }).join("") || "<li>Nothing yet.</li>";
}

function escapeHtml(t) {
  return t.replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
}

// ------------------------------------------------------------- wall x-ray --
// A straight-on drawing of the wall: tape-measure ruler on top, studs as real
// 1.5 in wide 2x4s, chalk-blue spacing below, dashed outlines for likely studs.
const C = {
  graphite: "#26282b", pencil: "#62666b", drywall: "#efefec", rule: "#c9cbc6",
  lumber: "#d9b582", lumberEdge: "#a47d47", grain: "#c29a62",
  chalk: "#2c64c9", laser: "#e3261f", tape: "#f2c524",
};
const STUD_W = 1.5;

function predictedStuds(studs, x0, x1) {
  if (studs.length < 2) return [];
  const c = studs.map((s) => s.center);
  const gaps = c.slice(1).map((v, i) => v - c[i]).sort((a, b) => a - b);
  const sp = gaps[Math.floor(gaps.length / 2)];
  if (sp < 6) return [];
  const out = [];
  for (let x = c[0] - sp; x >= x0 + STUD_W / 2; x -= sp) out.push(x);
  for (let x = c[c.length - 1] + sp; x <= x1 - STUD_W / 2; x += sp) out.push(x);
  return out;
}

function renderXray(s) {
  const host = $("xray");
  const W = Math.max(host.clientWidth, 320);
  const { x0, x1, y0, y1 } = s.wall;
  const pad = 26;
  const k = (W - pad * 2) / (x1 - x0);               // pixels per inch
  const X = (v) => pad + (v - x0) * k;
  const tapeH = 30, gap = 10;
  const wallTop = tapeH + gap + 14;
  const wallH = Math.max(120, Math.min(240, (y1 - y0) * k * 0.6));
  const wallBot = wallTop + wallH;
  const H = wallBot + 62;
  const ready = !s.setup_step;
  const L = s.laser;
  let g = "";

  // tape measure
  g += `<rect x="${X(x0) - 6}" y="0" width="${(x1 - x0) * k + 12}" height="${tapeH}" rx="3" fill="${C.tape}" stroke="${C.graphite}" stroke-width="1.5"/>`;
  const labelEvery = k >= 22 ? 1 : k >= 11 ? 2 : k >= 6 ? 4 : 8;
  const minor = k >= 16 ? 0.25 : k >= 8 ? 0.5 : 1;
  for (let v = Math.ceil(x0 / minor) * minor; v <= x1 + 1e-6; v += minor) {
    const whole = Math.abs(v - Math.round(v)) < 1e-6;
    const half = Math.abs(v * 2 - Math.round(v * 2)) < 1e-6;
    const len = whole ? 12 : half ? 8 : 5;
    g += `<line x1="${X(v)}" x2="${X(v)}" y1="0" y2="${len}" stroke="${C.graphite}" stroke-width="${whole ? 1.3 : 0.8}"/>`;
    const n = Math.round(v);
    if (whole && n % labelEvery === 0 && n !== x0) {
      if (n % 16 === 0) {   // real tape measures flag every 16 in (stud spacing) in red
        g += `<rect x="${X(n) - 11}" y="13" width="22" height="14" rx="2" fill="${C.laser}"/>`;
        g += `<text x="${X(n)}" y="24.5" text-anchor="middle" font-size="11" font-weight="700" fill="#fff">${n}</text>`;
      } else {
        g += `<text x="${X(n)}" y="25" text-anchor="middle" font-size="11" font-weight="600" fill="${C.graphite}">${n}</text>`;
      }
    }
  }

  // finder position marker (under the tape)
  if (ready && s.tracker.x !== null) {
    const fx = X(s.tracker.x);
    g += `<path d="M${fx - 7},${tapeH + 3} L${fx + 7},${tapeH + 3} L${fx},${tapeH + 13} Z" fill="${C.graphite}"/>`;
  }

  // drywall
  g += `<rect x="${X(x0)}" y="${wallTop}" width="${(x1 - x0) * k}" height="${wallH}" fill="${C.drywall}" stroke="${C.graphite}" stroke-width="1.5"/>`;
  g += `<clipPath id="wallclip"><rect x="${X(x0)}" y="${wallTop}" width="${(x1 - x0) * k}" height="${wallH}"/></clipPath>`;
  let inner = "";      // under the studs
  let over = "";       // on top of the studs (laser, finder)

  // stud in progress
  if (s.open_x !== null && s.tracker.x !== null) {
    const a = Math.min(s.open_x, s.tracker.x), b = Math.max(s.open_x, s.tracker.x);
    inner += `<rect x="${X(a)}" y="${wallTop}" width="${Math.max((b - a) * k, 2)}" height="${wallH}" fill="${C.chalk}" opacity="0.16"/>`;
    inner += `<line x1="${X(s.open_x)}" x2="${X(s.open_x)}" y1="${wallTop}" y2="${wallBot}" stroke="${C.chalk}" stroke-width="1.5" stroke-dasharray="4 3"/>`;
  }

  // likely studs
  predictedStuds(s.studs, x0, x1).forEach((c) => {
    inner += `<rect x="${X(c - STUD_W / 2)}" y="${wallTop + 1}" width="${STUD_W * k}" height="${wallH - 2}" fill="none" stroke="${C.lumberEdge}" stroke-width="1.5" stroke-dasharray="6 4"/>`;
    g += `<text x="${X(c)}" y="${wallBot + 17}" text-anchor="middle" font-size="11.5" fill="${C.pencil}">likely ${fmt(c)}</text>`;
  });

  // studs
  let studsSvg = "";
  s.studs.forEach((st, i) => {
    const aimed = L.aim_index === i;
    const sx = X(st.center - STUD_W / 2), sw = STUD_W * k;
    let body = "";
    body += `<rect x="${X(st.left)}" y="${wallTop}" width="${Math.max((st.right - st.left) * k, 1)}" height="${wallH}" fill="${C.lumber}" opacity="0.28"/>`;
    body += `<rect class="stud-body" x="${sx}" y="${wallTop}" width="${sw}" height="${wallH}" fill="${C.lumber}" stroke="${aimed ? C.laser : C.lumberEdge}" stroke-width="${aimed ? 3 : 1.5}"/>`;
    // wood grain
    [0.33, 0.62].forEach((f, j) => {
      const gx = sx + sw * f;
      const w = Math.min(sw * 0.12, 3);
      body += `<path d="M${gx},${wallTop + 4} C${gx + w},${wallTop + wallH * 0.35} ${gx - w},${wallTop + wallH * (0.6 + j * 0.1)} ${gx},${wallBot - 4}" fill="none" stroke="${C.grain}" stroke-width="1"/>`;
    });
    studsSvg += `<g class="stud-hit" data-i="${i}" tabindex="0" role="button" aria-label="Stud ${i + 1} at ${fmt(st.center)} inches. Point the laser here.">${body}` +
      `<rect x="${sx - 6}" y="${wallTop}" width="${sw + 12}" height="${wallH + 40}" fill="transparent"/></g>`;
    g += `<text x="${X(st.center)}" y="${wallBot + 17}" text-anchor="middle" font-size="12.5" font-weight="700" fill="${aimed ? C.laser : C.graphite}">${fmt(st.center)} in</text>`;
    g += `<text x="${X(st.center)}" y="${wallBot + 31}" text-anchor="middle" font-size="11" fill="${C.pencil}">Stud ${i + 1}</text>`;
  });

  // spacing between neighbours (center to center), chalk blue
  const dimY = wallBot + 50;
  for (let i = 1; i < s.studs.length; i++) {
    const a = X(s.studs[i - 1].center), b = X(s.studs[i].center);
    if (b - a < 40) continue;
    const mid = (a + b) / 2;
    const label = `${fmt(s.studs[i].center - s.studs[i - 1].center)} in`;
    const tw = label.length * 6.6 + 10;
    g += `<line x1="${a}" x2="${b}" y1="${dimY}" y2="${dimY}" stroke="${C.chalk}" stroke-width="1.5"/>`;
    g += `<line x1="${a}" x2="${a}" y1="${dimY - 5}" y2="${dimY + 5}" stroke="${C.chalk}" stroke-width="1.5"/>`;
    g += `<line x1="${b}" x2="${b}" y1="${dimY - 5}" y2="${dimY + 5}" stroke="${C.chalk}" stroke-width="1.5"/>`;
    g += `<rect x="${mid - tw / 2}" y="${dimY - 8}" width="${tw}" height="16" fill="${getComputedStyle(document.body).backgroundColor}"/>`;
    g += `<text x="${mid}" y="${dimY + 4}" text-anchor="middle" font-size="12" font-weight="600" fill="${C.chalk}">${label}</text>`;
  }

  // laser line
  if (ready && L.x !== null) {
    const lx = X(L.x);
    over += `<line x1="${lx}" x2="${lx}" y1="${wallTop}" y2="${wallBot}" stroke="${C.laser}" stroke-width="7" opacity="0.25"/>`;
    over += `<line x1="${lx}" x2="${lx}" y1="${wallTop}" y2="${wallBot}" stroke="${C.laser}" stroke-width="2"/>`;
  }

  // finder guide line
  if (ready && s.tracker.x !== null) {
    const fx = X(s.tracker.x);
    over += `<line x1="${fx}" x2="${fx}" y1="${wallTop}" y2="${wallBot}" stroke="${C.graphite}" stroke-width="1" stroke-dasharray="2 4" opacity="0.6"/>`;
  }

  g += `<g clip-path="url(#wallclip)">${inner}</g>${studsSvg}` +
       `<g clip-path="url(#wallclip)" pointer-events="none">${over}</g>`;

  if (!s.studs.length) {
    const msg = s.setup_step ? "Finish setup to start mapping." : "No studs yet. Sweep the stud finder across the wall.";
    g += `<text x="${W / 2}" y="${wallTop + wallH / 2 + 5}" text-anchor="middle" font-size="14" fill="${C.pencil}">${msg}</text>`;
  }

  host.innerHTML = `<svg viewBox="0 0 ${W} ${H}" width="${W}" height="${H}" role="img" aria-label="Wall diagram with ${s.studs.length} studs">${g}</svg>`;

  $("xray-hint").textContent = !s.studs.length ? ""
    : L.calibrated ? "Click a stud to point the laser at it."
    : "Calibrate the laser to point it at a stud.";
}

// Stud clicks (the SVG is redrawn often, so listen on the container).
function aimFromEvent(e) {
  const g = e.target.closest(".stud-hit");
  if (g && state && state.laser.calibrated) command("aim", Number(g.dataset.i));
}
$("xray").addEventListener("click", aimFromEvent);
$("xray").addEventListener("keydown", (e) => {
  if (e.key === "Enter") { e.stopPropagation(); aimFromEvent(e); }
});
window.addEventListener("resize", () => state && renderXray(state));
