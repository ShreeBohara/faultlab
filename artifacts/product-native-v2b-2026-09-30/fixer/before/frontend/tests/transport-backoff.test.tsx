// @vitest-environment jsdom
// September 30 builder: model transport retry rule v2 (faultlab-transport-retry/v2-lab-backoff), frozen into every new
// Learn plan. The agent keeps one retry per request; the Explorer and the Mechanic back off (5 s, 20 s, 60 s) and retry up
// to 3 times, at most 12 per campaign. Plans saved earlier, and baseline or compare plans, keep rule v1.
import { createElement as h } from 'react'
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { runApi, validateCampaignPlan, validateRunOptions, type RunOptions, type TransportRetryDeclarationV2 } from '../src/runPlans'
import { CampaignPlan } from '../src/components/CampaignPlan'
import { LATER_PHASE_RETRIES, LATER_PHASE_RETRIES_V2 } from '../src/components/DiscoveryProtocol'
import { RunSetup } from '../src/components/RunSetup'
import { SearchAttemptsPanel } from '../src/components/SearchAttemptsPanel'
import { validateSearchAttempts, type SearchAttempt } from '../src/searchAttempts'
import { campaign, config, fixtureResponse, hash, readiness } from './fixtures'
import { discoveryV1, planned, runOptions, transportRetryRule } from './run-fixtures'

beforeEach(() => { vi.stubGlobal('fetch', vi.fn(async (url: string) => ({ ok: true, json: async () => fixtureResponse(url) }))) })
afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals() })

/** As the backend freezes it into every new Learn plan (app/agents/transport_retry.py declaration_v2(8)). */
const ruleV2: TransportRetryDeclarationV2 = { protocol: 'faultlab-transport-retry/v2-lab-backoff', retryable: ['CONNECTION_ERROR', 'REQUEST_TIMEOUT', 'HTTP_503'],
  agent_roles: ['actor'], agent_retries_per_request: 1, service_unavailable_delay_seconds: 1, actor_retries_per_episode_max: 8,
  lab_roles: ['explorer', 'mechanic'], lab_retries_per_request: 3, lab_backoff_seconds: [5, 20, 60], lab_retries_per_campaign_max: 12, stop_during_wait: 'STOPPED',
  rule: 'Agent roles keep rule v1. FaultLab\'s own lab roles in this Learn campaign may re-send the identical request up to 3 times, after waits of 5 s, 20 s and 60 s.' }
const learnPlan = (transport_retry: unknown) => planned(campaign, { mode: 'learn', config_profile_id: 'live-v1', source_mode: 'live',
  selection: { kind: 'development_search', manifest_hash: runOptions.learn.manifest_hash, search_space: runOptions.learn.search_space },
  discovery: discoveryV1, transport_retry: transport_retry as TransportRetryDeclarationV2 })
const envelope = (plan: ReturnType<typeof planned>) => ({ campaign_id: campaign.campaign_id, status: 'PLANNED' as const, plan })

it('accepts rule v2 only in a Learn plan and only exactly as declared; rule v1 plans still read', () => {
  expect(validateCampaignPlan(envelope(learnPlan(ruleV2)), campaign.campaign_id).status).toBe('PLANNED')
  expect(validateCampaignPlan(envelope(learnPlan(transportRetryRule)), campaign.campaign_id).status).toBe('PLANNED')   // saved before v2
  expect(() => validateCampaignPlan(envelope(planned(campaign, { transport_retry: ruleV2 })), campaign.campaign_id)).toThrow('Malformed campaign plan transport retry rule')
  for (const change of [{ lab_backoff_seconds: [5, 20, 30] }, { lab_retries_per_campaign_max: 24 }, { lab_retries_per_request: 4 }, { agent_retries_per_request: 2 },
    { lab_roles: ['explorer'] }, { agent_roles: ['actor', 'explorer'] }, { stop_during_wait: 'ERROR' }, { actor_retries_per_episode_max: 16 }, { rule: ' ' }]) {
    expect(() => validateCampaignPlan(envelope(learnPlan({ ...ruleV2, ...change })), campaign.campaign_id)).toThrow('Malformed campaign plan transport retry rule')
  }
  expect(validateRunOptions({ ...runOptions, learn: { ...runOptions.learn, transport_retry: ruleV2 } }).learn.transport_retry).toEqual(ruleV2)
  expect(() => validateRunOptions({ ...runOptions, learn: { ...runOptions.learn, transport_retry: { ...ruleV2, lab_backoff_seconds: [1, 1, 1] } } } as RunOptions)).toThrow('Malformed Learn transport retry rule')
})

it('shows rule v2 in the saved plan, beside the discovery bound, and rule v1 for a plan saved before it', () => {
  render(h(CampaignPlan, { campaign, resource: { data: envelope(learnPlan(ruleV2)), error: null, loading: false } }))
  let region = screen.getByRole('region', { name: 'Saved campaign plan' })
  expect(within(region).getByText('Model transport retries').nextElementSibling!.textContent).toBe('Agent (Actor) requests: at most one charged retry per request that received no answer (connection error, timeout, HTTP 503) · at most 8 per episode · Explorer and Mechanic requests: up to 3 charged retries each, after waits of 5 s, 20 s, 60 s · at most 12 per campaign · a Stop during a wait ends the campaign STOPPED · never after an answer · never an extra turn')
  expect(within(region).getByText(ruleV2.rule)).toBeTruthy()
  expect(within(region).getByText(/Explorer requests/).textContent).toContain('at most 8 charged Explorer transport retries during discovery (up to 3 per request with no answer, after waits of 5 s, 20 s and 60 s)')
  expect(within(region).getByText(LATER_PHASE_RETRIES_V2)).toBeTruthy()
  expect(within(region).queryByText(LATER_PHASE_RETRIES)).toBeNull()
  cleanup()
  render(h(CampaignPlan, { campaign, resource: { data: envelope(learnPlan(transportRetryRule)), error: null, loading: false } }))
  region = screen.getByRole('region', { name: 'Saved campaign plan' })
  expect(within(region).getByText('Model transport retries').nextElementSibling!.textContent).toMatch(/^At most one charged retry per Actor, Explorer or Mechanic request/)
  expect(within(region).getByText(/Explorer requests/).textContent).toContain('(one per request with no answer)')
  expect(within(region).getByText(LATER_PHASE_RETRIES)).toBeTruthy()
})

