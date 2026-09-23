import { getSearchAttempts } from '../searchAttempts'
import { useResource } from '../useResource'
import { Empty, EpisodeLinks, Hash, Json, Panel, ResourceNote } from './common'

const decisionLabel = { SELECTED: 'Selected for execution', SKIPPED_DUPLICATE: 'Duplicate declined · no Actor trial', INVALID_OUTPUT: 'Invalid output · no Actor trial' }
export function SearchAttemptsPanel({ campaignId, onEpisode }: { campaignId: string; onEpisode: (id: string) => void }) {
  const resource = useResource(campaignId ? `search-attempts:${campaignId}` : null, () => getSearchAttempts(campaignId), 6000)
  if (!campaignId) return null
  const rows = resource.data
  return <Panel title="Fault search · selection attempts">
    <p className="muted">Explorer responses and executed Actor trials are different counts. A declined duplicate still uses a model request. Only the trial ledger records whether a selected fault actually ran and triggered.</p>
    <ResourceNote resource={resource} />
    {rows && <div className="stat-strip"><div><strong>{rows.length}</strong><span>Recorded selection responses</span></div><div><strong>{rows.filter(row => row.search_decision.status === 'SELECTED').length}</strong><span>Selected for execution</span></div><div><strong>{rows.filter(row => row.search_decision.status === 'SKIPPED_DUPLICATE').length}</strong><span>Duplicates declined</span></div><div><strong>{rows.filter(row => row.search_decision.status === 'INVALID_OUTPUT').length}</strong><span>Invalid selections</span></div></div>}
    {rows?.length === 0 && <Empty>No search-decision records available for this campaign. Older records may contain executed trials without a selection ledger; this does not mean no faults were tested.</Empty>}
    {!!rows?.length && <p className="muted">A different seed or hypothesis alone does not create a new fault schedule. These records cover autonomous discovery, not challenge or selector-comparison studies.</p>}
    {rows?.map(row => <details className="attempt" key={row.selection_ref}><summary>Selection {row.selection_index + 1} · {decisionLabel[row.search_decision.status]}</summary>
      <p><code>{row.selection_ref}</code> · {row.provenance.replaceAll('_', ' ')}</p>
      {row.search_decision.reason && <p>Recorded reason: {row.search_decision.reason.replaceAll('_', ' ').toLowerCase()}.</p>}
      <p>Schedule identity: <Hash value={row.search_decision.schedule_hash} /></p>
      {(row.selected_output ?? row.output)?.fault_spec.primitives.map((primitive, index) => <p key={index}>{primitive.kind} · {primitive.target_service}.{primitive.target_tool} · occurrence {primitive.occurrence}</p>)}
      {!!row.search_decision.prior_selection_refs.length && <p>Earlier selection references: {row.search_decision.prior_selection_refs.join(', ')}</p>}
      {!!row.search_decision.prior_episode_refs.length && <><p>Earlier executed trials for this schedule</p><EpisodeLinks ids={row.search_decision.prior_episode_refs} onSelect={onEpisode} /></>}
      <Json value={row} title="Inspect original response and saved selection decision" />
    </details>)}
  </Panel>
}
