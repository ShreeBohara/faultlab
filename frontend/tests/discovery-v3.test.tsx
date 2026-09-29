// @vitest-environment jsdom
import { createElement as h } from 'react'
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { api } from '../src/api'
import { runApi, validateCampaignPlan, validateRunOptions, type DiscoveryDeclaration, type RunOptions } from '../src/runPlans'
import { RunSetup } from '../src/components/RunSetup'
import { CampaignPlan } from '../src/components/CampaignPlan'
import { HISTORY_AT_PLAN_TIME, NO_HISTORY_IS_STILL_V3 } from '../src/components/DiscoveryProtocol'
import { SearchAttemptsPanel } from '../src/components/SearchAttemptsPanel'
import { CounterexamplePanel } from '../src/components/CounterexamplePanel'
import { validateSearchAttempts } from '../src/searchAttempts'
import { validateExperiments } from '../src/experiments'
import { validateHistoryCheck } from '../src/runPlans'
import { campaign, config, fixtureResponse, hash, readiness } from './fixtures'
import { agentHistory, discoveryV1, discoveryV2, discoveryV3, discoveryV3Precheck, planned, runOptions } from './run-fixtures'

beforeEach(() => { vi.stubGlobal('fetch', vi.fn(async (url: string) => ({ ok: true, json: async () => fixtureResponse(url) }))) })
afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals() })

const liveConfig = { ...config, live_enabled: true, model_configured: true, data_store: runOptions.data_store }
const liveReadiness = { data: { ...readiness, live_configuration: { ready: true, missing_fields: [] } }, error: null, loading: false }
const registered: RunOptions = { ...runOptions, agents: runOptions.agents.map(agent => ({ ...agent, registered: true, registration_id: agent.proposed_registration_id })) }
const saved = (declaration: DiscoveryDeclaration, available = true): DiscoveryDeclaration => ({ ...declaration, history: agentHistory(available) })
const learnPlan = (discovery: DiscoveryDeclaration | null, agent: 'reference' | 'smolagents' = 'smolagents') => planned(campaign, {
  mode: 'learn', config_profile_id: 'live-v1', source_mode: 'live', agent,
  selection: { kind: 'development_search', manifest_hash: runOptions.learn.manifest_hash, search_space: runOptions.learn.search_space }, discovery })
const check = (plan: ReturnType<typeof learnPlan>) => validateCampaignPlan({ campaign_id: campaign.campaign_id, status: 'PLANNED', plan }, campaign.campaign_id)
const options = (protocols: NonNullable<RunOptions['learn']['discovery_protocols']>) => ({ ...runOptions, learn: { ...runOptions.learn, discovery_protocols: protocols } })

it('accepts the v3 options with history still unfrozen and rejects an over-reaching v3 option', () => {
  expect(validateRunOptions(runOptions)).toEqual(runOptions)
  const [v1, v2, v3, v3p] = runOptions.learn.discovery_protocols!
  for (const protocols of [
    [{ ...v1, default: false }, { ...v3, default: true }, v2, v3p],                             // v3 is never the default
    [v1, v2, v3, { ...v3p, supported_agents: ['reference', 'smolagents'] }],                     // the pre-check never covers the native agent
    [v1, v2, { ...v3, declaration: saved(discoveryV3) }, v3p],                                   // options never carry a frozen history
    [v1, v2, { ...v3, declaration: { ...discoveryV3, history: undefined } }, v3p],               // ...but a v3 option says it has none yet
    [{ ...v1, declaration: { ...discoveryV1, history: null } }, v2, v3, v3p],                    // v1 and v2 never carry the field
    [v1, v2, { ...v3, declaration: { ...discoveryV3, explorer_requests_max: 16 } }, v3p],        // v3-history's budget is v1's
    [v1, v2, v3, { ...v3p, declaration: { ...discoveryV3Precheck, pre_check: null } }],          // v3 with pre-check is v2's dispatch
  ] as NonNullable<RunOptions['learn']['discovery_protocols']>[]) expect(() => validateRunOptions(options(protocols))).toThrow('Malformed')
})

