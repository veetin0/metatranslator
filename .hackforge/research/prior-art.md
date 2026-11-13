# Prior art, audience, consent (Part A)

Method: web searches on 2026-11-13. Secondary sources are marked (2nd). Items I could not verify are marked **NOT FOUND**. Do not quote unverified numbers in the deck.

## 1. Prior art

| Product / research | What it is | Lesson for Signer |
|---|---|---|
| SignAll | Camera-based ASL recognition. A 2025 overview (2nd) says SignAll rates itself "foundational" and suits short one-way messages (announcements, signage). Full conversation is a "future goal". [ezud overview](https://ezud.com/ai-sign-language-translation/) | Confirms bounded vocabulary is the honest scope. Shutdown/funding status: **NOT FOUND**. |
| Signapse | The reverse direction: text to avatar sign video (BSL), used by UK rail operators for station announcements (2nd, same overview). | Not competing. Avatars are the target of the WFD/WASLI criticism below. |
| Google SignGemma | DeepMind ASL-to-English on-device model, announced May 2025. Weights were not openly released and there is an access-interest form. Current status unclear, so **do not plan on it**. [forum thread](https://discuss.ai.google.dev/t/how-to-get-access-to-signgemma/106766), [Slator](https://tech.slator.com/?p=106104) | Shows the big labs are still not shipping. Signer should use open models (MediaPipe landmarks + our own classifier, or a VLM). |
| Hand Talk, KinTrans, Ava, PopSign | **NOT FOUND** in these searches. From memory only (unverified): Hand Talk is a Brazilian text-to-Libras avatar app; PopSign is a CMU/Georgia Tech ASL game that collected data; Ava is speech-to-text captioning. | Verify before citing. |
| Research limits | Signer-dependent evaluation can substantially overestimate sign translation ability [EMNLP Findings 2025](https://preview.aclanthology.org/new-sigs/2025.findings-emnlp.997/). BLEU-type metrics are poorly suited to sign translation [arXiv 2510.25434](https://arxiv.org/html/2510.25434v2). | We must evaluate on held-out signers, not just held-out clips. Report that number honestly. |
| Live-captioning glasses (the hearing→deaf direction) | Meta Ray-Ban Display has built-in **Live Captions**: speech to text in the lens, started from the glasses or the Meta AI app, language packs downloaded first [Meta help](https://www.meta.com/help/ai-glasses/23879220601763496/). The display leaks little light, so bystanders usually cannot read it (2nd, [Verge via scour](https://scour.ing/p/https://www.theverge.com/tech/801684/meta-ray-ban-display-review-smart-glasses-ai-wearables)). XRAI Glass is a caption platform (AR2 glasses $699, free offline tier). TranscribeGlass/AirCaps is a viral caption-glasses startup. [HearingTracker review](https://www.hearingtracker.com/resources/hear-with-your-eyes-five-ar-live-captioning-glasses), [Sci Am](https://www.scientificamerican.com/article/new-glasses-can-transcribe-speech-in-real-time/) | These all serve the **deaf wearer**. Signer inverts it: the **hearing wearer** understands a signer. Nobody covers this on the Ray-Ban Display. Sci Am notes sign-language-first communities see little need for caption glasses, and some fear interpreter requests being undercut. |
| Meta accessibility | Meta's accessibility post covers its AI glasses work, including Be My Eyes style use for blind users [Meta](https://about.fb.com/news/2025/05/advancing-accessibility-meta/). Details of the Be My Eyes integration were not re-checked. | Meta judges value inclusive use cases. Signer extends this to deaf signers. |

### What the deaf community says (verified)
- **WFD + WASLI statement on signing avatars (2018):** sign languages have their own grammar, so word-for-word is impossible. Sign language work must be led by deaf people. Concern about projects built without deaf leadership. [WASLI](https://wasli.org/news/wfd-wasli-statement-use-signing-avatars/), [WFD](https://wfdeaf.org/?p=7496)
- **WFD 2025 conference:** workshop checklist for judging sign language AI: data ownership, community involvement, transparency, real-world performance (2nd, via search summary; primary page not opened).
- **efsli** (European interpreters' forum) calls for deaf leadership and ethically sourced data, and for AI to supplement, not replace, interpreters. [efsli](https://efsli.org/?p=30895)
- **EUD:** position paper "Sign Language in the Era of AI" (2025). [PDF](https://eud.eu/wp-content/uploads/2025/07/Sign-Language-in-the-Era-of-Artificial-Intelligence.pdf). Not read in detail.
- **Academic:** "Deaf in AI" (De Meulder 2025): AI language tech risks eroding deaf linguistic rights [link](https://ojs.letras.up.pt/index.php/LLLD/article/view/14775). "Lessons in co-creation" [arXiv 2408.13171](https://arxiv.org/pdf/2408.13171). Microsoft Research on US deaf community views of automatic translation [link](https://microsoft.com/en-us/research/?p=979521).
- **Kuurojen Liitto (Finland):** no position on AI sign translation found. Their 2027 election theses discuss interpreting access and do not mention AI. [PDF](https://kuurojenliitto.fi/wp-content/uploads/2026/06/Kuurojen_liitto_eduskuntavaaliteesit_2027_fi.pdf). **NAD statement: NOT FOUND.**

### Design response (use in deck and UI)
1. **Frame as a bridge for the hearing person's moment of need**, never an interpreter replacement. Show a visible line: "Quick everyday phrases. For medical, legal and exams, book an interpreter." (efsli, WFD stance.)
2. **Two-way by default:** the signer sees the hearing wearer's speech as captions (use Ray-Ban Display Live Captions, or mirror to a signer-facing phone/tablet card). This also answers "makes the deaf person do the work".
3. **Signer in control:** consent card they tap/sign; they can correct or reject any output (a "no, not that" sign or a button on their screen); they see what the glasses think they said.
4. **Trust UI:** per-phrase confidence; low confidence shows "?" and the wearer is asked to confirm instead of the system speaking a guess. Bounded vocabulary is disclosed up front.
5. **Deaf involvement:** say honestly that we did not co-design with deaf users in 36 h. Make "co-design with Kuurojen Liitto / a school for the deaf" the first pilot step, and give the signer ownership of any data. Do not claim deaf endorsement.
6. **Language honesty:** ASL (open data) in the demo, FinSL as pilot roadmap. FinSL data is scarce (**no public FinSL recognition dataset found**). Say this plainly.

## 2. Audience and pilot

- **FinSL users in Finland:** estimates conflict. About 4,000–5,000 deaf/hard-of-hearing signers plus an estimated 6,000–9,000 hearing signers (government bill HE 294/2014) [eduskunta](https://www.eduskunta.fi/valtiopaivaasiakirjat/HE+294/2014). Kuurojen Liitto 2024: FinSL is the mother tongue of 3,000–4,000 deaf people. EUD lists "FinSL 5,000" [EUD](https://eud.eu/member-countries/finland/). **Use "roughly 3,000–5,000 deaf FinSL signers" and cite the range.** These are population estimates, not census counts.
- **Interpreters (Finland):** 819 sign language interpreters and 3,987 service users in 2016, with Kela planning cuts to about 500 interpreters through tendering [Eduskunta KK 241/2017](https://www.eduskunta.fi/pdf/KK+241/2017+vp?lang=fi) (as summarised by search; figures are old). Orders keep growing, and 79% of written-interpreting orders were fulfilled in Jan–Sep 2018 (2019 parliamentary question). Evenings and weekends are hard to cover [MTV](https://www.mtvuutiset.fi/artikkeli/kuuroilta-kritiikkia-palvelujen-leikkauksista-se-ei-voi-olla-oikein/9044040). Kuurojen Liitto says getting an interpreter is uncertain and service cuts hurt users [STT](https://www.sttinfo.fi/tiedote/70659396/kuurojen-palveluja-leikattu-kovalla-kadella-perusoikeudet-jo-vaarantuneet?lang=fi). **No current (2024-26) interpreter count: NOT FOUND.** EU-wide shortage stats: **NOT FOUND.**
- **Kela interpreter service:** statutory service under the disability services law. Hours are limited and need booking [Kela](https://www.kela.fi/yhteistyokumppanit-vammaisten-tulkkauspalvelu-palveluntuottajille-palvelukuvaus-ja-tulkkaustuotteet). Signer fills the **unbooked, ad hoc gap** (corridor chat, front desk, a classmate), not the booked-interpreter slot.
- **Classroom inclusion:** no Finnish statistics found (**NOT FOUND**). The pitch story: a deaf pupil with an interpreter still cannot talk to classmates in breaks and group work.
- **Plausible pilot partners (suggestions, none contacted):**
  1. Kuurojen Liitto (Finnish Association of the Deaf): sets the co-design process and FinSL data ethics.
  2. A school with deaf pupils (e.g. a Helsinki-area school or a Valteri-type national support school): classroom/peer use.
  3. University accessibility services (Aalto, University of Helsinki): service desk plus lecturers.
  4. A public library or city service desk (Oodi): bounded phrase set, hearing staff wear glasses.
  Pilot design: 1 site, bounded vocabulary of ~50 desk/class phrases, 4 weeks, success = comprehension rate and signer-rated "accurate/respectful" score.

## 3. Consent and data practice

- **GDPR:** biometric data used to *uniquely identify* a person is special-category (Art. 9). Recognising sign gestures is not identification, so design the system to **not identify** (no face recognition, no signer profile). Keep that distinction in the deck, but treat it as an argument, not legal advice. Regulators are active: the EDPB says makers cannot push transparency duties onto wearers; the Hamburg regulator found Ray-Ban Meta bystander warnings too dim; CNIL issued an alert on 11 May 2026 (all 2nd-source: [ppc.land EDPB](https://ppc.land/edpb-says-smart-glasses-makers-cant-rely-on-wearers-to-meet-gdpr-duties/), [ppc.land Hamburg](https://ppc.land/hamburg-regulator-finds-ray-ban-meta-glasses-expose-bystanders-without-consent/), [gdprlocal](https://gdprlocal.com/smart-glasses-and-gdpr/)). Primary EDPB/Hamburg documents not read. Not legal advice.
- **Privacy LED:** Meta says the LED shows when media is saved; the Hamburg finding says it may not light in some situations. So **do not rely on the LED as consent**. Use an explicit consent step.
- **Pose landmarks vs video:** extract hand/face/body landmarks (e.g. MediaPipe) on-device or on the paired phone and discard frames immediately. Landmarks are not recognisable video, so less sensitive, but face-mesh landmarks can still be personal data, so treat them as personal data anyway.
- **Recommended practice (state these as the prototype's behaviour):**
  1. No storage by default; frames held in RAM, dropped after landmark extraction. No cloud upload of video. If a cloud model is used, send landmarks or short text only. Say it plainly if this is not true.
  2. **Consent gesture:** signer must show an agreed sign (or tap a phone "consent card" in their own language) before recognition starts. Show a visible "Signer is ON" state to the signer (phone card/tablet) and a clear stop sign/button.
  3. Auto-stop on timeout, glasses removed, or connectivity lost (covers the D3 "device state changes" requirement).
  4. Signer can see exactly what is shown/spoken, and can veto it.
  5. Minimal logs: counts only, no content, unless the signer opts in.
  6. Demo-day scope: volunteer signer consent in writing, and a sign at the table.
