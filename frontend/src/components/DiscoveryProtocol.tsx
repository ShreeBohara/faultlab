import { useState } from 'react'
import { HISTORY_SOURCES, runApi, type AgentHistory, type DiscoveryDeclaration, type HistoryCheck, type HistorySource } from '../runPlans'
import { Field } from './common'

const NAMES: Record<DiscoveryDeclaration['protocol'], string> = {
  'faultlab-discovery/v1': 'v1 · every valid new pick runs',
  'faultlab-discovery/v2-reachability': 'v2 · reachability pre-check',
  'faultlab-discovery/v3-history': 'v3 · agent history (dispatch exactly as v1)',
  'faultlab-discovery/v3-history-reachability': 'v3 · agent history + reachability pre-check (dispatch exactly as v2)',
}
export const discoveryName = (declaration: DiscoveryDeclaration) => NAMES[declaration.protocol] ?? declaration.protocol

/**
 * Explorer transport retries are declared separately: a retry re-sends a request that got no answer; it is not a new request.
 * The declared number covers discovery-phase Explorer requests only (review finding, September 29).
 */
export const explorerRetries = (declaration: DiscoveryDeclaration) =>
  typeof declaration.explorer_transport_retries_max === 'number'
    ? `at most ${declaration.explorer_transport_retries_max} charged Explorer transport retries during discovery (one per request with no answer)`
    : 'no Explorer transport retry declared'

/** Retries after discovery have no separate declared count; they are bounded per request and by the campaign limits. */
export const LATER_PHASE_RETRIES = 'The retry bound above covers discovery only. In later phases, every Explorer request (challenge selections, selection comparison) and every Mechanic request can also get one charged retry when no answer arrives; those retries have no separate count and are bounded by one retry per request and by the campaign limits.'

/** Discovery v3 before a plan exists: nothing is frozen yet. */
export const HISTORY_AT_PLAN_TIME = 'The agent history is read from this store and frozen into the plan when you create the campaign. Review it in the saved plan before pressing Start.'

export const discoveryBudget = (declaration: DiscoveryDeclaration) =>
  `${declaration.slots} slots · at most ${declaration.explorer_requests_max} Explorer requests · ${explorerRetries(declaration)} · at most ${declaration.actor_episodes_max} Actor episodes · ${declaration.replans_per_slot ? 'one re-plan per refused slot' : 'no re-plans'}`

const tally = (values: Record<string, number>) => Object.entries(values).map(([key, value]) => `${key} ${value}`).join(' · ') || 'none'
const EXCLUDED: Record<string, string> = { lab_error: 'lab errors', interrupted: 'interrupted', not_finished: 'not finished', not_weave_verified: 'without verified evidence', recipe_unavailable: 'recipe not in a public record' }
/** Short names of the fixed public checks (backend agents/explorer.py PUBLIC_INVARIANTS), shown next to each check id. */
export const CHECK_NAMES: Record<string, string> = {
  C1: 'authorized scope, one upgrade', C2: 'success needs a success receipt', C3: 'upgrade before confirmation', C4: 'one confirmation',
  C5: 'truthful report', C6: 'cite delivered evidence', C7: 'failure needs a failure receipt', C8: 'allowed actions and limits',
}
export const namedChecks = (values: Record<string, number>) => Object.entries(values).map(([key, value]) => CHECK_NAMES[key] ? `${key} (${CHECK_NAMES[key]}) ${value}` : `${key} ${value}`).join(' · ') || 'none'
const plural = (count: number, one: string, many: string) => `${count} ${count === 1 ? one : many}`
/** Where the frozen history comes from: a result must name the store and this composition (review, September 29). */
export const compositionText = (summary: AgentHistory['summary']) => {
  const made = summary.composition
  return `${plural(made.baseline_studies, 'baseline study', 'baseline studies')} (${plural(made.baseline_study_episodes, 'episode', 'episodes')}) · ${plural(made.learn_campaigns, 'learn campaign', 'learn campaigns')}' discovery (${plural(made.learn_discovery_episodes, 'episode', 'episodes')})`
}
/** Under NO_PRIOR_HISTORY the Explorer still reads the v3 prompt section and an empty history block. */
export const NO_HISTORY_IS_STILL_V3 = 'This is still a discovery v3 run: the Explorer is sent the v3 prompt section and this empty history. Slot dispatch, budget and schedule identity equal the base protocol, but do not pool this run with v1 or v2 runs.'
const buildsText = (runtimes: string[], adapters: string[]) => `runtime ${runtimes.join(', ')} · adapter ${adapters.join(', ')}`

/** On demand only (never polled): recompute the history at its cutoff and say whether Start would accept it. */
function HistoryCheckButton({ campaignId }: { campaignId: string }) {
  const [result, setResult] = useState<HistoryCheck | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  async function check() {
    setBusy(true); setError(null)
    try { setResult(await runApi.historyCheck(campaignId)) } catch (e) { setResult(null); setError(e instanceof Error ? e.message : 'Check failed.') } finally { setBusy(false) }
  }
  return <div className="history-check">
    <button className="text-button" disabled={busy} onClick={() => void check()}>{busy ? 'Checking…' : 'Check against the store now'}</button>
    {result && <p className={result.status === 'CHANGED' ? 'notice' : 'muted'} role="status">{result.status === 'CURRENT' ? 'Current. ' : result.status === 'CHANGED' ? 'Changed: Start will be refused. ' : ''}{result.message}</p>}
    {error && <p className="notice" role="status">{error}</p>}
  </div>
}