it('validates a saved v3 plan only with its frozen history', () => {
  for (const discovery of [saved(discoveryV3), saved(discoveryV3, false)]) expect(check(learnPlan(discovery)).status).toBe('PLANNED')
  expect(check(learnPlan(saved(discoveryV3Precheck), 'reference')).status).toBe('PLANNED')
  const other = agentHistory()
  for (const plan of [
    learnPlan(discoveryV3),                                                                              // history not frozen
    learnPlan(saved(discoveryV3Precheck)),                                                               // pre-check with the native agent
    learnPlan({ ...discoveryV3, history: { ...other, policy_hash: 'f'.repeat(64) } }),                  // frozen for another starting policy
    learnPlan({ ...discoveryV3, history: { ...other, status: 'NO_PRIOR_HISTORY' } }),                   // status disagrees with its summary
    learnPlan({ ...discoveryV3, history: { ...other, summary: { ...other.summary, verified_episodes: 0 } } }),
    learnPlan({ ...discoveryV3, history: { ...other, summary_hash: 'not-a-hash' } }),
    learnPlan({ ...discoveryV1, history: agentHistory() }),                                              // v1 carries no history
  ]) expect(() => check(plan)).toThrow('Malformed')
})

it('shows the frozen history, its hash and cutoff in the saved plan, and says plainly when there is none', () => {
  render(h(CampaignPlan, { campaign, resource: { data: { campaign_id: campaign.campaign_id, status: 'PLANNED', plan: learnPlan(saved(discoveryV3)) }, error: null, loading: false } }))
  const region = screen.getByRole('region', { name: 'Frozen agent history' })
  expect(within(region).getByText(/^Prior evidence, not an instruction: verified development outcomes/)).toBeTruthy()
  expect(within(region).getByText(/the Explorer still chooses freely/)).toBeTruthy()
  expect(within(region).getByText('e'.repeat(64))).toBeTruthy()
  expect(within(region).getByText(/store row 827 · later records never enter this history/)).toBeTruthy()
  expect(within(region).getByText('6 verified episodes · 2 recipes')).toBeTruthy()
  expect(within(region).getByText('lab errors: 1')).toBeTruthy()
  const dev5 = within(region).getByText(/FAILED \(UPGRADE_REJECTED\)/).closest('li')!
  expect(dev5.textContent).toContain('dev-5')
  expect(dev5.textContent).toContain('3 verified · outcomes VIOLATION 3 · failed checks C3 (upgrade before confirmation) 3 · C5 (truthful report) 3 · every fault fired 3 of 3')
  expect(dev5.textContent).toContain('Ran under runtime a8a32234a45a, c0a8aad71dfe · adapter 61497db3ae1d, 8a579f997793')
  expect(within(region).getByText('2 baseline studies (6 episodes) · 0 learn campaigns\' discovery (0 episodes)')).toBeTruthy()
  expect(within(region).getByText('runtime a8a32234a45a · adapter 61497db3ae1d (4) · runtime c0a8aad71dfe · adapter 8a579f997793 (2)')).toBeTruthy()
  expect(within(region).getByRole('list', { name: 'Recipes in the agent history' }).children).toHaveLength(2)
  expect(screen.getByText('v3 · agent history (dispatch exactly as v1)')).toBeTruthy()
  cleanup()
  render(h(CampaignPlan, { campaign, resource: { data: { campaign_id: campaign.campaign_id, status: 'PLANNED', plan: learnPlan(saved(discoveryV3, false)) }, error: null, loading: false } }))
  const empty = screen.getByRole('region', { name: 'Frozen agent history' })
  expect(within(empty).getByText(/^No prior history: this store has no verified development episodes/)).toBeTruthy()
  expect(within(empty).getByText(NO_HISTORY_IS_STILL_V3)).toBeTruthy()  // review: not a v1 run
  expect(within(empty).getByText('No prior history for this agent in this store')).toBeTruthy()
  expect(within(empty).queryByRole('list', { name: 'Recipes in the agent history' })).toBeNull()
})

