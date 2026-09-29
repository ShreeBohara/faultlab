// @vitest-environment jsdom
import { createElement as h } from 'react'
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { api } from '../src/api'
import { runApi, validateCampaignPlan, validateRunOptions, type RunOptions } from '../src/runPlans'
import { RunSetup } from '../src/components/RunSetup'
import { CampaignPlan } from '../src/components/CampaignPlan'
import { LATER_PHASE_RETRIES } from '../src/components/DiscoveryProtocol'
import { SearchAttemptsPanel } from '../src/components/SearchAttemptsPanel'
import { validateSearchAttempts, type SearchAttempt } from '../src/searchAttempts'
import { campaign, config, fixtureResponse, hash, readiness } from './fixtures'
import { discoveryV1, discoveryV2, planned, runOptions } from './run-fixtures'

beforeEach(() => { vi.stubGlobal('fetch', vi.fn(async (url: string) => ({ ok: true, json: async () => fixtureResponse(url) }))) })
afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals() })

const liveConfig = { ...config, live_enabled: true, model_configured: true, data_store: runOptions.data_store }
const liveReadiness = { data: { ...readiness, live_configuration: { ready: true, missing_fields: [] } }, error: null, loading: false }
const registered: RunOptions = { ...runOptions, agents: runOptions.agents.map(agent => ({ ...agent, registered: true, registration_id: agent.proposed_registration_id })) }
const learnPlan = (discovery: typeof discoveryV1 | null, agent: 'reference' | 'smolagents' = 'reference') => planned(campaign, {
  mode: 'learn', config_profile_id: 'live-v1', source_mode: 'live', agent,
  selection: { kind: 'development_search', manifest_hash: runOptions.learn.manifest_hash, search_space: runOptions.learn.search_space }, discovery })

it('accepts the declared discovery protocols and rejects an inconsistent or over-reaching declaration', () => {
  expect(validateRunOptions(runOptions)).toEqual(runOptions)
  const [v1, v2] = runOptions.learn.discovery_protocols!
  for (const protocols of [
    [v1, { ...v2, default: true }],                                              // v2 is never the default
    [v1, { ...v2, supported_agents: ['reference', 'smolagents'] }],              // never pre-checks the native agent
    [v1, { ...v2, declaration: { ...discoveryV2, explorer_requests_max: 8 } }],  // budget must be two requests per slot
    [v1, { ...v2, declaration: { ...discoveryV2, explorer_transport_retries_max: 32 } }],  // at most one retry per request
    [{ ...v1, declaration: { ...discoveryV1, explorer_transport_retries_max: 16 } }, v2],
    [v1, { ...v2, declaration: { ...discoveryV2, pre_check: null } }],
    [{ ...v1, declaration: { ...discoveryV1, replans_per_slot: 1 } }, v2],
  ]) expect(() => validateRunOptions({ ...runOptions, learn: { ...runOptions.learn, discovery_protocols: protocols } })).toThrow('Malformed')
})

it('validates the frozen discovery block and shows it in the saved plan', async () => {
  for (const discovery of [discoveryV1, discoveryV2, null]) {
    expect(validateCampaignPlan({ campaign_id: campaign.campaign_id, status: 'PLANNED', plan: learnPlan(discovery) }, campaign.campaign_id).status).toBe('PLANNED')
  }
  for (const plan of [learnPlan(discoveryV2, 'smolagents'), { ...planned(campaign), discovery: discoveryV1 }, learnPlan({ ...discoveryV2, actor_episodes_max: 16 })]) {
    expect(() => validateCampaignPlan({ campaign_id: campaign.campaign_id, status: 'PLANNED', plan }, campaign.campaign_id)).toThrow('Malformed')
  }
  render(h(CampaignPlan, { campaign, resource: { data: { campaign_id: campaign.campaign_id, status: 'PLANNED', plan: learnPlan(discoveryV2) }, error: null, loading: false } }))
  const region = screen.getByRole('region', { name: 'Saved campaign plan' })
  expect(within(region).getByText('v2 · reachability pre-check')).toBeTruthy()
  expect(within(region).getByText(/at most 16 Explorer requests · at most 16 charged Explorer transport retries during discovery \(one per request with no answer\) · at most 8 Actor episodes · one re-plan per refused slot/)).toBeTruthy()
  expect(within(region).getAllByText(/no wait action/).some(node => node.tagName === 'LI')).toBe(true)
  // Review finding: the caller model must not claim a re-send after UNKNOWN, and must say which Actor it describes.
  expect(within(region).getAllByText(/does not send a failed write again/).some(node => node.tagName === 'LI')).toBe(true)
  expect(within(region).queryAllByText(/sends a write again only after/)).toEqual([])
  const described = within(region).getAllByText(/describes the typical path of deepseek-ai\/DeepSeek-V3\.1 under policy-v0, not other models/).find(node => node.tagName === 'P')
  expect(described?.textContent).toContain('reference-actor/policy-v0/v2')
  expect(within(region).queryAllByText(/Checked against/)).toEqual([])
})

