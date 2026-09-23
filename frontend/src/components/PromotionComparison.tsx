import { api } from '../api'
import type { Matrix, MatrixCell } from '../api'
import type { EvaluationBatch, PolicyVersion } from '../generated/contracts'
import { useResource } from '../useResource'
import { Badge, Empty, Panel, ResourceNote } from './common'
import { campaignProposals } from './RunSummary'

// The existing promotion protocol requires six cases, with three exact pairs
// per case. Protected recipes/trials stay hidden by the evaluation endpoint.
const REQUIRED_PAIRS = 18
const OUTCOMES = ['COMPLETED', 'VIOLATION', 'SAFE_UNRESOLVED', 'CORRECTLY_REJECTED'] as const
type Counts = { trials: number; completed: number; violations: number; safeUnresolved: number; correctlyRejected: number; httpAttempts: number }
type Comparison = { status: 'available'; before: Counts; after: Counts; pairs: number }
  | { status: 'incomplete' | 'unavailable'; reason: string; pairs: number }

export function promotionComparison(batch: EvaluationBatch, matrix: Matrix | undefined, candidate: PolicyVersion, parent: PolicyVersion | undefined, campaignId: string): Comparison {
  const unavailable = (reason: string): Comparison => ({ status: 'unavailable', reason, pairs: batch.trial_pairs.length })
  if (!matrix || matrix.campaign_id !== campaignId) return unavailable('The matching campaign ledger is not available.')
  if (batch.purpose !== 'promotion' || batch.split !== 'promotion') return unavailable('This saved evaluation is not a promotion batch.')
  if (!(candidate.evaluation_refs ?? []).includes(batch.batch_id) || !candidate.policy_hash || batch.candidate_hash !== candidate.policy_hash
    || !parent?.policy_hash || candidate.parent_version !== parent.version || batch.incumbent_hash !== parent.policy_hash
    || batch.candidate_hash === batch.incumbent_hash) return unavailable('The evaluation and policy identities do not match.')
  if (batch.decision === 'INCOMPLETE' || batch.trial_pairs.length < REQUIRED_PAIRS) return { status: 'incomplete', reason: 'The required promotion pairs did not all finish. No before-and-after totals are shown.', pairs: batch.trial_pairs.length }
  if (batch.trial_pairs.length !== REQUIRED_PAIRS) return unavailable('The recorded pair count differs from the promotion protocol.')

  const byId = new Map<string, MatrixCell[]>()
  for (const cell of matrix.cells) {
    if (cell.episode_id) byId.set(cell.episode_id, [...(byId.get(cell.episode_id) ?? []), cell])
  }
  const seen = new Set<string>()
  const before: MatrixCell[] = [], after: MatrixCell[] = []
  for (const pair of batch.trial_pairs) {
    if (pair.length !== 2 || pair.some(id => seen.has(id)) || pair[0] === pair[1]) return unavailable('The evaluation contains duplicate episode identities.')
    pair.forEach(id => seen.add(id))
    const rows = pair.map(id => byId.get(id))
    if (rows.some(row => row?.length !== 1)) return unavailable('A paired episode is missing or duplicated in the campaign ledger.')
    const cells = rows.map(row => row![0])
    // Execution order is not treatment identity. Match the frozen hashes even
    // when the candidate appears first in the recorded pair.
    const incumbent = cells.find(cell => cell.policy_hash === batch.incumbent_hash)
    const proposed = cells.find(cell => cell.policy_hash === batch.candidate_hash)
    if (!incumbent || !proposed || incumbent.arm !== 'B0' || proposed.arm !== 'L') return unavailable('A pair does not match the incumbent and candidate policies.')
    if (incumbent.scenario_alias !== proposed.scenario_alias || incumbent.fault_scheduled !== proposed.fault_scheduled) return unavailable('The paired scenario records do not match.')
    if (cells.some(cell => cell.source_mode !== 'live' || cell.lifecycle !== 'COMPLETED' || !OUTCOMES.includes(cell.outcome as typeof OUTCOMES[number])
      || (cell.fault_scheduled && !cell.fault_triggered))) return unavailable('Every pair needs finished live trials and any scheduled fault must have triggered.')
    if (cells.some(cell => !Number.isInteger(cell.usage?.http_attempts) || cell.usage!.http_attempts! < 0)) return unavailable('HTTP request counts are missing from the paired evidence.')
    before.push(incumbent); after.push(proposed)
  }
  const count = (cells: MatrixCell[]): Counts => ({ trials: cells.length,
    completed: cells.filter(cell => cell.outcome === 'COMPLETED').length,
    violations: cells.filter(cell => cell.outcome === 'VIOLATION').length,
    safeUnresolved: cells.filter(cell => cell.outcome === 'SAFE_UNRESOLVED').length,
    correctlyRejected: cells.filter(cell => cell.outcome === 'CORRECTLY_REJECTED').length,
    httpAttempts: cells.reduce((total, cell) => total + cell.usage!.http_attempts!, 0) })
  return { status: 'available', before: count(before), after: count(after), pairs: batch.trial_pairs.length }
}

