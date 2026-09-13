// @vitest-environment jsdom
import { createElement as h, StrictMode } from 'react'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { EvidenceScreen } from '../src/components/EvidenceScreen'
import { api, request } from '../src/api'
import { campaign, episode, fixtureResponse } from './fixtures'
let writes: string[]
beforeEach(() => {
  const storage = () => { const values = new Map<string, string>(); return { getItem: (key: string) => values.get(key) ?? null, setItem: (key: string, value: string) => values.set(key, value), clear: () => values.clear(), removeItem: (key: string) => values.delete(key) } }
  vi.stubGlobal('localStorage', storage()); vi.stubGlobal('sessionStorage', storage()); writes = []
  HTMLElement.prototype.scrollIntoView = vi.fn()
  vi.stubGlobal('fetch', vi.fn(async (url: string, options: RequestInit) => {
    if (options?.method === 'POST') { writes.push(url); if (url.endsWith('/campaigns')) return { ok: true, json: async () => ({ ...campaign, state: 'IDLE', latest_episode_id: null, state_seq: 0 }) }; if (url.endsWith('/start')) return { ok: true, json: async () => ({ ...campaign, state: 'RUNNING', state_seq: 1 }) } }
    return { ok: true, json: async () => fixtureResponse(String(url)) }
  }))
})
afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.restoreAllMocks() })
describe('evidence screen behavior', () => {
  it('starts read-only with honest empty states and unavailable live controls', async () => {
    render(h(EvidenceScreen))
    await screen.findByText('Backend connected')
    expect(screen.getByText(/No trials yet/)).toBeTruthy()
    expect(screen.getByText(/Independent external validation is/)).toBeTruthy()
    expect((screen.getByRole('button', { name: 'Compare' }) as HTMLButtonElement).disabled).toBe(true)
    expect(writes).toEqual([])
  })
  it('restores campaign and event cursor on reload; replay performs zero mutations', async () => {
    localStorage.setItem('faultlab:campaign', campaign.campaign_id)
    const first = render(h(StrictMode, null, h(EvidenceScreen)))
    await screen.findByText('episode started')
    await waitFor(() => expect(screen.getAllByText('episode started')).toHaveLength(1))
    expect(sessionStorage.getItem(`faultlab:events:${episode.episode_id}`)).toContain('"next_after":3')
    fireEvent.click(screen.getByRole('button', { name: 'Recorded playback' }))
    expect(await screen.findByText('Recorded playback · read only')).toBeTruthy()
    expect((screen.getByRole('button', { name: /Start campaign/ }) as HTMLButtonElement).disabled).toBe(true)
    expect(writes).toEqual([])
    first.unmount()
    render(h(EvidenceScreen))
    await screen.findByText('episode started')
    expect(vi.mocked(fetch).mock.calls.some(([url]) => String(url).includes('after=3'))).toBe(true)
    expect(writes).toEqual([])
  })
  it('requires a separate explicit Start after campaign creation', async () => {
    render(h(EvidenceScreen)); await screen.findByText('Backend connected')
    fireEvent.click(screen.getByRole('button', { name: 'Create campaign' }))
    await waitFor(() => expect(writes).toEqual(['/api/campaigns']))
    await screen.findByText(/Campaign created. Press Start/)
    expect(localStorage.getItem('faultlab:campaign')).toBe(campaign.campaign_id)
  })
  it('opens the matching stored episode from a matrix cell', async () => {
    localStorage.setItem('faultlab:campaign', campaign.campaign_id)
    render(h(EvidenceScreen)); await screen.findByText('episode started')
    const button = screen.getByRole('button', { name: `${episode.episode_id} ↗` })
    fireEvent.click(button)
    expect(button.getAttribute('aria-pressed')).toBe('true')
    expect(screen.getByText(episode.world_id)).toBeTruthy()
    expect(writes).toEqual([])
  })
  it('shows malformed health and does not trigger execution to repair it', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => ({ ok: true, json: async () => ({ wrong: true }) })))
    render(h(EvidenceScreen))
    await screen.findByText('Backend unavailable')
    expect(screen.getByText(/Malformed health response/)).toBeTruthy()
    expect(writes).toEqual([])
  })
  it('deduplicates concurrent reads and never retries writes', async () => {
    let resolve!: (value: unknown) => void
    const remote = new Promise(r => { resolve = r })
    const fetcher = vi.fn(() => remote)
    vi.stubGlobal('fetch', fetcher)
    const first = api.health(); const second = api.health()
    expect(fetcher).toHaveBeenCalledTimes(1)
    resolve({ ok: true, json: async () => ({ status: 'ok', service: 'faultlab-backend' }) })
    await Promise.all([first, second])
    const failing = vi.fn(async () => { throw new Error('offline') }); vi.stubGlobal('fetch', failing)
    await expect(request('/reset-demo', x => x, {})).rejects.toThrow('offline')
    expect(failing).toHaveBeenCalledTimes(1)
  })
})

