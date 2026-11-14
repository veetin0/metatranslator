// Signer static demo: webcam -> MediaPipe Holistic (WASM, in the browser) -> signer.js (segmenter, BiGRU, phrases).
// No server: nothing leaves the device.
import {FilesetResolver, HolisticLandmarker} from "./vendor/vision_bundle.mjs";
import {CONF_LOW, Engine, GRU, N} from "./signer.js";

const $ = id => document.getElementById(id);
const POSE = [[11, 12], [11, 13], [13, 15], [12, 14], [14, 16], [11, 23], [12, 24], [23, 24], [9, 10]];
const HAND = [[0, 1], [1, 2], [2, 3], [3, 4], [0, 5], [5, 6], [6, 7], [7, 8], [5, 9], [9, 10], [10, 11], [11, 12],
  [9, 13], [13, 14], [14, 15], [15, 16], [13, 17], [17, 18], [18, 19], [19, 20], [0, 17]];
const MIN_FRAME_MS = 30;  // cap at ~30 fps (the camera rate); tracking runs as fast as the machine allows below that
let stream, landmarker, gru, engine, frame = null, frameAt = 0, running = false, lastRun = 0, lastVideoTime = -1;
let frames = 0, fpsAt = performance.now();
const sk = $("sk"), ctx = sk.getContext("2d");

function status(text, kind) {
  $("status").className = "pill " + kind; $("status-text").textContent = text;
  $("lens-state").className = "lens-state" + (kind === "on" ? " on" : ""); $("lens-state-text").textContent = kind === "on" ? "Signer ON" : "Signer OFF";
}
// ring light: a bright frame around the screen so the display lights your hands and face in dark rooms
$("ring").onchange = () => $("ringlight").hidden = !$("ring").checked;
$("showlens").onchange =() => $("lens-wrap").hidden = !$("showlens").checked;

// the glasses lens preview: same wrap as hud-web (24 chars, newest 2 lines), unsure shows "? " and alternatives
function lens(text, tier, alts = []) {
  const out = []; let cur = "";
  for (const w of (tier === "unsure" ? "? " + text : text).split(/\s+/).filter(Boolean)) {
    if (!cur) cur = w; else if (cur.length + 1 + w.length <= 24) cur += " " + w; else { out.push(cur); cur = w; }
  }
  if (cur) out.push(cur);
  const el = $("lens-cap"); el.className = "lens-cap " + tier;
  el.replaceChildren(...out.slice(-2).map(l => Object.assign(document.createElement("p"), {textContent: l})),
    ...(tier === "unsure" ? alts.slice(0, 2) : []).map(a => Object.assign(document.createElement("p"), {className: "alt", textContent: "or " + a.text})));
}

// model + MediaPipe load once, on the first "Turn on camera"
let ready;
function load() {
  ready ??= (async () => {
    const [man, bin] = await Promise.all([fetch("model/gru.json").then(r => r.json()), fetch("model/gru.bin").then(r => r.arrayBuffer())]);
    gru = new GRU(man, bin);
    for (const g of gru.classes) if (!g.endsWith("_G")) $("chips").append(Object.assign(document.createElement("li"), {textContent: g, id: "chip-" + g}));
    const fileset = await FilesetResolver.forVisionTasks("vendor/wasm");
    const make = delegate => HolisticLandmarker.createFromOptions(fileset, {
      baseOptions: {modelAssetPath: "vendor/holistic_landmarker.task", delegate}, runningMode: "VIDEO",
      minPoseDetectionConfidence: 0.5, minHandLandmarksConfidence: 0.5, outputFaceBlendshapes: false});
    landmarker = await make("GPU").catch(() => make("CPU"));
  })();
  return ready;
}

$("caption").classList.add("placeholder");
$("consent").onchange = () => $("go").disabled = !$("consent").checked;

$("go").onclick = async () => {
  $("go").disabled = true;
  try {
    stream = await navigator.mediaDevices.getUserMedia({video: {width: 640, height: 480, frameRate: {ideal: 30},facingMode: "user"}});
  } catch (e) {
    status("Camera blocked", "err"); $("go").disabled = false; return;
  }
  $("v").srcObject = stream;
  $("empty").hidden = true;
  status("Loading model…", "off");
  try { await load(); } catch (e) {
    console.error(e); stop("Model failed to load"); return;
  }
  if (!stream) return;  // stopped while loading
  engine = new Engine(gru);
  running = true; lastVideoTime = -1;
  status("Translating", "on"); $("stop").disabled = false;
  requestAnimationFrame(tick);
};

function toFrame(r) {
  const f = new Float32Array(N * 3).fill(NaN);
  const put = (pts, base, n) => {
    const p = pts && pts[0];
    if (!p || p.length !== n) return;
    p.forEach((q, i) => { f[(base + i) * 3] = q.x; f[(base + i) * 3 + 1] = q.y; f[(base + i) * 3 + 2] = q.z ?? NaN; });
  };
  put(r.poseLandmarks, 0, 33); put(r.leftHandLandmarks, 33, 21); put(r.rightHandLandmarks, 54, 21);
  return f;
}

