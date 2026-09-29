// @vitest-environment jsdom
// September 29 builder changes: the declared model transport retry rule in saved plans, Explorer
// transport retries in the fault-search record, and faithful task display in the Run desk
// receipt and campaign history (verification findings LOW 2 and 3).
import { createElement as h } from 'react'
import { cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import { api } from '../src/api'
import { runApi, validateCampaignPlan } from '../src/runPlans'
import { CampaignPlan } from '../src/components/CampaignPlan'
import { CampaignHistory } from '../src/components/CampaignHistory'
import { RunControls } from '../src/components/RunControls'
import { SearchAttemptsPanel } from '../src/components/SearchAttemptsPanel'
import { validateSearchAttempts, type SearchAttempt } from '../src/searchAttempts'
import { campaign, config, fixtureResponse, hash } from './fixtures'
import { planned, transportRetryRule } from './run-fixtures'

afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals() })

const envelope = (plan: ReturnType<typeof planned>) => ({ campaign_id: campaign.campaign_id, status: 'PLANNED' as const, plan })

it('accepts the declared retry rule, or none for an older plan, and refuses any other rule', () => {
  expect(validateCampaignPlan(envelope(planned(campaign)), campaign.campaign_id).status).toBe('PLANNED')
  const older = planned(campaign); delete older.transport_retry
  expect(validateCampaignPlan(envelope(older), campaign.campaign_id).status).toBe('PLANNED')
  expect(validateCampaignPlan(envelope(planned(campaign, { transport_retry: null })), campaign.campaign_id).status).toBe('PLANNED')
  for (const change of [{ retries_per_request: 2 }, { roles: ['actor', 'explorer'] }, { roles: ['explorer', 'actor', 'mechanic'] },
    { retryable: ['CONNECTION_ERROR', 'REQUEST_TIMEOUT', 'HTTP_500'] }, { service_unavailable_delay_seconds: 0 },
    { actor_retries_per_episode_max: 16 }, { protocol: 'faultlab-transport-retry/v2' }, { rule: ' ' }]) {
    const plan = planned(campaign, { transport_retry: { ...transportRetryRule, ...change } as typeof transportRetryRule })
    expect(() => validateCampaignPlan(envelope(plan), campaign.campaign_id)).toThrow('Malformed campaign plan transport retry rule')
  }
})

it('shows the frozen retry rule in the saved plan, and says when an older plan declared none', () => {
  render(h(CampaignPlan, { campaign, resource: { data: envelope(planned(campaign)), error: null, loading: false } }))
  const region = screen.getByRole('region', { name: 'Saved campaign plan' })
  const field = within(region).getByText('Model transport retries').nextElementSibling!
  expect(field.textContent).toBe('At most one charged retry per Actor, Explorer or Mechanic request that received no answer (connection error, timeout, HTTP 503) · at most 8 per episode for the agent · never after an answer · never an extra turn')
  expect(within(region).getByText(transportRetryRule.rule)).toBeTruthy()
  cleanup()
  const older = planned(campaign); delete older.transport_retry
  render(h(CampaignPlan, { campaign, resource: { data: envelope(older), error: null, loading: false } }))
  expect(screen.getByText('Model transport retries').nextElementSibling!.textContent).toBe('Not declared: this plan was saved before model transport retries were declared in plans.')
})

// A task whose visible sentence hides a second one in variation selectors and a zero-width space.
const HIDDEN = 'Upgrade the order.' + Array.from('Hi', c => String.fromCodePoint(0xFE00 + (c.charCodeAt(0) % 16))).join('') + '​'

it('shows the recorded task in the Run desk receipt with every hidden character marked', async () => {
  const saved = { ...campaign, state: 'IDLE' as const, task_text: HIDDEN }
  vi.stubGlobal('fetch', vi.fn(async (url: string) => ({ ok: true, json: async () => fixtureResponse(url) })))
  vi.spyOn(runApi, 'plan').mockResolvedValue({ campaign_id: saved.campaign_id, status: 'LEGACY', plan: null })
  render(h(RunControls, { config, campaign: saved, replay: false, onCampaign: vi.fn(), onReplay: vi.fn() }))
  const field = (await screen.findByText('Recorded task')).nextElementSibling!
  expect(field.querySelector('span.task-text')).toBeTruthy()
  expect(Array.from(field.querySelectorAll('.task-mark'), mark => mark.textContent)).toEqual(['⟨U+FE08⟩', '⟨U+FE09⟩', '⟨U+200B⟩'])
  expect(field.textContent).not.toContain('​')
})

it('shows the saved task in campaign history with every hidden character marked', async () => {
  const saved = { ...campaign, campaign_id: 'campaign-hidden', task_text: HIDDEN }
  vi.spyOn(api, 'campaigns').mockResolvedValue({ campaigns: [saved], next_before: null, has_more: false })
  render(h(CampaignHistory, { selectedId: saved.campaign_id, refreshKey: 0, onOpen: vi.fn() }))
  const field = (await screen.findByText('Saved task')).nextElementSibling!
  expect(Array.from(field.querySelectorAll('.task-mark'), mark => mark.textContent)).toEqual(['⟨U+FE08⟩', '⟨U+FE09⟩', '⟨U+200B⟩'])
  expect(field.textContent!.startsWith('Upgrade the order.')).toBe(true)
})

