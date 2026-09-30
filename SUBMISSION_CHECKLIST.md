# Submission checklist

Go through this **before** pressing submit on Builderbase. Rule: *final means final* — no code or submission edits afterwards.

Owner: **A** = backend/Claude side, **B** = frontend teammate, **Both** = check together.

## 1. Repository (rules: public, accessible until judging is done)

- [ ] **Make the repo public**: `gh repo edit balintkss/kbc_kissmi --visibility public --accept-visibility-change-consequences` (currently **PRIVATE**) — Both
- [ ] Open the repo link in an **incognito window** and confirm it loads without login — Both
- [ ] Everything is pushed: `git status` clean and `git log origin/main -1` = your last local commit — Both
- [ ] Tag the submitted version: `git tag submission && git push origin submission` — A
- [ ] No commits after the submission (judges assess the submitted version) — Both
- [ ] Optional: delete `hello_world.txt` or keep it — nobody minds, just decide — Both

## 2. No secrets or private data (rules: "never upload passwords, API keys or confidential data")

- [x] Database (`data/*.db`, 323 MB) is git-ignored — checked
- [x] `data/demo_credentials.txt` is git-ignored — checked
- [x] `.env` is git-ignored; only `.env.example` with placeholders is committed — checked
- [x] Secret scan of full git history: no GitHub/Anthropic/Google keys or passwords — checked
- [ ] **Re-run the scan right before submitting** (new commits since): 
      `git log --all -p | grep -inE "sk-proj-|sk-[A-Za-z0-9]{20}|gho_|ghp_|sk-ant|AIza|api_key *=|password *=" ` — A
- [ ] OpenAI key only in the git-ignored `.env` (backend), never hard-coded, never in frontend code — A
- [ ] **Revoke the OpenAI key after the hackathon** (it was shared in a chat transcript) — A
- [ ] No GCP credentials (they're personal and valid 1 week) in any file, screenshot or video — Both
- [ ] Demo video and screenshots don't show demo passwords, tokens, or your terminal with env vars — Both
- [ ] All customer data is synthetic — say so in README and video (already in README) — Both

## 3. Aikido security audit (10% of the score)

- [ ] Aikido account created via the hackathon link, **Continue with GitHub** — owner of the repo (balintkss) or someone with access
- [ ] Repo connected to Aikido — Both
- [ ] **Baseline scan run → screenshot BEFORE** (save it immediately) — Both
- [ ] Fix findings (focus: IDOR, authentication, authorization, business logic) — A
- [ ] Mark fixed issues as **resolved** in Aikido — A
- [ ] Re-scan → **screenshot AFTER** — Both
- [ ] Any finding you consciously don't fix: one line in README "Known issues" explaining why — A
- [ ] Run the scan **before** the frontend freeze too — the frontend adds its own attack surface (XSS, token storage) — B

## 4. It actually works (judging: "Technical ability — does it work?")

- [ ] **Fresh clone test** on the teammate's laptop, following only the README "Run it" section, start to finish — B
- [ ] `requirements.txt` complete (fastapi, uvicorn, pandas, httpx, + LLM SDK once added) — A
- [ ] `python -m twin.evaluate` output matches the numbers in the README — A
- [ ] Demo personas 1–4 each log in and show a sensible highlight, plan and push — Both
- [ ] Anonymous vs. logged-in page difference is visible in the demo — B
- [ ] Customer correction ("that's not me") works in the UI — B
- [ ] Chat (pull) answers in the customer's language and uses twin context — A
- [ ] No crash on edge cases in the demo path (wrong password, expired token, unknown topic) — Both
- [ ] If there's a hosted demo: link works from a phone on mobile data — Both

## 5. README (rules: explain project, how to run, anything unfinished)

- [ ] Concept + USP understandable in 30 seconds (top of README) — Both
- [ ] Run instructions correct after the last changes (frontend start command added) — B
- [ ] "Status / unfinished" section honest and up to date — A
- [ ] Team members named — Both
- [ ] Mention partner tech used (Google Cloud / ElevenLabs / Cursor) if used — Both
- [ ] Links in README work (demo video, hosted demo if any) — Both

## 6. Demo video (< 3 minutes)

- [ ] **Under 3:00** — check the actual file length — Both
- [ ] Story: problem → Lotte's twin (car from fuel purchases) → payday push → one highlighted product with the reason → anonymous vs logged-in → the pull chat → scale (5K twins in 80 s, accuracy table, 2.3M story) — Both
- [ ] Shows the real running product, not only slides — Both
- [ ] Audio understandable; captions if possible — Both
- [ ] Uploaded as **unlisted** (not private) YouTube/Drive with "anyone with the link" — open in incognito to verify — Both
- [ ] Clearly labelled as a concept prototype with synthetic data — Both

## 7. Builderbase form

- [ ] Short description (2–3 sentences: the twin, "you never have to explain yourself", one-highlight across channels, scales to 2.3M) — Both
- [ ] Demo video link — Both
- [ ] GitHub repo link (public!) — Both
- [ ] Aikido screenshots: before **and** after — Both
- [ ] All fields filled under Overview; one team member submits, one project per team — Both
- [ ] Every link in the form opened once in incognito — Both

## 8. Fit with the judging criteria (sanity check)

- [ ] **Creativity** — we pitch the twin/context layer, not "categorize transactions + recommend a product"
- [ ] **Technical** — working API + UI, measurable accuracy, runs from a clean clone
- [ ] **Fit** — answers the 5 KBC questions: signals, recognition, auto-adaptation, across channels, at scale
- [ ] **Security** — Aikido before/after, no secrets, IDOR-safe by design

## 9. Timing

- [ ] Code freeze **30 min before the deadline** (video + form take longer than expected) — Both
- [ ] Submit with **≥ 10 min buffer** — Both
- [ ] After submitting: don't push, keep repo public until judging is complete — Both
