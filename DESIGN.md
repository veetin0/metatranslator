# Signer design system (frozen with CONTRACTS.md; only a contract change moves it)

**Feel:** calm, plain and trustworthy. Signer is a communication aid, not a gadget: the words are the interface, and the system always says how sure it is.
Base: ui-ux-pro-max "Minimalism & Swiss" (accessibility profile), adapted for two very different surfaces.

## Surfaces
1. **Lens** — what the hearing wearer sees on Meta Ray-Ban Display. Built twice from the same spec: DAT Display cards (`glasses-app/`) and the Web App mirror (`hud-web/`, 600×600). **Additive display: black is transparent**, only light is drawn, and the wearer is looking at a person, so the lens stays nearly empty.
2. **Signer Card** — the web page the Deaf signer holds (`card/`, phone/tablet, served by the core). Light theme, large touch targets, readable at arm's length.

## Palette
### Lens (on pure black `#000000`, which renders as transparent)
| Token | Hex | Use |
|---|---|---|
| `--lens-bg` | `#000000` | background, always |
| `--lens-text` | `#FFFFFF` | confirmed caption (≥ 0.80) |
| `--lens-unsure` | `#FFB020` | "?" tier (0.50–0.80): amber caption + top-2 |
| `--lens-dim` | `#9AA4B2` | "Didn't catch that", footer readout, state text |
| `--lens-on` | `#34D399` | ON dot only (8 px) |
| `--lens-alert` | `#FF6B6B` | core down / permission denied, icon + word, never fill |
No filled panels, no gradients, no large bright areas (they wash out the wearer's view and cost battery). Outline at most 2 px.

### Card (light)
| Token | Hex | Use |
|---|---|---|
| `--color-primary` | `#1E40AF` | Start button, links, focus ring |
| `--color-on-primary` | `#FFFFFF` | text on primary |
| `--color-accent` | `#16A34A` | "Translation ON" light, ✓ |
| `--color-on-accent` | `#000000` | |
| `--color-destructive` | `#DC2626` | Stop, ✗, delete taught sign |
| `--color-on-destructive` | `#FFFFFF` | |
| `--color-warn` | `#B45309` | "?" tier text on light bg (4.5:1 on white) |
| `--color-background` | `#EFF6FF` | page |
| `--color-card` | `#FFFFFF` | panels |
| `--color-foreground` | `#1E3A8A` | body text |
| `--color-muted` | `#E9EFF5` | history rows |
| `--color-muted-foreground` | `#475569` | timestamps, helper text |
| `--color-border` | `#BFDBFE` | |
Every state is shown with **word + icon + colour**, never colour alone.

## Type
- **Lens:** system sans (`-apple-system, "SF Pro", Roboto, "Noto Sans", sans-serif`), no web fonts (Web App first load < 300 KB). Caption 40 px / 600 weight, line-height 1.2, max 2 lines × ~24 chars, then the oldest line drops. Top-2 alternatives 28 px. Footer/state 22 px. Nothing under 22 px.
- **Card:** Figtree (headings 600) + Noto Sans (body 400/500), self-hosted woff2 subset in `card/fonts/` (the card must work offline on the laptop's network); system sans fallback. Body 18 px, line-height 1.5; sentence in history 22 px; headings 28/22 px.

## Layout
- **Lens (600×600):** caption block anchored to the lower-middle (y 300–500), centred, 48 px side margins. State line top-left (ON dot + "Signer ON"), readout footer bottom-centre ("17/19 confirmed"). Everything else black. D-pad focus order: state → caption → footer actions (Web App only).
- **Card:** single column, max-width 560 px, mobile-first. Order: consent block (big Start / Stop, ON light) → latest translation (glosses, sentence, confidence word) with ✓ / ✗ / Not right → reply captions from the wearer → history → Teach a sign → privacy note + QR.

## Spacing and radius
Spacing scale 4, 8, 12, 16, 24, 32, 48 px. Radius: 12 px panels, 999 px pills/buttons. Touch targets ≥ 56×56 px on the card (≥ 44 minimum), 12 px apart. Start/Stop is ≥ 72 px tall, full width.

## Components
- **Consent button:** one at a time — Start (primary) when off, Stop (destructive) when on. Stop never needs a confirm.
- **ON light:** green dot + "Translation ON — camera in use, nothing recorded". Off: grey dot + "Translation OFF".
- **Caption tiers:** confirmed = white text (lens) / foreground (card) + "✓ sure"; unsure = amber + "?" + top-2 choices, not spoken; none = dim "Didn't catch that".
- **State chips** (lens + card): Connecting…, ON, Paused, Glasses off, Permission denied, Core down, Link slow. Icon + word.
- **Feedback buttons:** ✓ Right / ✗ Wrong / "Not right" (veto, removes the caption from the lens).
- Icons: Lucide SVG inline. No emoji as icons (the ✓/✗ glyphs above are text labels in buttons with words).

## Motion
Lens: caption fade-in 150 ms, no movement, no flashing; updates throttled ≥ 500 ms (DAT sends replace the whole screen). Card: 200 ms colour/opacity transitions only. `prefers-reduced-motion` → no transitions.

## Avoid
- Filled or bright panels on the lens, white backgrounds on the lens, scrolling text, more than 2 caption lines.
- Speaking or showing an "unsure" caption as if it were certain.
- Colour-only states, placeholder-only labels, icons without labels.
- Partner logos or "Meta-endorsed" style claims.
- Gradients, glassmorphism, decorative illustration.
