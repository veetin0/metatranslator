// D7: the Web App renders every event in contracts/events.example.jsonl.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { coreUrl, initial, reduce, speakText, view, wrap } from "../src/lens.js";

const events = readFileSync(new URL("../../contracts/events.example.jsonl", import.meta.url), "utf8")
  .split("\n")
  .filter(Boolean)
  .map((l) => JSON.parse(l));

test("every contract event renders without error", () => {
  let s = initial();
  for (const ev of events) {
    s = reduce(s, ev);
    const html = view(s);
    assert.ok(html.includes('class="state'), `state line missing after ${ev.type}`);
  }
});

test("state line shows the word for every state, and link slow", () => {
  const words = { connecting: "Connecting…", on: "Signer ON", paused: "Paused", glasses_off: "Glasses off",
    permission_denied: "Permission denied", off: "Signer OFF", core_down: "Core down" };
  for (const [state, word] of Object.entries(words)) {
    const html = view(reduce(initial(), { type: "state", state, link: "ok" }));
    assert.ok(html.includes(word), state);
  }
  assert.ok(view(reduce(initial(), { type: "state", state: "on", link: "slow" })).includes("Link slow"));
  assert.ok(view(reduce(initial(), { type: "state", state: "on", link: "ok" })).includes("dot-on"));
  assert.ok(view(reduce(initial(), { type: "state", state: "core_down" })).includes("<svg"));
});

test("caption tiers: confirmed white, unsure amber with ? and top-2, none dim", () => {
  const [c1, c2, c3] = events.filter((e) => e.type === "caption");
  let html = view(reduce(initial(), c1));
  assert.ok(html.includes("tier-confirmed") && html.includes("Hello, can I ask a") && !html.includes("? Hello"));
  html = view(reduce(initial(), c2));
  assert.ok(html.includes("tier-unsure") && html.includes("? Where is the book?"));
  assert.ok(html.includes("or Where is the water?"));
  html = view(reduce(initial(), c3));
  assert.ok(html.includes("tier-none") && html.includes("Didn&#39;t catch that") && !html.includes("Not right"));
});

test("retract removes only the matching caption; off clears it", () => {
  const [c1, c2] = events.filter((e) => e.type === "caption");
  let s = reduce(initial(), c2);
  assert.equal(reduce(s, { type: "retract", id: "c1" }).caption.id, "c2");
  s = reduce(s, { type: "retract", id: "c2" });
  assert.equal(s.caption, null);
  assert.ok(!view(s).includes("Where is the book"));
  assert.equal(reduce(reduce(initial(), c1), { type: "state", state: "off" }).caption, null);
});

test("stats readout footer, partial and reply leave the lens alone", () => {
  const s = reduce(initial(), { type: "stats", confirmed: 17, total: 19 });
  assert.ok(view(s).includes("17/19 confirmed"));
  assert.deepEqual(reduce(s, { type: "partial", gloss: "HELLO", confidence: 0.6 }), s);
  assert.deepEqual(reduce(s, { type: "reply", text: "Sure", source: "stt" }), s);
});

test("captions wrap to 2 lines of <= 24 chars, oldest line drops", () => {
  assert.deepEqual(wrap("Hello, can I ask a question?"), ["Hello, can I ask a", "question?"]);
  const long = wrap("one two three four five six seven eight nine ten eleven twelve");
  assert.equal(long.length, 2);
  assert.ok(long.every((l) => l.length <= 24));
  assert.ok(long[1].endsWith("twelve"));
});

test("only confirmed captions with speak:true are spoken", () => {
  const spoken = events.map(speakText).filter(Boolean);
  assert.deepEqual(spoken, ["Hello, can I ask a question?"]);
  assert.equal(speakText({ type: "caption", tier: "unsure", speak: true, text: "x" }), null);
});

test("text is escaped", () => {
  const html = view(reduce(initial(), { type: "caption", id: "x", tier: "confirmed", text: "<b>hi</b>" }));
  assert.ok(!html.includes("<b>") && html.includes("&lt;b&gt;"));
});

test("core url from ?core=, default for the simulator", () => {
  assert.equal(coreUrl(""), "ws://127.0.0.1:8000/ws/events");
  assert.equal(coreUrl("?core=wss://x.trycloudflare.com/ws/events"), "wss://x.trycloudflare.com/ws/events");
});
