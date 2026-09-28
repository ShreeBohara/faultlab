// @vitest-environment jsdom
import { createElement as h, StrictMode } from 'react'
import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import { api, validateCampaignPage } from '../src/api'
import { CampaignHistory } from '../src/components/CampaignHistory'
import { campaign } from './fixtures'

afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals(); vi.useRealTimers() })

const first = { ...campaign, campaign_id: 'campaign-newest' }
const older = { ...campaign, campaign_id: 'campaign-older', created_at: '2026-09-10T12:00:00Z', state: 'STOPPED' as const }
const firstPage = { campaigns: [first], next_before: 42, has_more: true }
const finalPage = { campaigns: [older], next_before: null, has_more: false }

it('loads one bounded history page under StrictMode and opens saved evidence without mutations or polling', async () => {
  const fetch = vi.fn(async () => ({ ok: true, json: async () => firstPage }))
  vi.stubGlobal('fetch', fetch)
  const open = vi.fn()
  render(h(StrictMode, null, h(CampaignHistory, { selectedId: '', refreshKey: 0, onOpen: open })))
  await screen.findByText(/1 saved campaigns loaded/)
  expect(fetch).toHaveBeenCalledExactlyOnceWith('/api/campaigns?limit=20', expect.objectContaining({ method: 'GET' }))
  fireEvent.change(screen.getByLabelText('Saved campaigns'), { target: { value: first.campaign_id } })
  fireEvent.click(screen.getByRole('button', { name: 'Open selected campaign' }))
  expect(open).toHaveBeenCalledExactlyOnceWith(first.campaign_id)
  vi.useFakeTimers()
  await act(() => vi.advanceTimersByTimeAsync(10000))
  expect(fetch).toHaveBeenCalledTimes(1)
})

it('loads older pages on demand and refreshes back to the newest page', async () => {
  const read = vi.spyOn(api, 'campaigns').mockResolvedValueOnce(firstPage).mockResolvedValueOnce(finalPage).mockResolvedValueOnce({ ...firstPage, has_more: false, next_before: null })
  render(h(CampaignHistory, { selectedId: first.campaign_id, refreshKey: 0, onOpen: vi.fn() }))
  await screen.findByText(/1 saved campaigns loaded/)
  const selector = screen.getByLabelText('Saved campaigns')
  expect((selector as HTMLSelectElement).value).toBe(first.campaign_id)
  fireEvent.click(screen.getByRole('button', { name: 'Load older campaigns' }))
  await screen.findByText(/2 saved campaigns loaded/)
  expect(read).toHaveBeenNthCalledWith(2, 42)
  expect(within(selector).getAllByRole('option').map(option => (option as HTMLOptionElement).value)).toEqual(['', first.campaign_id, older.campaign_id])
  expect(screen.queryByRole('button', { name: 'Load older campaigns' })).toBeNull()
  fireEvent.click(screen.getByRole('button', { name: 'Refresh history' }))
  await screen.findByText(/1 saved campaigns loaded/)
  expect(read).toHaveBeenNthCalledWith(3)
  expect(within(selector).queryByRole('option', { name: /campaign-older/ })).toBeNull()
})

it('updates the matching history row and selected status from the current campaign without reloading pages', async () => {
  const running = { ...first, state: 'RUNNING' as const, state_seq: 3 }
  const read = vi.spyOn(api, 'campaigns').mockResolvedValueOnce({ ...firstPage, campaigns: [running] }).mockResolvedValueOnce(finalPage).mockResolvedValueOnce({ ...firstPage, campaigns: [running] })
  const props = { selectedId: first.campaign_id, currentCampaign: running, refreshKey: 0, onOpen: vi.fn() }
  const view = render(h(CampaignHistory, props))
  await screen.findByText(/1 saved campaigns loaded/)
  fireEvent.click(screen.getByRole('button', { name: 'Load older campaigns' }))
  await screen.findByText(/2 saved campaigns loaded/)
  view.rerender(h(CampaignHistory, { ...props, currentCampaign: { ...running, state: 'COMPLETED', state_seq: 4 } }))
  expect(screen.getByText('Completed', { exact: true })).toBeTruthy()
  expect(screen.getByRole('option', { name: /campaign-newest/ }).textContent).toContain('Completed')
  expect(screen.getByRole('option', { name: /campaign-older/ }).textContent).toContain('Stopped')
  expect(read).toHaveBeenCalledTimes(2)
  expect(screen.getByText(/2 saved campaigns loaded/)).toBeTruthy()
  fireEvent.change(screen.getByLabelText('Saved campaigns'), { target: { value: older.campaign_id } })
  expect(screen.getByText('Stopped', { exact: true })).toBeTruthy()
  expect(screen.queryByText('Completed', { exact: true })).toBeNull()
  fireEvent.change(screen.getByLabelText('Saved campaigns'), { target: { value: first.campaign_id } })
  fireEvent.click(screen.getByRole('button', { name: 'Refresh history' }))
  await screen.findByText(/1 saved campaigns loaded/)
  expect(read).toHaveBeenCalledTimes(3)
  expect(screen.getByText('Completed', { exact: true })).toBeTruthy()
  expect(screen.queryByRole('option', { name: /campaign-older/ })).toBeNull()
})

