// Signer in the browser: a line-for-line port of core/signer_core (features, segmenter, BiGRU, phrase builder,
// template translator). Pure logic, no DOM, so `node site/test.mjs` can check it against the Python outputs.
// A frame is a Float32Array(75 * 3): 0-32 pose, 33-53 left hand, 54-74 right hand; NaN = not detected.

export const N = 75, STEPS = 32, CONF_HIGH = 0.80, CONF_LOW = 0.50, NONE_TEXT = "Didn't catch that";
export const tierFor = c => (c >= CONF_HIGH ? "confirmed" : c >= CONF_LOW ? "unsure" : "none");

// ---------------------------------------------------------------- features (vision/features.py)
const POSE_KEEP = [0, 11, 12, 13, 14, 15, 16];
const FINGERS = [[0, 1, 2, 3, 4], [0, 5, 6, 7, 8], [0, 9, 10, 11, 12], [0, 13, 14, 15, 16], [0, 17, 18, 19, 20]];
const N_POSE = 21, N_HAND = 78, DIM = 180, LH = 21, RH = 99, FLAGS = 177;

const fin = Number.isFinite;
const has = (f, a, b) => { for (let i = a * 3; i < b * 3; i++) if (Number.isNaN(f[i])) return false; return true; };

export function frameFeatures(frames) {
  const T = frames.length, out = new Float32Array(T * DIM);
  // shoulder centre / width per frame, invalid frames take the nearest valid one
  const cen = new Float64Array(T * 3), wid = new Float64Array(T), ok = new Array(T);
  const good = [];
  for (let t = 0; t < T; t++) {
    const f = frames[t], l = 11 * 3, r = 12 * 3;
    let v = !(Number.isNaN(f[l]) || Number.isNaN(f[l + 1]) || Number.isNaN(f[l + 2]) || Number.isNaN(f[r]) || Number.isNaN(f[r + 1]) || Number.isNaN(f[r + 2]));
    if (v) {
      const dx = f[l] - f[r], dy = f[l + 1] - f[r + 1], dz = f[l + 2] - f[r + 2];
      wid[t] = Math.hypot(dx, dy, dz);
      for (let k = 0; k < 3; k++) cen[t * 3 + k] = (f[l + k] + f[r + k]) / 2;
      v = fin(wid[t]) && wid[t] > 1e-4;
    }
    ok[t] = v;
    if (v) good.push(t);
  }
  const src = new Array(T);
  for (let t = 0; t < T; t++) {
    if (ok[t] || !good.length) { src[t] = t; continue; }
    let best = good[0];
    for (const g of good) if (Math.abs(g - t) < Math.abs(best - t)) best = g;
    src[t] = best;
  }
  for (let t = 0; t < T; t++) {
    const f = frames[t], s = src[t];
    const c = good.length ? [cen[s * 3], cen[s * 3 + 1], cen[s * 3 + 2]] : [0.5, 0.5, 0], w = good.length ? wid[s] : 0.25;
    const n = i => [(f[i * 3] - c[0]) / w, (f[i * 3 + 1] - c[1]) / w, (f[i * 3 + 2] - c[2]) / w];
    const o = t * DIM;
    const poseOk = POSE_KEEP.every(i => !(Number.isNaN(f[i * 3]) || Number.isNaN(f[i * 3 + 1]) || Number.isNaN(f[i * 3 + 2])));
    if (poseOk) POSE_KEEP.forEach((i, j) => { const p = n(i); out[o + j * 3] = p[0]; out[o + j * 3 + 1] = p[1]; out[o + j * 3 + 2] = p[2]; });
    out[o + FLAGS] = poseOk ? 1 : 0;
    [[LH, 33, 1], [RH, 54, 2]].forEach(([col, base, flag]) => {
      if (!has(f, base, base + 21)) return;
      const h = []; for (let i = 0; i < 21; i++) h.push(n(base + i));
      h.forEach((p, i) => { out[o + col + i * 3] = p[0]; out[o + col + i * 3 + 1] = p[1]; out[o + col + i * 3 + 2] = p[2]; });
      let a = 0;
      for (const ch of FINGERS) for (let k = 1; k <= 3; k++) {
        const p0 = h[ch[k - 1]], p1 = h[ch[k]], p2 = h[ch[k + 1]];
        const u = [p0[0] - p1[0], p0[1] - p1[1], p0[2] - p1[2]], v = [p2[0] - p1[0], p2[1] - p1[1], p2[2] - p1[2]];
        const cos = (u[0] * v[0] + u[1] * v[1] + u[2] * v[2]) / (Math.hypot(...u) * Math.hypot(...v) + 1e-9);
        out[o + col + 63 + a++] = Math.acos(Math.max(-1, Math.min(1, cos))) / Math.PI;
      }
      out[o + FLAGS + flag] = 1;
    });
  }
  return out;
}

