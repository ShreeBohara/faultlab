import { useState } from 'react'
import { HISTORY_SOURCES, isLabBackoff, runApi, type AgentHistory, type DiscoveryDeclaration, type HistoryCheck, type HistoryReplay, type HistorySource, type TransportRetryDeclaration } from '../runPlans'
import { Field } from './common'

const NAMES: Record<DiscoveryDeclaration['protocol'], string> = {
  'faultlab-discovery/v1': 'v1 · every valid new pick runs',
  'faultlab-discovery/v2-reachability': 'v2 · reachability pre-check',
  'faultlab-discovery/v3-history': 'v3 · agent history (dispatch exactly as v1)',
  'faultlab-discovery/v3-history-reachability': 'v3 · agent history + reachability pre-check (dispatch exactly as v2)',
  'faultlab-discovery/v4-history-replay': 'v4 · history replay first, then v3 · agent history',
}
export const discoveryName = (declaration: DiscoveryDeclaration) => NAMES[declaration.protocol] ?? declaration.protocol

/**
 * Explorer transport retries are declared separately: a retry re-sends a request that got no answer; it is not a new request.
 * The declared number covers discovery-phase Explorer requests only (review finding, September 29). How many a single
 * request may get depends on the plan's transport retry rule: one under rule v1, up to three with backoff under rule v2.
 * Under rule v2 the campaign-wide cap of lab-role retries (12) also bounds discovery, so when the plan declares more
 * (discovery v2 declares 16) the lower number is the real bound and the text says so (review finding P-6, September 30).
 */
export const explorerRetries = (declaration: DiscoveryDeclaration, rule?: TransportRetryDeclaration | null) => {
  const declared = declaration.explorer_transport_retries_max
  if (typeof declared !== 'number') return 'no Explorer transport retry declared'
  if (!isLabBackoff(rule)) return `at most ${declared} charged Explorer transport retries during discovery (one per request with no answer)`
  const cap = rule.lab_retries_per_campaign_max
  const capNote = declared > cap ? `; the plan declares ${declared}, but the campaign's cap of ${cap} Explorer and Mechanic retries is reached first` : ''
  return `at most ${Math.min(declared, cap)} charged Explorer transport retries during discovery (up to 3 per request with no answer, after waits of 5 s, 20 s and 60 s${capNote})`
}

/** Rule v1: retries after discovery have no separate declared count; they are bounded per request and by the campaign limits. */
export const LATER_PHASE_RETRIES = 'The retry bound above covers discovery only. In later phases, every Explorer request (challenge selections, selection comparison) and every Mechanic request can also get one charged retry when no answer arrives; those retries have no separate count and are bounded by one retry per request and by the campaign limits.'
/** Rule v2 (lab-role backoff, every new Learn plan). */
export const LATER_PHASE_RETRIES_V2 = 'The retry bound above covers discovery only. In later phases, every Explorer challenge selection and every Mechanic diagnosis or candidate request can also be sent again up to 3 times when no answer arrives, after waits of 5 s, 20 s and 60 s. All of this campaign\'s Explorer and Mechanic retries, discovery included, are capped at 12, and every one is charged before it is sent. A selection comparison started separately keeps one retry per request.'

/** Discovery v3 before a plan exists: nothing is frozen yet. */
export const HISTORY_AT_PLAN_TIME = 'The agent history is read from this store and frozen into the plan when you create the campaign. Review it in the saved plan before pressing Start.'

export const discoveryBudget = (declaration: DiscoveryDeclaration, rule?: TransportRetryDeclaration | null) =>
  `${declaration.slots} slots · at most ${declaration.explorer_requests_max} Explorer requests · ${explorerRetries(declaration, rule)} · at most ${declaration.actor_episodes_max} Actor episodes · ${declaration.replans_per_slot ? 'one re-plan per refused slot' : 'no re-plans'}`

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
/** Discovery v4 under NO_PRIOR_HISTORY: nothing to replay, so it runs as v3 · agent history with its own protocol id. */
export const NO_HISTORY_IS_STILL_V4 = 'This is still a discovery v4 run with nothing to replay: the Explorer is sent the v3 prompt section, this empty history and the v4 protocol id. Slot dispatch, budget and schedule identity equal v3 · agent history, but do not pool this run with v1 or v2 runs.'
/** Discovery v4 before a plan exists: the replay list is computed from the history when the campaign is created. */
export const REPLAY_AT_PLAN_TIME = 'The replay list is computed from this agent history and frozen into the plan when you create the campaign. Review it in the saved plan before pressing Start.'
/** How every result of a replay slot must be reported (backend history_replay.CLAIM_RULE, shortened). */
export const REPLAY_CLAIM = 'A source found in a replay slot is a history replay of that row, chosen by this fixed rule and not by the Explorer: report it as a history replay, never as independent discovery.'
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

/** A replayed row with no development case: its recipe came from an Explorer pick in an earlier learn campaign. The replay
 * itself is not an Explorer pick, so the label must not read as one (review finding LOW-2, September 30). */
