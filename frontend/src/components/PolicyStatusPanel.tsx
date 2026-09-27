import { getPolicyStatus, unseenResult } from '../policyStatus'
import type { CampaignPolicyStatus, StudyPolicyStatus } from '../policyStatus'
import { useResource } from '../useResource'
import { Hash, Panel, ResourceNote } from './common'

const developmentLabels = { QUALIFIED: 'Qualified on development cases', NOT_QUALIFIED: 'Not qualified', REPLAY_ONLY: 'Replay only', INCOMPLETE: 'Incomplete' }

function StatusColumns({ study, active }: { study?: StudyPolicyStatus; active: CampaignPolicyStatus['active_policy'] }) {
  return <div className="policy-status-columns">
    <section aria-label="Development qualified"><h3>Development qualified</h3>
      <p className={`policy-status-value ${study?.development.status === 'QUALIFIED' ? 'status-good' : ''}`}>{study ? developmentLabels[study.development.status] : 'Not recorded'}</p>
      <p>{study?.development.reason ?? 'No completion study is recorded for this campaign.'}</p>
      {study?.development.status === 'QUALIFIED' && <p className="muted">This met the development qualification rule. It is not an accepted or activated policy.</p>}
      {study?.development.status === 'REPLAY_ONLY' && <p className="muted">A replay tests an existing policy. It does not generate or qualify a new repair.</p>}
    </section>
    <section aria-label="Unseen-case result"><h3>Unseen-case result</h3>
      {!study?.unseen_checks.length ? <><p className="policy-status-value">Not run</p><p>No unseen-case check is recorded for this exact study and policy.</p></> : study.unseen_checks.map(check => {
        const result = unseenResult(check)
        return <div className="unseen-check" key={check.check_id}><p className={`policy-status-value status-${result.tone}`}>{result.label}</p><p>{result.detail}</p><p className="muted">Recorded decision: {check.decision} · {check.status}</p><details><summary>Check identity</summary><code>{check.check_id}</code><p className="muted">{check.predicate}</p></details></div>
      })}
    </section>
    <section aria-label="Active policy"><h3>Active policy</h3><p className="policy-status-value">{active.version === 'policy-v0' ? 'Baseline remains active' : active.version ? 'Recorded active policy' : 'Not available'}</p>
      {active.version ? <><p><code>{active.version}</code></p><Hash value={active.hash} /><p className="muted">Read from this campaign's active policy pointer, independently of the study results.</p></> : <p>The active policy record could not be identified. No activation is inferred.</p>}
    </section>
  </div>
}

export function PolicyStatusPanel({ campaignId }: { campaignId: string }) {
  const resource = useResource(campaignId ? `policy-status:${campaignId}` : null, () => getPolicyStatus(campaignId), 6000)
  if (!campaignId) return null
  return <Panel title="Repair status" className="policy-status-panel" aside={<span className="small-label">Three separate decisions</span>}>
    <p className="muted">A promising development result, an unseen-case check and the policy currently in use answer different questions.</p>
    <ResourceNote resource={resource} />
    {!resource.data && !resource.loading && <p className="muted">Status unavailable. Missing data does not count as a passed check.</p>}
    {resource.data && (resource.data.studies.length ? resource.data.studies.map(study => <article className="policy-status-study" key={study.study_id}>
      <div className="policy-status-identity"><strong>{study.policy_version ?? 'No candidate policy selected'}</strong><details><summary>Study identity</summary><p><code>{study.study_id}</code></p><Hash value={study.policy_hash} /><p className="muted">Source campaign: <code>{study.source_campaign_id}</code></p></details></div>
      <StatusColumns study={study} active={resource.data!.active_policy} />
    </article>) : <StatusColumns active={resource.data.active_policy} />)}
  </Panel>
}
