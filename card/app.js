// Signer Card: consent Start/Stop, ON light, latest translation with feedback + readout, replies (+ typed fallback),
// history, Teach a sign, D3 state banners, privacy + share link (CONTRACTS §2, §4, §12).
// Served by the core at GET /; ?core=http://host:8000 points it at another core.
import { qrSvg } from "./qr.js";

const base = new URLSearchParams(location.search).get("core") || location.origin;
const wsUrl = base.replace(/^http/, "ws") + "/ws/events";
const $ = (id) => document.getElementById(id);

const CHIP = {
  off: "Translation OFF", connecting: "Connecting…", on: "ON", paused: "Paused", glasses_off: "Glasses off",
  permission_denied: "Permission denied", core_down: "Core down",
};
const CONF = { confirmed: "sure", unsure: "not sure", none: "Please sign again" };
const CONF_ICON = { confirmed: "i-check", unsure: "i-help", none: "i-x" };
// D3 states: icon + plain-language next step. Shown as a banner; never colour alone.
const BANNER = {
  permission_denied: {
    level: "alert", icon: "i-lock", title: "Camera permission denied",
    next: "The glasses app is not allowed to use the camera. Open the Meta AI app on the phone, allow camera access for Signer, then press Start translating again.",
  },
  glasses_off: {
    level: "warn", icon: "i-glasses", title: "Glasses are off or not connected",
    next: "Put the glasses on and check they are connected to the phone. If translation does not come back, press Start translating again.",
  },
  core_down: {
    level: "alert", icon: "i-wifi-off", title: "Lost connection to the translator",
    next: "Reconnecting automatically. Check the laptop is on and on the same Wi-Fi. Nothing is translated until it is back.",
  },
};

let serverState = "off"; // last `state` event / /session answer
let coreDown = false; // the card's own view of the /ws/events socket (CONTRACTS §4: core_down is client-made)
let link = "ok";
let stats = { confirmed: 0, total: 0 };
const captions = []; // newest first: {ev, verdict, retracted}
const replies = [];
let teachActive = null; // {gloss, reps_needed}
let taught = [];
let teachAvailable = true;

const esc = (t) => String(t).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
const time = (ms) => new Date(ms || Date.now()).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
const icon = (id, size = 22) => `<svg class="ico" aria-hidden="true" viewBox="0 0 24 24" width="${size}" height="${size}"><use href="#${id}"/></svg>`;
const announce = (t) => { const a = $("announce"); a.textContent = ""; setTimeout(() => (a.textContent = t), 50); };
let appFault = null; // "glasses_off" | "permission_denied" from the iOS app (state with from:"app"), never the session
const effective = () => (coreDown ? "core_down" : appFault || serverState);

// Re-render a region without dropping keyboard focus on the control the user just pressed.
function keepFocus(render) {
  const a = document.activeElement;
  const key = a && a.dataset && (a.dataset.verdict || a.dataset.teachDelete) ? { ...a.dataset } : null;
  render();
  if (!key) return;
  const sel = key.verdict ? `button[data-id="${CSS.escape(key.id)}"][data-verdict="${key.verdict}"]` : `button[data-teach-delete="${CSS.escape(key.teachDelete)}"]`;
  document.querySelector(sel)?.focus();
}

function renderState() {
  const st = effective();
  const on = !coreDown && (serverState === "on" || serverState === "paused");
  $("start").hidden = on;
  $("stop").hidden = !on;
  const live = serverState === "on" && !coreDown;
  $("light").classList.toggle("on", live);
  $("light-text").textContent = live ? "Translation ON — camera in use, nothing recorded" : "Translation OFF";
  const chip = $("chip");
  const alert = st === "core_down" || st === "permission_denied";
  const warn = st === "glasses_off";
  chip.className = "chip" + (live ? " on" : "") + (alert ? " alert" : "") + (warn ? " warn" : "");
  $("chip-text").textContent = (CHIP[st] || st) + (link === "slow" && !coreDown ? " · Link slow" : "");

  const b = BANNER[st];
  const banner = $("banner");
  banner.hidden = !b;
  if (b) {
    banner.className = "banner " + b.level;
    banner.dataset.state = st;
    $("banner-icon-use").setAttribute("href", "#" + b.icon);
    $("banner-title").textContent = b.title;
    $("banner-next").textContent = b.next;
  } else {
    delete banner.dataset.state;
  }
}

