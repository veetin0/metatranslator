// Signer live demo: webcam -> relay /ws/frames (JPEG, header pose:true) -> landmarks back for the skeleton,
// recognised signs and captions from /ws/events.
const $ = id => document.getElementById(id);
const POSE = [[11, 12], [11, 13], [13, 15], [12, 14], [14, 16], [11, 23], [12, 24], [23, 24], [9, 10]];
const HAND = [[0, 1], [1, 2], [2, 3], [3, 4], [0, 5], [5, 6], [6, 7], [7, 8], [5, 9], [9, 10], [10, 11], [11, 12],
  [9, 13], [13, 14], [14, 15], [15, 16], [13, 17], [17, 18], [18, 19], [19, 20], [0, 17]];
const JSONH = {method: "POST", headers: {"content-type": "application/json"}, body: JSON.stringify({by: "card"})};
let ws, ev, timer, stream, seq = 0, pose = null, poseAt = 0, frames = 0, fpsAt = performance.now();
const grab = document.createElement("canvas");
const sk = $("sk"), ctx = sk.getContext("2d");

function status(text, kind) { $("status").className = "pill " + kind; $("status-text").textContent = text; }

fetch("/vocab").then(r => r.json()).then(d => {
  for (const s of d.signs || []) {
    const g = typeof s === "string" ? s : s.gloss;
    if (!g || g.endsWith("_G")) continue;  // taught glasses reps count as the base sign
    $("chips").append(Object.assign(document.createElement("li"), {textContent: g, id: "chip-" + g}));
  }
}).catch(() => {});
$("caption").classList.add("placeholder");
$("consent").onchange = () => $("go").disabled = !$("consent").checked;

$("go").onclick = async () => {
  $("go").disabled = true;
  try {
    stream = await navigator.mediaDevices.getUserMedia({video: {width: 640, height: 480, facingMode: "user"}});
  } catch (e) {
    status("Camera blocked", "err"); $("go").disabled = false; return;
  }
  $("v").srcObject = stream;
  $("empty").hidden = true;
  status("Connecting…", "off");
  const r = await fetch("/session/start", JSONH).catch(() => null);
  if (!r || !r.ok) { status("Server unreachable", "err"); return; }
  const base = location.origin.replace(/^http/, "ws");
  ev = new WebSocket(base + "/ws/events");
  ev.onmessage = m => onEvent(JSON.parse(m.data));
  ws = new WebSocket(base + "/ws/frames");
  ws.binaryType = "arraybuffer";
  ws.onopen = () => { status("Translating", "on"); $("stop").disabled = false; timer = setInterval(sendFrame, 66); };
  ws.onmessage = m => {
    const e = JSON.parse(m.data);
    if (e.type === "pose") { pose = e.p; poseAt = performance.now(); $("signing").hidden = !e.active; tickFps(); }
  };
  ws.onclose = () => { if (timer) stop(false, "Disconnected"); };
  requestAnimationFrame(draw);
};

function tickFps() {
  frames++;
  const t = performance.now();
  if (t - fpsAt > 1000) { $("fps").textContent = `${Math.round(frames * 1000 / (t - fpsAt))} fps tracked`; frames = 0; fpsAt = t; }
}

let inflight = 0;
function sendFrame() {
  const v = $("v");
  if (!v.videoWidth || !ws || ws.readyState !== 1 || inflight > 2) return;
  grab.width = v.videoWidth; grab.height = v.videoHeight;
  grab.getContext("2d").drawImage(v, 0, 0);
  inflight++;
  grab.toBlob(async b => {
    inflight--;
    const jpeg = new Uint8Array(await b.arrayBuffer());
    const head = new TextEncoder().encode(JSON.stringify({seq: seq++, ts_ms: Date.now(), w: grab.width, h: grab.height, source: "webcam", rot: 0, pose: true}));
    const out = new Uint8Array(4 + head.length + jpeg.length);
    new DataView(out.buffer).setUint32(0, head.length);
    out.set(head, 4); out.set(jpeg, 4 + head.length);
    if (ws && ws.readyState === 1 && ws.bufferedAmount < 400000) ws.send(out);
  }, "image/jpeg", 0.7);
}

