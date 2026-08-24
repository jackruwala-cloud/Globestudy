# Deploying the API (the "brain")

The front-ends (Lovable web app, Chrome extension) call this FastAPI service.
Locally it runs on `http://localhost:8000`, which cloud-hosted front-ends can't
reach — so pick one of the paths below to give it a public URL, then paste that
URL into the app/extension **Settings → API base URL**.

All deploy files live in this folder (`intl-student-advisor/`). Treat this
folder as the repo/service root.

---

## Option A — Render.com (recommended, ~2 minutes, free tier)

1. Put this folder in a GitHub repo (this folder as the repo root).
2. On https://render.com → **New +** → **Blueprint** → select the repo.
   Render reads [`render.yaml`](render.yaml) and provisions a Python web service that:
   - installs `api/requirements-api.txt`
   - runs `python -m ingestion.build_index` (builds the knowledge base)
   - starts `uvicorn api.main:app` on Render's `$PORT`
   - health-checks `/health`
3. When it's live, copy the service URL (e.g. `https://globestudy-api.onrender.com`).
4. In the app/extension Settings, set **API base URL** to that URL.
5. (Recommended) In Render → the service → Environment, set `ALLOWED_ORIGINS`
   to your app origin(s), e.g. `https://your-app.lovable.app`, and redeploy.

> Free tier note: the service sleeps when idle and takes a few seconds to wake
> on the first request. Fine for testing; upgrade for production.

## Option B — Railway / any Docker host

- Railway: New Project → Deploy from repo. It detects the [`Dockerfile`](Dockerfile)
  (or the [`Procfile`](Procfile)). Set `ALLOWED_ORIGINS` in Variables. Railway
  provides `$PORT` automatically.
- Any Docker host / Fly.io:
  ```bash
  docker build -t globestudy-api .
  docker run -p 8000:8000 -e ALLOWED_ORIGINS="*" globestudy-api
  ```

## Option C — Dev tunnel (fastest, no cloud account)

Expose your already-running local API publicly for testing:

```bash
# cloudflared (no account needed for quick tunnels)
cloudflared tunnel --url http://localhost:8000

# or ngrok (needs a free authtoken once)
ngrok http 8000
```

Copy the public `https://…` URL it prints into Settings → API base URL.
(Neither `cloudflared` nor `ngrok` is installed here yet — install via Homebrew:
`brew install cloudflared` or `brew install ngrok`.)

---

## After deploying

- Verify: open `https://<your-api-url>/health` — you should see JSON with
  `"status":"ok"`.
- Lock down CORS: set `ALLOWED_ORIGINS` to your real front-end origin(s) instead
  of `*`.
- If you enable LLM mode (`qa.mode: llm`), set `ANTHROPIC_API_KEY` as an
  environment variable on the host — never commit it.
