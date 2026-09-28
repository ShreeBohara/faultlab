// @vitest-environment jsdom
import { createElement as h } from 'react'
import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { api, validateRecording } from '../src/api'
import { runApi, validateCampaignPlan, validateRunOptions, type RunOptions } from '../src/runPlans'
import { RunSetup } from '../src/components/RunSetup'
import { RunControls } from '../src/components/RunControls'
import { RecordingDownload } from '../src/components/RecordingDownload'
import { campaign, config, fixtureResponse, readiness, registration } from './fixtures'
import { planned, runOptions } from './run-fixtures'
import { validateContract } from '../src/generated/validate'
import type { AgentRegistration } from '../src/generated/contracts'

beforeEach(() => { vi.stubGlobal('fetch', vi.fn(async (url: string) => ({ ok: true, json: async () => fixtureResponse(url) }))) })
afterEach(() => { cleanup(); vi.useRealTimers(); vi.restoreAllMocks(); vi.unstubAllGlobals() })

it('decodes only provider-free public run options and rejects conflicting identities or unsupported cases', () => {
  expect(validateRunOptions(runOptions)).toEqual(runOptions)
  const patches = [
    { provider_calls: 1 }, { setup_hash: 'not-a-digest' }, { caps: {} },
    { task: { ...runOptions.task, task_definition_id: 'arbitrary-task' } },
    { profiles: [runOptions.profiles[0], runOptions.profiles[0]] },
    { development: { ...runOptions.development, cases: runOptions.development.cases.map((item, i) => i ? item : { ...item, case_id: 'protected-1' }) } },
    { agents: runOptions.agents.map((item, i) => i ? item : { ...item, behavior_verified: true }) },
    { agents: runOptions.agents.map((item, i) => i ? item : { ...item, provider_access: 'verified' }) },
    { agents: runOptions.agents.map((item, i) => i ? item : { ...item, registered: true }) },
    { agents: runOptions.agents.map((item, i) => i ? item : { ...item, compare_available: true }) },
    { learn: { ...runOptions.learn, search_space: { ...runOptions.learn.search_space, occurrence: [-1] } } },
  ]
  for (const patch of patches) expect(() => validateRunOptions({ ...runOptions, ...patch })).toThrow('Malformed')
})

it('keeps missing historical plans explicit and validates every planned mode/profile binding', () => {
  const envelope = { campaign_id: campaign.campaign_id, status: 'PLANNED', plan: planned(campaign) }
  expect(validateCampaignPlan(envelope, campaign.campaign_id)).toEqual(envelope)
  expect(validateCampaignPlan({ campaign_id: campaign.campaign_id, status: 'LEGACY', plan: null }, campaign.campaign_id).status).toBe('LEGACY')
  for (const patch of [ { campaign_id: 'foreign' }, { status: 'LEGACY' }, { plan: null }, { plan: { ...envelope.plan, agent: 'smolagents' } }, { plan: { ...envelope.plan, mode: 'learn' } }, { plan: { ...envelope.plan, plan_hash: '' } } ]) {
    expect(() => validateCampaignPlan({ ...envelope, ...patch }, campaign.campaign_id)).toThrow('Malformed')
  }
  for (const mode of ['learn', 'compare'] as const) {
    const plan = planned(campaign, { mode, config_profile_id: 'live-v1', source_mode: 'live', agent: 'smolagents', selection: mode === 'learn' ? { kind: 'development_search', manifest_hash: runOptions.learn.manifest_hash, search_space: runOptions.learn.search_space } : { kind: 'protected_comparison', ...runOptions.compare } })
    expect(validateCampaignPlan({ ...envelope, plan }, campaign.campaign_id).status).toBe('PLANNED')
  }
})