export function clipFeatures(frames, steps = STEPS) {
  const T = frames.length, feat = frameFeatures(frames), out = new Float32Array(steps * DIM);
  const lo = new Int32Array(steps), hi = new Int32Array(steps), fr = new Float64Array(steps);
  for (let s = 0; s < steps; s++) {
    const u = T > 1 ? (s * (T - 1)) / (steps - 1) : 0;
    lo[s] = Math.floor(u); hi[s] = Math.min(lo[s] + 1, T - 1); fr[s] = u - lo[s];
  }
  for (const [c0, c1, flag] of [[0, N_POSE, 0], [LH, LH + N_HAND, 1], [RH, RH + N_HAND, 2]]) {
    for (let s = 0; s < steps; s++) {
      const p0 = feat[lo[s] * DIM + FLAGS + flag], p1 = feat[hi[s] * DIM + FLAGS + flag];
      const w = p0 * (1 - fr[s]) + p1 * fr[s];
      if (w < 0.5) continue;  // absent: zeros, flag 0
      for (let c = c0; c < c1; c++) {
        out[s * DIM + c] = (feat[lo[s] * DIM + c] * p0 * (1 - fr[s]) + feat[hi[s] * DIM + c] * p1 * fr[s]) / Math.max(w, 1e-6);
      }
      out[s * DIM + FLAGS + flag] = 1;
    }
  }
  return out;
}

export function trimActive(frames, pad = 2) {
  const hand = f => has(f, 33, 54) || has(f, 54, 75);
  let a = -1, b = -1;
  frames.forEach((f, i) => { if (hand(f)) { if (a < 0) a = i; b = i; } });
  return a < 0 ? frames : frames.slice(Math.max(0, a - pad), b + pad + 1);
}

// ---------------------------------------------------------------- segmenter (model/segmenter.py)
const L_SH = 11, R_SH = 12, L_HIP = 23, R_HIP = 24, WRISTS = [33, 54];

function restLine(f) {
  const y1 = f[L_HIP * 3 + 1], y2 = f[R_HIP * 3 + 1];
  if (fin(y1) && fin(y2)) return (y1 + y2) / 2;
  const ok = [L_SH, R_SH].every(i => fin(f[i * 3]) && fin(f[i * 3 + 1]));
  if (!ok) return Infinity;
  const w = Math.hypot(f[L_SH * 3] - f[R_SH * 3], f[L_SH * 3 + 1] - f[R_SH * 3 + 1]);
  return (f[L_SH * 3 + 1] + f[R_SH * 3 + 1]) / 2 + 2.2 * Math.max(w, 1e-3);
}
export function isUp(f) {
  const line = restLine(f);
  return WRISTS.some(w => { const y = f[w * 3 + 1]; return fin(y) && y < line; });
}

export class Segmenter {
  constructor({onFrames = 2, gapMs = 350, minMs = 250, maxMs = 4000, preRoll = 3, minFrames = 4} = {}) {
    Object.assign(this, {onFrames, gapMs, minMs, maxMs, minFrames, preMax: Math.max(preRoll, onFrames)});
    this.reset();
  }
  reset() { this.pre = []; this.frames = []; this.ts = []; this.active = false; this.run = 0; this.lastUpI = -1; this.lastUpTs = 0; }
  push(frame, ts) {
    const up = isUp(frame);
    if (!this.active) {
      this.pre.push([frame, ts]); if (this.pre.length > this.preMax) this.pre.shift();
      this.run = up ? this.run + 1 : 0;
      if (this.run >= this.onFrames) {
        this.active = true;
        this.frames = this.pre.map(p => p[0]); this.ts = this.pre.map(p => p[1]); this.pre = [];
        this.lastUpI = this.frames.length - 1; this.lastUpTs = ts;
      }
      return null;
    }
    if (ts - this.ts[0] > this.maxMs) { const seg = this.close(this.frames.length - 1, 0); this.push(frame, ts); return seg; }
    this.frames.push(frame); this.ts.push(ts);
    if (up) { this.lastUpI = this.frames.length - 1; this.lastUpTs = ts; }
    if (!up && ts - this.lastUpTs >= this.gapMs) return this.close(this.lastUpI);
    return null;
  }
  flush() { if (!this.active) { this.reset(); return null; } return this.close(this.lastUpI); }
  close(last, post = 1) {
    const frames = this.frames.slice(0, last + 1 + post), ts = this.ts.slice(0, last + 1 + post);
    this.reset();
    if (frames.length < this.minFrames || ts[ts.length - 1] - ts[0] < this.minMs) return null;
    return {frames, startMs: ts[0], endMs: ts[ts.length - 1]};
  }
}

