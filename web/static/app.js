// Flight recorder web UI — live data from the Pi (no sample data).
"use strict";

const MONTHS = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
const level    = t => t === 0 ? 0 : t <= 2 ? 1 : t <= 5 ? 2 : t <= 10 ? 3 : 4;
const levelOps = o => o === 0 ? 0 : o <= 20 ? 1 : o <= 50 ? 2 : o <= 100 ? 3 : 4;

let mode = "tasks";          // 'tasks' | 'ops'
let selectedDate = null;
const dayMap = new Map();    // "YYYY-MM-DD" -> {task_count, op_count, top_tasks}

const $ = id => document.getElementById(id);
const esc = s => String(s == null ? "" : s)
  .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
  .replace(/"/g, "&quot;");
const fmtDate = d => d.toLocaleDateString("en-US",
  {weekday:"short", month:"short", day:"numeric", year:"numeric"});
const iso = d => d.getFullYear() + "-" +
  String(d.getMonth() + 1).padStart(2, "0") + "-" +
  String(d.getDate()).padStart(2, "0");

function opLine(op) {
  const cmd = esc(op.command || "?") + (op.detail ? ": " + esc(op.detail) : "");
  const meta = esc(op.status || "") +
    (op.duration_ms != null ? " \u00B7 " + op.duration_ms + "ms" : "");
  return `<li><span class="op-line">${cmd}</span><br/><span class="op-meta">${meta}</span></li>`;
}

function taskBlock(t) {
  const n = t.op_count != null ? t.op_count : (t.ops ? t.ops.length : 0);
  let h = `<details><summary>${esc(t.title)}<span class="n">${n} operations</span></summary>`;
  if (t.what_why) h += `<p class="desc"><b>What / why:</b> ${esc(t.what_why)}</p>`;
  if (t.outcome)  h += `<p class="outcome"><b>Outcome:</b> ${esc(t.outcome)}</p>`;
  h += `<ul class="cmds">${(t.ops || []).map(opLine).join("")}</ul></details>`;
  return h;
}

// ---------- heatmap ----------
// Size day cells so the year grid exactly fills the available width.
// Returns the column pitch in px. Below a 10px minimum cell size the grid
// keeps scrolling instead of shrinking further.
function fitCells(nWeeks) {
  const cm = document.querySelector('.cal-main');
  const wd = document.querySelector('.wdays');
  const avail = cm.clientWidth - (wd ? wd.offsetWidth + 6 : 32);
  let cell = (avail - 3 * (nWeeks - 1)) / nWeeks;
  if (cell < 10) cell = 10;
  cm.closest('.card').style.setProperty('--cell', cell + 'px');
  return cell + 3;
}

function buildGrid() {
  const weeksEl = $("weeks"), monthsEl = $("months");
  weeksEl.innerHTML = ""; monthsEl.innerHTML = "";
  const today = new Date(); today.setHours(0, 0, 0, 0);
  const NDAYS = 364;
  const days = [];
  for (let i = NDAYS - 1; i >= 0; i--) {
    const d = new Date(today); d.setDate(d.getDate() - i);
    days.push(d);
  }
  const lead = days[0].getDay();
  const cells = [];
  for (let i = 0; i < lead; i++) cells.push(null);
  days.forEach(d => cells.push(d));
  while (cells.length % 7 !== 0) cells.push(null);
  const nWeeks = cells.length / 7;
  const pitch = fitCells(nWeeks);

  cells.forEach(d => {
    const el = document.createElement("div");
    if (d === null) { el.className = "day empty"; }
    else {
      const key = iso(d);
      el.className = "day"; el.dataset.date = key;
      el.addEventListener("mouseenter", ev => showTip(ev, d));
      el.addEventListener("mousemove", moveTip);
      el.addEventListener("mouseleave", () => { $("tip").hidden = true; });
      el.addEventListener("click", () => selectDay(key, el));
    }
    weeksEl.appendChild(el);
  });

  let lastLabel = -10;
  for (let w = 0; w < nWeeks; w++) {
    for (let r = 0; r < 7; r++) {
      const d = cells[w * 7 + r];
      if (d && d.getDate() === 1 && w - lastLabel > 3) {
        const s = document.createElement("span");
        s.textContent = MONTHS[d.getMonth()];
        s.style.left = (w * pitch) + "px";
        monthsEl.appendChild(s); lastLabel = w; break;
      }
    }
  }
  // On narrow screens the grid scrolls horizontally: default to the newest days.
  const cm = document.querySelector(".cal-main");
  if (cm) cm.scrollLeft = cm.scrollWidth;
  paint();
}

function paint() {
  document.querySelectorAll('.day[data-date]').forEach(el => {
    const a = dayMap.get(el.dataset.date);
    const t = a ? a.task_count : 0, o = a ? a.op_count : 0;
    // Ops are a finer-grained count of the same activity, so the ops view is
    // floored at the task color: toggling to ops can hold or darken, never lighten.
    const lv = mode === "tasks" ? level(t) : Math.max(levelOps(o), level(t));
    el.className = "day l" + lv + (el.dataset.date === selectedDate ? " selected" : "");
  });
}

function showTip(ev, d) {
  const key = iso(d), a = dayMap.get(key);
  const tc = a ? a.task_count : 0, oc = a ? a.op_count : 0;
  let h = `<b>${fmtDate(d)}</b><br/>${tc} tasks \u00B7 ${oc} operations`;
  if (a && a.top_tasks && a.top_tasks.length && mode === "tasks") {
    h += "<ul>" + a.top_tasks.map(t => `<li>${esc(t)}</li>`).join("") + "</ul>";
  }
  const tip = $("tip");
  tip.innerHTML = h; tip.hidden = false; moveTip(ev);
}
function moveTip(ev) {
  const tip = $("tip");
  tip.style.left = Math.min(ev.clientX + 14, window.innerWidth - 280) + "px";
  tip.style.top  = Math.min(ev.clientY + 14, window.innerHeight - 140) + "px";
}

function buildYears(activity) {
  const yearsEl = $("years"); yearsEl.innerHTML = "";
  const years = [...new Set(activity.map(a => (a.date || "").slice(0, 4)).filter(Boolean))].sort().reverse();
  const cur = String(new Date().getFullYear());
  if (!years.includes(cur)) years.unshift(cur);
  years.forEach((y, i) => {
    const b = document.createElement("button");
    b.textContent = y;
    if (i === 0) b.classList.add("active"); else b.disabled = true;
    yearsEl.appendChild(b);
  });
}

// ---------- day report ----------
function closeReport() {
  selectedDate = null;
  document.querySelectorAll(".day.selected").forEach(x => x.classList.remove("selected"));
  $("report").hidden = true;
}

async function selectDay(key, el) {
  if (key === selectedDate) { closeReport(); return; }
  selectedDate = key;
  document.querySelectorAll(".day.selected").forEach(x => x.classList.remove("selected"));
  el.classList.add("selected");
  const d = await fetch("/api/day/" + key).then(r => r.json());
  $("report-title").textContent = fmtDate(new Date(key + "T12:00:00"));
  $("report-meta").textContent =
    `${d.task_count} high-level tasks \u00B7 ${d.op_count} operations (system.run / file.read / file.write)`;
  $("report-body").innerHTML = d.tasks.length
    ? d.tasks.map(taskBlock).join("")
    : '<div class="empty-day">No recorded activity on this day.</div>';
  $("report").hidden = false;
  $("report").scrollIntoView({behavior: "smooth", block: "nearest"});
}

// ---------- recent ----------
function buildRecent(recent) {
  $("recent").innerHTML = recent.length ? recent.map(r =>
    `<li><details><summary><span class="t">${esc(r.title)}</span>` +
    `<span class="d">${esc(r.date)}</span>` +
    `<span class="c">${r.op_count != null ? r.op_count : (r.ops || []).length} ops</span>` +
    `</summary>` +
    (r.what_why ? `<p class="desc"><b>What / why:</b> ${esc(r.what_why)}</p>` : "") +
    (r.outcome ? `<p class="outcome"><b>Outcome:</b> ${esc(r.outcome)}</p>` : "") +
    `<ul class="cmds">${(r.ops || []).map(opLine).join("")}</ul></details></li>`
  ).join("") : '<li class="loading">No activity recorded yet.</li>';
}

// ---------- init ----------
$("btn-tasks").addEventListener("click", e => {
  mode = "tasks"; e.target.classList.add("active");
  $("btn-ops").classList.remove("active"); paint();
});
$("btn-ops").addEventListener("click", e => {
  mode = "ops"; e.target.classList.add("active");
  $("btn-tasks").classList.remove("active"); paint();
});
$("report-close").addEventListener("click", closeReport);

(async function init() {
  try {
    const [meta, activity, recent] = await Promise.all([
      fetch("/api/meta").then(r => r.json()),
      fetch("/api/activity?days=400").then(r => r.json()),
      fetch("/api/recent").then(r => r.json()),
    ]);
    $("hostname").textContent = meta.hostname || "unknown";
    activity.forEach(a => { if (a.date) dayMap.set(a.date, a); });
    buildYears(activity);
    buildGrid();
    buildRecent(recent);
  } catch (e) {
    $("recent").innerHTML = '<li class="err">Could not reach the recorder API.</li>';
  }
})();

let _rzT = null;
window.addEventListener("resize", () => {
  clearTimeout(_rzT);
  _rzT = setTimeout(() => { buildGrid(); }, 150);
});