const liveConfig = { ...config, live_enabled: true, model_configured: true, data_store: runOptions.data_store }
const liveReadiness = { data: { ...readiness, live_configuration: { ready: true, missing_fields: [] } }, error: null, loading: false }
function selectedOptions(agentKind: 'reference' | 'smolagents', extra: Partial<RunOptions['agents'][number]> = {}): RunOptions {
  return { ...runOptions, agents: runOptions.agents.map(agent => agent.agent === agentKind ? { ...agent, registered: true, registration_id: agent.proposed_registration_id, ...extra } : agent) }
}

it('creates an offline selected public case when both live agents are unavailable and never starts it', async () => {
  const unavailable = { ...runOptions, agents: runOptions.agents.map(agent => ({ ...agent, status: 'UNAVAILABLE' as const, reason_code: 'MODEL_UNCONFIGURED', message: 'Configure a model.', model: '', configuration_hash: null, proposed_registration_id: null, source_conformance: 'UNAVAILABLE' as const })) }
  vi.spyOn(runApi, 'options').mockResolvedValue(validateRunOptions(unavailable))
  const create = vi.spyOn(runApi, 'create').mockResolvedValue({ ...campaign, state: 'IDLE' })
  const register = vi.spyOn(runApi, 'register')
  const start = vi.spyOn(api, 'start')
  const receive = vi.fn()
  render(h(RunSetup, { config, replay: false, onCampaign: receive }))
  await screen.findByText('Current plan preview')
  expect(screen.queryByRole('button', { name: 'Register configured agent' })).toBeNull()
  fireEvent.change(screen.getByLabelText('Public development case'), { target: { value: 'dev-4' } })
  expect(create).not.toHaveBeenCalled()
  expect(register).not.toHaveBeenCalled()
  await waitFor(() => expect((screen.getByRole('button', { name: 'Create campaign' }) as HTMLButtonElement).disabled).toBe(false))
  fireEvent.click(screen.getByRole('button', { name: 'Create campaign' }))
  await waitFor(() => expect(create).toHaveBeenCalledOnce())
  expect(create.mock.calls[0][0]).toMatchObject({ expected_store_identity: runOptions.data_store.identity, expected_setup_hash: runOptions.setup_hash, task_definition_id: runOptions.task.task_definition_id, mode: 'baseline', config_profile_id: 'offline-v1', development_case_id: 'dev-4' })
  expect(create.mock.calls[0][0].agent_registration_id).toBeUndefined()
  expect(start).not.toHaveBeenCalled()
  expect(receive).toHaveBeenCalledOnce()
})

it('registers native explicitly, refreshes read-only options, and creates original Learn with that exact registration', async () => {
  const options = vi.spyOn(runApi, 'options').mockResolvedValueOnce(runOptions).mockResolvedValue(selectedOptions('smolagents'))
  const register = vi.spyOn(runApi, 'register').mockResolvedValue(validateContract<AgentRegistration>('AgentRegistration', registration))
  const create = vi.spyOn(runApi, 'create').mockResolvedValue({ ...campaign, mode: 'learn', state: 'IDLE', config_profile_id: 'live-v1' })
  const start = vi.spyOn(api, 'start')
  render(h(RunSetup, { config: liveConfig, replay: false, readiness: liveReadiness, onCampaign: vi.fn() }))
  await screen.findByText('Current plan preview')
  fireEvent.change(screen.getByLabelText('Execution profile'), { target: { value: 'live-v1' } })
  fireEvent.change(screen.getByLabelText('Reviewed agent'), { target: { value: 'smolagents' } })
  fireEvent.change(screen.getByLabelText('Campaign mode'), { target: { value: 'learn' } })
  expect(screen.queryByLabelText('Public development case')).toBeNull()
  expect(screen.getByText(/Separate reference-context and completion research studies are not supported/)).toBeTruthy()
  expect(screen.getByText(/This is not behavioral validation/)).toBeTruthy()
  expect(register).not.toHaveBeenCalled(); expect(create).not.toHaveBeenCalled()
  expect((screen.getByRole('button', { name: 'Create campaign' }) as HTMLButtonElement).disabled).toBe(true)
  fireEvent.click(screen.getByRole('button', { name: 'Register configured agent' }))
  await waitFor(() => expect(options).toHaveBeenCalledTimes(2))
  await screen.findByText('smolagents-fixture')
  expect(register).toHaveBeenCalledExactlyOnceWith(runOptions.data_store.identity, 'smolagents')
  await waitFor(() => expect((screen.getByRole('button', { name: 'Create campaign' }) as HTMLButtonElement).disabled).toBe(false))
  fireEvent.click(screen.getByRole('button', { name: 'Create campaign' }))
  await waitFor(() => expect(create).toHaveBeenCalledOnce())
  expect(create.mock.calls[0][0]).toMatchObject({ mode: 'learn', agent_registration_id: 'smolagents-fixture', config_profile_id: 'live-v1' })
  expect(create.mock.calls[0][0].development_case_id).toBeUndefined()
  expect(start).not.toHaveBeenCalled()
})