it('offers v3 for the native agent without the pre-check and sends the declared id; nothing starts', async () => {
  vi.spyOn(runApi, 'options').mockResolvedValue(registered)
  const create = vi.spyOn(runApi, 'create').mockResolvedValue({ ...campaign, mode: 'learn', state: 'IDLE', config_profile_id: 'live-v1' })
  const start = vi.spyOn(api, 'start')
  render(h(RunSetup, { config: liveConfig, replay: false, readiness: liveReadiness, onCampaign: vi.fn() }))
  await screen.findByText('Current plan preview')
  fireEvent.change(screen.getByLabelText('Execution profile'), { target: { value: 'live-v1' } })
  fireEvent.change(screen.getByLabelText('Reviewed agent'), { target: { value: 'smolagents' } })
  fireEvent.change(screen.getByLabelText('Campaign mode'), { target: { value: 'learn' } })
  expect((screen.getByRole('option', { name: 'v3 · agent history' }) as HTMLOptionElement).disabled).toBe(false)
  expect((screen.getByRole('option', { name: 'v3 · agent history + reachability pre-check' }) as HTMLOptionElement).disabled).toBe(true)
  fireEvent.change(screen.getByLabelText('Discovery protocol'), { target: { value: 'faultlab-discovery/v3-history' } })
  expect(screen.getByText(HISTORY_AT_PLAN_TIME)).toBeTruthy()
  const preview = screen.getByRole('region', { name: 'Current plan preview' })
  expect(within(preview).getByText(/v3 · agent history · 8 slots · at most 8 Explorer requests · at most 8 charged Explorer transport retries during discovery \(one per request with no answer\) · at most 8 Actor episodes · no re-plans/)).toBeTruthy()
  await waitFor(() => expect((screen.getByRole('button', { name: 'Create campaign' }) as HTMLButtonElement).disabled).toBe(false))
  fireEvent.click(screen.getByRole('button', { name: 'Create campaign' }))
  await waitFor(() => expect(create).toHaveBeenCalledOnce())
  expect(create.mock.calls[0][0]).toMatchObject({ mode: 'learn', discovery_protocol: 'faultlab-discovery/v3-history', agent_registration_id: 'smolagents-fixture' })
  expect(start).not.toHaveBeenCalled()
})

it('reads v3 pre-check selections like v2 ones and still rejects an undeclared protocol', () => {
  const spec = { seed: 1, primitives: [{ kind: 'F2' as const, target_tool: 'update_order' as const, target_service: 'orders' as const, occurrence: 1, parameters: { completion_delay_ticks: 2, terminal_status: 'FAILED' as const, failure_code: 'UPGRADE_REJECTED' as const } }] }
  const label = { labeller: 'faultlab-reachability/v2', all_forced: true, recipe: ['Recipe in words'], faults: [{ index: 0, fault: 'F2 in words', kind: 'F2', target: 'update_order:orders', attempt: 1, agent_attempts_seen: 0, rule: null, verdict: 'FORCED', reason_code: 'FORCED', explanation: 'Fires on the normal path.' }], agent_path: [], agent_business_calls: 3, fixture_id: 'standard-v1', caller_model: {} }
  const row = (protocol: string) => [{ selection_ref: 'selection-1', campaign_id: campaign.campaign_id, selection_index: 0, configuration_hash: hash, policy_hash: hash, raw_response: 'Model text',
    usage: { model_calls: 1, input_tokens: 100, output_tokens: 20, cost_dollars: null }, provenance: 'model', error: null, output: { fault_spec: spec, hypothesis: 'h' }, selected_output: { fault_spec: spec, hypothesis: 'h' },
    search_decision: { status: 'SELECTED', schedule_hash: hash, reason: null, prior_selection_refs: [], prior_episode_refs: [], discovery_protocol: protocol, identity_version: 'faultlab-schedule-identity/v2-order-aware', slot_request: 1, replan_of: null, refused_fault_spec: null, reachability: label } }]
  expect(validateSearchAttempts(row('faultlab-discovery/v3-history-reachability'), campaign.campaign_id)).toHaveLength(1)
  expect(() => validateSearchAttempts(row('faultlab-discovery/v3-history'), campaign.campaign_id)).toThrow(/Malformed/)
  expect(discoveryV2.protocol).toBe('faultlab-discovery/v2-reachability')
})


