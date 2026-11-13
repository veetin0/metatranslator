# Possibilities (Part B): deliverables beyond code

Criteria: J1 creativity/use case, J2 technical execution, J3 real-world value/feasibility, J4 UX (input, accessibility, trust). 25% each. Evidence for the facts behind these is in `research/prior-art.md`.

## Ranked by score gain per hour

| # | Deliverable | Hours | Hits | Why |
|---|---|---|---|---|
| 1 | **Live-demo setup plan + no-glasses fallback** (rehearsed script, bounded phrases, laptop/phone camera mode, recorded backup clip) | 2-3 | J2, J4 | Meta judges expect a live demo on glasses (RULES I4). Devices are shared (BRIEF A1). A failed demo costs more than any asset gains. Cheapest big win. |
| 2 | **Signer-facing "consent card"** (phone web page): consent toggle, "Signer ON" indicator, live captions of what the hearing person says, "that's wrong" button, privacy statement | 3-4 | J4, J3, J1 | Answers R3 consent, I1 two-way, and the "tech makes deaf people do the work" criticism in one artifact. It is real UI, so it is also demonstrable. Co-owner with the build team: it is code, and it is the highest-value non-glasses screen. |
| 3 | **Deck** with a one-slide design response to the deaf community critique (WFD/efsli/"Deaf in AI"), the FinSL numbers range, the pilot plan (4 weeks, 1 site, bounded vocab, success metric) | 3-4 | J3, J1, D2, D4, D5 | Required deliverable. Pilot slide is cheap and scores J3. Slide titled "What we are not": not an interpreter replacement. |
| 4 | **Short demo video (60-90 s)** of the scenario (teacher and deaf pupil at a classroom door): glasses POV with the text overlay, consent moment, two-way captions | 4-6 | J1, J4, J2 (fallback) | Doubles as insurance if live demo fails. Keep it screen-recorded POV plus real footage; avoid heavy animation. Ask Q1 whether a video is required. |
| 5 | **Honest eval slide/chart**: accuracy on held-out signers, confidence calibration, vocabulary size | 1-2 | J2, J4 | Cheap if the model eval exists. Research shows signer-dependent eval overstates performance, so reporting held-out signers is a credibility signal. |
| 6 | **3D render / mockup of the glasses UI** (Blender: Ray-Ban Display POV with a caption overlay) | 3-5 | J1 (pitch) | Nice for the deck, little scoring on its own. Only after 1-5. A simple 2D mock of the 600x600-style display overlay in the browser is cheaper and more accurate. |
| 7 | **Short film of the scenario** | 8+ | J1 | Skip. The 60-90 s video covers it. |
| 8 | Pilot letter / one-pager for Kuurojen Liitto or a school | 1 | J3 | Only an outreach draft. Do **not** claim any partner has agreed. |

Recommended minimum set: 1, 2, 3, 5, then 4. 6 and 7 only with spare time.

## Rule/risk checks
- R3: consent and safe data: items 1-2 give visible, demonstrable evidence. Be literal about what is stored.
- D3: permissions, errors, connectivity, device state changes: the demo plan should *show* one of each (permission denied, camera lost, signer withdraws consent). A 10-second "failure tour" in the demo is cheap and scores J2.
- Do not name or imply deaf-community endorsement. State that co-design is the first pilot step.
- Q1-Q4 in BRIEF.md decide whether video is required and how the camera is reached; ask organisers early.

## Tools on this machine
- Inventory (lead's machine) lists Blender, FFmpeg, Docker, Node 22, Xcode, Expo. **On this builder machine** `blender` and `ffmpeg` were not on PATH (checked with `which`); Node (v26), Docker and xcodebuild were. Confirm which machine renders.
- Absent per inventory: Manim, ImageMagick, OpenSCAD, SoX, cv2. Use FFmpeg for video cuts/captions, browser screenshots for UI mocks, Blender only for item 6.
- Browser capture: browser MCP/Playwright screenshots can produce evidence frames for the deck without extra tools.
