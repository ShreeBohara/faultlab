// @vitest-environment jsdom
import { createElement as h } from 'react'
import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { api } from '../src/api'
import { EvidenceScreen } from '../src/components/EvidenceScreen'
import { RunControls } from '../src/components/RunControls'
import { SponsorEvidence } from '../src/components/SponsorEvidence'
import { validateExperiments } from '../src/experiments'
import { baseline, bundle, campaign, config, fixtureResponse, readiness, registration, regressionCase, verifiedExperiments } from './fixtures'

beforeEach(() => {
  const values = new Map<string, string>()
  const storage = { getItem: (key: string) => values.get(key) ?? null, setItem: (key: string, value: string) => values.set(key, value), removeItem: (key: string) => values.delete(key) }
  vi.stubGlobal('localStorage', storage)
  vi.stubGlobal('sessionStorage', storage)
  HTMLElement.prototype.scrollIntoView = vi.fn()
})
afterEach(() => { cleanup(); vi.useRealTimers(); vi.unstubAllGlobals(); vi.restoreAllMocks() })

it('keeps the history status consistent with completed campaign polls without refreshing history', async () => {
  localStorage.setItem('faultlab:campaign', campaign.campaign_id)
  vi.stubGlobal('fetch', vi.fn(async (url: string) => ({ ok: true, json: async () => fixtureResponse(String(url)) })))
  const running = { ...campaign, state: 'RUNNING' as const, state_seq: 2 }
  const history = vi.spyOn(api, 'campaigns').mockResolvedValue({ campaigns: [running], next_before: null, has_more: false })
  vi.spyOn(api, 'campaign').mockResolvedValueOnce(running).mockResolvedValue(campaign)
  render(h(EvidenceScreen))
  await screen.findByText(/1 saved campaigns loaded/)
  await waitFor(() => expect(screen.getByRole('option', { name: /campaign-fixture/ }).textContent).toContain('Running'))
  await waitFor(() => expect(screen.getByRole('option', { name: /campaign-fixture/ }).textContent).toContain('Completed'), { timeout: 2000 })
  expect(history).toHaveBeenCalledOnce()
})

it('shows one recoverable missing-campaign notice without polling missing child records or selecting history automatically', async () => {
  const missing = 'campaign-from-another-store'
  localStorage.setItem('faultlab:campaign', missing)
  const fetcher = vi.fn(async (url: string) => String(url).includes(missing)
    ? { ok: false, status: 404, json: async () => ({ error: { message: 'Unknown record' } }) }
    : { ok: true, json: async () => fixtureResponse(String(url)) })
  vi.stubGlobal('fetch', fetcher)
  render(h(EvidenceScreen))
  await screen.findByRole('heading', { name: 'Saved campaign unavailable' })
  expect(screen.getAllByRole('alert')).toHaveLength(1)
  expect(screen.queryByText(/Retrying with backoff/)).toBeNull()
  expect(screen.queryByText('episode started')).toBeNull()
  expect(localStorage.getItem('faultlab:campaign')).toBe(missing)
  const missingReads = () => fetcher.mock.calls.map(([url]) => url).filter(url => url.includes(missing))
  vi.useFakeTimers()
  await act(() => vi.advanceTimersByTimeAsync(30000))
  expect(missingReads()).toEqual([`/api/campaigns/${missing}`])
  await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Retry saved campaign' })) })
  expect(missingReads()).toHaveLength(2)
  await act(() => vi.advanceTimersByTimeAsync(10000))
  expect(missingReads()).toHaveLength(2)
  await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Load recording' })) })
  expect(missingReads()).toHaveLength(3)
  vi.useRealTimers()
  fireEvent.change(screen.getByLabelText('Saved campaigns', { exact: true }), { target: { value: campaign.campaign_id } })
  fireEvent.click(screen.getByRole('button', { name: 'Open selected campaign' }))
  await screen.findByText('episode started')
  expect(screen.queryByRole('heading', { name: 'Saved campaign unavailable' })).toBeNull()
  expect(localStorage.getItem('faultlab:campaign')).toBe(campaign.campaign_id)
  expect(vi.mocked(fetch).mock.calls.every(([, options]) => options?.method === 'GET')).toBe(true)
})

