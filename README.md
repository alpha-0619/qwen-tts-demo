# Qwen TTS — live demo

A small, production-shaped demo of async AI generation: type text, get speech back.
It focuses on the part that actually matters when a model takes time to respond — the
**submit → poll → status** flow and its loading / success / error states.

## The idea

Speech synthesis with Qwen3-TTS is fast, but every request is wrapped in an **async job**
on the backend:

```
POST /generate        → { job_id }              (returns immediately)
GET  /status/{job_id} → { status, audio_url? }  (the frontend polls this)
GET  /audio/{job_id}  → audio/wav               (proxied through the backend)
```

The frontend only ever speaks this job contract. That's the point: swap Qwen TTS for a
genuinely slow, asynchronous model (say, a 30–60s video generator) and **nothing on the
frontend changes** — the polling, the loading states and the error handling are already there.

Two deliberate choices:

- **The audio is proxied** through the backend (`/audio/{id}`) rather than handing the
  browser the upstream URL. This avoids mixed-content / CORS problems and keeps the upstream
  provider and the API key invisible to the client.
- **The API key lives only in a server-side environment variable** (`DASHSCOPE_API_KEY`) —
  never in the frontend, never in git.

## Stack

- **Backend** — FastAPI (Python), httpx, in-memory job store
- **Frontend** — React + Vite, hand-written CSS (no UI framework)
- **TTS** — Alibaba Cloud DashScope, `qwen3-tts-flash` (international endpoint)

## Project layout

```
backend/    FastAPI app — main.py (API + jobs), tts.py (provider)
frontend/   React + Vite app
```

## Run locally

**Backend** — without a key it serves a generated tone, so the whole pipeline works offline.

```bash
cd backend
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt   # Windows
.venv/Scripts/python -m uvicorn main:app --reload --port 8000
# (real speech: copy .env.example to .env and set DASHSCOPE_API_KEY)
```

**Frontend**

```bash
cd frontend
npm install
npm run dev   # http://localhost:5173
```

## Environment

| Where | Variable | Notes |
|---|---|---|
| backend | `DASHSCOPE_API_KEY` | DashScope (Singapore) key. Server-side only. |
| backend | `ALLOWED_ORIGINS` | CORS origins, comma-separated. `*` for dev. |
| frontend | `VITE_API_BASE` | Backend base URL. |

## Deploy

- **Backend** → Render (free): root dir `backend`, build `pip install -r requirements.txt`,
  start `uvicorn main:app --host 0.0.0.0 --port $PORT`, set `DASHSCOPE_API_KEY`.
- **Frontend** → Vercel (free): root dir `frontend`, set `VITE_API_BASE` to the backend URL.
