// Lens state + view (CONTRACTS §4, §7; DESIGN.md "Lens"). Pure: no DOM, so tests render every contract event.

export const MAX_CHARS = 24;
export const MAX_LINES = 2;

export const STATE_LABEL = {
  off: "Signer OFF",
  connecting: "Connecting…",
  on: "Signer ON",
  paused: "Paused",
  glasses_off: "Glasses off",
  permission_denied: "Permission denied",
  core_down: "Core down",
};
export const ALERT = new Set(["permission_denied", "core_down"]);

// Lucide "triangle-alert", inline (no icon font, first load < 300 KB)
const ALERT_ICON =
  '<svg class="icon" aria-hidden="true" viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3"/><path d="M12 9v4"/><path d="M12 17h.01"/></svg>';

export function initial() {
  return { state: "connecting", link: "ok", caption: null, stats: null };
}

export function reduce(s, ev) {
  switch (ev && ev.type) {
    case "state":
      return { ...s, state: ev.state, link: ev.link || "ok", caption: ev.state === "off" ? null : s.caption };
    case "caption":
      return { ...s, caption: ev };
    case "retract":
      return s.caption && s.caption.id === ev.id ? { ...s, caption: null } : s;
    case "stats":
      return { ...s, stats: { confirmed: ev.confirmed, total: ev.total } };
    default: // partial and reply are card-only; unknown types are ignored
      return s;
  }
}

/** Word-wrap to lines of <= MAX_CHARS and keep the newest MAX_LINES (the oldest line drops). */
export function wrap(text, max = MAX_CHARS, lines = MAX_LINES) {
  const out = [];
  let cur = "";
  for (const word of String(text).split(/\s+/).filter(Boolean)) {
    if (!cur) cur = word;
    else if (cur.length + 1 + word.length <= max) cur += " " + word;
    else {
      out.push(cur);
      cur = word;
    }
  }
  if (cur) out.push(cur);
  return out.slice(-lines);
}

export function esc(t) {
  return String(t).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
}

function stateLine(s) {
  const label = STATE_LABEL[s.state] || s.state;
  const lead = ALERT.has(s.state)
    ? ALERT_ICON
    : `<span class="dot${s.state === "on" ? " dot-on" : ""}" aria-hidden="true"></span>`;
  const slow = s.link === "slow" ? '<span class="slow"> · Link slow</span>' : "";
  const cls = ALERT.has(s.state) ? "state alert" : "state";
  return `<div class="${cls}" data-focus="state" tabindex="0" role="status">${lead}<span>${esc(label)}</span>${slow}</div>`;
}

function captionBlock(c) {
  if (!c) return '<div class="caption" data-focus="caption" tabindex="-1" aria-live="polite"></div>';
  const tier = c.tier || "none";
  const text = tier === "unsure" ? `? ${c.text}` : c.text;
  const lines = wrap(text).map((l) => `<p class="line">${esc(l)}</p>`).join("");
  const alts =
    tier === "unsure"
      ? (c.alternatives || []).slice(0, 2).map((a) => `<p class="alt">or ${esc(a.text)}</p>`).join("")
      : "";
  return `<div class="caption tier-${esc(tier)}" data-focus="caption" data-id="${esc(c.id)}" tabindex="0" aria-live="polite">${lines}${alts}</div>`;
}

function footer(s) {
  const read = s.stats ? `${s.stats.confirmed}/${s.stats.total} confirmed` : "";
  const veto =
    s.caption && s.caption.tier !== "none"
      ? `<button class="act" data-focus="veto" data-action="veto" data-id="${esc(s.caption.id)}">Not right</button>`
      : "";
  return `<div class="footer"><span class="readout">${esc(read)}</span>${veto}</div>`;
}

export function view(s) {
  return stateLine(s) + captionBlock(s.caption) + footer(s);
}

/** Should this event be read aloud? Only confirmed captions (contract: speak is true only for confirmed). */
export function speakText(ev) {
  return ev && ev.type === "caption" && ev.speak === true && ev.tier === "confirmed" ? ev.text : null;
}

export function coreUrl(search, fallback = "ws://127.0.0.1:8000/ws/events") {
  const q = new URLSearchParams(search).get("core");
  return q || fallback;
}