function tick(now) {
  if (!running) return;
  const v = $("v");
  if (v.readyState >= 2 && v.currentTime !== lastVideoTime && now - lastRun >= MIN_FRAME_MS) {
    lastVideoTime = v.currentTime; lastRun = now;
    try {
      frame = toFrame(landmarker.detectForVideo(v, now)); frameAt = now;
      for (const e of engine.push(frame, Math.round(now))) onEvent(e);
      $("signing").hidden = !engine.active;
      tickFps();
    } catch (e) { console.error(e); }
  }
  draw(now);
  requestAnimationFrame(tick);
}

function tickFps() {
  frames++;
  const t = performance.now();
  if (t - fpsAt > 1000) {
    const fps = Math.round(frames * 1000 / (t - fpsAt));
    // low tracked fps blurs fast signs and drops hands: usually a dim room (long exposure) or a slow machine
    $("fps").textContent = `${fps} fps tracked` + (fps < 15 ? " · low: try the ring light or more light" : "");
    frames = 0; fpsAt = t;
  }
}

function draw(now) {
  const v = $("v");
  const w = sk.clientWidth, h = sk.clientHeight, dpr = devicePixelRatio || 1;
  if (sk.width !== Math.round(w * dpr)) { sk.width = Math.round(w * dpr); sk.height = Math.round(h * dpr); }
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, w, h);
  const age = now - frameAt;
  if (!frame || age > 600 || !$("showsk").checked || !v.videoWidth) return;
  // object-fit: cover mapping from image (0..1) to the element
  const s = Math.max(w / v.videoWidth, h / v.videoHeight);
  const dw = v.videoWidth * s, dh = v.videoHeight * s, ox = (w - dw) / 2, oy = (h - dh) / 2;
  const P = i => { const x = frame[i * 3], y = frame[i * 3 + 1]; return Number.isNaN(x) ? null : [ox + x * dw, oy + y * dh]; };
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

const pct = c => Math.round(c * 100) + "%";
const TIER = {confirmed: "✓ Sure", unsure: "? Not sure", none: "Low confidence, not used in the translation"};
const CAPTION_MS = 2000;  // a translated phrase stays on the lens and the Translation card this long
let captionTimer;
function onEvent(e) {
  if (e.type === "partial") {
    // every guess is shown here, even under 50%; the phrase builder still leaves "none" signs out of the translation
    const g = $("gloss");
    g.textContent = e.gloss; g.classList.remove("pop", "placeholder"); void g.offsetWidth; g.classList.add("pop");
    g.classList.toggle("low", e.tier === "none");
    $("tier").className = "tier " + e.tier;
    $("tier").textContent = `${TIER[e.tier]} · ${pct(e.confidence)}`;
    $("bars").replaceChildren(...e.top.map(([gl, c]) => {
      const li = document.createElement("li");
      if (c < CONF_LOW) li.className = "low";
      li.innerHTML = `<span></span><span class="track"><span class="fill"></span></span><span class="pct">${pct(c)}</span>`;
      li.firstChild.textContent = gl;
      requestAnimationFrame(() => li.querySelector(".fill").style.width = pct(c));
      return li;
    }));
    const chip = e.tier === "none" ? null : $("chip-" + e.gloss);
    if (chip) { chip.classList.add("hit"); setTimeout(() => chip.classList.remove("hit"), 1500); }
  }
  if (e.type === "caption") {
    const c = $("caption");
    c.classList.remove("placeholder");
    c.textContent = e.text + (e.tier === "unsure" && e.alternatives.length ? `  (or: ${e.alternatives.map(a => a.text).join(" / ")})` : "");
    if (e.tier !== "none") lens(e.text, e.tier, e.alternatives || []);
    if (e.tier !== "none") {
      const li = document.createElement("li");
      li.innerHTML = "<span></span><small></small>";
      li.firstChild.textContent = e.text;
      li.lastChild.textContent = `${e.tier === "confirmed" ? "✓" : "?"} ${pct(e.confidence)}`;
      $("history").prepend(li);
    }
    clearTimeout(captionTimer);
    captionTimer = setTimeout(() => {
      $("lens-cap").replaceChildren();
      c.textContent = "Your sentence appears here after a short pause."; c.classList.add("placeholder");
    }, CAPTION_MS);
    if (e.speak && $("speak").checked && "speechSynthesis" in window) speechSynthesis.speak(new SpeechSynthesisUtterance(e.text));
  }
}

function stop(label = "Camera off") {
  running = false;
  if (engine && label === "Camera off") for (const e of engine.flush()) onEvent(e);
  engine = null; frame = null;
  stream && stream.getTracks().forEach(t => t.stop()); stream = null;
  ctx.clearRect(0, 0, sk.width, sk.height);
  $("lens-cap").replaceChildren(); $("signing").hidden = true; $("empty").hidden = false; $("stop").disabled = true;
  $("go").disabled = !$("consent").checked; $("fps").textContent = "";
  status(label, label === "Camera off" ? "off" : "err");
}
$("stop").onclick = () => stop();
