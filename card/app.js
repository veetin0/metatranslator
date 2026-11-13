// Signer Card: consent Start/Stop, ON light, latest translation with feedback, replies, history (CONTRACTS §2, §4).
// Served by the core at GET /; ?core=http://host:8000 points it at another core.
const base = new URLSearchParams(location.search).get("core") || location.origin;
const wsUrl = base.replace(/^http/, "ws") + "/ws/events";
const $ = (id) => document.getElementById(id);

const CHIP = {
  off: "Translation OFF", connecting: "Connecting…", on: "ON", paused: "Paused", glasses_off: "Glasses off",
  permission_denied: "Permission denied", core_down: "Core down",
};
const CONF = { confirmed: "✓ sure", unsure: "? not sure", none: "Please sign again" };

let session = "off";
let link = "ok";
const captions = []; // newest first: {ev, verdict, retracted}
const replies = [];

const esc = (t) => String(t).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
const time = (ms) => new Date(ms || Date.now()).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });

function renderState() {
  const on = session === "on";
  $("start").hidden = on;
  $("stop").hidden = !on;
  $("light").classList.toggle("on", on);
  $("light-text").textContent = on ? "Translation ON — camera in use, nothing recorded" : "Translation OFF";
  const chip = $("chip");
  chip.className = "chip" + (on ? " on" : "") + (["core_down", "permission_denied"].includes(session) ? " alert" : "");
  $("chip-text").textContent = (CHIP[session] || session) + (link === "slow" ? " · Link slow" : "");
}

function captionHtml(c, withButtons) {
  const ev = c.ev;
  const alts = ev.tier === "unsure" && ev.alternatives?.length
    ? `<p class="alts">Or: ${ev.alternatives.slice(0, 2).map((a) => esc(a.text)).join(" · ")}</p>` : "";
  const gloss = ev.gloss?.length ? `<p class="gloss">${esc(ev.gloss.join(" "))}</p>` : "";
  const pressed = (v) => `aria-pressed="${c.verdict === v}"`;
  const buttons = withButtons && ev.tier !== "none" && !c.retracted
    ? `<div class="fb">
        <button class="right" data-id="${esc(ev.id)}" data-verdict="right" ${pressed("right")}>✓ Right</button>
        <button class="wrong" data-id="${esc(ev.id)}" data-verdict="wrong" ${pressed("wrong")}>✗ Wrong</button>
        <button class="veto" data-id="${esc(ev.id)}" data-verdict="veto" ${pressed("veto")}>Not right — remove</button>
      </div>` : "";
  const note = c.retracted ? `<p class="help">Removed from the glasses.</p>` : "";
  return `${gloss}<p class="sentence">${esc(ev.text)}</p>
    <p><span class="conf ${esc(ev.tier)}">${esc(CONF[ev.tier] || ev.tier)}</span> <span class="time">${time(ev.ts)}</span></p>
    ${alts}${note}${buttons}`;
}

function renderCaptions() {
  const latest = captions[0];
  $("latest").innerHTML = latest ? captionHtml(latest, true) : '<p class="empty">Nothing yet. Press Start and sign.</p>';
  $("latest").classList.toggle("retracted", !!latest?.retracted);
  $("history").innerHTML = captions.length > 1 // the latest is shown above
    ? captions.slice(1, 31).map((c) => `<li class="${c.retracted ? "retracted" : ""}">${captionHtml(c, true)}</li>`).join("")
    : '<li class="empty">Your translations will appear here.</li>';
}

function renderReplies() {
  $("replies").innerHTML = replies.length
    ? replies.slice(0, 10).map((r) => `<li><p class="sentence">${esc(r.text)}</p><p class="time">${time(r.ts)}</p></li>`).join("")
    : '<li class="empty">No replies yet.</li>';
}

function onEvent(ev) {
  switch (ev.type) {
    case "state":
      session = ev.state;
      link = ev.link || "ok";
      if (session !== "on") $("partial").textContent = "";
      renderState();
      break;
    case "partial":
      $("partial").textContent = `Seeing: ${ev.gloss}…`;
      break;
    case "caption":
      $("partial").textContent = "";
      captions.unshift({ ev, verdict: null, retracted: false });
      renderCaptions();
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
      break;
    case "stats":
      $("stats").textContent = `${ev.confirmed}/${ev.total} confirmed`;
      break;
  }
}

async function post(path, body) {
  const r = await fetch(base + path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  if (!r.ok) throw new Error(`${path} ${r.status}`);
  return r.json();
}

async function consent(path) {
  const btns = [$("start"), $("stop")];
  btns.forEach((b) => (b.disabled = true));
  try {
    const s = await post(path, { by: "card" });
    session = s.state;
    renderState();
  } catch {
    session = "core_down";
    renderState();
  } finally {
    btns.forEach((b) => (b.disabled = false));
    (session === "on" ? $("stop") : $("start")).focus();
  }
}

$("start").addEventListener("click", () => consent("/session/start"));
$("stop").addEventListener("click", () => consent("/session/stop"));
document.addEventListener("click", async (e) => {
  const b = e.target.closest("button[data-verdict]");
  if (!b) return;
  const c = captions.find((x) => x.ev.id === b.dataset.id);
  if (c) c.verdict = b.dataset.verdict;
  renderCaptions();
  try {
    await post("/feedback", { caption_id: b.dataset.id, verdict: b.dataset.verdict });
  } catch {
    /* stats event will not arrive; the chip shows core_down if the socket is gone */
  }
});

let downTimer = null;
function connect() {
  const ws = new WebSocket(wsUrl);
  ws.onopen = () => {
    clearTimeout(downTimer);
    ws.send(JSON.stringify({ type: "hello", client: "card" }));
  };
  ws.onmessage = (m) => {
    try { onEvent(JSON.parse(m.data)); } catch { /* ignore */ }
  };
  ws.onclose = () => {
    clearTimeout(downTimer);
    downTimer = setTimeout(() => onEvent({ type: "state", state: "core_down", link: "ok" }), 2000);
    setTimeout(connect, 1000);
  };
}

renderState();
connect();
