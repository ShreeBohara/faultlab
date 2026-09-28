import { useRef, useState } from 'react'
import { api, type ConfigStatus } from '../api'
import type { AgentRegistration, PolicyVersion, RegressionBundle, RegressionCase, RegressionExecution } from '../generated/contracts'
import { useResource } from '../useResource'
import { Badge, Empty, EpisodeLinks, Field, Hash, Json, Panel, ResourceNote } from './common'
import { matchingExecution, RegressionExecutionHistory } from './RegressionExecutionHistory'
const artifactLabels = { incident_fixture: 'Incident fixture', candidate_comparison: 'Candidate comparison', accepted_policy_bundle: 'Accepted policy bundle' }
export function RegressionControls({ cases, registrations, policies, config, replay, onEpisode }: { cases?: RegressionCase[]; registrations?: AgentRegistration[]; policies?: PolicyVersion[]; config?: ConfigStatus; replay: boolean; onEpisode: (id: string) => void }) {
  const [selected, setSelected] = useState(''); const [agent, setAgent] = useState(''); const [policy, setPolicy] = useState('')
  const [savedExecutionId, setSavedExecutionId] = useState(''); const [executionOrigin, setExecutionOrigin] = useState<'saved' | 'new'>('new')
  const [bundle, setBundle] = useState<RegressionBundle>(); const [execution, setExecution] = useState<RegressionExecution>(); const [busy, setBusy] = useState(false); const [error, setError] = useState<string | null>(null)
  const locked = useRef(false)
  const regression = cases?.find(c => c.regression_id === selected)
  const registration = registrations?.find(r => r.registration_id === agent)
  const running = useResource(execution && bundle && executionOrigin === 'new' ? `regression:${bundle.manifest_hash}:${execution.execution_id}` : null,
    async () => matchingExecution(await api.execution(execution!.execution_id), bundle!, execution!.execution_id))
  const latest = running.data ?? execution
  const bundledPolicies = bundle ? policies?.filter(p => p.content != null && p.policy_hash === bundle.policy_hash) ?? [] : []
  const allowedPolicies = bundledPolicies.filter(p => ['BASELINE', 'ACCEPTED', 'REJECTED', 'INCOMPLETE', 'NO_CHANGE'].includes(p.decision) && (bundle?.artifact_kind !== 'accepted_policy_bundle' || p.decision === 'ACCEPTED'))
  const selectedPolicy = allowedPolicies.find(p => p.version === policy)
  const displayedPolicy = selectedPolicy ?? allowedPolicies[0]
  // Legacy bundles omit the kind; use the same policy-based interpretation as the backend.
  const artifactKind = bundle?.artifact_kind ?? (displayedPolicy ? displayedPolicy.decision === 'ACCEPTED' ? 'accepted_policy_bundle' : displayedPolicy.decision === 'BASELINE' ? 'incident_fixture' : 'candidate_comparison' : undefined)
  const approvedProfile = config?.execution_profiles?.find(p => p.profile_id === bundle?.execution_profile_id)
  const readOnly = config?.data_store?.read_only === true
  const liveReady = !readOnly && !!config?.live_enabled && !!config.model_configured && !!approvedProfile
  const executionBlocked = replay || busy || !liveReady || !!config?.active_campaign_id || !registration || registration.dry_run_status !== 'PASSED' || !registration.budget_compatible || !selectedPolicy || latest?.status === 'RUNNING' || latest?.status === 'PENDING'
  async function loadBundle(download: boolean) {
    if (!regression || locked.current) return
    locked.current = true; setBusy(true); setError(null)
    try {
      const value = await api.bundle(regression.regression_id)
      if (value.bundle_id !== regression.bundle_id) throw new Error('The returned bundle does not match the selected regression.')
      setBundle(value); setExecution(undefined); setSavedExecutionId(''); setExecutionOrigin('new')
      if (download) { const url = URL.createObjectURL(await api.download(regression.regression_id)); const a = document.createElement('a'); a.href = url; a.download = `${value.bundle_id}.zip`; a.click(); window.setTimeout(() => URL.revokeObjectURL(url), 1000) }
    } catch (e) { setError(e instanceof Error ? e.message : 'Bundle read failed.') } finally { locked.current = false; setBusy(false) }
  }
  async function loadSavedExecution(executionId = savedExecutionId) {
    const expectedId = executionId.trim()
    if (!bundle || !expectedId || locked.current) return
    locked.current = true; setBusy(true); setError(null); setExecution(undefined); setExecutionOrigin('saved'); setSavedExecutionId(expectedId)
    try {
      setExecution(matchingExecution(await api.execution(expectedId), bundle, expectedId))
    } catch (e) { setError(e instanceof Error ? e.message : 'Saved execution read failed.') } finally { locked.current = false; setBusy(false) }
  }
  return <Panel title="Portable regression" number="08"><p className="muted">Inspect and download stored evidence, or explicitly execute a new regression in fresh synthetic worlds.</p>{!cases?.length ? <Empty>No regression bundle has been exported for this campaign.</Empty> : <><label>Saved regression<select value={selected} disabled={busy} onChange={e => { setSelected(e.target.value); setBundle(undefined); setExecution(undefined); setPolicy(''); setAgent(''); setSavedExecutionId(''); setExecutionOrigin('new'); setError(null) }}><option value="">Select a regression</option>{cases.map(c => <option value={c.regression_id} key={c.regression_id}>{c.artifact_kind ? artifactLabels[c.artifact_kind] : 'Saved regression'} · {c.regression_id} · {c.target_invariant}{!c.bundle_id ? ' · export pending' : ''}</option>)}</select></label><div className="controls"><button disabled={!regression?.bundle_id || busy} onClick={() => void loadBundle(false)}>Inspect saved bundle</button><button disabled={!regression?.bundle_id || busy} onClick={() => void loadBundle(true)}>Download regression</button></div></>}
    {bundle && <><dl className="facts"><Field name="Artifact">{artifactKind ? artifactLabels[artifactKind] : 'Saved regression (legacy)'}</Field><Field name="Scope">{bundle.scope ?? 'orders.upgrade_then_confirm/v1'}</Field><Field name="Execution profile">{bundle.execution_profile_id}</Field><Field name="Declared per-episode budget">{bundle.caps.actor_calls ?? '—'} actor calls · {bundle.caps.http_attempts ?? '—'} HTTP attempts · {bundle.caps.wall_seconds ?? '—'} seconds</Field><Field name="Manifest"><Hash value={bundle.manifest_hash} /></Field></dl><Json value={bundle} title="Saved bundle, full repeated trials and setup instructions" />{artifactKind === 'candidate_comparison' && <p className="notice">This comparison records a candidate test. Running it does not accept or promote the policy.</p>}{artifactKind === 'incident_fixture' && <p className="muted">This fixture lets you rerun a recorded failure. It does not claim an accepted repair.</p>}<RegressionExecutionHistory key={`${regression!.regression_id}:${bundle.manifest_hash}`} regressionId={regression!.regression_id} bundle={bundle} selectedId={executionOrigin === 'saved' ? execution?.execution_id ?? '' : ''} disabled={busy} onOpen={id => void loadSavedExecution(id)} /><div className="controls"><label>Saved execution ID<input value={savedExecutionId} disabled={busy} onChange={e => setSavedExecutionId(e.target.value)} placeholder="execution-…" /></label><button disabled={busy || !savedExecutionId.trim()} onClick={() => void loadSavedExecution()}>Open saved execution</button></div><p className="muted">An execution ID can also open a saved run directly. This does not start or resume a run. Open it again to refresh the saved status.</p><label>Reviewed agent<select value={agent} onChange={e => setAgent(e.target.value)}><option value="">Select registered agent</option>{registrations?.map(r => <option key={r.registration_id} value={r.registration_id} disabled={r.dry_run_status !== 'PASSED' || !r.budget_compatible}>{r.name} · {r.model} · {r.registration_id} · {r.provenance_class} · {r.dry_run_status}</option>)}</select></label><label>Immutable policy<select value={policy} onChange={e => setPolicy(e.target.value)}><option value="">Select policy version</option>{allowedPolicies.map(p => <option key={p.version} value={p.version}>{p.version} · {p.decision}</option>)}</select></label><p className="notice">Fresh execution can make bounded model and telemetry calls. It allocates new world and execution IDs. {registration?.provenance_class === 'internal_smoke' && 'This agent proves internal harness plumbing only.'}</p><button className="primary" disabled={executionBlocked} onClick={async () => { if (executionBlocked || !regression || locked.current) return; locked.current = true; setBusy(true); setError(null); try { setExecution(matchingExecution(await api.execute(regression.regression_id, agent, bundle.execution_profile_id, policy), bundle)); setExecutionOrigin('new') } catch (e) { setError(e instanceof Error ? e.message : 'Execution failed.') } finally { locked.current = false; setBusy(false) } }}>Run fresh regression ↗</button>{!liveReady && <p className="muted">{readOnly ? 'Fresh execution is disabled in this read-only archive.' : 'Fresh execution awaits configured live access.'}</p>}</>}
    <ResourceNote resource={running} />{latest && <article className="experiment"><h3>{executionOrigin === 'saved' ? 'Saved execution' : 'New execution'} · {latest.execution_id}</h3><Badge value={latest.mode} /> <Badge value={latest.status} /><dl className="facts"><Field name="Usage">{latest.usage.model_calls ?? 'Not recorded'} model calls · {latest.usage.http_attempts ?? 'Not recorded'} HTTP attempts</Field><Field name="Recorded trials">{latest.episode_ids.length}</Field><Field name="Recorded worlds">{latest.world_ids.join(', ') || 'Not allocated yet'}</Field></dl><EpisodeLinks ids={latest.episode_ids} onSelect={onEpisode} />{latest.stop_reason && <p>{latest.stop_reason}</p>}<Json value={latest} title="Execution budget and provenance" /></article>}{error && <p role="alert" className="error">{error}</p>}
  </Panel>
}
