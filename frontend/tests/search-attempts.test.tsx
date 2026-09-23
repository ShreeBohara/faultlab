// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import { SearchAttemptsPanel } from '../src/components/SearchAttemptsPanel'
import { validateSearchAttempts } from '../src/searchAttempts'
import type { SearchAttempt } from '../src/searchAttempts'
import { campaign, hash } from './fixtures'

afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals() })
function attempt(duplicate = false): SearchAttempt {
  const output = { fault_spec: { seed: duplicate ? 99 : 1, primitives: [{ kind: 'F4' as const, target_tool: 'send_confirmation' as const, target_service: 'notifications' as const, occurrence: 1, parameters: { failure_count: 2 } }] }, hypothesis: 'A model-authored hypothesis, not a fixed finding.' }
  return { selection_ref: duplicate ? 'selection-duplicate' : 'selection-original', campaign_id: campaign.campaign_id,
    selection_index: duplicate ? 1 : 0, configuration_hash: hash, policy_hash: hash,
    search_decision: { status: duplicate ? 'SKIPPED_DUPLICATE' : 'SELECTED', schedule_hash: hash,
      reason: duplicate ? 'DUPLICATE_DISCOVERY_SCHEDULE' : null, prior_selection_refs: duplicate ? ['selection-original'] : [], prior_episode_refs: duplicate ? ['episode-earlier'] : [] },
    selected_output: duplicate ? null : output, output, raw_response: 'Original model text retained.',
    usage: { model_calls: 1, input_tokens: 100, output_tokens: 20, cost_dollars: null }, provenance: 'model', error: null }
}

it('distinguishes recorded proposals from selected schedules and declined duplicates without creating a trial', async () => {
  const calls: { url: string; method: string }[] = [], select = vi.fn()
  vi.stubGlobal('fetch', vi.fn(async (url: string, options: RequestInit) => { calls.push({ url: String(url), method: options.method! }); return { ok: true, json: async () => [attempt(), attempt(true)] } }))
  render(<SearchAttemptsPanel campaignId={campaign.campaign_id} onEpisode={select} />)
  const total = await screen.findByText('Recorded selection responses')
  expect(total.parentElement?.textContent).toBe('2Recorded selection responses')
  expect(screen.getByText('Selected for execution').parentElement?.textContent).toBe('1Selected for execution')
  expect(screen.getByText('Duplicates declined').parentElement?.textContent).toBe('1Duplicates declined')
  expect(screen.getByText(/Only the trial ledger records whether/)).toBeTruthy()
  fireEvent.click(screen.getByText('Selection 2 · Duplicate declined · no Actor trial'))
  fireEvent.click(screen.getByRole('button', { name: 'episode-earlier' }))
  expect(select).toHaveBeenCalledWith('episode-earlier')
  expect(screen.getByText(/Recorded reason: duplicate discovery schedule/)).toBeTruthy()
  expect(calls).toEqual([{ url: `/api/campaigns/${campaign.campaign_id}/search-attempts`, method: 'GET' }])
  expect(screen.queryByRole('button', { name: /start|run|retry|execute/i })).toBeNull()
  const original = screen.getAllByText('Inspect original response and saved selection decision')[0].parentElement!
  expect(original.hasAttribute('open')).toBe(false)
  expect(within(original).getByText(/Original model text retained/, { exact: false })).toBeTruthy()
})

it.each([
  ['wrong campaign', (a: SearchAttempt) => { a.campaign_id = 'campaign-other' }],
  ['declined selection with dispatch output', (a: SearchAttempt) => { a.search_decision.status = 'SKIPPED_DUPLICATE' }],
  ['selected schedule without dispatch output', (a: SearchAttempt) => { a.selected_output = null }],
  ['invalid typed recipe', (a: SearchAttempt) => { a.selected_output!.fault_spec.primitives[0].occurrence = -1 }],
  ['invalid usage', (a: SearchAttempt) => { a.usage.model_calls = -1 }],
] as const)('rejects %s instead of presenting it as a tested schedule', (_, mutate) => {
  const saved = attempt(); mutate(saved)
  expect(() => validateSearchAttempts([saved], campaign.campaign_id)).toThrow(/Malformed/)
})

it('rejects duplicate selection records and preserves an invalid response as a non-executed attempt', () => {
  expect(() => validateSearchAttempts([attempt(), attempt()], campaign.campaign_id)).toThrow(/Malformed/)
  const invalid = { ...attempt(), selected_output: null, output: null, error: 'INVALID_EXPLORER_OUTPUT', search_decision: { status: 'INVALID_OUTPUT', schedule_hash: null, reason: 'INVALID_EXPLORER_OUTPUT', prior_selection_refs: [], prior_episode_refs: [] } }
  expect(validateSearchAttempts([invalid], campaign.campaign_id)[0].raw_response).toBe(invalid.raw_response)
})

it('does not turn absent historical search records into a claim that no faults ran', async () => {
  vi.stubGlobal('fetch', vi.fn(async () => ({ ok: true, json: async () => [] })))
  render(<SearchAttemptsPanel campaignId={campaign.campaign_id} onEpisode={vi.fn()} />)
  await screen.findByText(/Older records may contain executed trials without a selection ledger/)
  await waitFor(() => expect(vi.mocked(fetch).mock.calls.every(([, options]) => options?.method === 'GET')).toBe(true))
})

it('clears previous campaign selections while the next read is pending and rejects a crossed response', async () => {
  let resolve!: (value: unknown) => void
  const pending = new Promise(r => { resolve = r })
  vi.stubGlobal('fetch', vi.fn(async (url: string) => ({ ok: true, json: async () => url.includes('campaign-other') ? pending : [attempt()] })))
  const view = render(<SearchAttemptsPanel campaignId={campaign.campaign_id} onEpisode={vi.fn()} />)
  await screen.findByText('Selection 1 · Selected for execution')
  view.rerender(<SearchAttemptsPanel campaignId="campaign-other" onEpisode={vi.fn()} />)
  expect(screen.queryByText('Selection 1 · Selected for execution')).toBeNull()
  resolve([attempt()])
  await screen.findByRole('alert')
  expect(screen.queryByText('Selection 1 · Selected for execution')).toBeNull()
})
