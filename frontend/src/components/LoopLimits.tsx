// The two Learn-loop rules (backend app/lab/loop_limits.py): shown in the Learn setup form (the rules offered), the saved
// plan, the challenge panel (each checked pick, only for a plan that declares the withdrawn challenge-pick rule) and the
// diagnosis panel (each Mechanic request-size record).
import { CHALLENGE_SELECTION_V2, MECHANIC_CONTEXT_V2, REACH_STATUS_LABELS, challengeSelectionText, contextRecordLabel, contextRecordText, mechanicContextText,
  mechanicEvidenceText, reachDecisionText, type ChallengeReachDecision, type ChallengeSelectionDeclaration, type MechanicContextDeclaration, type MechanicContextRecord,
  type MechanicEvidenceDeclaration } from '../loopLimits'
import type { AgentKind } from '../runPlans'
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