const archiveConfig = { ...config, live_enabled: true, model_configured: true, execution_profiles: [{ profile_id: 'sandbox-v1', caps: bundle.caps, requires_live: true }], data_store: { identity: 'archive-fixture', path: '/local/saved-evidence/lab.sqlite3', read_only: true } }
it('allows archive navigation and bundle inspection while disabling every saved-data mutation', async () => {
  localStorage.setItem('faultlab:campaign', campaign.campaign_id)
  const idle = { ...campaign, state: 'IDLE' as const }
  vi.stubGlobal('fetch', vi.fn(async (url: string) => ({ ok: true, json: async () => {
    if (url.endsWith('/config/status')) return archiveConfig
    if (url.endsWith('/readiness')) return { ...readiness, ready: false, simulator: { ready: false, code: 'READ_ONLY_ARCHIVE', message: 'This archive cannot start work.' } }
    if (url.endsWith('/regressions')) return [regressionCase]
    if (url.endsWith('/bundle')) return bundle
    if (url.endsWith('/agent-registrations')) return [registration]
    return fixtureResponse(url, idle)
  } })))
  const save = vi.spyOn(api, 'saveAria')
  render(h(EvidenceScreen))
  await screen.findByRole('heading', { name: 'Read-only archive' })
  await screen.findByText('episode started')
  expect(screen.getByText(archiveConfig.data_store.path)).toBeTruthy()
  expect(screen.getByText('Fresh execution disabled')).toBeTruthy()
  expect(screen.queryByText('Simulator unavailable')).toBeNull()
  for (const name of ['Create campaign', /Start campaign/, 'Stop', 'Reset future world', 'Retry evidence sync']) {
    const button = screen.getByRole('button', { name, exact: typeof name === 'string' }) as HTMLButtonElement
    expect(button.disabled).toBe(true)
    fireEvent.click(button)
  }
  fireEvent.change(screen.getByLabelText('Saved regression'), { target: { value: regressionCase.regression_id } })
  expect((screen.getByRole('button', { name: 'Download regression' }) as HTMLButtonElement).disabled).toBe(false)
  fireEvent.click(screen.getByRole('button', { name: 'Inspect saved bundle' }))
  await screen.findByText('sandbox-v1')
  fireEvent.change(screen.getByLabelText('Reviewed agent'), { target: { value: registration.registration_id } })
  fireEvent.change(screen.getByLabelText('Immutable policy'), { target: { value: baseline.version } })
  const fresh = screen.getByRole('button', { name: /Run fresh regression/ }) as HTMLButtonElement
  expect(fresh.disabled).toBe(true)
  fireEvent.click(fresh)
  fireEvent.click(screen.getByText('Capture observed Aria evidence'))
  const capture = screen.getByRole('button', { name: 'Save evidence capture' })
  expect(capture.closest('fieldset')?.disabled).toBe(true)
  fireEvent.submit(capture.closest('form')!)
  expect(save).not.toHaveBeenCalled()
  fireEvent.click(screen.getByRole('button', { name: 'Recorded playback' }))
  await screen.findByText('Recorded playback · read only')
  expect((screen.getByRole('button', { name: 'Refresh history' }) as HTMLButtonElement).disabled).toBe(false)
  expect(vi.mocked(fetch).mock.calls.every(([, options]) => options?.method === 'GET')).toBe(true)
})

it('never offers Stop in an archive even when the saved selected campaign was active', () => {
  const stop = vi.spyOn(api, 'stop')
  render(h(RunControls, { config: { ...archiveConfig, active_campaign_id: campaign.campaign_id }, campaign: { ...campaign, state: 'RUNNING' }, replay: false, onCampaign: vi.fn(), onReplay: vi.fn() }))
  const button = screen.getByRole('button', { name: 'Stop', exact: true }) as HTMLButtonElement
  expect(button.disabled).toBe(true)
  fireEvent.click(button)
  expect(stop).not.toHaveBeenCalled()
})

it('labels verified source episodes separately from campaign uploads and Aria, including separate study sources', () => {
  const source = verifiedExperiments.evidence[0]
  const evidence = Array.from({ length: 7 }, (_, index) => ({ ...source, episode_id: `episode-${index}` }))
  const experiments = validateExperiments({ ...verifiedExperiments, evidence: [...evidence, evidence[0], { ...source, episode_id: 'local-only', source: 'local_only' }] })
  render(h(SponsorEvidence, { config, campaign, experiments, aria: { data: [], loading: false, error: null }, replay: false }))
  const header = screen.getByRole('heading', { name: 'Weave source evidence' }).parentElement!
  expect(within(header).getByText('7 verified source episodes')).toBeTruthy()
  expect(screen.getByText(/Counts cover saved source references, including separate development studies/)).toBeTruthy()
  const campaignTelemetry = screen.getByText(/Campaign telemetry/)
  expect(within(campaignTelemetry).getByText('Locally recorded')).toBeTruthy()
  expect(within(screen.getByRole('heading', { name: 'Aria analyst' }).parentElement!).getByText('Pending')).toBeTruthy()
})

it('does not treat an ingestion status alone as a verified source reference', async () => {
  render(h(SponsorEvidence, { campaign, experiments: validateExperiments({ ...verifiedExperiments, evidence: [] }), aria: { data: [], loading: false, error: null }, replay: false }))
  await waitFor(() => expect(screen.getByText('No verified source evidence')).toBeTruthy())
  expect(screen.getByText('Ingestion · INGESTED')).toBeTruthy()
})
