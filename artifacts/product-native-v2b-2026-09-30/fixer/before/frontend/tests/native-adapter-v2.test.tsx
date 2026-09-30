// @vitest-environment jsdom
// Native adapter v2 (smolagents-toolcalling-v2) in the dashboard: an explicit, separately named agent choice.
import { createElement as h } from 'react'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { api } from '../src/api'
import { agentName, isAgentKind, isNativeAgent, NATIVE_V2_LABEL, runApi, validateCampaignPlan, validateRunOptions, type RunOptions } from '../src/runPlans'
import { importApi } from '../src/bundleImports'
import { RunSetup } from '../src/components/RunSetup'
import { CampaignPlan } from '../src/components/CampaignPlan'
import { BundleImports } from '../src/components/BundleImports'
import { validateContract } from '../src/generated/validate'
import type { AgentRegistration } from '../src/generated/contracts'
import { campaign, config, fixtureResponse, readiness, registration } from './fixtures'
import { planned, runOptions } from './run-fixtures'
import { imported, importConfig, importReadiness, target } from './import-fixtures'

const V2 = 'smolagents ToolCallingAgent - adapter v2 (short evidence labels, strict final report turn)'
const nativeRow = runOptions.agents.find(agent => agent.agent === 'smolagents')!
const v2Row = { ...nativeRow, agent: 'smolagents-v2' as const, label: V2, proposed_registration_id: 'smolagents-v2-fixture', configuration_hash: 'd'.repeat(64) }
const withV2: RunOptions = {
  ...runOptions, agents: [...runOptions.agents, v2Row],
  learn: { ...runOptions.learn, discovery_protocols: runOptions.learn.discovery_protocols!.map(option =>
    option.supported_agents.includes('smolagents') ? { ...option, supported_agents: [...option.supported_agents, 'smolagents-v2' as const] } : option) },
}

beforeEach(() => {
  const values = new Map<string, string>()
  const storage = { getItem: (key: string) => values.get(key) ?? null, setItem: (key: string, value: string) => values.set(key, value), removeItem: (key: string) => values.delete(key) }
  vi.stubGlobal('localStorage', storage); vi.stubGlobal('sessionStorage', storage)
  vi.stubGlobal('fetch', vi.fn(async (url: string) => ({ ok: true, json: async () => fixtureResponse(url) })))
  HTMLElement.prototype.scrollIntoView = vi.fn()
})
afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals() })

it('names each agent kind, keeping v1 and the reference Actor as before', () => {
  expect(NATIVE_V2_LABEL).toBe(V2)
  expect(agentName('smolagents-v2')).toBe(V2)
  expect(agentName('smolagents')).toBe('smolagents ToolCallingAgent')
  expect(agentName('reference')).toBe('FaultLab reference actor')
  expect(agentName('unsupported')).toBe('unsupported')
  expect([isNativeAgent('smolagents'), isNativeAgent('smolagents-v2'), isNativeAgent('reference')]).toEqual([true, true, false])
  expect([isAgentKind('smolagents-v2'), isAgentKind('smolagents-v3'), isAgentKind(undefined)]).toEqual([true, false, false])
})

it('accepts run options offering v2 and rejects unknown, duplicate or missing agents and a pre-check that claims v2', () => {
  expect(validateRunOptions(withV2)).toEqual(withV2)
  expect(validateRunOptions(runOptions)).toEqual(runOptions)                     // an older backend without v2 still reads
  const bad: Partial<RunOptions>[] = [
    { agents: [...runOptions.agents, { ...v2Row, agent: 'smolagents-v3' as never }] },
    { agents: [...runOptions.agents, { ...nativeRow }] },
    { agents: [runOptions.agents[0], v2Row] },                                   // v1 must stay offered
    { learn: { ...withV2.learn, discovery_protocols: withV2.learn.discovery_protocols!.map(option => option.protocol_id === 'faultlab-discovery/v2-reachability' ? { ...option, supported_agents: ['reference', 'smolagents-v2'] } : option) } },
  ]
  for (const patch of bad) expect(() => validateRunOptions({ ...withV2, ...patch })).toThrow('Malformed')
})

it('validates and shows a saved v2 plan with its full adapter name', () => {
  const plan = planned(campaign, { config_profile_id: 'live-v1', source_mode: 'live', agent: 'smolagents-v2', agent_registration_id: 'smolagents-1.26.0-adapter-v2-0123456789abcdef' })
  const envelope = { campaign_id: campaign.campaign_id, status: 'PLANNED' as const, plan }
  expect(validateCampaignPlan(envelope, campaign.campaign_id)).toEqual(envelope)
  expect(() => validateCampaignPlan({ ...envelope, plan: { ...plan, agent: 'smolagents-v3' } }, campaign.campaign_id)).toThrow('Malformed')
  render(h(CampaignPlan, { campaign, resource: { data: envelope, error: null, loading: false } }))
  const saved = screen.getByRole('region', { name: 'Saved campaign plan' })
  expect(saved.textContent).toContain(V2)
  expect(saved.textContent).toContain('do not support this native agent')
})