it('preserves loaded history when an older-page read fails and permits an explicit retry', async () => {
  const read = vi.spyOn(api, 'campaigns').mockResolvedValueOnce(firstPage).mockRejectedValueOnce(new Error('Backend unavailable.')).mockResolvedValueOnce(finalPage)
  render(h(CampaignHistory, { selectedId: first.campaign_id, refreshKey: 0, onOpen: vi.fn() }))
  await screen.findByText(/1 saved campaigns loaded/)
  fireEvent.click(screen.getByRole('button', { name: 'Load older campaigns' }))
  expect((await screen.findByRole('alert')).textContent).toContain('Previously loaded history remains available.')
  expect((screen.getByRole('button', { name: 'Open selected campaign' }) as HTMLButtonElement).disabled).toBe(false)
  fireEvent.click(screen.getByRole('button', { name: 'Load older campaigns' }))
  await screen.findByText(/2 saved campaigns loaded/)
  expect(read).toHaveBeenNthCalledWith(3, 42)
  expect(screen.queryByRole('alert')).toBeNull()
})

it('shows loading and empty states without implying a run was started', async () => {
  let finish!: (value: typeof finalPage) => void
  vi.spyOn(api, 'campaigns').mockImplementation(() => new Promise(resolve => { finish = resolve }))
  render(h(CampaignHistory, { selectedId: '', refreshKey: 0, onOpen: vi.fn() }))
  expect(screen.getByRole('status').textContent).toBe('Loading saved campaigns…')
  expect((screen.getByRole('button', { name: 'Refresh history' }) as HTMLButtonElement).disabled).toBe(true)
  await act(async () => { finish({ campaigns: [], has_more: false, next_before: null }) })
  expect(screen.getByText(/No saved campaigns yet/)).toBeTruthy()
  expect((screen.getByRole('button', { name: 'Open selected campaign' }) as HTMLButtonElement).disabled).toBe(true)
})

it('discards an old history response when a newly created campaign refreshes the list', async () => {
  let finish!: (value: typeof finalPage) => void
  const read = vi.spyOn(api, 'campaigns').mockImplementationOnce(() => new Promise(resolve => { finish = resolve })).mockResolvedValue(firstPage)
  const props = { selectedId: '', refreshKey: 0, onOpen: vi.fn() }
  const view = render(h(CampaignHistory, props))
  view.rerender(h(CampaignHistory, { ...props, refreshKey: 1 }))
  await screen.findByText(/1 saved campaigns loaded/)
  await act(async () => { finish(finalPage) })
  expect(read).toHaveBeenCalledTimes(2)
  expect(within(screen.getByLabelText('Saved campaigns')).queryByRole('option', { name: /campaign-older/ })).toBeNull()
})

it('keeps a first-load failure actionable without an automatic read loop', async () => {
  const read = vi.spyOn(api, 'campaigns').mockRejectedValueOnce(new Error('History unavailable.')).mockResolvedValue(finalPage)
  render(h(CampaignHistory, { selectedId: '', refreshKey: 0, onOpen: vi.fn() }))
  expect((await screen.findByRole('alert')).textContent).toContain('Use Refresh history to try again.')
  fireEvent.click(screen.getByRole('button', { name: 'Refresh history' }))
  await waitFor(() => expect(screen.queryByRole('alert')).toBeNull())
  expect(read).toHaveBeenCalledTimes(2)
})

it('validates campaign history records and requires pagination to advance', () => {
  expect(validateCampaignPage(firstPage, 100)).toEqual(firstPage)
  expect(validateCampaignPage(finalPage, 42)).toEqual(finalPage)
  for (const value of [
    { ...firstPage, next_before: 0 }, { ...firstPage, next_before: 1.5 },
    { ...firstPage, next_before: null }, { ...finalPage, next_before: 42 },
    { ...firstPage, next_before: 100 }, { ...firstPage, campaigns: [] },
    { ...firstPage, campaigns: [first, first] }, { ...firstPage, campaigns: [{ ...first, state: 'ASSUMED_COMPLETE' }] },
  ]) expect(() => validateCampaignPage(value, 100)).toThrow(/Malformed/)
})
