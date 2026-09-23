import { contextGroups, getContextStudies } from '../contextStudy'
import { useResource } from '../useResource'
import { Badge, Empty, EpisodeLinks, Field, Hash, Json, Panel, ResourceNote } from './common'

const words = (value: string) => value.toLowerCase().replaceAll('_', ' ')

export function ContextStudyPanel({ campaignId, onEpisode }: { campaignId: string; onEpisode: (id: string) => void }) {
  const resource = useResource(campaignId ? `context-studies:${campaignId}` : null, () => getContextStudies(campaignId), 6000)
  if (!campaignId) return null
  return <Panel title="Attempt-context study · baseline engineering comparison">
    <p>This study compares two Actor input protocols. Both arms run the same unchanged empty policy, the same model, the same tools, the same C1–C8 checks and the same episode limits; only the per-turn context differs. <strong>Nothing here proposes, accepts or activates a recovery policy.</strong></p>
    <ResourceNote resource={resource} />
    {resource.data?.length === 0 && <Empty>No attempt-context study recorded for this campaign.</Empty>}
    {resource.data?.map(study => {
      const changed = study.arms.find(arm => arm !== 'B0') ?? ''
      const assessment = study.assessment ?? null
      const profiles = study.action_profile_totals ?? {}
      return <article key={study.study_id} className="experiment">
        <div className="split-heading"><h3>{study.study_id}</h3><Badge value={study.status} /></div>
        <p>Study decision: <strong>{words(study.decision)}</strong>. {study.status === 'RUNNING' ? `Current stage: ${study.stage}; ${study.trial_rows.length} trial results saved. The study is still running.` : study.reason}</p>
        <p className="muted">An observed gain here is baseline engineering on the agent's input, not a learned repair, not an accepted policy and not a final-audit or transfer result.</p>
        {!!assessment?.incomplete_case_ids?.length && <p className="notice">These cases did not produce a complete set of valid paired trials and are excluded from the decision: {assessment.incomplete_case_ids.join(', ')}. Their original results are preserved below.</p>}
        {!!assessment?.regressed_case_ids?.length && <p className="error">The changed arm lost a target outcome in: {assessment.regressed_case_ids.join(', ')}.</p>}
        <dl className="facts compact">
          <Field name="Recorded stage">{study.stage}</Field>
          <Field name="Actor model">{study.model}</Field>
          <Field name="Policy in both arms">{study.policy_version} <Hash value={study.policy_hash} /></Field>
          <Field name="Configuration"><Hash value={study.configuration_hash} /></Field>
          {study.arms.map(arm => <Field key={arm} name={`Arm ${arm} context`}>{study.protocol_by_arm[arm]}</Field>)}
          <Field name="Charged model calls">{study.charged_model_calls}</Field>
          <Field name="Remote episode evidence">{Object.values(study.evidence).filter(source => source === 'weave_verified').length} verified / {study.trial_rows.length} recorded trials</Field>
          {assessment?.primary_completions && <Field name="Primary-case completions">{study.arms.map(arm => `${arm} ${assessment.primary_completions?.[arm] ?? 0}`).join(' · ')} of {assessment.primary_denominator ?? 0} paired trials</Field>}
        </dl>
        {!!Object.keys(profiles).length && <div className="table-scroll"><table><caption>Public actions per arm · counted from dispatched requests and delivered observations only</caption><thead><tr><th>Arm / service</th><th>Episodes</th><th>Write requests</th><th>Status reads</th><th>Status reads before any write</th><th>Episodes with no write request</th></tr></thead><tbody>{study.arms.flatMap(arm => Object.entries(profiles[arm] ?? {}).map(([service, counts]) => <tr key={`${arm}:${service}`}><th scope="row">{arm}<br />{service}</th><td>{counts.episodes}</td><td>{counts.write_requests}</td><td>{counts.status_reads}</td><td>{counts.status_reads_before_any_write}</td><td>{counts.episodes_with_no_write_request}</td></tr>))}</tbody></table></div>}
        {study.trial_rows.length ? <><div className="table-scroll"><table><caption>Recorded outcomes by case and arm · no cases combined</caption><thead><tr><th>Case</th><th>Arm / context protocol</th><th>Attempted / valid</th><th>Completed tasks</th><th>Violations</th><th>Safe unresolved</th><th>Correctly rejected</th><th>Triggered / scheduled</th></tr></thead><tbody>{contextGroups(study.trial_rows).map(group => <tr key={JSON.stringify([group.caseId, group.arm, group.protocol])}><th scope="row">{group.caseId}</th><td>{group.arm === 'B0' ? 'B0 · preserved context' : `${group.arm} · attempted-write context`}<br /><code>{group.protocol}</code></td><td>{group.attempted} / {group.valid}</td><td>{group.completed}</td><td>{group.violations}</td><td>{group.unresolved}</td><td>{group.rejected}</td><td>{group.triggered} / {group.scheduled}</td></tr>)}</tbody></table></div>
          <p className="muted">Attempted includes lab errors and interruptions. Task outcomes count only completed trial records; safe unresolved means the task was not finished. Mixed totals across cases are not an accuracy benchmark.</p>
          <details className="attempt"><summary>Open original trial evidence · {study.trial_rows.length} recorded</summary>{study.trial_rows.map(({ case_id, actor_context_protocol, trial }) => <div key={trial.episode_id}><p>{case_id} · {trial.arm} · <code>{actor_context_protocol}</code> · <Badge value={trial.lifecycle === 'COMPLETED' ? trial.outcome ?? 'UNVERIFIED' : trial.lifecycle} /> · <Badge value={study.evidence[trial.episode_id] ?? 'UNVERIFIED'} /></p><EpisodeLinks ids={[trial.episode_id]} onSelect={onEpisode} /></div>)}</details></> : <Empty>No trial results recorded in this study yet.</Empty>}
        {assessment && <Json value={assessment} title={`Inspect the recorded ${changed || 'changed'}-arm assessment`} />}
        <Json value={study} title="Inspect complete saved context study" />
      </article>
    })}
  </Panel>
}
