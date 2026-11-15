# Signer: stats and info for the pitch video

Numbers come from `eval/results/` (checked by `deck/check_numbers.py`), except the speed numbers, which come from our glasses test.

## Headline accuracy

- **95% top-1 on 24 everyday signs** (99% top-3). 7,995 clips, 5 folds where the test signers never appear in training. (`m8_confusion.json`)
- **98.6% right when it's sure.** Of the guesses it is at least 80% confident about, 98.6% are correct. That covers 91% of signs. The rest show in amber with a "?" and are never spoken as if certain.
- **84% on a different camera it never trained on.** 203 WLASL clips. Accuracy went from 52% to 84% after adding ASL Citizen data. When it was sure, it was 96% right. (`m5_wlasl_eval.json`)
- **Baseline:** a nearest-neighbour model scored 51%, so the BiGRU network roughly doubles it. Chance is 1 in 24.

## Speed on the glasses

- On the same Wi-Fi: about **23 frames per second**, **66 ms median frame delay**, **0 of 1,290 frames dropped**.
- Camera stream: 504×896 at 24 fps.
- Captions appear after a short rest at the end of each sign. This is deliberate, so it doesn't cut people off.
- Don't quote the delay over mobile data and the tunnel. That link was bad (up to 1.1 s early on, 53 of 270 frames dropped).

## Privacy (strong selling point)

- The model only sees hand and body points, not stored video. Frames are never written or uploaded.
- The signer starts and stops translation from their own card. An "ON" light shows when the camera is in use.
- No face ID and no signer profile. Taught signs are deleted in one tap.

## Build facts

- A real iOS app on Meta's Wearables Device Access Toolkit (DAT). It uses the glasses camera, the 600×600 lens display and the speaker.
- A browser demo runs the same model on the visitor's own device, with nothing uploaded.
- Data: about 8,000 PopSign clips plus ASL Citizen and WLASL. Only the derived landmarks are kept.

## Say it carefully

- **Glasses-camera accuracy is not measured at scale.** We have 93% on 28 held-out glasses reps, but the same people trained it, so call it "early". For a live test, have someone else sign facing the wearer from 1–2 m in good light.
- **It's 24 signs, not ASL grammar.** Say "everyday phrases", never "fluent translation".
- **It doesn't replace an interpreter.** For medical, legal and exams, book one.
- **ASL Citizen and WLASL are non-commercial research data.** Credit them, and don't pitch the model as a commercial product.
- A "number of Deaf people worldwide" stat needs a cited source. None is verified in the repo.

## Story beats (comedic, one arc)

1. **Hook:** "Where's the book?" has no interpreter. Typing on a phone turns a talk into passing notes.
2. **Reveal:** the caption appears on the lens while the signer is still looking at the wearer.
3. **Honest-numbers payoff:** 95% overall, 98.6% when sure, and amber when it isn't. Joke idea: "it would rather say 'um?' than lie".
4. **Close:** the pilot is one classroom, one Deaf student, two weeks.

## Credits line

PopSign ASL v1.0, Georgia Tech / Deaf Professional Arts Network (Thad Starner et al.), CC BY 4.0. Also ASL Citizen (Microsoft and Boston University) and WLASL, both non-commercial research use only.