function captionHtml(c, withButtons) {
  const ev = c.ev;
  const unsure = ev.tier === "unsure";
  const alts = unsure && ev.alternatives?.length
    ? `<p class="alts">${icon("i-help", 20)}<span>Or: ${ev.alternatives.slice(0, 2).map((a) => esc(a.text)).join(" · ")}</span></p>` : "";
  const gloss = ev.gloss?.length ? `<p class="gloss">${esc(ev.gloss.join(" "))}</p>` : "";
  const pressed = (v) => `aria-pressed="${c.verdict === v}"`;
  const id = esc(ev.id);
  const buttons = withButtons && ev.tier !== "none" && !c.retracted
    ? `<div class="fb">
        <button class="right" data-id="${id}" data-verdict="right" ${pressed("right")}>${icon("i-check")}Right</button>
        <button class="wrong" data-id="${id}" data-verdict="wrong" ${pressed("wrong")}>${icon("i-x")}Wrong</button>
        <button class="veto" data-id="${id}" data-verdict="veto" ${pressed("veto")}>${icon("i-octagon-x")}Not right, remove it</button>
      </div>` : "";
  const note = c.retracted ? `<p class="removed">${icon("i-octagon-x", 20)}Removed from the glasses.</p>` : "";
  const audio = ev.audio_url && !c.retracted
    ? `<button class="btn-sm btn-outline play" type="button" data-audio="${esc(ev.audio_url)}">${icon("i-volume")}Play voice</button>` : "";
  const text = unsure ? `? ${ev.text}` : ev.text;
  return `${gloss}<p class="sentence">${esc(text)}</p>
    <p class="meta"><span class="conf ${esc(ev.tier)}">${icon(CONF_ICON[ev.tier] || "i-help", 20)}${esc(CONF[ev.tier] || ev.tier)}</span> <span class="time">${time(ev.ts)}</span></p>
    ${alts}${note}${audio}${buttons}`;
}

function renderCaptions() {
  keepFocus(() => {
    const latest = captions[0];
    $("latest").innerHTML = latest ? captionHtml(latest, true) : '<p class="empty">Nothing yet. Press Start and sign.</p>';
    $("latest").classList.toggle("retracted", !!latest?.retracted);
    $("history").innerHTML = captions.length > 1 // the latest is shown above
      ? captions.slice(1, 31).map((c) => `<li class="${c.retracted ? "retracted" : ""} t-${esc(c.ev.tier)}">${captionHtml(c, true)}</li>`).join("")
      : '<li class="empty">Your translations will appear here.</li>';
  });
}

function renderReadout() {
  const el = $("readout");
  const none = !stats.total;
  el.dataset.empty = String(none);
  $("readout-text").innerHTML = none
    ? "No feedback yet. Tap Right or Wrong on a translation."
    : `<strong>${stats.confirmed} of ${stats.total}</strong> confirmed right`;
}

function renderReplies() {
  $("replies").innerHTML = replies.length
    ? replies.slice(0, 10).map((r, i) => `<li class="${i === 0 ? "latest-reply" : ""}">
        <p class="reply-text">${esc(r.text)}</p>
        <p class="time">${r.source === "typed" ? "Typed" : "Heard"} · ${time(r.ts)}</p></li>`).join("")
    : '<li class="empty">No replies yet.</li>';
}

