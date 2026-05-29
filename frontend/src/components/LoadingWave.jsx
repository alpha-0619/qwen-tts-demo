// Animated waveform used as the loading indicator (on-theme for audio,
// gives a sense of "alive" progress without faking a percentage).
const BARS = 30

export default function LoadingWave() {
  return (
    <div className="loadwave" aria-hidden="true">
      {Array.from({ length: BARS }).map((_, i) => (
        <span
          key={i}
          className="loadwave__bar"
          style={{ animationDelay: `${(i * 0.045).toFixed(3)}s` }}
        />
      ))}
    </div>
  )
}
