import { getSearchAttempts, type SearchAttempt } from '../searchAttempts'
import { useResource } from '../useResource'
import { Empty, EpisodeLinks, Hash, Json, Panel, ResourceNote } from './common'

const decisionLabel = {
  SELECTED: 'Selected for execution', SKIPPED_DUPLICATE: 'Duplicate declined · no Actor trial', INVALID_OUTPUT: 'Invalid output · no Actor trial',
  SKIPPED_UNREACHABLE: 'Refused by the reachability pre-check · no Actor trial', PRECHECK_FAILED: 'Pre-check could not run · no Actor trial',
}
const verdictLabel = { FORCED: 'Forced', NOT_FORCED: 'Not forced', IMPOSSIBLE: 'Impossible' }

function Reachability({ row, rows }: { row: SearchAttempt; rows: SearchAttempt[] }) {
  const decision = row.search_decision
  if (!decision.discovery_protocol) return null
  const replan = rows.find(other => other.search_decision.replan_of === row.selection_ref)
  const recipe = decision.reachability?.recipe
  return <div className="reachability">
    {decision.replan_of && <p>Re-plan request for this slot, after refused selection <code>{decision.replan_of}</code>.</p>}
    {replan && <p>This slot received one re-plan request: <code>{replan.selection_ref}</code> · {decisionLabel[replan.search_decision.status]}.</p>}
    {decision.reachability ? <>
      <p>Pre-check: {decision.reachability.all_forced ? 'every fault is forced on this agent\'s path, so the pick ran.' : 'not every fault is forced on this agent\'s path, so no Actor trial ran.'}</p>
      <ul className="fault-verdicts">{decision.reachability.faults.map(fault => <li key={fault.index}><strong>{verdictLabel[fault.verdict]}</strong> · {fault.fault}<br /><span className="muted">{fault.explanation}</span></li>)}</ul>
      <p className="muted">Agent path in the free replay: {decision.reachability.agent_path.map(token => token.split('#')[0]).join(' → ') || 'no business call'} ({decision.reachability.agent_business_calls} business calls).</p>
    </> : decision.status === 'SKIPPED_DUPLICATE' && recipe === undefined && decision.refused_fault_spec ? <p className="muted">Exact repeat of an earlier recipe in this campaign; the pre-check was not needed.</p> : null}
  </div>
}

export function SearchAttemptsPanel({ campaignId, onEpisode }: { campaignId: string; onEpisode: (id: string) => void }) {
  const resource = useResource(campaignId ? `search-attempts:${campaignId}` : null, () => getSearchAttempts(campaignId), 6000)
  if (!campaignId) return null
  const rows = resource.data
  const v2 = !!rows?.some(row => row.search_decision.discovery_protocol)
  return <Panel title="Fault search · selection attempts">
    <p className="muted">Explorer responses and executed Actor trials are different counts. A declined duplicate still uses a model request. Only the trial ledger records whether a selected fault actually ran and triggered.</p>
    <ResourceNote resource={resource} />
    {rows && <div className="stat-strip"><div><strong>{rows.length}</strong><span>Recorded selection responses</span></div><div><strong>{rows.filter(row => row.search_decision.status === 'SELECTED').length}</strong><span>Selected for execution</span></div><div><strong>{rows.filter(row => row.search_decision.status === 'SKIPPED_DUPLICATE').length}</strong><span>Duplicates declined</span></div>{v2 && <div><strong>{rows.filter(row => row.search_decision.status === 'SKIPPED_UNREACHABLE').length}</strong><span>Refused by pre-check</span></div>}<div><strong>{rows.filter(row => row.search_decision.status === 'INVALID_OUTPUT').length}</strong><span>Invalid selections</span></div></div>}
    {rows?.length === 0 && <Empty>No search-decision records available for this campaign. Older records may contain executed trials without a selection ledger; this does not mean no faults were tested.</Empty>}
    {!!rows?.length && <p className="muted">A different seed or hypothesis alone does not create a new fault schedule. These records cover autonomous discovery, not challenge or selector-comparison studies.</p>}
    {v2 && <p className="muted">Discovery protocol v2: before any paid Actor trial, a free replay of the real simulator labels each fault for this agent. Only picks whose every fault is forced run; a refused pick gets one re-plan request in the same slot.</p>}
    {rows?.map(row => <details className="attempt" key={row.selection_ref}><summary>Selection {row.selection_index + 1}{row.search_decision.slot_request === 2 ? ' · re-plan' : ''} · {decisionLabel[row.search_decision.status]}</summary>
      <p><code>{row.selection_ref}</code> · {row.provenance.replaceAll('_', ' ')}</p>
      {row.search_decision.reason && <p>Recorded reason: {row.search_decision.reason.replaceAll('_', ' ').toLowerCase()}.</p>}
      <p>Schedule identity: <Hash value={row.search_decision.schedule_hash} /></p>
      {(row.selected_output ?? row.output)?.fault_spec.primitives.map((primitive, index) => <p key={index}>{primitive.kind} · {primitive.target_service}.{primitive.target_tool} · occurrence {primitive.occurrence}</p>)}
      <Reachability row={row} rows={rows} />
      {!!row.search_decision.prior_selection_refs.length && <p>Earlier selection references: {row.search_decision.prior_selection_refs.join(', ')}</p>}
      {!!row.search_decision.prior_episode_refs.length && <><p>Earlier executed trials for this schedule</p><EpisodeLinks ids={row.search_decision.prior_episode_refs} onSelect={onEpisode} /></>}
      <Json value={row} title="Inspect original response and saved selection decision" />
    </details>)}
  </Panel>
}
