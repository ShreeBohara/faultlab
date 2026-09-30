// The two Learn-loop rules (backend app/lab/loop_limits.py): shown in the Learn setup form (the rules offered), the saved
// plan, the challenge panel (each checked pick, only for a plan that declares the withdrawn challenge-pick rule) and the
// diagnosis panel (each Mechanic request-size record).
import { CHALLENGE_SELECTION_V2, MECHANIC_CONTEXT_V2, REACH_STATUS_LABELS, challengeSelectionText, contextRecordLabel, contextRecordText, mechanicContextText,
  mechanicEvidenceText, reachDecisionText, type ChallengeReachDecision, type ChallengeSelectionDeclaration, type MechanicContextDeclaration, type MechanicContextRecord,
  type MechanicEvidenceDeclaration } from '../loopLimits'
import type { AgentKind, DiscoveryDeclaration } from '../runPlans'
import { DECISION_LABELS, EXPLORER_SELECTION_V3, FIREABILITY_PROTOCOLS, ROW_STATUS_LABELS, decisionText, explorerSelectionText, targetText,
  type ExplorerFireability, type ExplorerSelectionDeclaration, type ExplorerSelectionPlan } from '../historyFireability'
import { Field, Json } from './common'

function StatusBadge({ value, text }: { value: string; text: string }) { return <span className={`badge badge-${value.toLowerCase()}`}>{text}</span> }

/** The rules a new Learn plan will freeze, as the backend offers them (only the offered ones; nothing is said about others).
 * The native citation-status rule is frozen only for native adapter v2, so it is shown only when that agent is chosen. */
export function OfferedLoopLimits({ mechanicContext, challengeSelection, mechanicEvidence, agent }: { mechanicContext?: MechanicContextDeclaration; challengeSelection?: ChallengeSelectionDeclaration; mechanicEvidence?: MechanicEvidenceDeclaration; agent?: AgentKind }) {
  const count = (mechanicContext ? 1 : 0) + (challengeSelection ? 1 : 0)
  const citation = mechanicEvidence && agent !== undefined && (mechanicEvidence.agents as string[]).includes(agent) ? mechanicEvidence : undefined
  if (!count && !citation) return null
  return <>{!!count && <><p className="muted">{count === 1 ? 'Every new Learn plan also freezes this rule:' : 'Every new Learn plan also freezes these two rules:'}</p>
    <dl className="facts compact">{mechanicContext && <Field name="Mechanic request size">{mechanicContextText(mechanicContext)}</Field>}{challengeSelection && <Field name="Challenge picks">{challengeSelectionText(challengeSelection)}</Field>}</dl></>}
    {citation && <><p className="muted">A new Learn plan for native adapter v2 also freezes:</p><dl className="facts compact"><Field name="Native citation status">{mechanicEvidenceText(citation)}</Field></dl></>}</>
}

export function LoopLimitFacts({ mechanicContext, challengeSelection, mechanicEvidence, agent }: { mechanicContext: MechanicContextDeclaration | null | undefined; challengeSelection: ChallengeSelectionDeclaration | null | undefined; mechanicEvidence?: MechanicEvidenceDeclaration | null; agent?: AgentKind }) {
  // Native citation status applies to native adapter v2 only; other agents' plans say nothing about it.
  const native = agent === 'smolagents-v2'
  return <><dl className="facts compact"><Field name="Mechanic request size">{mechanicContextText(mechanicContext)}</Field><Field name="Challenge picks">{challengeSelectionText(challengeSelection)}</Field>{native && <Field name="Native citation status">{mechanicEvidenceText(mechanicEvidence)}</Field>}</dl>
    {(mechanicContext || challengeSelection || (native && mechanicEvidence)) && <details><summary>Exact rule text</summary>{mechanicContext && <p className="muted">{mechanicContext.protocol}: {mechanicContext.rule}</p>}{challengeSelection && <p className="muted">{challengeSelection.protocol}: {challengeSelection.rule}</p>}{native && mechanicEvidence && <p className="muted">{mechanicEvidence.protocol}: {mechanicEvidence.rule}</p>}</details>}</>
}

/** History fireability offered for a new Learn plan: only when the chosen discovery protocol freezes it. */
export function OfferedExplorerSelection({ rule, protocol }: { rule?: ExplorerSelectionDeclaration; protocol?: string }) {
  if (!rule || !protocol || !(rule.discovery_protocols as readonly string[]).includes(protocol)) return null
  return <><p className="muted">A new Learn plan with this discovery protocol also freezes this rule, with a table computed from the frozen agent history when you create the campaign:</p>
    <dl className="facts compact"><Field name="History fireability">{explorerSelectionText(rule)}</Field></dl></>
}

