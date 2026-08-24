# GlobeStudy Browser Extension (Chrome, MV3)

A quick-answer popup for international students. It calls the same citation API
as the web app — every answer shows its official sources, confidence, and risk
level, and refuses when there's no verified source.

## Features
- Ask box + **voice input** (Web Speech API mic button)
- Cited answers with confidence + risk badges and the high-stakes notice
- "No verified source" refusals with who-to-ask referrals (never guesses)
- Configurable **API base URL** (Settings), with a health-check button
- Demo fallback if the API is unreachable (clearly badged)

## Load it in Chrome (developer mode)
1. Deploy the API (see ../DEPLOY.md) or run it locally (`./run.sh api`).
2. Open `chrome://extensions`, toggle **Developer mode** (top right).
3. Click **Load unpacked** and select this `extension/` folder.
4. Click the puzzle icon → pin "GlobeStudy — Student Advisor".
5. Open the popup → ⚙️ → set the **API base URL** → Test connection → Save.

Works in Chrome and other Chromium browsers (Edge, Brave, Arc). Voice input
requires a Chromium browser with Web Speech support and microphone permission.

> Note: no custom toolbar icon is bundled (Chrome shows a default). Drop
> 16/48/128px PNGs in this folder and add an `"icons"` block to `manifest.json`
> if you want branded icons.