it('keeps v1 as the default native choice and registers v2 only when it is chosen explicitly', async () => {
  const registeredV2 = { ...withV2, agents: withV2.agents.map(agent => agent.agent === 'smolagents-v2' ? { ...agent, registered: true, registration_id: agent.proposed_registration_id } : agent) }
  const options = vi.spyOn(runApi, 'options').mockResolvedValueOnce(withV2).mockResolvedValue(registeredV2)
  const register = vi.spyOn(runApi, 'register').mockResolvedValue(validateContract<AgentRegistration>('AgentRegistration', registration))
  const create = vi.spyOn(runApi, 'create').mockResolvedValue({ ...campaign, state: 'IDLE', config_profile_id: 'live-v1' })
  const start = vi.spyOn(api, 'start')
  const liveConfig = { ...config, live_enabled: true, model_configured: true, data_store: runOptions.data_store }
  const liveReadiness = { data: { ...readiness, live_configuration: { ready: true, missing_fields: [] } }, error: null, loading: false }
  render(h(RunSetup, { config: liveConfig, replay: false, readiness: liveReadiness, onCampaign: vi.fn() }))
  await screen.findByText('Current plan preview')
  fireEvent.change(screen.getByLabelText('Execution profile'), { target: { value: 'live-v1' } })
  const agentSelect = screen.getByLabelText('Reviewed agent') as HTMLSelectElement
  expect(Array.from(agentSelect.options).map(option => option.textContent)).toEqual(['FaultLab reference actor', 'smolagents ToolCallingAgent 1.26.0', V2])
  fireEvent.change(agentSelect, { target: { value: 'smolagents' } })
  expect(screen.queryByText(/Adapter v2 is a separate agent/)).toBeNull()
  fireEvent.change(agentSelect, { target: { value: 'smolagents-v2' } })
  expect(screen.getByText(/Adapter v2 is a separate agent from v1/)).toBeTruthy()
  expect(screen.getByText(/Separate reference-context and completion research studies are not supported/)).toBeTruthy()
  expect(screen.getByRole('region', { name: 'Current plan preview' }).textContent).toContain(V2)
  fireEvent.click(screen.getByRole('button', { name: 'Register configured agent' }))
  await waitFor(() => expect(options).toHaveBeenCalledTimes(2))
  expect(register).toHaveBeenCalledExactlyOnceWith(runOptions.data_store.identity, 'smolagents-v2')
  await screen.findByText('smolagents-v2-fixture')
  await waitFor(() => expect((screen.getByRole('button', { name: 'Create campaign' }) as HTMLButtonElement).disabled).toBe(false))
  fireEvent.click(screen.getByRole('button', { name: 'Create campaign' }))
  await waitFor(() => expect(create).toHaveBeenCalledOnce())
  expect(create.mock.calls[0][0]).toMatchObject({ agent_registration_id: 'smolagents-v2-fixture', config_profile_id: 'live-v1' })
  expect(start).not.toHaveBeenCalled()
})

it('names a v2 import target by its adapter, not only its kind', async () => {
  const v2Target = { ...target, agent_registration_id: 'native-v2-import-target', agent: 'smolagents-v2' }
  const bundle = { ...imported, targets: [{ ...target, compatible: true, reason: null }, { ...v2Target, compatible: true, reason: null }] }
  vi.spyOn(importApi, 'list').mockResolvedValue({ items: [imported], has_more: false, next_before: null })
  vi.spyOn(importApi, 'detail').mockResolvedValue(bundle)
  vi.spyOn(importApi, 'executions').mockResolvedValue({ items: [], has_more: false, next_before: null })
  render(h(BundleImports, { config: importConfig, readiness: importReadiness, replay: false, onEpisode: vi.fn() }))
  await screen.findByRole('option', { name: /import-browser-fixture/ })
  fireEvent.change(screen.getByLabelText('Saved imported bundles'), { target: { value: imported.import_id } })
  const select = await screen.findByLabelText('Fresh target registration') as HTMLSelectElement
  const labels = Array.from(select.options).map(option => option.textContent ?? '')
  expect(labels.some(text => text.startsWith(`${V2} · `) && text.includes('native-v2-import-target'))).toBe(true)
  expect(labels.some(text => text.startsWith('smolagents ToolCallingAgent · ') && text.includes('native-import-target'))).toBe(true)
  fireEvent.change(select, { target: { value: 'native-v2-import-target' } })
  expect(screen.getByText(V2)).toBeTruthy()
})
