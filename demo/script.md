# Live demo script (target 2:00 on stage, hard stop 2:30)

Uses only the 20 PopSign signs from `data/VOCAB.md` (HELLO BYE YES NO PLEASE THANKYOU WAIT FINISH POTTY WATER
WHERE WHY WHO TIME BOOK LISTEN TALK HOME SICK HAPPY). Captions below are the exact template-mode output of
`core/signer_core/language/template.py` (fluent mode off on stage: deterministic).

**Roles.** Signer (Deaf volunteer or team member, consent form signed) stands 1-1.5 m from the Wearer, facing them,
hands at chest height, plain background behind. Presenter narrates and holds the clicker. Card on a tablet in the
signer's hand; Card screen mirrored to the projector if possible.

**Pace.** One sign, hands down to REST for about 1 s, next sign. After the phrase, hands down and wait for the
caption before the next phrase. If a caption comes back amber ("?"), the wearer does not speak it; signer repeats once.

## Phrases

| # | Signs (gloss) | Expected lens caption | Start | Sign | Caption + speak | Ends |
|---|---|---|---|---|---|---|
| 0 | (signer taps **Start** on the card) | "Signer ON" state, ON light on the card | 0:00 | — | — | 0:10 |
| 1 | HELLO | Hello. | 0:10 | 3 s | 4 s | 0:17 |
| 2 | WHERE BOOK | Where is the book? | 0:17 | 5 s | 5 s | 0:27 |
| 3 | PLEASE WAIT | Please wait. | 0:27 | 5 s | 5 s | 0:37 |
| 4 | WHERE POTTY | Where is the bathroom? | 0:37 | 5 s | 5 s | 0:47 |
| 5 | WATER PLEASE | Water, please. | 0:47 | 5 s | 5 s | 0:57 |
| 6 | THANKYOU BYE | Thank you, bye! | 0:57 | 5 s | 5 s | 1:07 |
| 7 | (signer taps **Stop** on the card) | ON light off; lens goes quiet | 1:07 | — | — | 1:12 |

"Caption + speak" = time for the caption to show, the wearer to tap to speak it, and the phrase to play.
The presenter fills 1:12-2:00 with the card (history with the ticks) and the honest-numbers slide.

## Narration cues (presenter, while the signer signs)
- 0:00 "The signer taps Start. Nothing is on before they say so."
- 0:17 "The wearer just looks at the signer. The caption is on the lens; a tap speaks it."
- 0:37 "Frames never leave the laptop's memory; only the words do."
- 1:07 "The signer taps Stop. It's off."

## Backup phrases (swap in if a main phrase fails twice in rehearsal)

| Replaces | Signs (gloss) | Expected lens caption |
|---|---|---|
| 2 or 4 | TIME | What time is it? |
| 3 | YES | Yes. |
| 5 | SICK | I feel sick. |
| 5 | HAPPY | I'm happy. |
| 6 | BYE | Bye! |
| any | LISTEN | I'm listening. |
| any | FINISH | I'm finished. |

## If something fails on stage
- **Amber "?" or "Didn't catch that"**: say "It tells us when it isn't sure", signer repeats once, then move on.
- **Two misses in a row**: drop to the backup phrase for that slot.
- **Core down / glasses off chip**: say what the chip says ("it shows its state, it never guesses"), switch the
  projector to the backup video (`video/out/demo.mp4`, M4-hw) and continue narrating.
- **No audio**: the caption still shows; say "the speech plays through the glasses speaker" and continue.

Timings are a plan until R1-R3 in `demo/rehearsals.md` replace them with measured times.