// ---------------------------------------------------------------- BiGRU (model/gru.py), plain JS, ~1 ms per sign
const sigmoid = x => 1 / (1 + Math.exp(-x));
function erf(x) {  // Abramowitz-Stegun 7.1.26 is too coarse for GELU; use the series/continued fraction of W. J. Cody's range split
  const s = Math.sign(x), a = Math.abs(x);
  if (a < 2.5) { let sum = a, term = a; for (let n = 1; n < 60; n++) { term *= -a * a / n; sum += term / (2 * n + 1); } return s * 2 / Math.sqrt(Math.PI) * sum; }
  let f = 0; for (let k = 60; k >= 1; k--) f = k / 2 / (a + f);
  return s * (1 - Math.exp(-a * a) / (Math.sqrt(Math.PI) * (a + f)));
}
const gelu = x => 0.5 * x * (1 + erf(x / Math.SQRT2));

export class GRU {
  constructor(manifest, buf) {
    this.classes = manifest.classes; this.H = manifest.hidden; this.mean = manifest.mean; this.std = manifest.std;
    this.w = {};
    for (const [name, [off, shape]] of Object.entries(manifest.tensors)) this.w[name] = new Float32Array(buf, off * 4, shape.reduce((a, b) => a * b, 1));
  }
  layer(x, T, inDim, l, rev) {  // x: T*inDim -> T*H for one direction
    const H = this.H, sfx = `l${l}${rev ? "_reverse" : ""}`;
    const Wi = this.w[`gru.weight_ih_${sfx}`], Wh = this.w[`gru.weight_hh_${sfx}`], bi = this.w[`gru.bias_ih_${sfx}`], bh = this.w[`gru.bias_hh_${sfx}`];
    const out = new Float32Array(T * H), h = new Float32Array(H), gi = new Float32Array(3 * H), gh = new Float32Array(3 * H);
    for (let s = 0; s < T; s++) {
      const t = rev ? T - 1 - s : s;
      for (let r = 0; r < 3 * H; r++) {
        let a = bi[r], b = bh[r];
        for (let k = 0; k < inDim; k++) a += Wi[r * inDim + k] * x[t * inDim + k];
        for (let k = 0; k < H; k++) b += Wh[r * H + k] * h[k];
        gi[r] = a; gh[r] = b;
      }
      for (let j = 0; j < H; j++) {
        const r = sigmoid(gi[j] + gh[j]), z = sigmoid(gi[H + j] + gh[H + j]), n = Math.tanh(gi[2 * H + j] + r * gh[2 * H + j]);
        h[j] = (1 - z) * n + z * h[j];
        out[t * H + j] = h[j];
      }
    }
    return out;
  }
  proba(feat) {  // feat: STEPS*DIM raw features -> softmax over classes
    const T = STEPS, H = this.H, W = this.w, x = new Float32Array(T * DIM);
    for (let t = 0; t < T; t++) for (let k = 0; k < DIM; k++) x[t * DIM + k] = (feat[t * DIM + k] - this.mean[k]) / this.std[k];
    const e = new Float32Array(T * H);
    for (let t = 0; t < T; t++) for (let j = 0; j < H; j++) {
      let a = W["inp.0.bias"][j];
      for (let k = 0; k < DIM; k++) a += W["inp.0.weight"][j * DIM + k] * x[t * DIM + k];
      e[t * H + j] = gelu(a);
    }
    let cur = e, dim = H;
    for (let l = 0; l < 2; l++) {
      const f = this.layer(cur, T, dim, l, false), b = this.layer(cur, T, dim, l, true), o = new Float32Array(T * 2 * H);
      for (let t = 0; t < T; t++) { o.set(f.subarray(t * H, t * H + H), t * 2 * H); o.set(b.subarray(t * H, t * H + H), t * 2 * H + H); }
      cur = o; dim = 2 * H;
    }
    const pool = new Float32Array(4 * H);
    for (let j = 0; j < 2 * H; j++) {
      let sum = 0, mx = -Infinity;
      for (let t = 0; t < T; t++) { const v = cur[t * 2 * H + j]; sum += v; if (v > mx) mx = v; }
      pool[j] = sum / T; pool[2 * H + j] = mx;
    }
    const C = this.classes.length, logit = new Float64Array(C);
    for (let c = 0; c < C; c++) { let a = W["out.1.bias"][c]; for (let k = 0; k < 4 * H; k++) a += W["out.1.weight"][c * 4 * H + k] * pool[k]; logit[c] = a; }
    const m = Math.max(...logit), ex = Array.from(logit, v => Math.exp(v - m)), sum = ex.reduce((a, b) => a + b, 0);
    return ex.map(v => v / sum);
  }
  predict(frames, top = 3) {
    const p = this.proba(clipFeatures(trimActive(frames)));
    return this.classes.map((g, i) => [g, p[i]]).sort((a, b) => b[1] - a[1]).slice(0, top);
  }
}

