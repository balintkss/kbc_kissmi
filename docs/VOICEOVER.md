# Voice-over for ElevenLabs (paste one block per clip)

Generated from `docs/DEMO_SCRIPT.md`. Target ≈ 150 words/min; each clip must fit its slot. Words in *[brackets]* in the script are already removed here.

## Clip 1 · 0:00–0:11 · 11 s slot · 29 words (≈ 12 s at 150 wpm)

Your bank sees every payment you make, and still treats you like a stranger. You fill in forms, you explain yourself again, and every page shows you every option.

## Clip 2 · 0:11–0:31 · 20 s slot · 52 words (≈ 21 s at 150 wpm)

Meet Lotte, 29, from Ghent. She never told KBC she bought a car. Kate+ worked it out from a garage payment in June and the fuel after it. Ninety percent confident, with the proof, transaction by transaction. And it knows what a car implies: maintenance, road tax, insurance at Ethias, not KBC.

## Clip 3 · 0:31–0:46 · 15 s slot · 36 words (≈ 14 s at 150 wpm)

The app doesn't sell her anything. It plans, and warns her early: before payday she'd dip below zero, so move €1,170 from savings. On payday: bills, a car reserve, savings, and €151 a week to spend.

## Clip 4 · 0:46–1:05 · 19 s slot · 49 words (≈ 20 s at 150 wpm)

Same page on the website. A stranger gets three options. Lotte gets one: mini-omnium, and the reason. It fits a second-hand car, and we can quote in two minutes because we already know it. App, website, adviser: Kate+ uses one governed memory, through one API, for the same answer.

## Clip 5 · 1:05–1:26 · 21 s slot · 54 words (≈ 22 s at 150 wpm)

Now she asks Kate+, in Dutch: can I afford a €1,200 trip in August? No salary, no rent, no savings typed in. Kate+ runs on GPT-4.1, like KBC's Kate, but never does the maths herself. A tool computes on Lotte's governed financial memory, and only hers. Yes: from savings, with her three-month buffer intact.

## Clip 6 · 1:26–1:41 · 15 s slot · 43 words (≈ 17 s at 150 wpm)

This synthetic scenario tests a family journey. In production, KBC never deduces a birth or health information from a payment. Julien first chooses to confirm a household change; then Kate can offer a relevant next step in French. The customer stays in control.

## Clip 7 · 1:41–1:55 · 14 s slot · 35 words (≈ 14 s at 150 wpm)

Marc is self-employed. His income swings almost fifty percent month to month. So his plan is built on a quiet month, and it warns him early: a slow month leaves him €388 short. Help first.

## Clip 8 · 1:55–2:22 · 27 s slot · 71 words (≈ 28 s at 150 wpm)

Behind it: 5,000 twins, built in about 80 seconds on one laptop core, zero LLM calls. When money is tight, we stay quiet: 102 sales messages held back. Jens, a student, was in the red 46 of the last 90 days. His insurance offer is held back; he gets help moving a bill instead, and the advisor sees the same context. All 2.3 million customers: about 20 minutes on 32 cores.

## Clip 9 · 2:22–2:35 · 13 s slot · 31 words (≈ 12 s at 150 wpm)

And when the twin is wrong (Marc has a cat, not a dog), he just says: that's not me. The fact stops driving anything, and his plan updates on the spot.

## Clip 10 · 2:35–2:45 · 10 s slot · 20 words (≈ 8 s at 150 wpm)

Kate+ gives every customer one governed financial memory, across every channel: help before sales, and a glass box you control.

**Total: 420 words ≈ 2.80 min at 150 wpm — at ElevenLabs speed 1.05–1.1 it lands around 2:35–2:45.**

## ElevenLabs settings

- **Tool:** Text to Speech (one clip at a time), or Studio (paste all clips, one paragraph each, export per paragraph).
- **Voice:** one calm, clear English narrator voice from the Voice Library; keep the same voice and settings for every clip.
- **Model:** the latest multilingual model offered in your account.
- **Settings:** Stability ≈ 50 %, Similarity ≈ 75 %, Style 0, Speaker boost on, **Speed 1.05–1.1** if a clip overruns its slot.
- **Pronunciation:** if it stumbles, write numbers out ("eleven thousand five hundred euros", "GPT four point one", "KBC" as "K B C").
- **Export:** MP3 44.1 kHz (or WAV), named `clip01.mp3` … `clip10.mp3`.
- **Disclosure:** add a small end-card line "Voice-over generated with ElevenLabs" (partner tech; also mention it in the README).
