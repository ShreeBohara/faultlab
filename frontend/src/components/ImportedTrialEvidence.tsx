import { api, object } from '../api'
import type { Episode, TrialResult } from '../generated/contracts'
import type { ImportedBundle, ImportedExecution } from '../bundleImports'
import { useResource } from '../useResource'
import { Badge, Empty, Field, Json, ResourceNote } from './common'
import { RecordingDownload } from './RecordingDownload'

export function faultExposure(verdict: unknown, scheduled?: boolean, triggered?: boolean, expectedFaults?: number): string {
  if (object(verdict) && Array.isArray(verdict.fault_executions)) {
    const faults = verdict.fault_executions.filter(item => object(item) && item.scheduled !== false)
    if (!faults.length) return scheduled || expectedFaults ? 'Scheduled · exposure record unavailable' : 'No scheduled faults'
    if (expectedFaults !== undefined && faults.length !== expectedFaults) return `Exposure record incomplete · ${faults.length} / ${expectedFaults} faults recorded`
    const count = faults.filter(item => object(item) && item.triggered === true).length
    return count === faults.length ? `Fully triggered · ${count} / ${faults.length}` : count ? `Partially triggered · ${count} / ${faults.length}` : `None triggered · 0 / ${faults.length}`
  }
  return !scheduled ? 'No scheduled faults' : triggered ? 'Fully triggered' : 'Not fully triggered · counts unavailable'
}
function OutcomeTable({ trials, episodes }: { trials: TrialResult[]; episodes: Record<string, unknown>[] }) {
  // Outcome and exposure lead so they stay visible at phone width; long IDs come last.
  return <div className="import-trials"><table><thead><tr><th>Recorded outcome</th><th>Fault exposure</th><th>Historical trial ID</th></tr></thead><tbody>{trials.slice(0, 20).map(trial => {
    const episode = episodes.find(value => value.episode_id === trial.episode_id)
    return <tr key={trial.episode_id}><td data-label="Recorded outcome"><Badge value={trial.outcome ?? trial.lifecycle} /></td><td data-label="Fault exposure">{faultExposure(episode?.verdict, trial.fault_scheduled, trial.fault_triggered)}</td><td data-label="Historical trial ID"><code>{trial.episode_id}</code></td></tr>
  })}</tbody></table>{trials.length > 20 && <p className="muted">Showing 20 of {trials.length} historical trials. All records are available below.</p>}</div>
}
export function ImportedHistoricalEvidence({ bundle }: { bundle: ImportedBundle }) {
  const recording = bundle.historical.recording
  const episodes = recording && Array.isArray(recording.episodes) ? recording.episodes.filter(object) : []
  const counts = bundle.historical.trials.reduce<Record<string, number>>((all, trial) => { const status = trial.outcome ?? trial.lifecycle; all[status] = (all[status] ?? 0) + 1; return all }, {})
  return <section aria-label="Imported historical evidence"><h3>Original bundled evidence</h3><p className="notice">Imported historical observations; not verified locally. Importing an ACCEPTED source decision does not accept or activate a policy here.</p>
    <p className="muted">{bundle.historical.trials.length} historical trials{Object.entries(counts).map(([name, count]) => ` · ${count} ${name.toLowerCase().replaceAll('_', ' ')}`).join('')}. These IDs belong to the source recording, not local fresh episodes.</p>
    {!!bundle.historical.trials.length && <OutcomeTable trials={bundle.historical.trials} episodes={episodes} />}
    <Json value={bundle.historical.trials} title="All original repeated trial results" />
    {recording ? <Json value={recording} title="Original bundled reports, events and provenance" /> : <Empty>No original development recording is included in this bundle.</Empty>}
  </section>
}
type ArtifactKind = ImportedBundle['artifact_kind']
/** One plain sentence saying whether this fresh result is the expected one for its artifact kind. */
export function freshVerdict(kind: ArtifactKind, value: ImportedExecution): string | null {
  const assertions = value.assertions
  if (!assertions) return null
  const required = typeof assertions.required_trials === 'number' ? assertions.required_trials : 3
  const valid = typeof assertions.valid_trials === 'number' ? assertions.valid_trials : 0
  const failures = typeof assertions.target_failures === 'number' ? assertions.target_failures : 0
  const check = typeof assertions.target_invariant === 'string' ? assertions.target_invariant : 'target'
  if (value.execution.status !== 'COMPLETED' || valid < required)
    return `No verdict: only ${valid} of ${required} fresh trials were valid, so this run neither confirms nor rules out the ${kind === 'incident_fixture' ? 'incident' : 'policy result'}.`
  if (kind === 'incident_fixture')
    return assertions.reproduced === true
      ? `Incident reproduced as expected in ${failures} of ${required} fresh trials: this regression still catches the ${check} failure.`
      : `Incident did not reproduce in every trial (${failures} of ${required} fresh trials violated ${check}); with this target the regression no longer reliably catches it.`
  return failures === 0
    ? `The bundled policy prevented the ${check} violation in all ${required} fresh trials. This is one fresh check, not local acceptance.`
    : `The bundled policy did not prevent the ${check} violation in ${failures} of ${required} fresh trials.`
}
export function ImportedFreshEvidence({ value, artifactKind, faultCount, onEpisode }: { value: ImportedExecution; artifactKind: ArtifactKind; faultCount: number; onEpisode: (owner: string, episode: string) => void }) {
  const execution = value.execution
  const verdict = freshVerdict(artifactKind, value)
  const charges = value.owner_charges
  const key = `${execution.execution_id}:${execution.status}:${execution.episode_ids.join(',')}`
  const episodes = useResource(execution.episode_ids.length ? key : null, async () => {
    const loaded = await Promise.all(execution.episode_ids.map(id => api.episode(id)))
    if (loaded.some((episode, index) => episode.episode_id !== execution.episode_ids[index] || episode.campaign_id !== value.owner_campaign_id || episode.configuration_hash !== value.target.configuration_hash || episode.agent_registration_id !== value.target.agent_registration_id)) throw new Error('Fresh trial identity does not match this imported execution target.')
    return loaded
  }, execution.status === 'RUNNING' || execution.status === 'PENDING' ? 1500 : null)
  return <section aria-label="Fresh imported execution evidence"><h3>Fresh execution · {execution.execution_id}</h3><Badge value={execution.status} />
    <dl className="facts compact"><Field name="Actual target agent">{value.target.agent}</Field><Field name="Actual target model">{value.target.model}</Field><Field name="Target registration"><code>{value.target.agent_registration_id}</code></Field><Field name="Target configuration"><code>{value.target.configuration_hash}</code></Field><Field name="Recorded trial usage">{execution.usage.model_calls ?? 0} model calls · {execution.usage.http_attempts ?? 0} HTTP attempts</Field>{charges && <Field name="Charged to its accounting ledger">{charges.model_calls} model requests (includes any transport retries; at most {charges.request_ceiling}) · {charges.reserved_model_calls} still reserved · {charges.actual_cost_dollars == null ? (charges.model_calls ? 'cost unknown' : 'no cost') : `$${charges.actual_cost_dollars.toFixed(4)}`}</Field>}<Field name="Fresh worlds">{execution.world_ids.join(', ') || 'Not allocated yet'}</Field></dl>
    <p className="muted">Accounting campaign: <code>{value.owner_campaign_id}</code>. The target identity above identifies these trials; the accounting campaign is not the tested agent.</p>
    {execution.stop_reason && <p className="notice">{execution.stop_reason}</p>}
    {value.error && <div role="alert" className="error">FaultLab could not finish this execution. This infrastructure error is separate from an agent rule violation.<Json value={value.error} title="Saved execution error" /></div>}
    {value.trial_errors && <div className="error">Saved trial diagnostics include lab integrity failures; these are separate from consistent agent mistakes.<Json value={value.trial_errors} title="Fresh trial integrity diagnostics" /></div>}
    <ResourceNote resource={episodes} />
    {!!episodes.data?.length && <div className="import-trials"><table><thead><tr><th>Fixed outcome</th><th>Fault exposure</th><th>Effects</th><th>Fresh trial</th></tr></thead><tbody>{episodes.data.map((episode: Episode) => <tr key={episode.episode_id}><td data-label="Fixed outcome"><Badge value={episode.verdict?.outcome ?? episode.lifecycle ?? 'NOT_RUN'} /></td><td data-label="Fault exposure">{episode.verdict ? faultExposure(episode.verdict, faultCount > 0, undefined, faultCount) : 'No exposure verdict recorded'}</td><td data-label="Effects">{episode.verdict ? `${episode.verdict.upgrade_effects} upgrade / ${episode.verdict.notification_effects} confirmation` : 'No verdict recorded'}</td><td data-label="Fresh trial"><button className="text-button" onClick={() => onEpisode(value.owner_campaign_id, episode.episode_id)}>{episode.episode_id}</button></td></tr>)}</tbody></table></div>}
    {!execution.episode_ids.length && <Empty>No fresh trials have been recorded.</Empty>}
    {verdict && <p className="notice fresh-verdict"><strong>{verdict}</strong></p>}
    {value.assertions ? <><p className="muted">Fresh execution assertions describe these new trials. They do not verify imported source evidence or promote a policy.</p><dl className="facts compact">{typeof value.assertions.reproduced === 'boolean' && <Field name="Target violation reproduced">{value.assertions.reproduced ? 'Yes, in these fresh trials' : 'Not established'}</Field>}{typeof value.assertions.valid_trials === 'number' && <Field name="Valid fresh trials">{value.assertions.valid_trials} / {String(value.assertions.required_trials ?? 'not recorded')}</Field>}{typeof value.assertions.target_failures === 'number' && <Field name="Fresh target violations">{value.assertions.target_failures}</Field>}</dl><Json value={value.assertions} title="Fresh regression assertions" /></> : <p className="muted">No final fresh-trial assertions have been recorded.</p>}
    <Json value={value} title="Fresh execution identity, budget and provenance" />
    <RecordingDownload campaignId={value.owner_campaign_id} label="Download fresh execution recording" />
  </section>
}