it('requires a compatible accepted policy for Compare and never exposes a protected case selector', async () => {
  const options = vi.spyOn(runApi, 'options').mockResolvedValue(selectedOptions('reference'))
  render(h(RunSetup, { config: liveConfig, replay: false, readiness: liveReadiness, onCampaign: vi.fn() }))
  await screen.findByText('Current plan preview')
  fireEvent.change(screen.getByLabelText('Execution profile'), { target: { value: 'live-v1' } })
  expect((screen.getByRole('option', { name: 'Compare · accepted policy required' }) as HTMLOptionElement).disabled).toBe(true)
  options.mockResolvedValue(selectedOptions('reference', { compare_available: true, accepted_policy_version: 'policy-accepted' }))
  fireEvent.click(screen.getByRole('button', { name: 'Refresh run options' }))
  await waitFor(() => expect((screen.getByRole('option', { name: 'Compare · accepted policy required' }) as HTMLOptionElement).disabled).toBe(false))
  fireEvent.change(screen.getByLabelText('Campaign mode'), { target: { value: 'compare' } })
  expect(screen.queryByLabelText('Public development case')).toBeNull()
  expect(screen.getByText('policy-accepted')).toBeTruthy()
  expect(screen.getByText(/Protected cases are not shown/)).toBeTruthy()
})

it('shows a failed create without automatic POST retries and requires manual refresh for changed setup', async () => {
  vi.spyOn(runApi, 'options').mockResolvedValue(runOptions)
  const create = vi.spyOn(runApi, 'create').mockRejectedValue(new Error('Current setup changed; refresh options.'))
  render(h(RunSetup, { config, replay: false, onCampaign: vi.fn() }))
  await screen.findByText('Current plan preview')
  await waitFor(() => expect((screen.getByRole('button', { name: 'Create campaign' }) as HTMLButtonElement).disabled).toBe(false))
  fireEvent.click(screen.getByRole('button', { name: 'Create campaign' }))
  await screen.findByRole('alert')
  vi.useFakeTimers()
  await act(() => vi.advanceTimersByTimeAsync(30000))
  expect(create).toHaveBeenCalledOnce()
  expect(screen.getByRole('alert').textContent).toContain('will not be retried automatically')
})

it('restores the frozen native plan instead of the current reference selection and starts only on an explicit click', async () => {
  const saved = { ...campaign, state: 'IDLE' as const, model: 'saved-native-model', config_profile_id: 'live-v1' }
  const plan = planned(saved, { config_profile_id: 'live-v1', source_mode: 'live', agent: 'smolagents', agent_registration_id: 'native-saved-registration' })
  vi.spyOn(runApi, 'options').mockResolvedValue(runOptions)
  vi.spyOn(runApi, 'plan').mockResolvedValue({ campaign_id: saved.campaign_id, status: 'PLANNED', plan })
  const start = vi.spyOn(api, 'start').mockResolvedValue({ ...saved, state: 'RUNNING' })
  const props = { config: liveConfig, campaign: saved, readiness: liveReadiness, replay: false, onCampaign: vi.fn(), onReplay: vi.fn() }
  const view = render(h(RunControls, props))
  await screen.findByText('native-saved-registration')
  expect(within(screen.getByRole('region', { name: 'Saved campaign plan' })).getByText('saved-native-model')).toBeTruthy()
  expect(start).not.toHaveBeenCalled()
  view.unmount(); render(h(RunControls, props))
  await screen.findByText('native-saved-registration')
  fireEvent.click(screen.getByRole('button', { name: /Start campaign/ }))
  await waitFor(() => expect(start).toHaveBeenCalledExactlyOnceWith(saved.campaign_id))
})