function draw() {
  if (!stream) return;
  const v = $("v");
  const w = sk.clientWidth, h = sk.clientHeight, dpr = devicePixelRatio || 1;
  if (sk.width !== w * dpr) { sk.width = w * dpr; sk.height = h * dpr; }
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, w, h);
  const age = performance.now() - poseAt;
  if (pose && pose.length === 75 && age < 600 && $("showsk").checked && v.videoWidth) {
    // object-fit: cover mapping from image (0..1) to the element
    const s = Math.max(w / v.videoWidth, h / v.videoHeight);
    const dw = v.videoWidth * s, dh = v.videoHeight * s, ox = (w - dw) / 2, oy = (h - dh) / 2;
    const P = i => pose[i] && [ox + pose[i][0] * dw, oy + pose[i][1] * dh];
    ctx.globalAlpha = Math.max(0.2, 1 - age / 600);
    ctx.lineCap = "round";
    const lines = (pairs, off, color, width) => {
      ctx.strokeStyle = color; ctx.lineWidth = width; ctx.beginPath();
      for (const [a, b] of pairs) { const p = P(a + off), q = P(b + off); if (p && q) { ctx.moveTo(...p); ctx.lineTo(...q); } }
      ctx.stroke();
    };
    const dots = (from, to, color, r) => {
      ctx.fillStyle = color;
      for (let i = from; i < to; i++) { const p = P(i); if (p) { ctx.beginPath(); ctx.arc(p[0], p[1], r, 0, 7); ctx.fill(); } }
    };
    lines(POSE, 0, "rgba(255,255,255,.85)", 4);
    dots(9, 17, "#fff", 4); dots(0, 1, "#fff", 4);
    lines(HAND, 33, "#34d399", 3); dots(33, 54, "#ecfdf5", 3);
    lines(HAND, 54, "#60a5fa", 3); dots(54, 75, "#eff6ff", 3);
    ctx.globalAlpha = 1;
  }
  requestAnimationFrame(draw);
}

const pct = c => Math.round(c * 100) + "%";
const TIER = {confirmed: "✓ Sure", unsure: "? Not sure", none: "Didn't catch that"};
function onEvent(e) {
  if (e.type === "partial") {
    const g = $("gloss");
    g.textContent = e.gloss; g.classList.remove("pop", "placeholder"); void g.offsetWidth; g.classList.add("pop");
    const tier = e.tier || (e.confidence >= 0.8 ? "confirmed" : e.confidence >= 0.5 ? "unsure" : "none");
    $("tier").className = "tier " + tier;
    $("tier").textContent = `${TIER[tier]} · ${pct(e.confidence)}`;
    $("bars").replaceChildren(...(e.top || [[e.gloss, e.confidence]]).map(([gl, c]) => {
      const li = document.createElement("li");
      li.innerHTML = `<span></span><span class="track"><span class="fill"></span></span><span class="pct">${pct(c)}</span>`;
      li.firstChild.textContent = gl;
      requestAnimationFrame(() => li.querySelector(".fill").style.width = pct(c));
      return li;
    }));
    const chip = $("chip-" + e.gloss);
    if (chip) { chip.classList.add("hit"); setTimeout(() => chip.classList.remove("hit"), 1500); }
  }
  if (e.type === "caption") {
    const c = $("caption");
    c.classList.remove("placeholder");
    c.textContent = e.text + (e.tier === "unsure" && e.alternatives?.length ? `  (or: ${e.alternatives.map(a => a.text).join(" / ")})` : "");
    if (e.tier !== "none") {
      const li = document.createElement("li");
      li.innerHTML = "<span></span><small></small>";
      li.firstChild.textContent = e.text;
      li.lastChild.textContent = `${e.tier === "confirmed" ? "✓" : "?"} ${pct(e.confidence)}`;
      $("history").prepend(li);
    }
    if (e.speak && $("speak").checked && "speechSynthesis" in window) speechSynthesis.speak(new SpeechSynthesisUtterance(e.text));
  }
}

async function stop(sendStop = true, label = "Camera off") {
  clearInterval(timer); timer = null;
  if (sendStop) await fetch("/session/stop", JSONH).catch(() => {});
  ws && ws.close(); ev && ev.close();
  stream && stream.getTracks().forEach(t => t.stop()); stream = null;
  ctx.clearRect(0, 0, sk.width, sk.height);
  $("signing").hidden = true; $("empty").hidden = false; $("stop").disabled = true;
  $("go").disabled = !$("consent").checked; $("fps").textContent = "";
  status(label, label === "Camera off" ? "off" : "err");
}
$("stop").onclick = () => stop();
