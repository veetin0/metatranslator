# Glasses slot plan (2 hours)

Goal: leave the slot with (1) three timed rehearsals logged, (2) real footage for the demo video, (3) every hardware unknown answered. Do everything that doesn't need the glasses BEFORE the slot.

## Before the slot (no glasses needed)
- [ ] Core running on the Mac, `/health` ok, tunnel up (`tunnel.sh`), phone reaches it (USB tethering, not the glasses Wi-Fi).
- [ ] iOS app built for the phone, signed, installed; Mock Device Kit run once end to end.
- [ ] PopSign landmarks rebuilt, M3 D4 and the gate green (the model is the real one).
- [ ] Volunteer signer(s) booked; consent form (`demo/volunteer-consent.md`) and table sign (`demo/consent-sign.pdf`) printed.
- [ ] Footage kit charged and tested: a second phone/camera on a tripod (third-person), screen recording of the Card, a way to capture the lens (Meta AI app capture or phone filming the wearer's POV).
- [ ] Video pipeline ready (`video/README.md` render command works on placeholder footage; footage file names known). Voice: Jessica.
- [ ] Meta AI app >= V292, firmware >= V128, Developer Mode on, glasses charged and paired, Neural Band charged.
- [ ] Phrase list (6 phrases from `demo/script.md`) memorised by the signer; backup phrases ready.

## In the slot
| Min | What | Output |
|---|---|---|
| 0-10 | Pair, launch app, check camera stream + lens caption + speaker volume. Watch for `CAPABILITY_DENIED`. | go / no-go |
| 10-20 | Neural Band Record/Stop, one full pass, no timing. Fix anything broken now. | working path |
| 20-30 | Domain-shift check: sign the vocabulary through the glasses camera, note accuracy per sign. | notes for the eval slide |
| 30-50 | **Rehearsal R1**, timed, with script; log it. | row in `demo/rehearsals.md` |
| 50-65 | Fix the top issues from R1. | |
| 65-80 | **Rehearsal R2**, timed; screen-record the Card; film third person. | row + footage |
| 80-95 | **Rehearsal R3** (the take to keep): record glasses POV, third-person, Card screen, audio. | row + footage |
| 95-110 | Fallback drills: kill core (core_down card), glasses off, permission denied, WS fallback, card-only. Record the lens once more for pickup shots. | notes |
| 110-120 | Back up all footage (copy off the Mac), log final timings and issues, charge. | footage on disk |

## Footage to capture (for M4-hw / D4)
1. Glasses POV: signer in view, caption appears on the lens.
2. Third person: signer, wearer, the speaker.
3. Card screen: consent Start, ON light, history with the tick, Stop.
4. Close-ups: Neural Band gesture, the lens caption.
5. A clean 5-10 s of ambient room sound for the video's room tone.

## After the slot
- Log R1-R3 in `demo/rehearsals.md` (real rows only), closing M4 D5.
- Hand the footage to the video pipeline: one render command on the Mac, then check D4 (60-90 s).
- Re-run the final eval if new signer data was recorded with consent.
