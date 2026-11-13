// Web App mirror of the lens: connect to /ws/events, render, speak confirmed captions, D-pad focus.
import { coreUrl, initial, reduce, speakText, view } from "./lens.js";
import "./lens.css";

const root = document.getElementById("lens");
const url = coreUrl(location.search);
let s = initial();
let ws = null;
let downTimer = null;
let lastPaint = 0;
let paintTimer = null;

function paint() {
  // DESIGN: updates throttled >= 500 ms (matches the DAT card)
  const wait = 500 - (Date.now() - lastPaint);
  if (wait > 0) {
    clearTimeout(paintTimer);
    paintTimer = setTimeout(paint, wait);
    return;
  }
  const focused = document.activeElement && document.activeElement.dataset.focus;
  root.innerHTML = view(s);
  lastPaint = Date.now();
  if (focused) root.querySelector(`[data-focus="${focused}"]`)?.focus();
}

function apply(ev) {
  s = reduce(s, ev);
  const say = speakText(ev);
  if (say && "speechSynthesis" in window) {
    speechSynthesis.cancel();
    speechSynthesis.speak(new SpeechSynthesisUtterance(say));
  }
  paint();
}

function send(msg) {
  if (ws && ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify(msg));
}

function connect() {
  ws = new WebSocket(url);
  ws.onopen = () => {
    clearTimeout(downTimer);
    send({ type: "hello", client: "hud" });
  };
  ws.onmessage = (m) => {
    try {
      apply(JSON.parse(m.data));
    } catch {
      /* ignore non-JSON */
    }
  };
  ws.onclose = () => {
    // core_down is produced by clients when the socket stays down > 2 s (CONTRACTS §4)
    clearTimeout(downTimer);
    downTimer = setTimeout(() => apply({ type: "state", state: "core_down", link: "ok" }), 2000);
    setTimeout(connect, 1000);
  };
}

root.addEventListener("click", (e) => {
  const b = e.target.closest("[data-action=veto]");
  if (b) send({ type: "feedback", caption_id: b.dataset.id, verdict: "veto" });
});

// D-pad: up/down move through state -> caption -> footer actions; Enter activates.
// Chrome --enable-spatial-navigation does this natively; this is the fallback.
document.addEventListener("keydown", (e) => {
  if (e.key !== "ArrowDown" && e.key !== "ArrowUp") return;
  const items = [...root.querySelectorAll("[data-focus]")].filter((el) => el.tabIndex >= 0);
  if (!items.length) return;
  const i = items.indexOf(document.activeElement);
  const n = e.key === "ArrowDown" ? Math.min(i + 1, items.length - 1) : Math.max(i - 1, 0);
  items[i < 0 ? 0 : n].focus();
  e.preventDefault();
});

paint();
connect();