it('declares v2 for the reference agent explicitly and never offers it for the native agent', async () => {
  vi.spyOn(runApi, 'options').mockResolvedValue(registered)
  const create = vi.spyOn(runApi, 'create').mockResolvedValue({ ...campaign, mode: 'learn', state: 'IDLE', config_profile_id: 'live-v1' })
  const start = vi.spyOn(api, 'start')
  render(h(RunSetup, { config: liveConfig, replay: false, readiness: liveReadiness, onCampaign: vi.fn() }))
  await screen.findByText('Current plan preview')
  fireEvent.change(screen.getByLabelText('Execution profile'), { target: { value: 'live-v1' } })
  fireEvent.change(screen.getByLabelText('Campaign mode'), { target: { value: 'learn' } })
  expect((screen.getByLabelText('Discovery protocol') as HTMLSelectElement).value).toBe('faultlab-discovery/v1')
  fireEvent.change(screen.getByLabelText('Discovery protocol'), { target: { value: 'faultlab-discovery/v2-reachability' } })
  const preview = screen.getByRole('region', { name: 'Current plan preview' })
  expect(within(preview).getByText(/v2 · reachability pre-check · 8 slots · at most 16 Explorer requests · at most 16 charged Explorer transport retries during discovery \(one per request with no answer\) · at most 8 Actor episodes/)).toBeTruthy()
  expect(screen.getByText(LATER_PHASE_RETRIES)).toBeTruthy()  // the declared retry bound is discovery-only
  await waitFor(() => expect((screen.getByRole('button', { name: 'Create campaign' }) as HTMLButtonElement).disabled).toBe(false))
  fireEvent.click(screen.getByRole('button', { name: 'Create campaign' }))
  await waitFor(() => expect(create).toHaveBeenCalledOnce())
  expect(create.mock.calls[0][0]).toMatchObject({ mode: 'learn', discovery_protocol: 'faultlab-discovery/v2-reachability', agent_registration_id: 'reference-fixture' })
  expect(start).not.toHaveBeenCalled()
  fireEvent.change(screen.getByLabelText('Reviewed agent'), { target: { value: 'smolagents' } })
  expect((screen.getByLabelText('Discovery protocol') as HTMLSelectElement).value).toBe('faultlab-discovery/v1')
  expect((screen.getByRole('option', { name: 'v2 · reachability pre-check' }) as HTMLOptionElement).disabled).toBe(true)
})

const faults = (verdicts: ('FORCED' | 'NOT_FORCED')[]) => verdicts.map((verdict, index) => ({ index, fault: `Fault ${index} described in words`, kind: 'F4', target: 'get_operation_status:orders', attempt: 1, agent_attempts_seen: 0, rule: null, verdict, reason_code: verdict === 'FORCED' ? 'FORCED' : 'N2_UNNEEDED_STATUS_CHECK', explanation: verdict === 'FORCED' ? 'Fires on the normal path.' : 'Not forced: this agent checks status only while an operation is pending.' }))
const label = (verdicts: ('FORCED' | 'NOT_FORCED')[]) => ({ labeller: 'faultlab-reachability/v2', all_forced: verdicts.every(v => v === 'FORCED'), recipe: ['Recipe in words'], faults: faults(verdicts), agent_path: ['get_order:orders#200', 'update_order:orders#200', 'send_confirmation:notifications#201'], agent_business_calls: 3, fixture_id: 'standard-v1', caller_model: {} })
const spec = { seed: 1, primitives: [{ kind: 'F4' as const, target_tool: 'get_operation_status' as const, target_service: 'orders' as const, occurrence: 1, parameters: { failure_count: 1 } }] }
function v2rows(): SearchAttempt[] {
  const base = { campaign_id: campaign.campaign_id, selection_index: 2, configuration_hash: hash, policy_hash: hash, raw_response: 'Model text', usage: { model_calls: 1, input_tokens: 100, output_tokens: 20, cost_dollars: null }, provenance: 'model', error: null }
  const common = { schedule_hash: hash, prior_selection_refs: [], prior_episode_refs: [], discovery_protocol: 'faultlab-discovery/v2-reachability' as const, identity_version: 'faultlab-schedule-identity/v2-order-aware' }
  return [
    { ...base, selection_ref: 'selection-refused', output: { fault_spec: spec, hypothesis: 'h' }, selected_output: null,
      search_decision: { ...common, status: 'SKIPPED_UNREACHABLE', reason: 'NOT_ALL_FAULTS_FORCED', slot_request: 1, replan_of: null, refused_fault_spec: spec, reachability: label(['NOT_FORCED']) } },
    { ...base, selection_ref: 'selection-replan', output: { fault_spec: spec, hypothesis: 'h' }, selected_output: { fault_spec: spec, hypothesis: 'h' },
      search_decision: { ...common, status: 'SELECTED', reason: null, slot_request: 2, replan_of: 'selection-refused', refused_fault_spec: null, reachability: label(['FORCED']) } },
  ]
}

