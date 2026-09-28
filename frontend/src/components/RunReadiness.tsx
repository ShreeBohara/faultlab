import type { ReadinessStatus } from '../api'
import type { Resource } from '../useResource'

export function RunReadiness({ resource, onCheck }: { resource: Resource<ReadinessStatus>; onCheck: () => void }) {
  const value = resource.data
  const archive = value?.simulator.code === 'READ_ONLY_ARCHIVE'
  return <div className="run-readiness" aria-label="Run readiness">
    <div className="split-heading"><h3>Run readiness</h3><button className="text-button" disabled={resource.loading} onClick={onCheck}>Check run readiness</button></div>
    <p className="muted">Checks the local simulator and configuration without model calls. Saved evidence remains available independently.</p>
    {resource.loading && <p className="muted" role="status">Checking run readiness…</p>}
    {resource.error && <p className="error" role="alert">Run readiness could not be checked. {resource.error} Check again before starting work.</p>}
    {value && <>
      <p><strong>{archive ? 'Fresh execution disabled' : value.simulator.ready ? 'Simulator ready' : 'Simulator unavailable'}</strong> · {value.simulator.message}</p>
      {!value.simulator.ready && <p className="muted"><code>{value.simulator.code}</code></p>}
      {!archive && <p><strong>{value.live_configuration.ready ? 'Live configuration ready' : 'Live configuration incomplete'}</strong>{!value.live_configuration.ready && ' · offline reference runs do not require live configuration.'}</p>}
      {!!value.live_configuration.missing_fields.length && <p className="muted">Missing settings: {value.live_configuration.missing_fields.map((name, index) => <span key={name}>{index > 0 && ', '}<code>{name}</code></span>)}</p>}
      <p className="muted">Provider access has not been checked. This check made zero provider calls; configured values do not establish available credits or working provider access.</p>
      {resource.updatedAt && <p className="muted">Last checked {new Date(resource.updatedAt).toLocaleTimeString()}. Check again after changing local services or settings.</p>}
    </>}
  </div>
}
