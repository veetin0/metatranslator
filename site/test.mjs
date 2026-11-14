// node site/test.mjs : the JS port must reproduce the Python probabilities and segments (site/model/testvec.json,
// written by core/tools/export_web.py).
import {readFileSync} from "node:fs";
import {GRU, Segmenter, clipFeatures, trimActive, toEnglish, comboOk, bestValidRun} from "./signer.js";

const dir = new URL("./model/", import.meta.url);
const man = JSON.parse(readFileSync(new URL("gru.json", dir)));
const bin = readFileSync(new URL("gru.bin", dir));
const gru = new GRU(man, bin.buffer.slice(bin.byteOffset, bin.byteOffset + bin.byteLength));
const tv = JSON.parse(readFileSync(new URL("testvec.json", dir)));
const toFrames = xyz => xyz.map(fr => Float32Array.from(fr.flat(), v => (v === null ? NaN : v)));

let worst = 0, fail = 0;
const cmp = (label, got, want) => {
  const d = Math.max(...got.map((v, i) => Math.abs(v - want[i])));
  worst = Math.max(worst, d);
  if (d > 2e-3) { fail++; console.log("FAIL", label, "max diff", d.toExponential(2)); }
};

for (const c of tv.clips) cmp(c.path, gru.proba(clipFeatures(trimActive(toFrames(c.xyz)))), c.proba);

const seg = new Segmenter(), got = [], s = tv.stream, frames = toFrames(s.xyz);
frames.forEach((f, i) => { const g = seg.push(f, s.ts[i]); if (g) got.push(g); });
const last = seg.flush(); if (last) got.push(last);
if (got.length !== s.segments.length) { fail++; console.log("FAIL segment count", got.length, "vs", s.segments.length); }
got.forEach((g, i) => {
  const w = s.segments[i]; if (!w) return;
  if (g.startMs !== w.start_ms || g.endMs !== w.end_ms || g.frames.length !== w.n) { fail++; console.log("FAIL segment", i, g.startMs, g.endMs, g.frames.length, w); }
  cmp("segment " + i, gru.proba(clipFeatures(trimActive(g.frames))), w.proba);
});

for (const [g, want] of [[["HELLO", "QUESTION"], "Hello, can I ask a question?"], [["WHERE", "POTTY"], "Where is the bathroom?"],
  [["HELLO", "WATER", "PLEASE"], "Hello, water, please."], [["HELP"], "I need help."]]) {
  const [t] = toEnglish(g); if (t !== want) { fail++; console.log("FAIL toEnglish", g, JSON.stringify(t), "want", JSON.stringify(want)); }
}
for (const [g, ok] of [[["WATER"], true], [["HELLO", "WATER", "PLEASE"], true], [["WHERE", "BOOK"], true], [["HAPPY", "WATER"], false],
  [["BYE", "HELLO"], false], [["TALK", "LISTEN", "PLEASE"], false]]) if (comboOk(g) !== ok) { fail++; console.log("FAIL comboOk", g, ok); }
for (const [g, c, want] of [[["HAPPY", "WATER"], [0.9, 0.6], [0, 1]], [["HAPPY", "WATER"], [0.6, 0.9], [1, 2]], [["HAPPY", "WATER", "PLEASE"], [0.9, 0.7, 0.7], [1, 3]],
  [["HAPPY", "WATER"], [0.95, 0.92], [0, 2]], [["HAPPY", "WATER"], [0.85, 0.85], [0, 1]]])
  if (bestValidRun(g, c).join() !== want.join()) { fail++; console.log("FAIL bestValidRun", g, c, want); }
console.log(fail ? `${fail} failures` : "ok", "- worst probability diff", worst.toExponential(2));
process.exit(fail ? 1 : 0);
