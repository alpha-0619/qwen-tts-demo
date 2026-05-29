import { useCallback, useEffect, useRef, useState } from 'react'
import { startGeneration, fetchStatus, audioSrc } from './api.js'
import LoadingWave from './components/LoadingWave.jsx'
import AudioPlayer from './components/AudioPlayer.jsx'
import { WaveIcon, AlertIcon } from './components/Icons.jsx'

const MAX = 500
const POLL_MS = 1000
const TIMEOUT_MS = 60000
const PLACEHOLDER =
  'Type something and hear it spoken — e.g. Hi Kenji, this is a live Qwen text-to-speech demo.'

// phase: idle | submitting | generating | finishing | success | error
const STATUS_LABEL = {
  submitting: 'Submitting…',
  generating: 'Generating speech…',
  finishing: 'Almost there…',
}

export default function App() {
  const [text, setText] = useState('')
  const [phase, setPhase] = useState('idle')
  const [audioUrl, setAudioUrl] = useState(null)
  const [errorMsg, setErrorMsg] = useState('')
  const [elapsed, setElapsed] = useState(0)

  const pollRef = useRef(null)
  const timerRef = useRef(null)
  const startRef = useRef(0)

  const loading = phase === 'submitting' || phase === 'generating' || phase === 'finishing'
  const over = text.length > MAX

  const cleanup = useCallback(() => {
    if (pollRef.current) {
      clearInterval(pollRef.current)
      pollRef.current = null
    }
    if (timerRef.current) {
      clearInterval(timerRef.current)
      timerRef.current = null
    }
  }, [])

  useEffect(() => cleanup, [cleanup])

  const reset = () => {
    cleanup()
    setPhase('idle')
    setAudioUrl(null)
    setErrorMsg('')
    setElapsed(0)
  }

  const fail = (msg) => {
    cleanup()
    setErrorMsg(msg || 'Something went wrong. Please try again.')
    setPhase('error')
  }

  const generate = async () => {
    const t = text.trim()
    if (!t || t.length > MAX || loading) return

    cleanup()
    setAudioUrl(null)
    setErrorMsg('')
    setElapsed(0)
    setPhase('submitting')
    startRef.current = Date.now()
    timerRef.current = setInterval(() => setElapsed((Date.now() - startRef.current) / 1000), 100)

    let job
    try {
      job = await startGeneration(t)
    } catch (e) {
      fail(e.message)
      return
    }
    setPhase('generating')

    pollRef.current = setInterval(async () => {
      if (Date.now() - startRef.current > TIMEOUT_MS) {
        fail('Generation timed out. Please try again.')
        return
      }
      try {
        const s = await fetchStatus(job.job_id)
        if (s.status === 'completed') {
          cleanup()
          setAudioUrl(audioSrc(s.audio_url))
          setPhase('finishing')
          setTimeout(() => setPhase('success'), 350)
        } else if (s.status === 'error') {
          fail(s.error)
        }
        // pending / processing -> keep polling
      } catch {
        // transient network error -> keep polling until timeout
      }
    }, POLL_MS)
  }

  return (
    <main className="app">
      <div className="glow" aria-hidden="true" />
      <section className="card">
        <header className="card__head">
          <span className="wordmark">Qwen TTS</span>
          <span className="tag">live demo</span>
        </header>

        <label className="field">
          <span className="field__label">Text to speech</span>
          <textarea
            className="field__input"
            placeholder={PLACEHOLDER}
            value={text}
            onChange={(e) => setText(e.target.value)}
            maxLength={MAX + 100}
            rows={3}
            disabled={loading}
          />
          <span className={`counter${over ? ' is-over' : ''}`}>
            {text.length} / {MAX}
          </span>
        </label>

        <div className="state">
          {phase !== 'success' && phase !== 'error' && !loading && (
            <button className="btn" onClick={generate} disabled={!text.trim() || over}>
              <WaveIcon /> Generate Speech
            </button>
          )}

          {loading && (
            <div className="loading">
              <LoadingWave />
              <div className="loading__meta">
                <span className="loading__label">{STATUS_LABEL[phase]}</span>
                <span className="loading__time">{elapsed.toFixed(1)}s</span>
              </div>
            </div>
          )}

          {phase === 'success' && audioUrl && (
            <AudioPlayer src={audioUrl} downloadHref={audioUrl} onReset={reset} />
          )}

          {phase === 'error' && (
            <div className="errbox">
              <div className="errbox__row">
                <AlertIcon />
                <span>Couldn&apos;t generate audio.</span>
              </div>
              <p className="errbox__msg">{errorMsg}</p>
              <button className="btn btn--ghost" onClick={generate}>
                Try again
              </button>
            </div>
          )}
        </div>
      </section>
      <footer className="foot">Async generation · submit → poll → status</footer>
    </main>
  )
}
