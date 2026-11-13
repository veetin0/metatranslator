# Brief

## Problem (one paragraph)
Deaf and hard-of-hearing signers and hearing non-signers struggle to talk in everyday moments (a classroom, a shop counter, a reception desk). Interpreters are scarce and must be booked; phone-based text is slow and breaks eye contact. The team wants "Signer": the hearing person wears Meta Ray-Ban Display glasses, whose first-person camera sees the signer; the system recognises signs (and facial expressions), turns them into text shown in the glasses' display and speaks them aloud via TTS. The brief says "through the classes" — read as classes/classrooms (a teacher or classmate understanding a deaf student), the most plausible pilot setting.

## Challenge owner — what they actually want
Meta wants the best *everyday* use case where the first-person view of AI glasses enables something a phone can't: hands-free, in-the-moment, beyond mirroring a phone screen. They want a clear problem and audience, a functional prototype and a deck, inclusive design for people with all abilities, consent and safe data practices, and a plausible path to adoption or a pilot. They explicitly want the prototype to handle permissions, errors, performance trade-offs, connectivity and device state changes. Display and audio-first, web apps and Device Access Toolkit (DAT) mobile integrations are on equal footing. Top teams may be invited to Meta's AI forum on 18 Nov 2026.

## Given
- Data: none supplied.
- APIs / SDKs / hardware: 10 × Meta Ray-Ban Display, 10 × Ray-Ban Meta Gen 2 (shared), Meta mentors for Web Apps and DAT (iOS, Android). Junction partner credits: Gemini API, OpenAI, Anthropic ($20/person), Modal ($100/person GPUs), Verda, Featherless, Cloudinary, MariaDB, etc. (see INVENTORY.md).
- Starter code: none.

## Deliverables and deadline
- Deadline (with time zone): 2026-11-15T10:00+02:00 (Helsinki) — ~38 h build window.
- Submission format: functional prototype + deck (per brief); Junction submission form (details not in material).
- Pitch / demo length: not stated.

## Assumptions we are making
- A1 — The demo runs on real Meta glasses on site; we also need a no-glasses fallback (laptop/phone camera) because devices are shared and may not be available at judging.
- A2 — Full continuous sign-language translation is an unsolved research problem; a credible prototype recognises a bounded vocabulary (classroom/everyday phrases + fingerspelling) reliably, and is honest about it.
- A3 — Sign language variant: ASL has the most public data/models; Junction is in Helsinki, so Finnish Sign Language (FinSL/viittomakieli) matters for the pilot story. We assume ASL for the model, FinSL as pilot roadmap, unless research shows otherwise.
- A4 — "Through the classes" means classroom setting.

## Ask the organisers
- Q1 — Submission format and pitch length? Is a demo video required?
- Q2 — Can the Ray-Ban Display camera stream be accessed by a web app, or only via DAT mobile integration? Frame rate/resolution limits?
- Q3 — Can a device be reserved for final judging/demo?
- Q4 — Are there Meta-specific consent/privacy requirements for recording bystanders (camera LED, etc.)?
