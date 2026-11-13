# Signer

ASL → English captions and speech for the hearing wearer of Meta Ray-Ban Display glasses. A Deaf person signs; the glasses camera sees it, a laptop core recognises the signs, and the wearer reads the sentence on the lens and hears it. Everyday phrases only: for medical, legal and exam settings, book an interpreter.

> Skeleton: sections are filled in as milestones land. Contracts: `.hackforge/CONTRACTS.md`. Design: `DESIGN.md`.

## How it works
<!-- M1–M2: data flow diagram, consent, confidence tiers -->

## Run it
```bash
python -m pip install -e "core[dev]"
python -m signer_core.relay            # core on :8000, Signer Card at http://<laptop>:8000/
cd hud-web && npm install && npm run preview -- --host 127.0.0.1 --port 4173   # lens preview in the Display Simulator
```
iOS app: open `glasses-app/ios/Signer.xcodeproj` (Xcode ≥ 26.4), set the core URL in Settings.

## Tests
`bash .hackforge/gate.sh`

## Results
<!-- M4: numbers from eval/results/final.json only -->

## Privacy
Frames stay on the phone and laptop, in memory only, and are dropped after landmark extraction. Nothing is recorded. Start/Stop on the Signer Card is consent.

## Credits
PopSign ASL v1.0 (CC BY 4.0). Meta Wearables Device Access Toolkit and Web Apps.