// ---------------------------------------------------------------- review fixes (September 29)
it('rejects histories the backend can no longer produce: v1 schema, single-case baseline rows, unaccounted episodes', () => {
  const other = agentHistory()
  const row = other.summary.recipes[1]
  for (const history of [
    { ...other, schema_version: 'faultlab-agent-history/v1' },                                                    // the pre-review format
    { ...other, summary: { ...other.summary, recipes: [other.summary.recipes[0], { ...row, sources: ['baseline_run'] }] } },   // operator-chosen case runs
    { ...other, summary: { ...other.summary, recipes: [other.summary.recipes[0], { ...row, runtime_hashes: [] }] } },          // a row must say its builds
    { ...other, summary: { ...other.summary, builds: [other.summary.builds[0]] } },                                // builds must account for every episode
    { ...other, summary: { ...other.summary, composition: { ...other.summary.composition, baseline_study_episodes: 5 } } },     // so must the composition
  ]) expect(() => check(learnPlan({ ...discoveryV3, history } as DiscoveryDeclaration))).toThrow('Malformed')
})

it('checks the frozen history against the store only when asked, and shows a stale plan plainly', async () => {
  const historyCheck = vi.spyOn(runApi, 'historyCheck').mockResolvedValue({ campaign_id: campaign.campaign_id, status: 'CHANGED', record_cutoff: 827, summary_hash: 'e'.repeat(64),
    message: 'The store\'s prior history for this agent changed at or before the plan\'s record cutoff (frozen summary eeeeeeeeeeee…, now ffffffffffff…); create a new plan' })
  render(h(CampaignPlan, { campaign: { ...campaign, state: 'IDLE' }, resource: { data: { campaign_id: campaign.campaign_id, status: 'PLANNED', plan: learnPlan(saved(discoveryV3)) }, error: null, loading: false } }))
  const region = screen.getByRole('region', { name: 'Frozen agent history' })
  expect(within(region).getByText(/If any record at or before store row 827 changed after the plan was saved, Start is refused/)).toBeTruthy()
  expect(historyCheck).not.toHaveBeenCalled()  // never polled
  fireEvent.click(within(region).getByRole('button', { name: 'Check against the store now' }))
  expect((await within(region).findByRole('status')).textContent).toMatch(/^Changed: Start will be refused\. The store's prior history .*create a new plan$/)
  expect(historyCheck).toHaveBeenCalledOnce()
  cleanup()
  render(h(CampaignPlan, { campaign: { ...campaign, state: 'NO_CHANGE' }, resource: { data: { campaign_id: campaign.campaign_id, status: 'PLANNED', plan: learnPlan(saved(discoveryV3)) }, error: null, loading: false } }))
  expect(screen.queryByRole('button', { name: 'Check against the store now' })).toBeNull()  // only before Start
  expect(() => validateHistoryCheck({ campaign_id: campaign.campaign_id, status: 'STALE', message: 'x', record_cutoff: 1, summary_hash: null }, campaign.campaign_id)).toThrow('Malformed')
  expect(validateHistoryCheck({ campaign_id: campaign.campaign_id, status: 'NOT_APPLICABLE', message: 'No v3.', record_cutoff: null, summary_hash: null }, campaign.campaign_id).status).toBe('NOT_APPLICABLE')
})

it('marks a v3 pick and source that re-try a history row as history-informed; v1 rows carry no flag', async () => {
  const spec = { seed: 77, primitives: [{ kind: 'F2' as const, target_tool: 'update_order' as const, target_service: 'orders' as const, occurrence: 1, parameters: { completion_delay_ticks: 2, terminal_status: 'FAILED' as const, failure_code: 'UPGRADE_REJECTED' as const } }] }
  const match = { row: 2, development_case_id: 'dev-5', basis: 'faultlab-schedule-identity/v2-order-aware' }
  const attempt = (extra: Record<string, unknown>) => ({ selection_ref: 'selection-1', campaign_id: campaign.campaign_id, selection_index: 0, configuration_hash: hash, policy_hash: hash, raw_response: 'Model text',
    usage: { model_calls: 1, input_tokens: 100, output_tokens: 20, cost_dollars: null }, provenance: 'model', error: null, output: { fault_spec: spec, hypothesis: 'h' }, selected_output: { fault_spec: spec, hypothesis: 'h' },
    search_decision: { status: 'SELECTED', schedule_hash: hash, reason: null, prior_selection_refs: [], prior_episode_refs: [] }, ...extra })
  expect(validateSearchAttempts([attempt({ matches_history_row: match })], campaign.campaign_id)[0].matches_history_row).toEqual(match)
  expect(validateSearchAttempts([attempt({ matches_history_row: null })], campaign.campaign_id)[0].matches_history_row).toBeNull()
  expect(validateSearchAttempts([attempt({})], campaign.campaign_id)[0].matches_history_row).toBeUndefined()
  expect(() => validateSearchAttempts([attempt({ matches_history_row: { row: 0, development_case_id: 'dev-5', basis: 'x' } })], campaign.campaign_id)).toThrow('Malformed')
  vi.stubGlobal('fetch', vi.fn(async () => ({ ok: true, json: async () => [attempt({ matches_history_row: match })] })))
  render(h(SearchAttemptsPanel, { campaignId: campaign.campaign_id, onEpisode: vi.fn() }))
  expect(await screen.findByText(/^History-informed: this recipe re-tries agent history row 2 \(dev-5\) that the Explorer was shown/)).toBeTruthy()
  cleanup()
  const counterexample = { counterexample_id: 'counterexample-1', campaign_id: campaign.campaign_id, agent_registration_id: 'smolagents-fixture', source_episode_id: 'episode-1', target_invariant: 'C3', scenario_hash: hash, configuration_hash: hash, report_ref: null, verdict_ref: 'verdict-1', created_at: '2026-09-29T00:00:00Z', reproduction_trial_ids: [], target_violation_count: 0, valid_count: 0, attempted_count: 0, reproduced: false }
  const experiments = (extra: Record<string, unknown>) => ({ counterexamples: [{ counterexample, source_recipe: spec, retained_recipe: null, reduction: null, diagnostics: [], interventions: [], challenges: [], ...extra }], evidence: [], ingestions: [], portability_ids: [] })
  const flagged = validateExperiments(experiments({ matches_history_row: match })).counterexamples
  expect(flagged[0].matches_history_row).toEqual(match)
  expect('matches_history_row' in validateExperiments(experiments({})).counterexamples[0]).toBe(false)
  expect(() => validateExperiments(experiments({ matches_history_row: 'dev-5' }))).toThrow('Malformed')
  render(h(CounterexamplePanel, { records: flagged, onEpisode: vi.fn() }))
  expect(screen.getByText('Agent history (v3)')).toBeTruthy()
  expect(screen.getByText(/re-tries agent history row 2 \(dev-5\)/)).toBeTruthy()
})
