import type { ReactNode } from 'react'
import type { Resource } from '../useResource'
import { safeEvidenceUrl } from '../api'

export const labels: Record<string, string> = {
  COMPLETED: 'Completed', VIOLATION: 'Violation', SAFE_UNRESOLVED: 'Safe unresolved', CORRECTLY_REJECTED: 'Correctly rejected', LAB_ERROR: 'Lab error', INTERRUPTED: 'Interrupted', NOT_RUN: 'Not run', CREATED: 'Created', RUNNING: 'Running', SCORING: 'Scoring', IDLE: 'Ready to start', WAITING_EVIDENCE: 'Waiting for evidence', STOPPED: 'Stopped', NO_CHANGE: 'No change', PROPOSED: 'Proposed', ACCEPTED: 'Accepted', REJECTED: 'Rejected', INCOMPLETE: 'Incomplete', BASELINE: 'Baseline', PENDING: 'Pending', UNVERIFIED: 'Unverified', FAILED: 'Failed', PASSED: 'Passed', UNSUPPORTED: 'Unsupported', local_only: 'Local only', local_recorded: 'Locally recorded', weave_pending: 'Weave pending', weave_error: 'Weave unsynced', weave_verified: 'Weave verified', offline_fixture: 'Offline reference smoke', live: 'Live provider execution', replay: 'Recorded playback', FLAKY: 'Flaky', LOCALLY_MINIMAL: 'Reduced within tested operations', REDUCED: 'Reduced', NO_REDUCTION: 'No reduction', PASSED_OBSERVED: 'Passed observed trials', COUNTEREXAMPLE_FOUND: 'Counterexample found', INCONCLUSIVE: 'Inconclusive', internal_smoke: 'Internal smoke — not external validation', external: 'Independent external source', reference: 'Reference implementation', POLICY_GAP: 'POLICY_GAP', CONTRACT_EVIDENCE_GAP: 'CONTRACT_EVIDENCE_GAP', FRESH_SANDBOX: 'Fresh sandbox execution', RECORDED_PLAYBACK: 'Recorded playback', VALIDATE_ONLY: 'Validation only', SUPPORTED: 'Supported', CONTRADICTED: 'Contradicted',
}
export const label = (value: string) => labels[value] ?? value.replaceAll('_', ' ').toLowerCase()
export function Badge({ value }: { value: string }) { return <span className={`badge badge-${value.toLowerCase()}`}>{label(value)}</span> }
export function Panel({ title, number, children, className = '', aside }: { title: string; number?: string; children: ReactNode; className?: string; aside?: ReactNode }) {
  return <section className={`panel ${className}`}><div className="panel-heading"><h2>{number && <span className="section-number">{number}</span>}{title}</h2>{aside}</div>{children}</section>
}
export function Empty({ children }: { children: ReactNode }) { return <p className="empty">{children}</p> }
export function ResourceNote({ resource }: { resource: Resource<unknown> }) { return resource.error ? <p role="alert" className="error">{resource.data ? 'Stale data · ' : ''}{resource.error} Retrying with backoff.</p> : resource.loading ? <p className="muted" role="status">Loading stored evidence…</p> : null }
export function Json({ value, title = 'Inspect stored record' }: { value: unknown; title?: string }) { return <details className="json"><summary>{title}</summary><pre>{JSON.stringify(value, null, 2)}</pre></details> }
export function Field({ name, children }: { name: string; children: ReactNode }) { return <div><dt>{name}</dt><dd>{children ?? 'Not recorded'}</dd></div> }
export function Hash({ value }: { value?: string | null }) { return <code className="hash">{value ?? 'Not recorded'}</code> }
export function EpisodeLinks({ ids, onSelect }: { ids: string[]; onSelect: (id: string) => void }) {
  return ids.length ? <div className="episode-links">{ids.map((id, i) => <button className="text-button" key={`${id}:${i}`} onClick={() => onSelect(id)} title={id}>{id}</button>)}</div> : <span className="muted">No trials recorded</span>
}
export function EvidenceLink({ url, children }: { url?: string | null; children: ReactNode }) { const safe = safeEvidenceUrl(url); return safe ? <a href={safe} target="_blank" rel="noreferrer">{children} ↗</a> : <span className="muted">{children} · unavailable</span> }