/** The saved plan's history fireability rule and its frozen table (v3 · agent history and v4 plans only; older ones say so). */
export function ExplorerSelectionFacts({ rule, discovery }: { rule: ExplorerSelectionPlan | null | undefined; discovery: DiscoveryDeclaration | null | undefined }) {
  if (!discovery || !(FIREABILITY_PROTOCOLS as readonly string[]).includes(discovery.protocol)) return null
  return <section className="loop-limit" aria-label="History fireability"><dl className="facts compact"><Field name="History fireability">{explorerSelectionText(rule)}</Field></dl>
    {rule && <>
      <p className="muted">Frozen table · {rule.table.verified_episodes} verified history episode{rule.table.verified_episodes === 1 ? '' : 's'} (the frozen agent history's own, row {rule.table.record_cutoff} cutoff) · {rule.table.refused_targets.length ? `${rule.table.refused_targets.length} target${rule.table.refused_targets.length === 1 ? '' : 's'} refused` : 'no target refused'}</p>
      {rule.table.rows.length ? <div className="table-scroll"><table className="fireability-table" aria-label="History fireability table"><thead><tr><th>Target</th><th>Verified episodes</th><th>Fired</th><th>Status</th></tr></thead>
        <tbody>{rule.table.rows.map(row => <tr key={`${row.kind}-${row.target_service}-${row.target_tool}`} className={row.status === 'REFUSED' ? 'fireability-refused' : ''}><td>{targetText(row)}</td><td>{row.verified_episodes}</td><td>{row.fired_share}</td><td>{row.status === 'REFUSED' ? <strong>{ROW_STATUS_LABELS[row.status]}</strong> : ROW_STATUS_LABELS[row.status]}</td></tr>)}</tbody></table></div>
        : <p className="muted">The frozen history has no verified episode with a scheduled fault, so no target can be refused.</p>}
      <details><summary>Exact rule text</summary><p className="muted">{rule.protocol}: {rule.rule}</p><p className="muted">{rule.table.meaning}</p></details>
    </>}
  </section>
}

/** Each challenge pick checked under the history fireability rule (discovery picks are in the fault-search panel). */
export function ChallengeFireabilityList({ summary }: { summary?: ExplorerFireability }) {
  if (summary === undefined) return null
  const rows = summary.decisions.filter(row => row.purpose === 'challenge')
  const refused = rows.filter(row => row.status === 'REFUSED_LOW_FIRED_SHARE').length
  return <section className="loop-limit" aria-label="Challenge picks checked for history fireability"><h3>Challenge picks · history fireability</h3>
    <p className="muted">{rows.length ? `${rows.length} challenge pick${rows.length === 1 ? '' : 's'} checked, ${refused} refused before any pair ran.` : 'No challenge pick has been checked yet.'} Rule {EXPLORER_SELECTION_V3}: a pick whose every fault is on a target that fired in fewer than half of at least 3 verified episodes of the frozen history is refused; one re-plan follows, inside the challenge's 8 Explorer requests. A pick with a fault on any other target runs, even beside such a target. The table is the same for every candidate.</p>
    {!!summary.refused_targets.length && <p className="muted">Refused on their own in this campaign: {summary.refused_targets.join('; ')}. A pick made only of faults on them never runs, so a passed challenge has tested one of these targets failing only if a pick below paired it with a fault on another target.</p>}
    {rows.map(row => <div className="attempt" key={row.selection_id}><div className="split-heading"><span>Explorer request {row.request_index === null ? '?' : row.request_index + 1}: {decisionText(row)}</span><StatusBadge value={row.status} text={DECISION_LABELS[row.status]} /></div>
      {row.recipe && <p className="muted">Pick: {row.recipe.join(' + ')}</p>}
    </div>)}
    {!!rows.length && <Json value={rows} title="Inspect every checked challenge pick" />}
  </section>
}

export function ChallengeReachList({ rows }: { rows?: ChallengeReachDecision[] }) {
  if (rows === undefined) return null
  const refused = rows.filter(row => row.status === 'REFUSED_UNREACHED').length
  return <section className="loop-limit" aria-label="Challenge picks checked against the candidate's reach"><h3>Challenge picks · candidate reach check</h3>
    <p className="muted">{rows.length ? `${rows.length} pick${rows.length === 1 ? '' : 's'} checked, ${refused} refused before any pair ran.` : 'No challenge pick has been checked yet.'} Rule {CHALLENGE_SELECTION_V2}: a fault on a tool and service the agent never called in the candidate arm's source validation is refused; one re-plan follows, inside the challenge's 8 Explorer requests.</p>
    {rows.map(row => <div className="attempt" key={row.selection_id}><div className="split-heading"><span>{reachDecisionText(row)}</span><StatusBadge value={row.status} text={REACH_STATUS_LABELS[row.status]} /></div>
      {row.recipe && <p className="muted">Pick: {row.recipe.join(' + ')}</p>}
      {row.status === 'REFUSED_UNREACHED' && <p className="muted">The agent called: {row.basis.tool_services_called_by_agent.join(', ') || 'nothing recorded'}{row.basis.called_only_by_candidate_policy.length ? ` · read only by the candidate policy: ${row.basis.called_only_by_candidate_policy.join(', ')}` : ''} · {row.basis.source_validation_episode_ids.length} source-validation episode(s)</p>}
    </div>)}
    {!!rows.length && <Json value={rows} title="Inspect every checked pick" />}
  </section>
}

export function MechanicContextList({ rows }: { rows?: MechanicContextRecord[] }) {
  if (rows === undefined) return null
  return <section className="loop-limit" aria-label="Mechanic request size"><h3>Mechanic request size</h3>
    <p className="muted">{rows.length ? `${rows.length} Mechanic request${rows.length === 1 ? '' : 's'} crossed the input limit.` : 'No Mechanic request has crossed the input limit.'} Rule {MECHANIC_CONTEXT_V2}: nothing over the limit is ever sent, and a request that cannot fit ends that source's search, never the campaign.</p>
    {rows.map(row => <div className="attempt" key={row.record_id}><div className="split-heading"><span>{contextRecordText(row)}</span><StatusBadge value={row.outcome} text={contextRecordLabel(row)} /></div>
      {row.statement && <p className="muted">{row.statement}</p>}
      {/* Only a request that went out has evidence "in full"; an unsent one's compaction attempt stays in the JSON below. */}
      {row.outcome === 'COMPACTED' && !!row.blocks?.length && <p className="muted">{row.blocks.map(block => `${block.field}: ${block.episodes_in_full} of ${block.episodes_total} episodes in full`).join(' · ')}</p>}
    </div>)}
    {!!rows.length && <Json value={rows} title="Inspect every request-size record" />}
  </section>
}
