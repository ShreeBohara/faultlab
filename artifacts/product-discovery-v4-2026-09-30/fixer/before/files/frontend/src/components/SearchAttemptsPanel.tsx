import { getSearchAttempts, type SearchAttempt, type TransportRetry } from '../searchAttempts'
import type { HistoryReplaySlot, HistoryRowMatch } from '../runPlans'
import { useResource } from '../useResource'
import { Empty, EpisodeLinks, Hash, Json, Panel, ResourceNote } from './common'

const decisionLabel = {
  SELECTED: 'Selected for execution', SKIPPED_DUPLICATE: 'Duplicate declined · no Actor trial', INVALID_OUTPUT: 'Invalid output · no Actor trial',
  SKIPPED_UNREACHABLE: 'Refused by the reachability pre-check · no Actor trial', PRECHECK_FAILED: 'Pre-check could not run · no Actor trial',
}
const verdictLabel = { FORCED: 'Forced', NOT_FORCED: 'Not forced', IMPOSSIBLE: 'Impossible' }
const failureText = (retry: TransportRetry) => retry.code === 'HTTP_ERROR' ? `HTTP ${retry.http_status}` : retry.code.replaceAll('_', ' ').toLowerCase()
/** Discovery v3: whether a pick (or a source) re-tries a row of the frozen agent history the Explorer was shown. */
export const historyMatchText = (match: HistoryRowMatch | null) => match
  ? `History-informed: this recipe re-tries agent history row ${match.row}${match.development_case_id ? ` (${match.development_case_id})` : ''} that the Explorer was shown. Report a result from it as history-informed, not as independent discovery.`
  : 'No match with any row of the frozen agent history.'

/** Discovery v4: a replay slot re-ran a frozen history row by the plan's fixed rule; it is never independent discovery. */
export const historyReplayTitle = (block: HistoryReplaySlot) => `History replay ${block.replay} of ${block.of} · agent history row ${block.history_row}${block.development_case_id ? ` (${block.development_case_id})` : ''}`
export const historyReplayText = (block: HistoryReplaySlot) =>
  `${historyReplayTitle(block)}: FaultLab re-ran this recorded recipe, which violated in ${block.violation_share} verified episodes with every fault fired, because the plan's fixed replay rule listed it. No Explorer request was sent. A source from this slot is a history replay of that row, never independent discovery.`

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
  const replays = rows?.filter(row => row.history_replay) ?? []
  return <Panel title="Fault search · selection attempts">
    <p className="muted">Explorer responses and executed Actor trials are different counts. A declined duplicate still uses a model request. Only the trial ledger records whether a selected fault actually ran and triggered.</p>
    <ResourceNote resource={resource} />
    {rows && <div className="stat-strip"><div><strong>{rows.length - replays.length}</strong><span>Recorded selection responses</span></div>{!!replays.length && <div><strong>{replays.length}</strong><span>History replays · no Explorer request</span></div>}<div><strong>{rows.filter(row => row.search_decision.status === 'SELECTED').length}</strong><span>Selected for execution</span></div><div><strong>{rows.filter(row => row.search_decision.status === 'SKIPPED_DUPLICATE').length}</strong><span>Duplicates declined</span></div>{v2 && <div><strong>{rows.filter(row => row.search_decision.status === 'SKIPPED_UNREACHABLE').length}</strong><span>Refused by pre-check</span></div>}<div><strong>{rows.filter(row => row.search_decision.status === 'INVALID_OUTPUT').length}</strong><span>Invalid selections</span></div></div>}
    {rows?.length === 0 && <Empty>No search-decision records available for this campaign. Older records may contain executed trials without a selection ledger; this does not mean no faults were tested.</Empty>}
    {!!rows?.length && <p className="muted">A different seed or hypothesis alone does not create a new fault schedule. These records cover autonomous discovery, not challenge or selector-comparison studies.</p>}
    {v2 && <p className="muted">{rows?.some(row => row.search_decision.discovery_protocol === 'faultlab-discovery/v3-history-reachability') ? 'Discovery protocol v3 with the reachability pre-check (v2\'s dispatch, plus the frozen agent history in the saved plan)' : 'Discovery protocol v2'}: before any paid Actor trial, a free replay of the real simulator labels each fault for this agent. Only picks whose every fault is forced run; a refused pick gets one re-plan request in the same slot.</p>}
    {!!replays.length && <p className="muted">Discovery protocol v4: the first {replays.length === 1 ? 'slot was a history replay' : `${replays.length} slots were history replays`} of the frozen agent history (see the saved plan), with no Explorer request; the Explorer chose the remaining slots.</p>}
    {rows?.map(row => <details className="attempt" key={row.selection_ref}><summary>Selection {row.selection_index + 1}{row.search_decision.slot_request === 2 ? ' · re-plan' : ''} · {row.history_replay ? `${historyReplayTitle(row.history_replay)} · no Explorer request` : decisionLabel[row.search_decision.status]}</summary>
      <p><code>{row.selection_ref}</code> · {row.provenance.replaceAll('_', ' ')}</p>
      {row.search_decision.reason && <p>Recorded reason: {row.search_decision.reason.replaceAll('_', ' ').toLowerCase()}.</p>}
      {row.transport_retries?.map(retry => <p key={retry.retry_id} className="notice">{retry.protocol === undefined
        ? <>Transport retry: the first request received no answer ({failureText(retry)}), so the identical request was sent once more. Both requests are charged ({row.usage.model_calls} model requests); this is not a new selection request.</>
        : <>Transport retry {retry.attempt} of at most 3: the previous request received no answer ({failureText(retry)}), so after waiting {retry.retry_delay_seconds} s the identical request was sent again. Every request is charged ({row.usage.model_calls} model requests in all); this is not a new selection request.</>} Provider failure <code>{retry.provider_failure_id}</code>.</p>)}
      {row.history_replay && <><p className="notice">{historyReplayText(row.history_replay)}</p><p>Replay episode</p><EpisodeLinks ids={[row.history_replay.episode_id]} onSelect={onEpisode} /></>}
      {row.matches_history_row !== undefined && !row.history_replay && <p className={row.matches_history_row ? 'notice' : 'muted'}>{historyMatchText(row.matches_history_row)}</p>}
      <p>Schedule identity: <Hash value={row.search_decision.schedule_hash} /></p>
      {(row.selected_output ?? row.output)?.fault_spec.primitives.map((primitive, index) => <p key={index}>{primitive.kind} · {primitive.target_service}.{primitive.target_tool} · occurrence {primitive.occurrence}</p>)}
      <Reachability row={row} rows={rows} />
      {!!row.search_decision.prior_selection_refs.length && <p>Earlier selection references: {row.search_decision.prior_selection_refs.join(', ')}</p>}
      {!!row.search_decision.prior_episode_refs.length && <><p>Earlier executed trials for this schedule</p><EpisodeLinks ids={row.search_decision.prior_episode_refs} onSelect={onEpisode} /></>}
      <Json value={row} title="Inspect original response and saved selection decision" />
    </details>)}
  </Panel>
}
