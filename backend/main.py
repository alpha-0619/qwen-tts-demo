"""
Qwen TTS demo - FastAPI backend.

An async job API wrapped around (synchronous) text-to-speech generation:

    POST /generate        -> { job_id, status }
    GET  /status/{job_id} -> { status, audio_url? , error? }
    GET  /audio/{job_id}  -> audio/wav bytes

Why a job/poll layer for a synchronous TTS call: it gives the frontend one
API-agnostic submit -> poll -> status-display contract. Qwen TTS happens to
resolve in a few seconds, but the same contract drives the genuinely-async
video models (Seedance / Kling, 30-60s) with no frontend change.

Audio is proxied through this backend (see /audio) instead of handing the
upstream pre-signed URL to the browser. That avoids mixed-content / CORS issues
and never exposes the upstream provider or the API key to the client.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
import uuid
from collections import defaultdict, deque
from pathlib import Path

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from tts import TTSError, active_provider, synthesize

# Load backend/.env regardless of the process working directory.
load_dotenv(Path(__file__).with_name(".env"))

logger = logging.getLogger("qwen_tts_demo")
logging.basicConfig(level=logging.INFO)

MAX_TEXT_LEN = 500
DEFAULT_VOICE = "Cherry"

app = FastAPI(title="Qwen TTS Demo API", version="1.0.0")

# CORS: comma-separated origins via env, "*" for local dev.
_origins = [o.strip() for o in os.getenv("ALLOWED_ORIGINS", "*").split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory job store. Fine for a single-instance demo; swap for Redis / a DB
# if this ever needs to scale to multiple instances.
JOBS: dict[str, dict] = {}
_tasks: set[asyncio.Task] = set()

# Simple in-memory per-IP rate limit on /generate (the quota-consuming endpoint).
# Stops anyone with the URL from hammering the API key's free quota.
RATE_LIMIT = 20  # max generations...
RATE_WINDOW = 60.0  # ...per this many seconds, per client IP
_hits: dict[str, deque] = defaultdict(deque)


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()  # real client IP behind Render's proxy
    return request.client.host if request.client else "unknown"


def _rate_limited(ip: str) -> bool:
    now = time.monotonic()
    hits = _hits[ip]
    while hits and now - hits[0] > RATE_WINDOW:
        hits.popleft()
    if len(hits) >= RATE_LIMIT:
        return True
    hits.append(now)
    return False


# Optional usage notification: ping a Telegram chat when the demo is used.
# Set TELEGRAM_BOT_TOKEN to enable; throttled to one ping/minute so a burst
# can't flood the chat.
_last_notify = [0.0]


async def _notify_telegram(text_preview: str, ip: str) -> None:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        return
    now = time.monotonic()
    if now - _last_notify[0] < 60.0:
        return
    _last_notify[0] = now
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "5314183916").strip()
    message = f"\U0001f514 Qwen TTS demo used\nIP: {ip}\nText: {text_preview[:80]}"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            await client.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": chat_id, "text": message},
            )
    except Exception:
        pass  # a notification failure must never affect the demo


class GenerateRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=MAX_TEXT_LEN)
    voice: str = Field(default=DEFAULT_VOICE)


class GenerateResponse(BaseModel):
    job_id: str
    status: str


async def _run_job(job_id: str, text: str, voice: str) -> None:
    JOBS[job_id]["status"] = "processing"
    try:
        audio = await synthesize(text, voice)
        JOBS[job_id].update(status="completed", audio=audio, content_type="audio/wav")
    except TTSError as exc:
        JOBS[job_id].update(status="error", error=str(exc))
    except Exception:  # last-resort guard: never leak internals to the client
        logger.exception("job %s failed", job_id)
        JOBS[job_id].update(status="error", error="Generation failed. Please try again.")


@app.get("/health")
async def health():
    return {"ok": True, "provider": active_provider()}


@app.post("/generate", response_model=GenerateResponse)
async def generate(req: GenerateRequest, request: Request):
    ip = _client_ip(request)
    if _rate_limited(ip):
        raise HTTPException(status_code=429, detail="Too many requests. Please wait a minute and try again.")
    text = req.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="Text must not be empty.")
    job_id = uuid.uuid4().hex
    JOBS[job_id] = {"status": "pending", "audio": None, "content_type": None, "error": None}
    task = asyncio.create_task(_run_job(job_id, text, req.voice or DEFAULT_VOICE))
    _tasks.add(task)  # keep a strong ref so the task isn't GC'd mid-flight
    task.add_done_callback(_tasks.discard)

    ntask = asyncio.create_task(_notify_telegram(text, ip))  # fire-and-forget usage ping
    _tasks.add(ntask)
    ntask.add_done_callback(_tasks.discard)

    return {"job_id": job_id, "status": "pending"}


@app.get("/status/{job_id}")
async def status(job_id: str):
    job = JOBS.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Unknown job id.")
    resp = {"status": job["status"]}
    if job["status"] == "completed":
        resp["audio_url"] = f"/audio/{job_id}"
    elif job["status"] == "error":
        resp["error"] = job["error"]
    return resp


@app.get("/audio/{job_id}")
async def audio(job_id: str):
    job = JOBS.get(job_id)
    if not job or job["status"] != "completed" or not job["audio"]:
        raise HTTPException(status_code=404, detail="Audio not available.")
    return Response(content=job["audio"], media_type=job["content_type"] or "audio/wav")