// ---------------------------------------------------------------- template translator (language/template.py)
const ENGLISH = {HELLO: "hello", BYE: "bye", YES: "yes", NO: "no", PLEASE: "please", THANKYOU: "thank you", WAIT: "wait",
  FINISH: "finished", POTTY: "bathroom", WATER: "water", WHERE: "where", WHY: "why", WHO: "who", TIME: "time", BOOK: "book",
  LISTEN: "listen", TALK: "talk", HOME: "home", SICK: "sick", HAPPY: "happy", HELP: "help", QUESTION: "question",
  UNDERSTAND: "understand", AGAIN: "again"};
const WH = ["WHERE", "WHY", "WHO"], QUESTION = ["WHERE", "WHY", "WHO", "QUESTION"], NOUNS = ["WATER", "BOOK", "HOME", "POTTY", "TIME"];
const PHRASES = {
  "HELLO QUESTION": "Hello, can I ask a question?", "QUESTION": "Can I ask a question?", "PLEASE WAIT": "Please wait.",
  "WAIT PLEASE": "Please wait.", "PLEASE HELP": "Please help me.", "HELP PLEASE": "Please help me.", "HELP": "I need help.",
  "THANKYOU BYE": "Thank you, bye!", "TIME": "What time is it?", "UNDERSTAND": "I understand.",
  "NO UNDERSTAND": "I don't understand.", "UNDERSTAND NO": "I don't understand.", "AGAIN": "Again, please.",
  "AGAIN PLEASE": "Can you say that again, please?", "PLEASE AGAIN": "Can you say that again, please?",
  "FINISH": "I'm finished.", "SICK": "I feel sick.", "HAPPY": "I'm happy.", "WATER PLEASE": "Water, please.",
  "PLEASE WATER": "Water, please.", "WHERE POTTY": "Where is the bathroom?", "POTTY WHERE": "Where is the bathroom?",
  "LISTEN": "I'm listening.", "THANKYOU": "Thank you.", "HELLO": "Hello.", "BYE": "Bye!", "YES": "Yes.", "NO": "No.",
  "PLEASE": "Please.", "WAIT": "Wait."};
const cap = s => s.charAt(0).toUpperCase() + s.slice(1);
const word = g => ENGLISH[g] ?? g.toLowerCase();
const sentence = (words, q) => { const s = words.filter(Boolean).join(" ").trim(); return s ? cap(s) + (q ? "?" : ".") : ""; };
const match = g => PHRASES[g.join(" ")] ?? null;
function wh(g) {
  const whs = g.filter(x => WH.includes(x));
  if (whs.length !== 1) return null;
  const w = whs[0], rest = g.filter(x => x !== w);
  if (!rest.length) return cap(word(w)) + "?";
  if (rest.length === 1 && NOUNS.includes(rest[0]) && w === "WHERE") return `Where is the ${word(rest[0])}?`;
  if (rest.length === 1 && w === "WHO") return ["SICK", "HAPPY"].includes(rest[0]) ? `Who is ${word(rest[0])}?` : null;
  return null;
}
export function toEnglish(gloss) {
  let g = gloss.filter(x => x && x !== "REST");
  if (!g.length) return ["", false];
  const q = g.some(x => QUESTION.includes(x)) || (g.length === 1 && g[0] === "TIME");
  let text = match(g) ?? wh(g);
  if (text) return [text, q || text.endsWith("?")];
  const head = [], tail = [];
  g = g.slice();
  while (g.length && g[0] === "HELLO") head.push(g.shift());
  while (g.length > 1 && ["THANKYOU", "BYE", "PLEASE"].includes(g[g.length - 1])) tail.unshift(g.pop());
  let core = g.length ? (match(g) ?? wh(g)) : "";
  if (!core) core = sentence(g.map(word), q);
  if (head.length && core) core = "Hello, " + (core.startsWith("I ") || core.startsWith("I'") ? core : core.charAt(0).toLowerCase() + core.slice(1));
  else if (head.length) core = "Hello.";
  if (tail.length) {
    const words = tail.map(word).join(", "), end = core ? core[core.length - 1] : ".";
    core = core ? core.slice(0, -1) + ", " + words + end : sentence([words], q);
  }
  return [core, q || core.endsWith("?")];
}
const applyQuestion = (t, q) => (!t || !q || t.endsWith("?") ? t : (".!".includes(t[t.length - 1]) ? t.slice(0, -1) : t) + "?");

