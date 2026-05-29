import { useEffect, useRef, useState } from 'react'
import { PlayIcon, PauseIcon, DownloadIcon, RefreshIcon } from './Icons.jsx'

// Deterministic pseudo-waveform bar heights (0.25 - 1.0) for the progress track.
const BARS = Array.from({ length: 48 }, (_, i) => {
  const v = Math.abs(Math.sin(i * 1.7) * 0.6 + Math.sin(i * 0.55 + 1) * 0.4)
  return 0.28 + (v - Math.floor(v)) * 0.72
})

function fmt(t) {
  if (!isFinite(t) || t < 0) return '0:00'
  const m = Math.floor(t / 60)
  const s = Math.floor(t % 60)
  return `${m}:${s.toString().padStart(2, '0')}`
}

export default function AudioPlayer({ src, downloadHref, onReset }) {
  const audioRef = useRef(null)
  const [playing, setPlaying] = useState(false)
  const [cur, setCur] = useState(0)
  const [dur, setDur] = useState(0)

  useEffect(() => {
    const a = audioRef.current
    if (!a) return
    const onTime = () => setCur(a.currentTime)
    const onMeta = () => setDur(a.duration)
    const onEnd = () => {
      setPlaying(false)
      setCur(0)
      a.currentTime = 0
    }
    a.addEventListener('timeupdate', onTime)
    a.addEventListener('loadedmetadata', onMeta)
    a.addEventListener('ended', onEnd)
    return () => {
      a.removeEventListener('timeupdate', onTime)
      a.removeEventListener('loadedmetadata', onMeta)
      a.removeEventListener('ended', onEnd)
    }
  }, [])

  const toggle = () => {
    const a = audioRef.current
    if (!a) return
    if (playing) {
      a.pause()
      setPlaying(false)
    } else {
      a.play().then(() => setPlaying(true)).catch(() => setPlaying(false))
    }
  }

  const seek = (e) => {
    const a = audioRef.current
    if (!a || !dur) return
    const rect = e.currentTarget.getBoundingClientRect()
    const frac = Math.min(1, Math.max(0, (e.clientX - rect.left) / rect.width))
    a.currentTime = frac * dur
    setCur(a.currentTime)
  }

  const progress = dur ? cur / dur : 0

  return (
    <div className="player">
      <audio ref={audioRef} src={src} preload="metadata" />
      <div className="player__top">
        <button className="player__play" onClick={toggle} aria-label={playing ? 'Pause' : 'Play'}>
          {playing ? <PauseIcon /> : <PlayIcon />}
        </button>
        <div
          className="player__wave"
          onClick={seek}
          role="slider"
          aria-label="Seek"
          aria-valuenow={Math.round(progress * 100)}
          aria-valuemin={0}
          aria-valuemax={100}
          tabIndex={0}
        >
          {BARS.map((h, i) => (
            <span
              key={i}
              className={`player__bar${i / BARS.length < progress ? ' is-filled' : ''}`}
              style={{ height: `${Math.round(h * 100)}%` }}
            />
          ))}
        </div>
        <div className="player__time">
          {fmt(cur)} / {fmt(dur)}
        </div>
      </div>
      <div className="player__actions">
        <a className="linkbtn" href={downloadHref} download="speech.wav">
          <DownloadIcon /> Download
        </a>
        <button className="linkbtn" type="button" onClick={onReset}>
          <RefreshIcon /> Generate again
        </button>
      </div>
    </div>
  )
}
