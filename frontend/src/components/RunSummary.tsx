import type { Campaign, PolicyVersion } from '../generated/contracts'
import type { Matrix } from '../api'
import type { Experiments } from '../experiments'
import { Badge, Panel } from './common'

// Every value below is read from persisted records. Nothing is inferred, and a stage
// that did not run is reported as not reached rather than left blank.
export function campaignProposals(policies: PolicyVersion[] | undefined, matrix: Matrix | undefined): PolicyVersion[] {
  const episodes = new Set((matrix?.cells ?? []).map(c => c.episode_id).filter((v): v is string => !!v))
  return (policies ?? []).filter(p => p.author === 'mechanic' && p.development_episode_ids.some(id => episodes.has(id)))
}

export function RunSummary({ campaign, matrix, experiments, policies }: { campaign?: Campaign; matrix?: Matrix; experiments?: Experiments; policies?: PolicyVersion[] }) {
  if (!campaign) return null
  const counts = matrix?.counts
  const records = experiments?.counterexamples ?? []
  // Keep reproduction, reduction and diagnosis attached to the same incident.
  const latest = records.at(-1)
  const counterexample = latest?.counterexample
  const reduction = latest?.reduction ?? null
  const tested = latest?.interventions.at(-1)
  const diagnosis = latest?.diagnostics.at(-1)
  // The API can attach a campaign challenge to several incident records.
  const challenges = [...new Map(records.flatMap(r => r.challenges).map(c => [c.challenge_id, c])).values()]
  const challenge = challenges.at(-1)
  const proposals = campaignProposals(policies, matrix)
  const accepted = proposals.find(p => p.decision === 'ACCEPTED')
  const verified = (experiments?.ingestions ?? []).filter(i => i.status === 'weave_verified').length
  const finished = ['NO_CHANGE', 'STOPPED', 'COMPLETED'].includes(campaign.state ?? '')
  const retainedLabel = campaign.active_policy_version === 'policy-v0' ? 'Baseline retained' : 'Current policy retained'
  return <Panel title="Run summary" className="summary-panel" aside={<div className="summary-heading-meta"><span className="small-label">Read from persisted records</span><Badge value={campaign.state ?? 'UNVERIFIED'} /></div>}>
    <div className="summary-context"><span>Actor <strong>{campaign.model}</strong></span><span>{records.length ? `Latest incident shown · ${records.length} recorded` : 'Waiting for incident evidence'}</span></div>
    <div className="stat-strip">
      <div><strong>{counts?.valid_attempted ?? '—'}</strong><span>Trials recorded</span></div>
      <div className="stat-alert"><strong>{counts?.violations ?? '—'}</strong><span>Violations</span></div>
      <div className="stat-good"><strong>{counts?.completed ?? '—'}</strong><span>Completed</span></div>
      <div><strong>{campaign.usage?.model_calls ?? '—'}</strong><span>Model calls</span></div>
      <div className="stat-good"><strong>{experiments ? verified : '—'}{experiments && <span> / {experiments.ingestions.length}</span>}</strong><span>Weave verified</span></div>
    </div>
    <ol className="summary-stages" aria-label="Learning cycle evidence">
      <li className={`summary-stage ${counterexample?.reproduced ? 'stage-supported' : 'stage-pending'}`}><span className="stage-index">01</span><div className="stage-content"><h3 className="stage-label">Repeat the failure</h3><div className="stage-detail">{counterexample
        ? <><Badge value={counterexample.reproduced ? 'SUPPORTED' : 'INCONCLUSIVE'} /><p>{counterexample.target_violation_count ?? 'not recorded'} of {counterexample.valid_count ?? 'not recorded'} fresh trials violated {counterexample.target_invariant}.</p></>
        : <><Badge value="NOT_RUN" /> No qualifying repeated violation was recorded.</>}</div></div></li>
      <li className={`summary-stage ${reduction ? 'stage-observed' : 'stage-pending'}`}><span className="stage-index">02</span><div className="stage-content"><h3 className="stage-label">Simplify the fault</h3><div className="stage-detail">{reduction
        ? <><Badge value={reduction.status} /><p>{reduction.stopping_reason === 'FINITE_NEIGHBORHOOD_EXHAUSTED' ? 'The defined reduction search is complete.' : reduction.stopping_reason}</p></>
        : <><Badge value="NOT_RUN" /> No reduction recorded.</>}</div></div></li>
      <li className={`summary-stage ${tested?.result === 'SUPPORTED' ? 'stage-supported' : tested ? 'stage-observed' : 'stage-pending'}`}><span className="stage-index">03</span><div className="stage-content"><h3 className="stage-label">Test the diagnosis</h3><div className="stage-detail">{tested
        ? <><Badge value={tested.result} /><p>{diagnosis ? `Fixed verdict: ${diagnosis.kind.replaceAll('_', ' ').toLowerCase()}. Model proposal: ${diagnosis.proposed_kind.replaceAll('_', ' ').toLowerCase()}.` : 'No diagnostic record.'}</p></>
        : <><Badge value="NOT_RUN" /> No controlled intervention finished.</>}</div></div></li>
      <li className={`summary-stage ${proposals.length ? 'stage-observed' : 'stage-pending'}`}><span className="stage-index">04</span><div className="stage-content"><h3 className="stage-label">Propose a repair</h3><div className="stage-detail">{proposals.length
        ? <><Badge value="PROPOSED" /><p>{proposals.length} candidate {proposals.length === 1 ? 'policy' : 'policies'} generated by the Mechanic.</p></>
        : <><Badge value="NOT_RUN" /> No candidate policy was generated in this campaign.</>}</div></div></li>
      <li className={`summary-stage ${challenge?.status === 'COUNTEREXAMPLE_FOUND' ? 'stage-rejected' : challenge ? 'stage-observed' : 'stage-pending'}`}><span className="stage-index">05</span><div className="stage-content"><h3 className="stage-label">Challenge the repair</h3><div className="stage-detail">{challenge
        ? <><Badge value={challenge.status} /><p>{challenge.stopping_reason}</p>{challenge.status === 'COUNTEREXAMPLE_FOUND' && <span className="stage-loop"><span aria-hidden="true">↩</span> Back to 04 · Repair</span>}</>
        : <><Badge value="NOT_RUN" /> Not reached. A candidate must repair every source-validation pair first.</>}</div></div></li>
      <li className={`summary-stage ${accepted ? 'stage-supported' : 'stage-pending'}`}><span className="stage-index">06</span><div className="stage-content"><h3 className="stage-label">Promote if qualified</h3><div className="stage-detail">{accepted
        ? <><Badge value="ACCEPTED" /><p>{accepted.version} was accepted in this campaign.</p></>
        : <><Badge value="NOT_RUN" /><p>No promotion batch qualified.</p></>}</div></div></li>
    </ol>
    <div className="summary-outcome"><span className="outcome-marker" aria-hidden="true">↺</span><div className="outcome-copy"><strong>{accepted ? 'Recovery policy accepted' : finished ? retainedLabel : 'No policy accepted yet'}</strong><p>{accepted
      ? `A learned policy was accepted; the active version is ${campaign.active_policy_version ?? accepted.version}.`
      : `No recovery policy has been accepted in this campaign. The active policy is still ${campaign.active_policy_version ?? 'the baseline'}.`}</p></div></div>
    {campaign.terminal_reason && <p className="muted">Recorded outcome · {campaign.terminal_reason}</p>}
  </Panel>
}
