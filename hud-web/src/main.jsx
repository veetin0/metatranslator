// Web App mirror of the lens on Meta's UI Toolkit: connect to /ws/events, render, speak confirmed captions.
// Pure logic stays in lens.js (tested); this file is the toolkit view and the socket wiring.
import { StrictMode, useEffect, useReducer, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import { App, Button, Page, Tag } from "@wearables-ui-toolkit/mrbd";
import { STATE_LABEL, ALERT, coreUrl, initial, reduce, speakText, wrap } from "./lens.js";
import "./lens.css";

const url = coreUrl(location.search);
const CAPTION_MS = 2000; // a translated phrase stays on the lens this long
const PAINT_MS = 500; // DESIGN: updates throttled >= 500 ms (matches the DAT card)

function useCore() {
  const [state, dispatch] = useReducer(reduce, undefined, initial);
  const ws = useRef(null);
  useEffect(() => {
    let down, retry, closed = false;
    const say = (ev) => {
      const text = speakText(ev);
      if (!text || !("speechSynthesis" in window)) return;
      try {
        speechSynthesis.cancel();
        speechSynthesis.speak(new SpeechSynthesisUtterance(text));
      } catch {
        /* no voice on this device; the caption is already shown */
      }
    };
    const connect = () => {
      const s = (ws.current = new WebSocket(url));
      s.onopen = () => {
        clearTimeout(down);
        s.send(JSON.stringify({ type: "hello", client: "hud" }));
      };
      s.onmessage = (m) => {
        try {
          const ev = JSON.parse(m.data);
          dispatch(ev); // before speech: a TTS failure must never cost the caption
          say(ev);
          // clear the phrase after CAPTION_MS; a newer caption has another id, so the retract leaves it alone
          if (ev.type === "caption") setTimeout(() => dispatch({ type: "retract", id: ev.id }), CAPTION_MS);
        } catch {
          /* ignore non-JSON */
        }
      };
      s.onclose = () => {
        if (closed) return;
        // core_down is produced by clients when the socket stays down > 2 s (CONTRACTS §4)
        clearTimeout(down);
        down = setTimeout(() => dispatch({ type: "state", state: "core_down", link: "ok" }), 2000);
        retry = setTimeout(connect, 1000);
      };
    };
    connect();
    return () => { closed = true; clearTimeout(down); clearTimeout(retry); ws.current && ws.current.close(); };
  }, []);
  const veto = (id) => {
    if (ws.current && ws.current.readyState === WebSocket.OPEN)
      ws.current.send(JSON.stringify({ type: "feedback", caption_id: id, verdict: "veto" }));
  };
  return [state, veto];
}

/** Render at most every PAINT_MS: the newest state wins. */
function useThrottled(value) {
  const [shown, setShown] = useState(value);
  const last = useRef(0);
  useEffect(() => {
    const wait = PAINT_MS - (Date.now() - last.current);
    const t = setTimeout(() => { last.current = Date.now(); setShown(value); }, Math.max(0, wait));
    return () => clearTimeout(t);
  }, [value]);
  return shown;
}

function StateLine({ s }) {
  const label = STATE_LABEL[s.state] || s.state;
  const cls = ALERT.has(s.state) ? "state alert" : "state";
  return (
    <div className={cls} role="status">
      <span className={"dot" + (s.state === "on" ? " dot-on" : "")} aria-hidden="true" />
      <span>{label}</span>
      {s.link === "slow" && <span className="slow"> · Link slow</span>}
    </div>
  );
}

function Caption({ c }) {
  if (!c) return <div className="caption" aria-live="polite" />;
  const tier = c.tier || "none";
  const lines = wrap(tier === "unsure" ? `? ${c.text}` : c.text);
  const alts = tier === "unsure" ? (c.alternatives || []).slice(0, 2) : [];
  return (
    <div className={`caption tier-${tier}`} data-id={c.id} aria-live="polite">
      {lines.map((l, i) => <p className="line" key={i}>{l}</p>)}
      {alts.map((a, i) => <Tag key={i} text={`or ${a.text}`} />)}
    </div>
  );
}

function Lens() {
  const [live, veto] = useCore();
  const s = useThrottled(live);
  const read = s.stats ? `${s.stats.confirmed}/${s.stats.total} confirmed` : "";
  return (
    <Page showHeader={false} enableSystemBarInset={false}>
      <div className="lens">
        <StateLine s={s} />
        <Caption c={s.caption} />
        <div className="footer">
          {read && <span className="readout">{read}</span>}
          {s.caption && s.caption.tier !== "none" && <Button title="Not right" onClick={() => veto(s.caption.id)} />}
        </div>
      </div>
    </Page>
  );
}

createRoot(document.getElementById("root")).render(
  <StrictMode>
    <App>
      <Lens />
    </App>
  </StrictMode>,
);