function renderTeach() {
  const prog = $("teach-progress");
  if (teachActive) {
    const mine = taught.find((t) => t.gloss === teachActive.gloss);
    const reps = Math.min(mine?.reps ?? 0, teachActive.reps_needed);
    const done = reps >= teachActive.reps_needed;
    const pips = Array.from({ length: teachActive.reps_needed }, (_, i) => `<span class="pip${i < reps ? " done" : ""}"></span>`).join("");
    prog.hidden = false;
    prog.className = "progress" + (done ? " finished" : "");
    prog.innerHTML = done
      ? `<p class="progress-title">${icon("i-circle-check")}<span>${esc(teachActive.gloss)} learned. Signer will use it from now on.</span></p>`
      : `<p class="progress-title">${icon("i-loader")}<span>Sign <strong>${esc(teachActive.gloss)}</strong> ${teachActive.reps_needed} times, with a pause between each.</span></p>
         <div class="pips" aria-hidden="true">${pips}</div>
         <p class="progress-count">${reps} of ${teachActive.reps_needed} signed</p>`;
  } else {
    prog.hidden = true;
  }
  $("teach-list").innerHTML = !teachAvailable
    ? '<li class="empty">Teaching is not turned on in this core.</li>'
    : taught.length
      ? taught.map((t) => `<li class="taught"><div><p class="taught-gloss">${esc(t.gloss)}</p><p class="time">means "${esc(t.english)}" · ${t.reps} reps</p></div>
          <button class="btn-sm btn-danger" type="button" data-teach-delete="${esc(t.gloss)}" aria-label="Delete ${esc(t.gloss)}">${icon("i-trash")}Delete</button></li>`).join("")
      : '<li class="empty">No signs taught yet.</li>';
}

function onEvent(ev) {
  switch (ev.type) {
    case "state":
      if (ev.from === "app") {
        appFault = ev.state === "glasses_off" || ev.state === "permission_denied" ? ev.state : null;
        renderState();
        break;
      }
      serverState = ev.state === "core_down" ? serverState : ev.state;
      link = ev.link || "ok";
      if (serverState !== "on") $("partial").textContent = "";
      renderState();
      break;
    case "partial":
      $("partial").textContent = `Seeing: ${ev.gloss}…`;
      break;
    case "caption":
      $("partial").textContent = "";
      captions.unshift({ ev, verdict: null, retracted: false });
      renderCaptions();
      announce(`${ev.tier === "unsure" ? "Not sure: " : ""}${ev.text}`);
      if (teachActive) refreshTeach();
      break;
    case "retract": {
      const c = captions.find((x) => x.ev.id === ev.id);
      if (c) c.retracted = true;
      renderCaptions();
      break;
    }
    case "reply":
      replies.unshift(ev);
      renderReplies();
      announce(`They said: ${ev.text}`);
      break;
    case "stats":
      stats = { confirmed: ev.confirmed, total: ev.total };
      renderReadout();
      break;
  }
}