// ---------------------------------------------------------------- recognizer + phrase builder (relay/pipeline.py)
export class Recognizer {
  constructor(gru) { this.gru = gru; this.seg = new Segmenter(); }
  get active() { return this.seg.active; }
  reset() { this.seg.reset(); }
  push(frame, ts) { return this.pred(this.seg.push(frame, ts)); }
  flush() { return this.pred(this.seg.flush()); }
  pred(seg) {
    if (!seg) return null;
    const top = this.gru.predict(seg.frames, 3), [gloss, confidence] = top[0];
    if (gloss === "REST") return null;
    return {gloss, confidence, tier: tierFor(confidence), top, startMs: seg.startMs, endMs: seg.endMs,
      alternatives: top.slice(1).filter(t => t[0] !== "REST").slice(0, 2)};
  }
}

export class PhraseBuilder {
  constructor(gapMs = 1200, maxSigns = 6) { this.gapMs = gapMs; this.maxSigns = maxSigns; this.preds = []; this.n = 0; }
  get pending() { return this.preds.length > 0; }
  add(p) { this.preds.push(p); return this.preds.length >= this.maxSigns ? this.flush() : null; }
  tick(ts) { return this.preds.length && ts - this.preds[this.preds.length - 1].endMs >= this.gapMs ? this.flush() : null; }
  reset() { this.preds = []; }
  flush() {
    const preds = this.preds; this.preds = [];
    return preds.length ? this.caption(preds, `c${++this.n}`) : null;
  }
  caption(preds, id) {
    const kept = preds.filter(p => p.tier !== "none");
    if (!kept.length) return {type: "caption", id, text: NONE_TEXT, gloss: [], tier: "none", alternatives: [], question: false,
      confidence: Math.max(...preds.map(p => p.confidence)), speak: false};
    const gloss = kept.map(p => p.gloss), confs = kept.map(p => p.confidence), conf = Math.min(...confs), tier = tierFor(conf);
    const [t0, q0] = toEnglish(gloss), text = applyQuestion(t0, q0), question = q0 || text.endsWith("?");
    const weakest = confs.indexOf(conf), others = Math.min(1, ...confs.filter((_, i) => i !== weakest));
    const alternatives = [];
    for (const [g, c] of kept[weakest].alternatives) {
      const alt = [...gloss.slice(0, weakest), g, ...gloss.slice(weakest + 1)], [at] = toEnglish(alt);
      if (at && at !== text) alternatives.push({text: at, gloss: alt, confidence: Math.min(c, others)});
    }
    return {type: "caption", id, text, gloss, tier, confidence: conf, alternatives: alternatives.slice(0, 2), question,
      speak: tier === "confirmed"};
  }
}

// One object the page drives: push(frame75, tsMs) -> {partial?, caption?}
export class Engine {
  constructor(gru) { this.rec = new Recognizer(gru); this.phrases = new PhraseBuilder(); }
  get active() { return this.rec.active; }
  push(frame, ts) {
    const out = [], p = this.rec.push(frame, ts);
    if (p) out.push(...this.onPred(p));
    const c = this.rec.active ? null : this.phrases.tick(ts);
    if (c) out.push(c);
    return out;
  }
  onPred(p) {
    const out = [{type: "partial", gloss: p.gloss, confidence: p.confidence, tier: p.tier, top: p.top.filter(t => t[0] !== "REST")}];
    const c = this.phrases.add(p);
    if (c) out.push(c);
    return out;
  }
  flush() {
    const out = [], p = this.rec.flush();
    if (p) out.push(...this.onPred(p));
    const c = this.phrases.flush();
    if (c) out.push(c);
    return out;
  }
  reset() { this.rec.reset(); this.phrases.reset(); }
}
