// @vitest-environment jsdom
import { createElement as h, StrictMode } from 'react'
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { api, validateReadiness } from '../src/api'
import { EvidenceScreen } from '../src/components/EvidenceScreen'
import { RunControls } from '../src/components/RunControls'
import { RunReadiness } from '../src/components/RunReadiness'
import { campaign, config, fixtureResponse, readiness } from './fixtures'

beforeEach(() => {
  vi.stubGlobal('fetch', vi.fn(async (url: string) => ({ ok: true, json: async () => fixtureResponse(url) })))
  const storage = () => ({ getItem: () => null, setItem: vi.fn() })
  vi.stubGlobal('localStorage', storage()); vi.stubGlobal('sessionStorage', storage())
})
afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals(); vi.useRealTimers() })

it('checks readiness once on mount and only rechecks on explicit request without writes', async () => {
  const fetch = vi.fn(async (url: string) => ({ ok: true, json: async () => fixtureResponse(String(url)) }))
  vi.stubGlobal('fetch', fetch)
  render(h(StrictMode, null, h(EvidenceScreen)))
  await screen.findByText('Simulator ready', { exact: true })
  const calls = () => fetch.mock.calls.filter(([url]) => url.endsWith('/readiness'))
  expect(calls()).toHaveLength(1)
  expect(screen.getByText('Live configuration incomplete')).toBeTruthy()
  expect(screen.getByText('WANDB_API_KEY')).toBeTruthy()
  expect(screen.getByText(/Provider access has not been checked/)).toBeTruthy()
  vi.useFakeTimers()
  await act(() => vi.advanceTimersByTimeAsync(1500))
  expect(calls()).toHaveLength(1)
  vi.useRealTimers()
  fireEvent.click(screen.getByRole('button', { name: 'Check run readiness' }))
  await waitFor(() => expect(calls()).toHaveLength(2))
  expect(vi.mocked(globalThis.fetch).mock.calls.every(([, options]) => options?.method === 'GET')).toBe(true)
})

it('permits offline execution with a ready simulator despite missing live settings', async () => {
  render(h(RunControls, { config, campaign: { ...campaign, state: 'IDLE' }, replay: false, onCampaign: vi.fn(), onReplay: vi.fn(), readiness: { data: readiness, loading: false, error: null }, onCheckReadiness: vi.fn() }))
  await screen.findByText(/Legacy campaign · no explicit run plan/)
  expect((screen.getByRole('button', { name: /Start campaign/ }) as HTMLButtonElement).disabled).toBe(false)
  await waitFor(() => expect((screen.getByRole('button', { name: 'Create campaign' }) as HTMLButtonElement).disabled).toBe(false))
})

it('blocks dispatch when the simulator is unavailable while keeping campaign creation and saved playback available', async () => {
  const unavailable = { ...readiness, ready: false, simulator: { ready: false, code: 'SIMULATOR_UNAVAILABLE', message: 'Start the local simulator before executing a campaign.' } }
  const start = vi.spyOn(api, 'start')
  render(h(RunControls, { config, campaign: { ...campaign, state: 'IDLE' }, replay: false, onCampaign: vi.fn(), onReplay: vi.fn(), readiness: { data: unavailable, loading: false, error: null }, onCheckReadiness: vi.fn() }))
  expect(screen.getByText('Simulator unavailable')).toBeTruthy()
  expect(screen.getByText('SIMULATOR_UNAVAILABLE')).toBeTruthy()
  for (const name of [/Start campaign/]) expect((screen.getByRole('button', { name }) as HTMLButtonElement).disabled).toBe(true)
  await waitFor(() => expect((screen.getByRole('button', { name: 'Create campaign' }) as HTMLButtonElement).disabled).toBe(false))
  expect((screen.getByRole('button', { name: 'Recorded playback' }) as HTMLButtonElement).disabled).toBe(false)
  fireEvent.click(screen.getByRole('button', { name: /Start campaign/ }))
  expect(start).not.toHaveBeenCalled()
})

it('keeps readiness failures visible and explicitly retryable', () => {
  const check = vi.fn()
  render(h(RunReadiness, { resource: { loading: false, error: 'The backend did not respond within 8 seconds.' }, onCheck: check }))
  expect(screen.getByRole('alert').textContent).toContain('Run readiness could not be checked.')
  expect(screen.queryByText('Simulator ready')).toBeNull()
  fireEvent.click(screen.getByRole('button', { name: 'Check run readiness' }))
  expect(check).toHaveBeenCalledOnce()
})
it.each([{ loading: true, error: null }, { loading: false, error: 'Unavailable' }])('waits for a verified readiness response before dispatch with %j', async resource => {
  render(h(RunControls, { config, campaign: { ...campaign, state: 'IDLE' }, replay: false, onCampaign: vi.fn(), onReplay: vi.fn(), readiness: resource, onCheckReadiness: vi.fn() }))
  for (const name of [/Start campaign/]) expect((screen.getByRole('button', { name }) as HTMLButtonElement).disabled).toBe(true)
  await waitFor(() => expect((screen.getByRole('button', { name: 'Create campaign' }) as HTMLButtonElement).disabled).toBe(false))
})

it('does not accept contradictory readiness or a claimed provider check', () => {
  expect(validateReadiness(readiness)).toEqual(readiness)
  for (const value of [
    { ...readiness, ready: false }, { ...readiness, provider_calls: 1 },
    { ...readiness, provider_access: 'verified' }, { ...readiness, models: {} },
    { ...readiness, live_configuration: { ready: false, missing_fields: [123] } },
  ]) expect(() => validateReadiness(value)).toThrow(/Malformed run readiness/)
})
