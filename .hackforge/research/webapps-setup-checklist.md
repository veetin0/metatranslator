# Web Apps setup checklist (Meta Ray-Ban Display)

Checked 2026-11-13 on the lead's Mac. Sources: https://wearables.developer.meta.com/docs/develop/webapps/setup/ , /webapps/wearables-documentation-mcp/ , /webapps/test/ , `search_webapps_docs` ("first Web App setup"), plugin skill `ai-glasses-webapp-build`.
In Signer the Web App is the lens preview in the simulator and Fallback A; the main lens path is DAT Display (DECISION.md).

| # | Item | Requirement | Status here |
|---|---|---|---|
| 1 | AI Coding plugin | `meta-wearables-webapp@meta-wearables` | ✅ installed + enabled (v128.1.1, user scope); skills `ai-glasses-webapp-build/-ui/-device/-webmcp/-test/-optimize-performance/-publish` on disk. **Loads in a new Claude session.** |
| 2 | Wearables MCP | `claude mcp add --transport http wearables https://mcp.developer.meta.com/wearables` | ✅ connected; `tools/list` returns `search_webapps_docs` + `search_dat_docs`; a test query answered. **In-session tool loads in a new session.** |
| 3 | Node + npm | needed for `npm install / run dev / test / build` | ✅ Node v22.20.0, npm 10.9.3 |
| 4 | Chrome + Display Simulator | extension `jpjlmmodokemlepklkdbimceggpbjcll` | ✅ installed in Chrome Default profile; turn it on via the extension icon on the app tab |
| 5 | Hardware | Meta Ray-Ban Display + paired phone with Meta AI app; Neural Band optional | ⏳ glasses in 2-hour slots (PLAN "Glasses time") |
| 6 | Versions | Web Apps: Meta AI app ≥ v272, glasses ≥ v125 (DAT needs V292 / V128, so aim for those) | ⏳ check on the phone: Settings → App Info → App version; Devices → glasses → ⚙ → General → About → Release Version |
| 7 | Developer Mode | Meta AI app → Settings → App Info → tap App version 5× → Enable (persists) | ⏳ on the phone |
| 8 | HTTPS hosting | public URL, valid TLS, no HTTP/LAN/localhost | ✅ options ready: `gh` logged in (GitHub Pages for the static page), `cloudflared` installed (quick tunnel for the core's WSS). No Vercel CLI (`npx vercel` if wanted). Page on HTTPS must use `wss://`. |
| 9 | Install on glasses | Meta AI app → App Settings → Apps → Web Apps → Connect Web App → URL → Save; or QR `fb-viewapp://web_app_deep_link?appName=<name>&appUrl=<https-url>` (simulator "View on Glasses QR") | ⏳ in glasses slot G1 (M0 check e) |
| 10 | Local verification | `npm run preview -- --host 127.0.0.1 --port 4173`; Chrome DevTools 600×600 viewport; Chrome started with `--enable-spatial-navigation` for arrow/Enter focus; simulator for additive display; console + network clean | ⏳ when `hud-web/` exists (M0.2) |

Gaps before writing `hud-web/` code: start a new Claude session so the plugin skills and `search_webapps_docs` tool load; phone-side checks 6–7; glasses slot for 9.