it('describes rule v2 in the Learn setup when the backend offers it', async () => {
  const offered: RunOptions = { ...runOptions, learn: { ...runOptions.learn, transport_retry: ruleV2 },
    agents: runOptions.agents.map(agent => ({ ...agent, registered: true, registration_id: agent.proposed_registration_id })) }
  vi.spyOn(runApi, 'options').mockResolvedValue(offered)
  const liveConfig = { ...config, live_enabled: true, model_configured: true, data_store: runOptions.data_store }
  const liveReadiness = { data: { ...readiness, live_configuration: { ready: true, missing_fields: [] } }, error: null, loading: false }
  render(h(RunSetup, { config: liveConfig, replay: false, readiness: liveReadiness, onCampaign: vi.fn() }))
  await screen.findByText('Current plan preview')
  fireEvent.change(screen.getByLabelText('Execution profile'), { target: { value: 'live-v1' } })
  fireEvent.change(screen.getByLabelText('Campaign mode'), { target: { value: 'learn' } })
  const preview = screen.getByRole('region', { name: 'Current plan preview' })
  await waitFor(() => expect(within(preview).getByText(/up to 3 per request with no answer, after waits of 5 s, 20 s and 60 s/)).toBeTruthy())
  expect(screen.getByText(LATER_PHASE_RETRIES_V2)).toBeTruthy()
})

function attempt(retries: unknown, modelCalls: number): SearchAttempt {
  const output = { fault_spec: { seed: 1, primitives: [{ kind: 'F2' as const, target_tool: 'update_order' as const, target_service: 'orders' as const, occurrence: 1, parameters: { completion_delay_ticks: 3, terminal_status: 'SUCCEEDED' as const, failure_code: null } }] }, hypothesis: 'A model-authored hypothesis.' }
  return { selection_ref: 'selection-backoff', campaign_id: campaign.campaign_id, selection_index: 0, configuration_hash: hash, policy_hash: hash,
    search_decision: { status: 'SELECTED', schedule_hash: hash, reason: null, prior_selection_refs: [], prior_episode_refs: [] },
    selected_output: output, output, raw_response: 'Original model text retained.',
    usage: { model_calls: modelCalls, input_tokens: 100, output_tokens: 20, cost_dollars: null }, provenance: 'model', error: null,
    transport_retries: retries as SearchAttempt['transport_retries'] }
}
const backoff = (attempt: 1 | 2 | 3, code = 'CONNECTION_ERROR') => ({ retry_id: `transport-retry-${attempt}`, protocol: 'faultlab-transport-retry/v2-lab-backoff',
  code, attempt, retry_delay_seconds: [5, 20, 60][attempt - 1], provider_failure_id: `provider-failure-${attempt}`, ...(code === 'HTTP_ERROR' ? { http_status: 503 } : {}) })

it('shows backed-off Explorer retries on their selection and refuses inconsistent ones', async () => {
  const three = [backoff(1), backoff(2, 'HTTP_ERROR'), backoff(3, 'REQUEST_TIMEOUT')]
  expect(validateSearchAttempts([attempt(three, 4)], campaign.campaign_id)[0].transport_retries).toEqual(three)
  expect(validateSearchAttempts([attempt([backoff(1)], 2)], campaign.campaign_id)).toHaveLength(1)
  const v1 = { retry_id: 'transport-retry-v1', code: 'CONNECTION_ERROR', attempt: 1, provider_failure_id: 'provider-failure-v1' }
  for (const bad of [attempt(three, 3), attempt([backoff(2)], 2), attempt([backoff(1), backoff(1)], 3), attempt([{ ...backoff(1), retry_delay_seconds: 1 }], 2),
    attempt([...three, { ...backoff(3), retry_id: 'transport-retry-4', attempt: 4 }], 5), attempt([backoff(1), { ...v1, attempt: 2 }], 3),
    attempt([{ ...backoff(1), protocol: 'faultlab-transport-retry/v1' }], 2), attempt([{ ...backoff(1), code: 'HTTP_ERROR' }], 2)]) {
    expect(() => validateSearchAttempts([bad], campaign.campaign_id)).toThrow(/Malformed/)
  }
  vi.stubGlobal('fetch', vi.fn(async () => ({ ok: true, json: async () => [attempt(three.slice(0, 2), 3)] })))
  render(h(SearchAttemptsPanel, { campaignId: campaign.campaign_id, onEpisode: vi.fn() }))
  fireEvent.click(await screen.findByText('Selection 1 · Selected for execution'))
  const notes = screen.getAllByText(/Transport retry \d of at most 3/)
  expect(notes.map(note => note.textContent)).toEqual([
    'Transport retry 1 of at most 3: the previous request received no answer (connection error), so after waiting 5 s the identical request was sent again. Every request is charged (3 model requests in all); this is not a new selection request. Provider failure provider-failure-1.',
    'Transport retry 2 of at most 3: the previous request received no answer (HTTP 503), so after waiting 20 s the identical request was sent again. Every request is charged (3 model requests in all); this is not a new selection request. Provider failure provider-failure-2.'])
})