function SavedComparison({ batchId, candidate, parent, matrix, campaignId }: { batchId: string; candidate: PolicyVersion; parent?: PolicyVersion; matrix?: Matrix; campaignId: string }) {
  const resource = useResource(`promotion:${campaignId}:${candidate.version}:${batchId}`, () => api.evaluation(batchId), 6000)
  const batch = resource.data
  const comparison = batch?.batch_id === batchId ? promotionComparison(batch, matrix, candidate, parent, campaignId) : undefined
  return <article className="experiment">
    <div className="split-heading"><h3>{candidate.version} · promotion comparison</h3><Badge value={candidate.decision_ref ? candidate.decision : 'PENDING'} /></div>
    <p className="muted">{candidate.decision_ref ? `Recorded policy decision: ${candidate.decision.toLowerCase().replaceAll('_', ' ')}.` : 'A final promotion decision has not been recorded.'} Batch <code>{batchId}</code>.</p>
    <ResourceNote resource={resource} />
    {batch && batch.batch_id !== batchId && <p role="alert" className="error">Comparison unavailable: the returned batch identity does not match.</p>}
    {comparison && <p>{comparison.pairs} recorded pairs / {REQUIRED_PAIRS} required.</p>}
    {comparison?.status === 'available' ? <>
      <div className="table-scroll"><table>
        <caption>Exact promotion pairs · previous policy versus tested candidate</caption>
        <thead><tr><th>Recorded measure</th><th>Before · {parent?.version}</th><th>After · {candidate.version}</th></tr></thead>
        <tbody>{([
          ['Trials in exact pairs', 'trials'], ['Completed tasks', 'completed'], ['Violations', 'violations'],
          ['Safe unresolved', 'safeUnresolved'], ['Correctly rejected', 'correctlyRejected'], ['HTTP requests', 'httpAttempts'],
        ] as const).map(([label, key]) => <tr key={key}><th scope="row">{label}</th><td>{comparison.before[key]}</td><td>{comparison.after[key]}</td></tr>)}</tbody>
      </table></div>
      <p className="muted">These counts include only the linked promotion pairs. Other campaign trials and retries remain in the ledger. The recorded promotion decision determines whether the candidate became active.</p>
    </> : comparison && <p className="notice"><strong>{comparison.status === 'incomplete' ? 'Comparison incomplete' : 'Comparison unavailable'}.</strong> {comparison.reason}</p>}
  </article>
}

export function PromotionComparison({ campaignId, matrix, policies }: { campaignId: string; matrix?: Matrix; policies?: PolicyVersion[] }) {
  if (!campaignId) return null
  const proposals = matrix?.campaign_id === campaignId ? campaignProposals(policies, matrix) : []
  const evaluated = proposals.filter(policy => policy.decision_ref || policy.evaluation_refs?.length)
  return <Panel title="Before and after · promotion evidence">
    <p className="muted">A fair comparison uses the same saved test pairs. Mixed campaign totals cannot show whether a repair helped.</p>
    {!evaluated.length && <Empty>No promotion evaluation is linked to this campaign's candidate policies.</Empty>}
    {evaluated.map(candidate => {
      const refs = [...new Set(candidate.evaluation_refs ?? [])]
      return refs.length ? refs.map(batchId => <SavedComparison key={`${candidate.version}:${batchId}`} batchId={batchId} candidate={candidate}
        parent={policies?.find(policy => policy.version === candidate.parent_version)} matrix={matrix} campaignId={campaignId} />)
        : <article className="experiment" key={candidate.version}><h3>{candidate.version}</h3><Badge value={candidate.decision} /><p>Promotion was reached, but its evaluation reference is unavailable. No comparison can be shown.</p></article>
    })}
  </Panel>
}