export const NO_CASE_REPLAY_ROW = 'no development case: a recipe first picked by the Explorer in an earlier learn campaign'
/** Discovery v4: the replay list frozen into a saved plan. These history rows run first, one agent episode each, no Explorer request. */
export function HistoryReplayFacts({ replay }: { replay: HistoryReplay }) {
  return <section className="agent-history history-replay" aria-label="Frozen history replay list">
    <h4>History replay list · runs first</h4>
    <p className={replay.status === 'AVAILABLE' ? 'muted' : 'notice'}>{replay.statement}</p>
    {!!replay.rows.length && <ul className="agent-history-recipes" aria-label="Recipes replayed first">{replay.rows.map(row => <li key={row.replay}>
      <strong>Replay {row.replay} · agent history row {row.history_row} ({row.development_case_id ?? NO_CASE_REPLAY_ROW})</strong> · {row.recipe.join('; ')}
      <div className="muted">violated in {row.violation_share} verified episodes · every fault fired {row.every_fault_fired} of {row.verified_episodes} · failed checks {namedChecks(row.failed_checks)} <span>({row.sources.map(source => HISTORY_SOURCES[source as HistorySource] ?? source).join(', ')})</span></div>
    </li>)}</ul>}
    <dl className="facts compact">
      <Field name="Replay slots">{replay.rows.length ? `${plural(replay.rows.length, 'slot', 'slots')} of this campaign's discovery slots · ${plural(replay.rows.length, 'agent episode', 'agent episodes')} · no Explorer request` : 'none'}</Field>
      <Field name="Frozen from">agent history summary <code>{replay.history_summary_hash}</code></Field>
    </dl>
    {!!replay.rows.length && <p className="muted">{REPLAY_CLAIM}</p>}
    <details><summary>Replay rule</summary><p className="muted">{replay.rule}</p><p className="muted">Start checks the history against the store again and recomputes this list from it; any difference refuses the run.</p></details>
  </section>
}

/** The frozen same-agent history of a saved v3 or v4 plan: exactly what the Explorer reads, its hash and the record cutoff. */
export function AgentHistoryFacts({ history, campaign, replayed = false }: { history: AgentHistory; campaign?: { campaign_id: string; state?: string | null }; replayed?: boolean }) {
  const summary = history.summary
  const excluded = Object.entries(summary.excluded).filter(([, value]) => value > 0)
  const idle = !!campaign && (campaign.state ?? 'IDLE') === 'IDLE'
  return <section className="agent-history" aria-label="Frozen agent history">
    <h4>Agent history shown to the Explorer</h4>
    <p className={summary.status === 'AVAILABLE' ? 'muted' : 'notice'}>{summary.statement}</p>
    {summary.status === 'NO_PRIOR_HISTORY' && <p className="muted">{replayed ? NO_HISTORY_IS_STILL_V4 : NO_HISTORY_IS_STILL_V3}</p>}
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
export function DiscoveryProtocolFacts({ declaration, campaign, transportRetry }: { declaration: DiscoveryDeclaration; campaign?: { campaign_id: string; state?: string | null }; transportRetry?: TransportRetryDeclaration | null }) {
  const caller = declaration.pre_check?.caller_model
  const v3 = declaration.history !== undefined
  const replayed = declaration.replay !== undefined
  return <div className="discovery-protocol">
    <dl className="facts compact">
      <Field name="Discovery protocol">{discoveryName(declaration)}</Field>
      <Field name="Selection budget">{discoveryBudget(declaration, transportRetry)}</Field>
      <Field name="Schedule identity">{declaration.schedule_identity.endsWith('v2-order-aware') ? 'Order-aware: order counts only for overlapping same-kind faults on one tool' : 'Sorted primitives (seed and order ignored)'}</Field>
    </dl>
    <p className="muted">{declaration.dispatch_rule}</p>
    {typeof declaration.explorer_transport_retries_max === 'number' && <p className="muted">{isLabBackoff(transportRetry) ? LATER_PHASE_RETRIES_V2 : LATER_PHASE_RETRIES}</p>}
    {caller && <details><summary>Pre-check caller model · this agent's limits and typical path</summary><ul className="muted">{caller.facts.map(fact => <li key={fact}>{fact}</li>)}</ul><p className="muted">Caller model <code>{caller.caller_id}</code> describes {caller.validated_against}. The pre-check changes only which picks run; it never changes what the Actor sees or how a trial is scored.</p></details>}
    {replayed && (declaration.replay ? <HistoryReplayFacts replay={declaration.replay} /> : <p className="muted">{REPLAY_AT_PLAN_TIME}</p>)}
    {v3 && (declaration.history ? <AgentHistoryFacts history={declaration.history} campaign={campaign} replayed={replayed} /> : <p className="muted">{HISTORY_AT_PLAN_TIME}</p>)}
  </div>
}