it('shows each pre-check refusal, its plain reason and the linked re-plan, without any execution control', async () => {
  vi.stubGlobal('fetch', vi.fn(async () => ({ ok: true, json: async () => v2rows() })))
  render(h(SearchAttemptsPanel, { campaignId: campaign.campaign_id, onEpisode: vi.fn() }))
  expect((await screen.findByText('Refused by pre-check')).parentElement?.textContent).toBe('1Refused by pre-check')
  fireEvent.click(screen.getByText('Selection 3 · Refused by the reachability pre-check · no Actor trial'))
  expect(screen.getAllByText(/checks status only while an operation is pending/).some(node => node.closest('ul.fault-verdicts'))).toBe(true)
  expect(screen.getByText(/This slot received one re-plan request/)).toBeTruthy()
  fireEvent.click(screen.getByText('Selection 3 · re-plan · Selected for execution'))
  expect(screen.getByText(/Re-plan request for this slot, after refused selection/)).toBeTruthy()
  expect(screen.queryByRole('button', { name: /start|run|retry|execute/i })).toBeNull()
})

it.each([
  ['a v2 status without the declared protocol', (rows: SearchAttempt[]) => { delete rows[0].search_decision.discovery_protocol }],
  ['a selected v2 pick that was not all forced', (rows: SearchAttempt[]) => { rows[1].search_decision.reachability = label(['NOT_FORCED']) as never }],
  ['a pre-check refusal whose faults were all forced', (rows: SearchAttempt[]) => { rows[0].search_decision.reachability = label(['FORCED']) as never }],
  ['a re-plan without its refused selection', (rows: SearchAttempt[]) => { rows[1].search_decision.replan_of = null }],
  ['a refusal without the refused recipe', (rows: SearchAttempt[]) => { rows[0].search_decision.refused_fault_spec = null }],
] as const)('rejects %s', (_, mutate) => {
  const rows = v2rows(); mutate(rows)
  expect(() => validateSearchAttempts(rows, campaign.campaign_id)).toThrow(/Malformed/)
})

// Transport retries (September 29): one charged retry per Explorer request that got no answer is
// declared beside the request budget, never inside it; plans saved earlier declare none.
it('shows the declared Explorer transport retry bound, and says so when an older plan declares none', () => {
  const older = { ...discoveryV2 }; delete older.explorer_transport_retries_max
  for (const [discovery, expected] of [[discoveryV2, 'at most 16 charged Explorer transport retries during discovery (one per request with no answer)'],
    [discoveryV1, 'at most 8 charged Explorer transport retries during discovery (one per request with no answer)'],
    [older, 'no Explorer transport retry declared'], [{ ...older, explorer_transport_retries_max: null }, 'no Explorer transport retry declared']] as const) {
    const plan = learnPlan(discovery as typeof discoveryV1)
    expect(validateCampaignPlan({ campaign_id: campaign.campaign_id, status: 'PLANNED', plan }, campaign.campaign_id).status).toBe('PLANNED')
    render(h(CampaignPlan, { campaign, resource: { data: { campaign_id: campaign.campaign_id, status: 'PLANNED', plan }, error: null, loading: false } }))
    const region = screen.getByRole('region', { name: 'Saved campaign plan' })
    const budget = within(region).getByText(/Explorer requests/)
    expect(budget.textContent).toContain(`at most ${discovery.explorer_requests_max} Explorer requests · ${expected} · at most 8 Actor episodes`)
    // Review finding (LOW, September 29): the declared number covers discovery only; the box says
    // how retries in later phases are bounded. A plan that declared no retries gets no such line.
    expect(within(region).queryByText(LATER_PHASE_RETRIES) !== null).toBe(typeof discovery.explorer_transport_retries_max === 'number')
    cleanup()
  }
})
