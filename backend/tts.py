"""
Text-to-speech provider layer.

Stage 1 ships a local fake provider (a generated sine tone) so the whole
submit -> poll -> status pipeline is testable without an API key. Stage 2 adds
the real Qwen3-TTS call; the active provider is chosen automatically by whether
DASHSCOPE_API_KEY is set, so no calling code has to change.
"""

from __future__ import annotations

import asyncio
import io
import math
import os
import struct
import wave

import httpx


class TTSError(Exception):
    """Speech synthesis failed. The message is safe to surface to the client."""


def _is_real_configured() -> bool:
    key = os.getenv("DASHSCOPE_API_KEY", "").strip()
    return bool(key) and not key.lower().startswith("your-")


def active_provider() -> str:
    """Human-readable name of the provider that will handle the next request."""
    return "qwen3-tts-flash" if _is_real_configured() else "fake"


def _tone_wav(seconds: float = 1.2, freq: float = 440.0, sample_rate: int = 24000) -> bytes:
    """A short sine-tone WAV, so the Stage-1 pipeline returns real playable audio."""
    n = int(seconds * sample_rate)
    fade = max(1, int(0.01 * sample_rate))  # 10ms fade in/out to avoid clicks
    amp = 0.3 * 32767
    frames = bytearray()
    for i in range(n):
        env = min(1.0, i / fade, (n - i) / fade)
        sample = int(amp * env * math.sin(2 * math.pi * freq * i / sample_rate))
        frames += struct.pack("<h", sample)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)  # 16-bit
        w.setframerate(sample_rate)
        w.writeframes(bytes(frames))
    return buf.getvalue()


async def _fake_synthesize(text: str, voice: str) -> bytes:
    # Stand in for real generation latency so the poll / loading cycle is observable.
    await asyncio.sleep(2.0)
    return _tone_wav()


# Qwen3-TTS, DashScope international (Singapore) endpoint. Synchronous: the POST
# returns a short-lived URL to the generated WAV in the same response.
QWEN_ENDPOINT = (
    "https://dashscope-intl.aliyuncs.com/api/v1/services/aigc/"
    "multimodal-generation/generation"
)
QWEN_MODEL = "qwen3-tts-flash"


async def _qwen_synthesize(text: str, voice: str) -> bytes:
    """Call Qwen3-TTS and return the generated WAV bytes.

    We download the audio here (server-side) so the rest of the app only deals
    in raw bytes, and the upstream URL / API key never reach the browser.
    """
    api_key = os.getenv("DASHSCOPE_API_KEY", "").strip()
    if not api_key:
        raise TTSError("Server is missing DASHSCOPE_API_KEY.")

    payload = {
        "model": QWEN_MODEL,
        "input": {
            "text": text,
            "voice": voice,
            "language_type": os.getenv("QWEN_LANGUAGE_TYPE", "Auto"),
        },
    }
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(QWEN_ENDPOINT, json=payload, headers=headers)
    except httpx.RequestError as exc:
        raise TTSError("Could not reach the speech service. Please try again.") from exc

    if resp.status_code != 200:
        detail = ""
        try:
            body = resp.json()
            detail = body.get("message") or body.get("code") or ""
        except Exception:
            detail = resp.text[:200]
        raise TTSError(f"Speech service error ({resp.status_code}). {detail}".strip())

    data = resp.json()
    output = data.get("output") or {}
    audio = output.get("audio") or {}
    audio_url = audio.get("url")
    if not audio_url:
        raise TTSError(f"Speech generation failed: {data.get('message') or 'no audio in response.'}")

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            audio_resp = await client.get(audio_url)
            audio_resp.raise_for_status()
    except httpx.HTTPError as exc:
        raise TTSError("Generated audio could not be downloaded.") from exc

    return audio_resp.content


async def synthesize(text: str, voice: str) -> bytes:
    """Convert text to WAV audio bytes using the active provider."""
    if _is_real_configured():
        return await _qwen_synthesize(text, voice)
    return await _fake_synthesize(text, voice)
