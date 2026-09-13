import { useRef, useState } from 'react'
import { api, safeEvidenceUrl, type AriaInput } from '../api'
export function AriaEvidenceForm({ campaignId, disabled }: { campaignId: string; disabled: boolean }) {
  const [mode, setMode] = useState<'automatic' | 'manual'>('automatic')
  const [status, setStatus] = useState<AriaInput['status']>('UNVERIFIED')
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const locked = useRef(false)
  return <details className="aria-form"><summary>Capture observed Aria evidence</summary><p className="muted">Record actual W&B automation history and attributed analysis. This form saves a pointer; it never invokes Aria. The backend requires a matching registered campaign run and automation.</p><form onSubmit={async e => {
    e.preventDefault(); if (locked.current) return
    const form = new FormData(e.currentTarget)
    const get = (name: string) => String(form.get(name) ?? '').trim()
    const nullable = (name: string) => get(name) || null
    setError(null); setMessage(null)
    for (const name of ['history_url', 'output_url']) { if (get(name) && !safeEvidenceUrl(get(name))) { setError('Evidence links must use HTTPS on wandb.ai or weave.wandb.ai with an actual record path.'); return } }
    locked.current = true; setBusy(true)
    try {
      await api.saveAria(campaignId, { run_id: get('run_id'), automation_id: get('automation_id'), invocation_mode: mode, provenance: 'manual_ui_capture', status, execution_id: nullable('execution_id'), observed_at: new Date(get('observed_at')).toISOString(), thread_id: nullable('thread_id'), history_url: nullable('history_url'), output_url: nullable('output_url'), summary: get('summary'), recorder: get('recorder') })
      setMessage('Attributed capture saved. Manual capture is not independent remote verification.')
    } catch (error) { setError(error instanceof Error ? error.message : 'Capture failed.') } finally { locked.current = false; setBusy(false) }
  }}><fieldset disabled={disabled || busy}><div className="two-fields"><label>Invocation<select value={mode} onChange={e => { setMode(e.target.value as typeof mode); if (e.target.value === 'manual' && status === 'COMPLETED') setStatus('UNVERIFIED') }}><option value="automatic">Automatic automation</option><option value="manual">Manual chat fallback</option></select></label><label>Observed status<select value={status} onChange={e => setStatus(e.target.value as typeof status)}><option value="UNVERIFIED">Unverified</option><option value="PENDING">Pending</option><option value="COMPLETED" disabled={mode === 'manual'}>Completed automatic execution</option><option value="FAILED">Failed</option></select></label></div><div className="two-fields"><label>Actual run ID<input name="run_id" required /></label><label>Automation ID<input name="automation_id" required /></label><label>Execution ID<input name="execution_id" required={status === 'COMPLETED'} /></label><label>Thread ID<input name="thread_id" required={status === 'COMPLETED'} /></label></div><label>Automation history URL<input name="history_url" type="url" placeholder="https://wandb.ai/…" required={status === 'COMPLETED'} /></label><label>Analysis output URL<input name="output_url" type="url" placeholder="https://wandb.ai/…" required={status === 'COMPLETED'} /></label><label>Attributed analysis<textarea name="summary" rows={3} required maxLength={20000} /></label><div className="two-fields"><label>Observed at (local time)<input type="datetime-local" name="observed_at" required /></label><label>Recorded by<input name="recorder" required /></label></div><button type="submit">{busy ? 'Saving capture…' : 'Save evidence capture'}</button></fieldset></form>{message && <p className="notice" role="status">{message}</p>}{error && <p className="error" role="alert">{error}</p>}</details>
}
