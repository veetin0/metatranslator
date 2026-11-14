# Signer: pitch video handoff

For whoever builds the pitch video (a teammate or another Claude). Everything here is checked against the repo as of 2026-11-14, commit 0088653. Deadline: 2026-11-15 10:00 (+02:00).

## One-line pitch
A Deaf person signs. The person wearing Meta Ray-Ban Display glasses reads it as English on the lens, and hears it when the system is sure.

## Story arc (suggested, strictly 120 s, not a second more)
1. **Problem.** Everyday conversations have no live ASL-to-English translation. Interpreters are booked for big moments, not for "where is the book?". Typing on a phone breaks eye contact. The burden is on the Deaf person every time.
2. **Idea.** The glasses camera sees what the wearer sees, so nobody holds a phone between two people. Words appear on the lens.
3. **Demo.** The signer taps Start on their card (consent). They sign. A caption appears; when confirmed it is spoken. Demo phrases (from `demo/script.md`): HELLO, WHERE BOOK, PLEASE WAIT, WATER PLEASE, THANKYOU BYE. The signer taps Stop and it is off.
4. **How it works.** Camera, then phone, then laptop. MediaPipe hand and pose points (frames are dropped, never stored). A BiGRU classifier gives a confidence score. Glosses become an English sentence.
5. **Honest numbers.** See the table below.
6. **What we are not.** A small everyday vocabulary, not full ASL grammar. It is not a replacement for an interpreter in medical, legal or exam settings. When unsure it says so.
7. **Next.** Pilot with one classroom and one Deaf student for two weeks. Grow the vocabulary with Deaf signers, with consent and credit.

## Numbers you may say (all in `eval/results/`; `deck/check_numbers.py` enforces them)
| Claim | Value | Source file |
|---|---|---|
| Baseline kNN, leave-one-signer-out, 7,996 PopSign clips, 20 signs | top-1 0.51 | `m3b.json` |
| BiGRU, 5 signer-disjoint folds, same clips | top-1 0.95, top-3 0.99 | `m3c_gru.json` |
| Same, with ASL Citizen added to training | top-1 0.950 (unchanged) | `m4_gru_citizen.json` |
| Other-camera test: held-out ASL Citizen clips | 0.68 PopSign-only, 0.97 with ASL Citizen | `m4_gru_citizen.json` |
| Teaching a new sign | 5 reps | taught on the glasses camera |

**Caveats to keep (do not drop them in the video):**
- The 0.97 is optimistic: the dataset has no signer ids, so the split is by download batch and the same person may be in both sets. One of two planned runs completed. Prefer saying "0.68 to 0.97 on a second camera setup, optimistic".
- PopSign is front-facing phone video. **Accuracy from the glasses' own camera has not been measured at scale**, and the glasses are currently lost. Do not claim glasses accuracy.
- The vocabulary is 20 PopSign signs plus a few taught ones (`data/VOCAB.md`). Do not say "ASL translator" without "everyday phrases".
- ASL Citizen is non-commercial research only. Do not present the product as ready to sell.
- Say "recognised live in our first tests" for the glasses, not a percentage.

## Rules that bind the video
- **R3:** consent Start, printed sign, signer controls Stop. Show the Start tap before any translation. Volunteer consent forms are in `demo/` (`consent-sign.pdf`, `volunteer-consent.md`).
- Do not show or imply stored video of anyone. "Frames never stored; only landmarks."
- English and ASL only.
- Credit the data on screen: PopSign ASL v1.0, Georgia Tech / Deaf Professional Arts Network (Thad Starner et al.), CC BY 4.0, signdata.cc.gatech.edu. ASL Citizen (Microsoft and Boston University), non-commercial research use.
- Confidence tiers on screen: 0.80 and above is white and spoken, 0.50 to 0.80 is amber "?" and not spoken, below that "Didn't catch that".

## Assets already in the repo
- Slides: `deck/signer.html` and `deck/signer.pdf` (8 slides, 1280x720; rebuild with `bash deck/build.sh`). einoperamaa also edits these.
- Demo script and fallbacks: `demo/script.md`, `demo/glasses-slot-plan.md`, `demo/rehearsals.md`.
- Screenshots in `.hackforge/evidence/`: `M1-card-start.png`, `M1-card-stop.png`, `M1-sim-caption.png`, `M1-sim-unsure.png`, `M3-card-readout.png`, `M3-card-reply.png`, `M3-card-teach.png`, `M3-card-core_down.png`, `M3-card-glasses_off.png`, `M3-card-permission_denied.png`.
- Design tokens: `DESIGN.md` (card palette and lens palette; the lens is black = transparent).
- `video/out/demo.mp4` is referenced by the demo script as a stage fallback but **does not exist yet**. Record it if there is time (screen capture of the Signer card plus the simulator lens).

## Live demo setup (if recording a real take)
- Relay: `env PYTHONPATH=core SIGNER_FLAGS=teach SIGNER_DEBUG_FRAMES=1 SIGNER_MAX_FRAME_AGE_MS=5000 core/.venv/bin/python -m signer_core.relay` (port 8000; loads `data/models/gru.pt` at the first Start).
- The Cloudflare tunnel is down. Restart with `cloudflared tunnel --no-autoupdate --url http://127.0.0.1:8000`; the URL changes and must be entered in the app.
- The iOS app needs a rebuild in Xcode for the camera-permission patch.
- Glasses are lost: a take from the glasses' camera is not possible right now. Alternatives: the Display Simulator for the lens, and the card on a phone or tablet.

## Tone
Calm, trustworthy, accessibility-first (see `DESIGN.md`). Some light humour is fine, but never at the expense of Deaf signers, the sponsor or the judges. Keep every number honest.

## Open items the video owner should know
- The deck does not yet show the ASL Citizen other-camera result.
- Nothing is pushed to a remote; all work is in local commits on `main`.