// Review finding (LOW, September 29): one presentation selector after each digit stayed unmarked
// (Unicode's Emoji property lists 0-9), a one-bit-per-digit hidden channel in order numbers.
const DIGITS = 'Upgrade order ref 1\uFE0F2\uFE0E3\uFE0F4\uFE0E, then confirm. Press 1\uFE0F\u20E3.'
const DIGIT_MARKS = ['\u27e8U+FE0F\u27e9', '\u27e8U+FE0E\u27e9', '\u27e8U+FE0F\u27e9', '\u27e8U+FE0E\u27e9']
const marks = (field: Element) => Array.from(field.querySelectorAll('.task-mark'), mark => mark.textContent)

it('marks a presentation selector after a digit in the Run desk, the saved plan and campaign history; a keycap stays plain', async () => {
  const saved = { ...campaign, state: 'IDLE' as const, task_text: DIGITS }
  vi.stubGlobal('fetch', vi.fn(async (url: string) => ({ ok: true, json: async () => fixtureResponse(url) })))
  vi.spyOn(runApi, 'plan').mockResolvedValue({ campaign_id: saved.campaign_id, status: 'LEGACY', plan: null })
  render(h(RunControls, { config, campaign: saved, replay: false, onCampaign: vi.fn(), onReplay: vi.fn() }))
  const recorded = (await screen.findByText('Recorded task')).nextElementSibling!
  expect(marks(recorded)).toEqual(DIGIT_MARKS)
  expect(recorded.textContent!.endsWith('Press 1\uFE0F\u20E3.')).toBe(true)
  cleanup()
  render(h(CampaignPlan, { campaign: saved, resource: { data: envelope(planned(saved)), error: null, loading: false } }))
  expect(marks(screen.getByText('Frozen instructions').nextElementSibling!)).toEqual(DIGIT_MARKS)
  cleanup()
  const history = { ...campaign, campaign_id: 'campaign-digits', task_text: DIGITS }
  vi.spyOn(api, 'campaigns').mockResolvedValue({ campaigns: [history], next_before: null, has_more: false })
  render(h(CampaignHistory, { selectedId: history.campaign_id, refreshKey: 0, onOpen: vi.fn() }))
  expect(marks((await screen.findByText('Saved task')).nextElementSibling!)).toEqual(DIGIT_MARKS)
})

function attempt(retries?: SearchAttempt['transport_retries'], modelCalls = 1): SearchAttempt {
  const output = { fault_spec: { seed: 1, primitives: [{ kind: 'F4' as const, target_tool: 'send_confirmation' as const, target_service: 'notifications' as const, occurrence: 1, parameters: { failure_count: 2 } }] }, hypothesis: 'A model-authored hypothesis.' }
  return { selection_ref: 'selection-retried', campaign_id: campaign.campaign_id, selection_index: 0, configuration_hash: hash, policy_hash: hash,
    search_decision: { status: 'SELECTED', schedule_hash: hash, reason: null, prior_selection_refs: [], prior_episode_refs: [] },
    selected_output: output, output, raw_response: 'Original model text retained.',
    usage: { model_calls: modelCalls, input_tokens: 100, output_tokens: 20, cost_dollars: null }, provenance: 'model', error: null,
    ...(retries === undefined ? {} : { transport_retries: retries }) }
}
const RETRY = { retry_id: 'transport-retry-1', code: 'CONNECTION_ERROR' as const, attempt: 1 as const, provider_failure_id: 'provider-failure-1' }

it('shows a charged Explorer transport retry on its selection and refuses inconsistent retry records', async () => {
  expect(validateSearchAttempts([attempt([RETRY], 2)], campaign.campaign_id)[0].transport_retries).toEqual([RETRY])
  expect(validateSearchAttempts([attempt(undefined)], campaign.campaign_id)[0].transport_retries).toBeUndefined()  // older records
  expect(validateSearchAttempts([attempt([])], campaign.campaign_id)).toHaveLength(1)
  const unavailable = { ...RETRY, code: 'HTTP_ERROR' as const, http_status: 503 as const, retry_delay_seconds: 1 as const }
  expect(validateSearchAttempts([attempt([unavailable], 2)], campaign.campaign_id)).toHaveLength(1)
  for (const bad of [attempt([RETRY], 1), attempt([], 2), attempt([RETRY, { ...RETRY, retry_id: 'transport-retry-2' }], 3),
    attempt([{ ...RETRY, code: 'HTTP_ERROR' as const }], 2), attempt([{ ...RETRY, http_status: 500 } as never], 2),
    attempt([{ ...RETRY, attempt: 2 } as never], 2), attempt([{ ...RETRY, code: 'EMPTY_FINAL_RESPONSE' } as never], 2)]) {
    expect(() => validateSearchAttempts([bad], campaign.campaign_id)).toThrow(/Malformed/)
  }
  vi.stubGlobal('fetch', vi.fn(async () => ({ ok: true, json: async () => [attempt([RETRY], 2)] })))
  render(h(SearchAttemptsPanel, { campaignId: campaign.campaign_id, onEpisode: vi.fn() }))
  fireEvent.click(await screen.findByText('Selection 1 · Selected for execution'))
  const note = screen.getByText(/Transport retry: the first request received no answer/)
  expect(note.textContent).toBe('Transport retry: the first request received no answer (connection error), so the identical request was sent once more. Both requests are charged (2 model requests); this is not a new selection request. Provider failure provider-failure-1.')
})
