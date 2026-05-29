// Thin client for the demo backend (submit -> poll -> status).
const API_BASE = (import.meta.env.VITE_API_BASE || 'http://127.0.0.1:8000').replace(/\/$/, '')

export async function startGeneration(text, voice) {
  const res = await fetch(`${API_BASE}/generate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text, ...(voice ? { voice } : {}) }),
  })
  if (!res.ok) {
    throw new Error(await readError(res, 'Could not start generation.'))
  }
  return res.json() // { job_id, status }
}

export async function fetchStatus(jobId) {
  const res = await fetch(`${API_BASE}/status/${jobId}`)
  if (!res.ok) throw new Error(await readError(res, 'Status check failed.'))
  return res.json() // { status, audio_url?, error? }
}

export function audioSrc(audioUrl) {
  return `${API_BASE}${audioUrl}`
}

async function readError(res, fallback) {
  try {
    const body = await res.json()
    const d = body.detail
    if (Array.isArray(d)) return d[0]?.msg || fallback
    if (typeof d === 'string') return d
  } catch {
    /* non-JSON error body */
  }
  return `${fallback} (${res.status})`
}
