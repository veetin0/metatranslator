# Options

Two architects (lean profile), one generalist judge (Meta wearables product/engineering persona, sonnet). Full designs: `options/safe-winner.md`, `options/ambitious.md`.

| Option | Summary |
|---|---|
| A — Signer: Class Bridge (safe winner) | Hearing teacher/classmate in Ray-Ban Display understands 24 classroom ASL signs (+REST): caption in lens + TTS. Signer Card (tablet web page) for consent, ON light, history, "Not right" veto, captions of the wearer's replies. Android DAT thin phone → Python Signer Core on laptop (MediaPipe → kNN/GRU → gloss→English). |
| B — Signer Duet (ambitious) | Same pipeline, 40 signs, true two-way loop, Duet card on the signer's own phone, Teach-a-sign in 30 s, NMM question/negation flags, Neural Band confirm, fingerspelling, Gemini verifier, live accuracy readout. |

## Judge scores (realistic, discounted for integration risk; self-scores in brackets)
| | A Class Bridge | B Duet |
|---|---|---|
| J1 Creativity & use case | 6 (7) | 8 (9) |
| J2 Technical execution | 7 (8) | 5 (7) |
| J3 Real-world value & feasibility | 7 (7) | 7 (8) |
| J4 UX: input, accessibility, trust | 8 (9) | 8 (9) |
| **Weighted average** | **7.0** | **7.0** |
| Feasibility | 8 | 5.5 |
| Expected (avg × feasibility/10) | 5.6 | 3.9 |

Rule check: no R violation in either. Notes: Gemini clip verifier sends video to the cloud (undercuts R3 claim) → cut. Sign-based consent/stop depends on the recogniser → card button must be the guaranteed path. Webcam/phone-camera fallback weakens R2 → dev/backup only.

## Grafts from B into A (judge)
1. Minimal Teach-a-sign (label + 5 repetitions → kNN prototypes, "delete my taught signs").
2. Live honesty readout from ✓/✗ taps ("session: 17/19 confirmed").
3. Gloss-only LLM validator (reject sentences adding content words; raw glosses always shown).
4. Consent mechanics: QR to open card, auto-stop after 2 min idle, consent reset on STOPPED, "Link slow, sign slower" chip.
5. "Type reply" fallback when mic/STT is denied.
6. Keep A's 24-sign vocabulary and cut order.

## Likely to fail live (dropped)
Neural Band input (experimental API), negation flag, sign-based consent, fingerspelling, Gemini verifier, 8 kHz DAT mic STT, triggering thermal/battery states on demand.