async function call(method, path, body) {
  const r = await fetch(base + path, {
    method,
    headers: body ? { "Content-Type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!r.ok) {
    const e = new Error(`${path} ${r.status}`);
    e.status = r.status;
    throw e;
  }
  return r.json();
}
const post = (path, body) => call("POST", path, body);

async function consent(path) {
  const btns = [$("start"), $("stop")];
  btns.forEach((b) => (b.disabled = true));
  try {
    const s = await post(path, { by: "card" });
    serverState = s.state;
    renderState();
  } catch {
    coreDown = true;
    renderState();
  } finally {
    btns.forEach((b) => (b.disabled = false));
    (serverState === "on" ? $("stop") : $("start")).focus();
  }
}

$("start").addEventListener("click", () => consent("/session/start"));
$("stop").addEventListener("click", () => consent("/session/stop"));

document.addEventListener("click", async (e) => {
  const fb = e.target.closest("button[data-verdict]");
  if (fb) {
    const c = captions.find((x) => x.ev.id === fb.dataset.id);
    const verdict = fb.dataset.verdict;
    if (c) c.verdict = verdict;
    renderCaptions();
    try {
      const r = await post("/feedback", { caption_id: fb.dataset.id, verdict });
      if (r && typeof r.total === "number") { stats = { confirmed: r.confirmed, total: r.total }; renderReadout(); }
    } catch {
      /* the stats event will not arrive; the banner shows core_down if the socket is gone */
    }
    return;
  }
  const del = e.target.closest("button[data-teach-delete]");
  if (del) {
    const gloss = del.dataset.teachDelete;
    del.disabled = true;
    try {
      await call("DELETE", `/teach/${encodeURIComponent(gloss)}`);
      if (teachActive?.gloss === gloss) teachActive = null;
      $("teach-msg").textContent = `${gloss} deleted.`;
    } catch {
      $("teach-msg").textContent = `Could not delete ${gloss}. Try again.`;
    }
    await refreshTeach();
    return;
  }
  const play = e.target.closest("button[data-audio]");
  if (play) new Audio(base + play.dataset.audio).play().catch(() => {});
});

// Typed-reply fallback (CONTRACTS §2 POST /reply)
$("reply-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const input = $("reply-text");
  const text = input.value.trim();
  if (!text) { $("reply-msg").textContent = "Type the reply first."; input.focus(); return; }
  try {
    await post("/reply", { text, source: "typed" });
    input.value = "";
    $("reply-msg").textContent = "Shown.";
  } catch {
    $("reply-msg").textContent = "Could not send. Check the connection and try again.";
  }
  input.focus();
});

// Teach a sign (CONTRACTS §2, M3). No progress event exists, so progress is read from GET /teach.
async function refreshTeach() {
  try {
    const r = await call("GET", "/teach");
    taught = r.taught || [];
    teachAvailable = true;
  } catch (err) {
    if (err.status === 404) teachAvailable = false;
  }
  renderTeach();
}

$("teach-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const gloss = $("teach-gloss").value.trim().toUpperCase();
  const english = $("teach-english").value.trim();
  const msg = $("teach-msg");
  if (!gloss || !english) { msg.textContent = "Fill in both the sign name and the English words."; return; }
  try {
    const r = await post("/teach", { gloss, english });
    teachActive = { gloss, reps_needed: r.reps_needed || 5 };
    msg.textContent = "";
    $("teach-gloss").value = "";
    $("teach-english").value = "";
    teachAvailable = true;
  } catch (err) {
    msg.textContent = err.status === 404 ? "Teaching is not turned on in this core." : "Could not start teaching. Check the connection and try again.";
  }
  await refreshTeach();
});
setInterval(() => { if (teachActive && !coreDown) refreshTeach(); }, 2000);

// Share link + QR
function renderShare() {
  const url = location.href.split("#")[0];
  $("url").textContent = url;
  const svg = qrSvg(url);
  $("qr").innerHTML = svg || "";
  $("qr").hidden = !svg;
  $("url-note").hidden = !/^(localhost|127\.|\[::1\])/.test(location.hostname);
  $("copy").addEventListener("click", async () => {
    try { await navigator.clipboard.writeText(url); $("copy-text").textContent = "Copied"; }
    catch { $("copy-text").textContent = "Select the address above"; }
    setTimeout(() => ($("copy-text").textContent = "Copy link"), 2000);
  });
}

// Socket: core_down is made here when the socket has been gone for more than 2 s; reconnects forever.
let downTimer = null;
function markUp() {
  clearTimeout(downTimer);
  downTimer = null;
  if (coreDown) { coreDown = false; renderState(); }
}
async function syncSession() {
  try {
    const s = await call("GET", "/session");
    if (s?.state) { serverState = s.state; renderState(); }
  } catch { /* socket close handling shows core_down */ }
}
function connect() {
  let ws;
  try { ws = new WebSocket(wsUrl); } catch { setTimeout(connect, 1000); return; }
  ws.onopen = () => {
    markUp();
    ws.send(JSON.stringify({ type: "hello", client: "card" }));
    syncSession();
    refreshTeach();
  };
  ws.onmessage = (m) => {
    try { onEvent(JSON.parse(m.data)); } catch { /* ignore */ }
  };
  ws.onclose = () => {
    // do not restart the timer on each failed retry, or the 2 s would never elapse
    if (!downTimer && !coreDown) downTimer = setTimeout(() => { downTimer = null; coreDown = true; renderState(); }, 2000);
    setTimeout(connect, 1000);
  };
}

renderState();
renderReadout();
renderReplies();
renderTeach();
renderShare();
connect();