it('labels a legacy plan as unrecorded and refuses Start when plan identity is invalid', async () => {
  const plan = vi.spyOn(runApi, 'plan').mockResolvedValueOnce({ campaign_id: campaign.campaign_id, status: 'LEGACY', plan: null }).mockRejectedValue(new Error('Malformed campaign plan identity response.'))
  const props = { config, campaign: { ...campaign, state: 'IDLE' as const }, replay: false, onCampaign: vi.fn(), onReplay: vi.fn() }
  const view = render(h(RunControls, props))
  await screen.findByText(/Legacy campaign · no explicit run plan was recorded/)
  expect(plan).toHaveBeenCalledOnce()
  view.unmount(); render(h(RunControls, props))
  await screen.findByText(/Malformed campaign plan identity/)
  expect((screen.getByRole('button', { name: /Start campaign/ }) as HTMLButtonElement).disabled).toBe(true)
})

it.each([true, false])('keeps archive setup mutations disabled with native registered=%s', async registered => {
  vi.spyOn(runApi, 'options').mockResolvedValue({ ...(registered ? selectedOptions('smolagents') : runOptions), data_store: { ...runOptions.data_store, read_only: true } })
  const register = vi.spyOn(runApi, 'register'); const create = vi.spyOn(runApi, 'create')
  render(h(RunSetup, { config: { ...liveConfig, data_store: { ...runOptions.data_store, read_only: true } }, replay: false, readiness: liveReadiness, onCampaign: vi.fn() }))
  await screen.findByText('Current plan preview')
  fireEvent.change(screen.getByLabelText('Execution profile'), { target: { value: 'live-v1' } })
  fireEvent.change(screen.getByLabelText('Reviewed agent'), { target: { value: 'smolagents' } })
  if (!registered) expect((screen.getByRole('button', { name: 'Register configured agent' }) as HTMLButtonElement).disabled).toBe(true)
  const button = screen.getByRole('button', { name: 'Create campaign' }) as HTMLButtonElement
  expect(button.disabled).toBe(true); fireEvent.click(button)
  expect(register).not.toHaveBeenCalled(); expect(create).not.toHaveBeenCalled()
})

it('downloads a NO_CHANGE recording on demand without dropping historical fields or requiring a regression bundle', async () => {
  const record = { recording_version: 'faultlab-development-recording/v1', campaign_id: campaign.campaign_id, campaign: { ...campaign, state: 'NO_CHANGE' }, historical_extra: { original: true } }
  expect(validateRecording(record, campaign.campaign_id)).toEqual(record)
  expect(() => validateRecording(record, 'foreign')).toThrow('identity')
  const read = vi.spyOn(api, 'recording').mockResolvedValue(record)
  const created = vi.fn().mockReturnValue('blob:recording'); vi.stubGlobal('URL', Object.assign(class extends URL {}, { createObjectURL: created, revokeObjectURL: vi.fn() }))
  const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})
  render(h(RecordingDownload, { campaignId: campaign.campaign_id }))
  expect(read).not.toHaveBeenCalled()
  fireEvent.click(screen.getByRole('button', { name: 'Download campaign recording' }))
  await waitFor(() => expect(click).toHaveBeenCalledOnce())
  expect(read).toHaveBeenCalledExactlyOnceWith(campaign.campaign_id)
  expect((click.mock.instances[0] as HTMLAnchorElement).download).toBe(`${campaign.campaign_id}-development-recording.json`)
  expect(created.mock.calls[0][0]).toBeInstanceOf(Blob)
})
