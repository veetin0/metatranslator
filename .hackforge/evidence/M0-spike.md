# M0 spike sheet: DAT glasses app go/no-go

Status: **not run on hardware.** The app (`glasses-app/ios`, runbook in `glasses-app/README.md`)
builds and was exercised against the Mock Device Kit only. Every row below stays `TODO` until
the lead runs it in glasses slot G1 and replaces `TODO` with `PASS` or `FAIL` and fills in the
result notes. The gate (D1) reads these rows and stays red until all six are filled in.

| Check | Result | What / pass criterion | Result notes |
|---|---|---|---|
| (a) | TODO | Glasses camera frames reach the phone at medium 504x896 at >= 7 fps (BirdSpotter only proves low/7). Read "Glasses frames/s" and "Frame size" in the app for 60 s. | |
| (b) | TODO | A DAT Display card ("Hello") is shown on the lens while the camera streams in the same `DeviceSession`; the stream keeps running. Log shows `display attach result: attached`. | |
| (c) | TODO | Phone TTS ("Speak test") is audible in the glasses speaker while streaming; audio route reads `BluetoothA2DPOutput`. | |
| (d) | TODO | Frames reach the laptop over USB tethering while the glasses stream (core sees >= 7 fps from the app), and captions come back and show on lens and phone. | |
| (e) | TODO | Fallback check: the Signer Web App hello (hud-web, task M0.2) installs via QR / `fb-viewapp://` and opens on the device. | |
| (f) | TODO | Latency sign end to lens (median of 5, ms) plus a 10 minute continuous-stream thermal note (glasses temperature, Thermal/Battery start vs end, errors, frames/s drift). | |

The result lines above are the only `PASS` or `FAIL` rows the gate counts.

## Decision

The decision line is written after G1, from the results above, once all six rows are filled in.
It will be one of the four outcomes below, written as a single line that begins with the word
Decision followed by a colon (`Decision: DAT Display|Fallback A|Fallback B|Fallback C`,
see DECISION.md "Fallbacks"):

- **DAT Display**: (a)-(d) pass; the camera stream and the DAT Display card run in one session,
  captions are drawn with DAT Display.
- **Fallback A**: DAT Display cannot run alongside the camera at the needed fps. Captions go to the
  Signer Web App on the glasses over WSS through the tunnel; the phone keeps the camera and TTS.
- **Fallback B**: no glasses frames (entitlement, freeze, no device). Phone back camera or webcam
  feeds the same core, captions stay on the glasses; labelled honestly on stage.
- **Fallback C**: no Display device. Ray-Ban Meta Gen 2, audio-only TTS.

If a `DeviceSessionError.CAPABILITY_DENIED` (or any capability refusal) appears, note the exact log
line here and report it to Meta immediately.

## Notes from the pre-hardware build (not results)

- Built with DAT 1.0.1 on Xcode 26.0.1 for the iOS Simulator; 64 unit tests pass.
- Against the Mock Device Kit (simulated Ray-Ban Display, bundled 504x896 clip, fake core): the session
  started, the camera streamed at 15 fps with 504x896 frames, the display attached next to the live
  camera and sent cards, frames and captions looped through the fake core. This says nothing about
  real glasses, Bluetooth bandwidth, the audio route or thermals.