import { CounterexamplePanel } from '../src/components/CounterexamplePanel'
import { DiagnosticPanel } from '../src/components/DiagnosticPanel'
import { ChallengePanel } from '../src/components/ChallengePanel'
import { validateExperiments } from '../src/experiments'
import { experiments, testedExperiment } from './fixtures'
it('renders repeated evidence, incomplete reduction, tested scope and challenge failure without re-scoring', () => {
  const records = validateExperiments({ ...experiments, counterexamples: [testedExperiment] }).counterexamples
  const select = vi.fn()
  render(h('div', null, h(CounterexamplePanel, { records, onEpisode: select }), h(DiagnosticPanel, { records, onEpisode: select }), h(ChallengePanel, { records, onEpisode: select })))
  expect(screen.getByText('Reduction budget reached.')).toBeTruthy()
  expect(screen.getByText('This contract and a 20-tick actor deadline.')).toBeTruthy()
  expect(screen.getByText(/Challenge failure blocks promotion/)).toBeTruthy()
  fireEvent.click(screen.getByRole('button', { name: 'episode-candidate1', exact: true }))
  expect(select).toHaveBeenCalledWith('episode-candidate1')
  expect(writes).toEqual([])
})

import { RegressionControls } from '../src/components/RegressionControls'
import { AriaEvidenceForm } from '../src/components/AriaEvidenceForm'
import { validateContract } from '../src/generated/validate'
import type { AgentRegistration, RegressionBundle } from '../src/generated/contracts'
import { baseline, bundle, config, registration, regressionCase } from './fixtures'
it('keeps bundle inspection read-only and gates fresh regression by explicit profile, agent and policy', async () => {
  const saved = validateContract<RegressionBundle>('RegressionBundle', bundle)
  const agent = validateContract<AgentRegistration>('AgentRegistration', registration)
  const read = vi.spyOn(api, 'bundle').mockResolvedValue(saved)
  const run = vi.spyOn(api, 'execute').mockResolvedValue({ execution_id: 'execution-new', bundle_id: saved.bundle_id, manifest_hash: saved.manifest_hash, registration_id: agent.registration_id, profile_id: saved.execution_profile_id, mode: 'FRESH_SANDBOX', explicit_action: true, policy_hash: saved.policy_hash, configuration_hash: saved.configuration_hash, declared_budget: saved.caps, usage: {}, episode_ids: [], world_ids: [], status: 'PENDING' })
  render(h(RegressionControls, { cases: [regressionCase], registrations: [agent], policies: [baseline], config: { ...config, live_enabled: true, model_configured: true, execution_profiles: [{ profile_id: 'sandbox-v1', caps: saved.caps, requires_live: true }] }, replay: false, onEpisode: vi.fn() }))
  expect(read).not.toHaveBeenCalled(); expect(run).not.toHaveBeenCalled()
  fireEvent.change(screen.getByLabelText('Saved regression'), { target: { value: regressionCase.regression_id } })
  fireEvent.click(screen.getByRole('button', { name: 'Inspect saved bundle' }))
  await screen.findByText('sandbox-v1')
  expect(run).not.toHaveBeenCalled()
  fireEvent.change(screen.getByLabelText('Reviewed agent'), { target: { value: agent.registration_id } })
  fireEvent.change(screen.getByLabelText('Immutable policy'), { target: { value: baseline.version } })
  fireEvent.click(screen.getByRole('button', { name: /Run fresh regression/ }))
  await waitFor(() => expect(run).toHaveBeenCalledWith(regressionCase.regression_id, agent.registration_id, 'sandbox-v1', baseline.version))
  await screen.findByText('New execution · execution-new')
})
it('rejects unsafe Aria links before saving attributed manual capture', async () => {
  const save = vi.spyOn(api, 'saveAria')
  render(h(AriaEvidenceForm, { campaignId: campaign.campaign_id, disabled: false }))
  fireEvent.click(screen.getByText('Capture observed Aria evidence'))
  fireEvent.change(screen.getByLabelText('Automation history URL'), { target: { value: 'https://evil.example/record' } })
  fireEvent.submit(screen.getByRole('button', { name: 'Save evidence capture' }).closest('form')!)
  expect(await screen.findByText(/Evidence links must use HTTPS/)).toBeTruthy()
  expect(save).not.toHaveBeenCalled()
})

import { RunControls } from '../src/components/RunControls'
it('acknowledges Stop only after the next persisted state is received', async () => {
  const running = { ...campaign, state: 'RUNNING' as const, state_seq: 5 }
  const stopped = { ...campaign, state: 'STOPPED' as const, state_seq: 6, stop_requested: true }
  const stop = vi.spyOn(api, 'stop').mockResolvedValue(stopped)
  const props = { config: { ...config, active_campaign_id: campaign.campaign_id }, campaign: running, replay: false, onCampaign: vi.fn(), onReplay: vi.fn() }
  const view = render(h(RunControls, props))
  fireEvent.click(screen.getByRole('button', { name: 'Stop', exact: true }))
  await screen.findByText('Stop requested; waiting for the next successful state poll.')
  expect(stop).toHaveBeenCalledOnce()
  expect(screen.queryByText('Stop acknowledged by the next successful poll.')).toBeNull()
  view.rerender(h(RunControls, { ...props, campaign: stopped }))
  expect(screen.getByText('Stop acknowledged by the next successful poll.')).toBeTruthy()
  expect((screen.getByRole('button', { name: 'Stop', exact: true }) as HTMLButtonElement).disabled).toBe(true)
})
