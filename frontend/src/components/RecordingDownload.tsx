import { useRef, useState } from 'react'
import { api } from '../api'

export function RecordingDownload({ campaignId }: { campaignId: string }) {
  const locked = useRef(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  return <div className="recording-download">
    <button className="text-button" disabled={busy} onClick={async () => {
      if (locked.current) return
      locked.current = true; setBusy(true); setError(null)
      try {
        const recording = await api.recording(campaignId)
        const url = URL.createObjectURL(new Blob([JSON.stringify(recording, null, 2) + '\n'], { type: 'application/json' }))
        const anchor = document.createElement('a')
        anchor.href = url; anchor.download = `${campaignId}-development-recording.json`; anchor.click()
        window.setTimeout(() => URL.revokeObjectURL(url), 1000)
      } catch (error) { setError(error instanceof Error ? error.message : 'The recording could not be downloaded.') }
      finally { locked.current = false; setBusy(false) }
    }}>{busy ? 'Preparing recording…' : 'Download campaign recording'}</button>
    <p className="muted">Public development evidence, including unsuccessful attempts. This JSON archive does not run an experiment.</p>
    {error && <p role="alert" className="error">{error}</p>}
  </div>
}