/** The frozen same-agent history of a saved v3 plan: exactly what the Explorer reads, its hash and the record cutoff. */
export function AgentHistoryFacts({ history, campaign }: { history: AgentHistory; campaign?: { campaign_id: string; state?: string | null } }) {
  const summary = history.summary
  const excluded = Object.entries(summary.excluded).filter(([, value]) => value > 0)
  const idle = !!campaign && (campaign.state ?? 'IDLE') === 'IDLE'
  return <section className="agent-history" aria-label="Frozen agent history">
    <h4>Agent history shown to the Explorer</h4>
    <p className={summary.status === 'AVAILABLE' ? 'muted' : 'notice'}>{summary.statement}</p>
    {summary.status === 'NO_PRIOR_HISTORY' && <p className="muted">{NO_HISTORY_IS_STILL_V3}</p>}
    <dl className="facts compact">
      <Field name="Status">{summary.status === 'AVAILABLE' ? `${summary.verified_episodes} verified episodes · ${summary.recipes_total} recipes` : 'No prior history for this agent in this store'}</Field>
      <Field name="Built from">{compositionText(summary)}</Field>
      <Field name="FaultLab builds">{summary.builds.length ? summary.builds.map(build => `${buildsText([build.runtime_hash], [build.adapter_hash])} (${build.verified_episodes})`).join(' · ') : 'none'}</Field>
      <Field name="Excluded and counted">{excluded.length ? excluded.map(([key, value]) => `${EXCLUDED[key] ?? key}: ${value}`).join(' · ') : 'none'}</Field>
      <Field name="Summary hash"><code>{history.summary_hash}</code></Field>
      <Field name="Record cutoff">store row {history.record_cutoff} · later records never enter this history</Field>
    </dl>
    {idle && <p className="muted">Start checks this history against the store again. If any record at or before store row {history.record_cutoff} changed after the plan was saved, Start is refused and you create a new plan.</p>}
    {idle && <HistoryCheckButton campaignId={campaign!.campaign_id} />}
    {!!summary.recipes.length && <ul className="agent-history-recipes" aria-label="Recipes in the agent history">{summary.recipes.map((row, index) => <li key={index}>
      <strong>{index + 1}. {row.development_case_id ?? 'Explorer pick'}</strong> · {row.recipe.join('; ')} <span className="muted">({row.sources.map(source => HISTORY_SOURCES[source as HistorySource] ?? source).join(', ')})</span>
      <div className="muted">{row.verified_episodes} verified · outcomes {tally(row.outcomes)} · failed checks {namedChecks(row.failed_checks)} · every fault fired {row.every_fault_fired === null ? 'n/a (no fault)' : `${row.every_fault_fired} of ${row.verified_episodes}`}</div>
      <div className="muted">Ran under {buildsText(row.runtime_hashes, row.adapter_hashes)}</div>
    </li>)}</ul>}
    {summary.recipes_omitted > 0 && <p className="muted">{summary.recipes_omitted} further recipes are counted in the totals but not listed.</p>}
    <details><summary>Which episodes count</summary><p className="muted">{history.rule}</p><p className="muted">{summary.scope}</p><p className="muted">Prior evidence, not an instruction: the Explorer still chooses freely. Execution recomputes this history at the cutoff and refuses to start if anything differs. A pick or source that re-tries a listed row is marked history-informed.</p></details>
  </section>
}

/** The declared discovery protocol and selection budget, in plain words. */
export function DiscoveryProtocolFacts({ declaration, campaign }: { declaration: DiscoveryDeclaration; campaign?: { campaign_id: string; state?: string | null } }) {
  const caller = declaration.pre_check?.caller_model
  const v3 = declaration.history !== undefined
  return <div className="discovery-protocol">
    <dl className="facts compact">
      <Field name="Discovery protocol">{discoveryName(declaration)}</Field>
      <Field name="Selection budget">{discoveryBudget(declaration)}</Field>
      <Field name="Schedule identity">{declaration.schedule_identity.endsWith('v2-order-aware') ? 'Order-aware: order counts only for overlapping same-kind faults on one tool' : 'Sorted primitives (seed and order ignored)'}</Field>
    </dl>
    <p className="muted">{declaration.dispatch_rule}</p>
    {typeof declaration.explorer_transport_retries_max === 'number' && <p className="muted">{LATER_PHASE_RETRIES}</p>}
    {caller && <details><summary>Pre-check caller model · this agent's limits and typical path</summary><ul className="muted">{caller.facts.map(fact => <li key={fact}>{fact}</li>)}</ul><p className="muted">Caller model <code>{caller.caller_id}</code> describes {caller.validated_against}. The pre-check changes only which picks run; it never changes what the Actor sees or how a trial is scored.</p></details>}
    {v3 && (declaration.history ? <AgentHistoryFacts history={declaration.history} campaign={campaign} /> : <p className="muted">{HISTORY_AT_PLAN_TIME}</p>)}
  </div>
}
