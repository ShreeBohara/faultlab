// @vitest-environment jsdom
// September 29 (evidence dependability): the declared automatic evidence retry in saved Learn plans, and the
// Run desk notice while a campaign waits for Weave evidence ("needs operator" after the last automatic retry).
import { createElement as h } from 'react'
import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import type { Campaign } from '../src/generated/contracts'
import { validateCampaignPlan } from '../src/runPlans'
import { validateEvidenceWait, type EvidenceWait } from '../src/evidenceWait'
import { CampaignPlan } from '../src/components/CampaignPlan'
import { RunControls } from '../src/components/RunControls'
import { campaign, config, fixtureResponse } from './fixtures'
import { discoveryV1, evidenceRetryRule, evidenceRetryRuleV1, planned, runOptions } from './run-fixtures'

afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals(); vi.useRealTimers() })

const learnPlan = (patch = {}) => planned(campaign, { mode: 'learn', config_profile_id: 'live-v1', source_mode: 'live',
  selection: { kind: 'development_search', manifest_hash: runOptions.learn.manifest_hash, search_space: runOptions.learn.search_space },
  discovery: discoveryV1, evidence_retry: evidenceRetryRule, ...patch })
const envelope = (plan: ReturnType<typeof planned>) => ({ campaign_id: campaign.campaign_id, status: 'PLANNED' as const, plan })

const waiting: Campaign = { ...campaign, mode: 'learn', config_profile_id: 'live-v1', state: 'WAITING_EVIDENCE', state_seq: 40,
  terminal_reason: 'Needs operator: Weave evidence for 6 episodes is still unverified after 3 automatic telemetry retries (last ingestion result: TRANSPORT). The campaign keeps waiting. Press Retry evidence sync, or Stop.' }
const attempt = (n: number) => ({ attempt: n, request_id: `evidence-retry-${n}`, scheduled_for: '2026-09-29T10:23:00+00:00', started_at: '2026-09-29T10:23:00+00:00',
  ended_at: '2026-09-29T10:23:05+00:00', status: 'COMPLETED', episode_ids: ['episode-a', 'episode-b'], verified: 0, still_pending: 2 })
const record = { wait_id: 'evidence-wait-1', campaign_id: waiting.campaign_id, status: 'NEEDS_OPERATOR', message: waiting.terminal_reason, episode_id: 'episode-a',
  pending_episode_ids: ['episode-a', 'episode-b'], state_before: 'CHALLENGING', started_at: '2026-09-29T10:22:28+00:00', ended_at: null, resolution: null,
  failed_reads: 4, last_read_result: 'TRANSPORT', automatic_retries_max: 3, delays_seconds: [30, 120, 300], automatic_attempts: [1, 2, 3].map(attempt),
  manual_retry_request_ids: [], next_automatic_retry_at: null }
const needsOperator: EvidenceWait = { schema_version: 'faultlab-evidence-wait/v1', campaign_id: waiting.campaign_id, campaign_state: 'WAITING_EVIDENCE',
  declared: evidenceRetryRule, declared_note: null, status: 'NEEDS_OPERATOR', needs_operator: true, message: waiting.terminal_reason!,
  current: record as EvidenceWait['current'], waits: [record as EvidenceWait['waits'][number]], waits_total: 1, automatic_retries_total: 3 }

it('accepts the declared evidence retry in a Learn plan, or none for an older plan, and refuses any other rule', () => {
  expect(validateCampaignPlan(envelope(learnPlan()), campaign.campaign_id).status).toBe('PLANNED')
  expect(validateCampaignPlan(envelope(learnPlan({ evidence_retry: null })), campaign.campaign_id).status).toBe('PLANNED')
  const older = learnPlan(); delete older.evidence_retry
  expect(validateCampaignPlan(envelope(older), campaign.campaign_id).status).toBe('PLANNED')
  // A plan saved under the first rule (no campaign limit) still reads; the backend refuses it at Start.
  expect(validateCampaignPlan(envelope(learnPlan({ evidence_retry: evidenceRetryRuleV1 })), campaign.campaign_id).status).toBe('PLANNED')
  const { automatic_retries_per_campaign: _limit, ...withoutLimit } = evidenceRetryRule
  for (const rule of [...[{ automatic_retries_per_wait: 4 }, { delays_seconds: [30, 120] }, { delays_seconds: [10, 120, 300] }, { repeats_model_requests: true },
    { repeats_business_actions: true }, { charged_model_calls: 1 }, { telemetry_only: false }, { after_last_retry: 'STOP' }, { protocol: 'faultlab-evidence-retry/v3' }, { rule: ' ' },
    { automatic_retries_per_campaign: 7 }, { automatic_retries_per_campaign: null }].map(change => ({ ...evidenceRetryRule, ...change })),
    withoutLimit,                                                     // v2 must declare its campaign limit
    { ...evidenceRetryRuleV1, automatic_retries_per_campaign: 6 }]) {  // v1 had none
    const plan = learnPlan({ evidence_retry: rule as typeof evidenceRetryRule })
    expect(() => validateCampaignPlan(envelope(plan), campaign.campaign_id)).toThrow('Malformed campaign plan evidence retry rule')
  }
  // Only a Learn plan waits for evidence.
  expect(() => validateCampaignPlan(envelope(planned(campaign, { evidence_retry: evidenceRetryRule })), campaign.campaign_id)).toThrow('Malformed campaign plan evidence retry rule')
})

it('shows the frozen evidence retry rule in a saved Learn plan, says when an older plan declared none, and shows nothing for other modes', () => {
  // Fixer (review F4): the plan names the rule id beside its cap (the exact text is still pinned).
  render(h(CampaignPlan, { campaign, resource: { data: envelope(learnPlan()), error: null, loading: false } }))
  const region = screen.getByRole('region', { name: 'Saved campaign plan' })
  expect(within(region).getByText('Automatic evidence retries').nextElementSibling!.textContent).toBe(
    'Up to 3 per evidence wait and 6 per campaign under rule faultlab-evidence-retry/v2 (after 30 s, 120 s, 300 s) · telemetry only: no episode, business action or model request is repeated, nothing is charged · then “needs operator”')
  expect(within(region).getByText(evidenceRetryRule.rule)).toBeTruthy()
  cleanup()
  render(h(CampaignPlan, { campaign, resource: { data: envelope(learnPlan({ evidence_retry: evidenceRetryRuleV1 })), error: null, loading: false } }))
  expect(screen.getByText('Automatic evidence retries').nextElementSibling!.textContent).toBe(
    'Up to 3 per evidence wait (no campaign limit: an earlier rule that Start now refuses) under rule faultlab-evidence-retry/v1 (after 30 s, 120 s, 300 s) · telemetry only: no episode, business action or model request is repeated, nothing is charged · then “needs operator”')
  cleanup()
  render(h(CampaignPlan, { campaign, resource: { data: envelope(learnPlan({ evidence_retry: null })), error: null, loading: false } }))
  expect(screen.getByText('Automatic evidence retries').nextElementSibling!.textContent).toBe('Not declared: this plan was saved before automatic evidence retries were declared. Only manual Retry evidence sync applies.')
  cleanup()
  render(h(CampaignPlan, { campaign, resource: { data: envelope(planned(campaign)), error: null, loading: false } }))
  expect(screen.queryByText('Automatic evidence retries')).toBeNull()
})

it('validates the evidence wait strictly', () => {
  expect(validateEvidenceWait(needsOperator, waiting.campaign_id)).toEqual(needsOperator)
  const notWaiting = { ...needsOperator, status: 'NOT_WAITING', needs_operator: false, current: null, message: 'This campaign is not waiting for evidence.' }
  expect(validateEvidenceWait(notWaiting, waiting.campaign_id).status).toBe('NOT_WAITING')
  const limited = { ...needsOperator, current: { ...record, automatic_retries_campaign_max: 6, limit_reached: 'PER_CAMPAIGN' } }
  expect(validateEvidenceWait(limited, waiting.campaign_id)).toEqual(limited)
  for (const bad of [
    { ...needsOperator, campaign_id: 'campaign-other' },
    { ...needsOperator, needs_operator: false },                                          // the flag must match the status
    { ...needsOperator, status: 'SOMETHING_ELSE' },
    { ...needsOperator, declared: { ...evidenceRetryRule, automatic_retries_per_wait: 5 } },
    { ...needsOperator, declared: null, declared_note: null },                            // an undeclared rule must say so
    { ...needsOperator, current: { ...record, automatic_attempts: [1, 2, 3, 4].map(attempt) } },   // never more attempts than declared
    { ...needsOperator, current: { ...record, ended_at: '2026-09-29T11:00:00+00:00' } },  // an open wait has no end
    { ...needsOperator, current: { ...record, campaign_id: 'campaign-other' } },
    { ...needsOperator, waits_total: 0 },
    { ...needsOperator, current: { ...record, limit_reached: 'SOMETIMES' } },
    { ...needsOperator, current: { ...record, automatic_retries_campaign_max: -1 } },
  ]) expect(() => validateEvidenceWait(bad, waiting.campaign_id)).toThrow('Malformed evidence wait response')
})

it('shows "needs operator" in the Run desk, reads the wait once per state change, and retries only on request', async () => {
  const fetch = vi.fn(async (url: string, options?: RequestInit) => ({ ok: true, json: async () =>
    url.endsWith('/evidence-wait') ? needsOperator : url.endsWith('/retry-evidence') ? { request_id: 'evidence-retry-manual', status: 'QUEUED' } : fixtureResponse(url, waiting) }))
  vi.stubGlobal('fetch', fetch)
  const props = { config, replay: false, onCampaign: vi.fn(), onReplay: vi.fn() }
  const view = render(h(RunControls, { ...props, campaign: waiting }))
  const region = await screen.findByRole('region', { name: 'Evidence wait' })
  await within(region).findByText('Needs operator: evidence still unverified')
  expect(within(region).getByText(waiting.terminal_reason!)).toBeTruthy()
  expect(within(region).getByText('Automatic retries').nextElementSibling!.textContent).toBe('3 of 3 made')
  expect(within(region).getByText('Next automatic retry').nextElementSibling!.textContent).toBe('None scheduled')
  expect(within(region).getByText('Automatic retries this campaign').nextElementSibling!.textContent).toBe('3 of 6')
  expect(within(within(region).getByRole('list', { name: 'Automatic retry attempts' })).getAllByRole('listitem').map(item => item.textContent))
    .toEqual([1, 2, 3].map(n => `Retry ${n} · Still unverified · 0 verified, 2 still pending`))
  expect(within(region).getByText(/telemetry only/)).toBeTruthy()
  expect(screen.getAllByText(waiting.terminal_reason!)).toHaveLength(1)     // the reason is not repeated outside the notice
  const reads = () => fetch.mock.calls.filter(([url]) => String(url).endsWith('/evidence-wait')).length
  expect(reads()).toBe(1)
  vi.useFakeTimers()
  await act(() => vi.advanceTimersByTimeAsync(10_000))
  expect(reads()).toBe(1)                                                    // never polled on a timer
  vi.useRealTimers()
  fireEvent.click(within(region).getByRole('button', { name: 'Retry evidence sync now' }))
  await within(region).findByText('Retry accepted for the 2 episodes this wait needs (saved evidence only). The campaign reads the evidence again when it finishes.')
  const posts = fetch.mock.calls.filter(([, options]) => (options as RequestInit | undefined)?.method === 'POST')
  expect(posts.map(([url]) => url)).toEqual([`/api/campaigns/${waiting.campaign_id}/retry-evidence`])
  // Only the wait's own episodes, blocked episode first: not every episode of the campaign.
  expect(JSON.parse(String((posts[0][1] as RequestInit).body))).toEqual({ episode_ids: ['episode-a', 'episode-b'] })
  view.rerender(h(RunControls, { ...props, campaign: { ...waiting, state_seq: 41 } }))
  await waitFor(() => expect(reads()).toBe(2))                              // a new campaign state: one new read
})

it('reads nothing about evidence waits for a campaign that is not waiting', async () => {
  const fetch = vi.fn(async (url: string) => ({ ok: true, json: async () => fixtureResponse(url) }))
  vi.stubGlobal('fetch', fetch)
  render(h(RunControls, { config, campaign: { ...campaign, state: 'STOPPED', terminal_reason: 'Stopped during an evidence wait: fixture.' }, replay: false, onCampaign: vi.fn(), onReplay: vi.fn() }))
  await screen.findByText('Stopped during an evidence wait: fixture.')
  expect(screen.queryByRole('region', { name: 'Evidence wait' })).toBeNull()
  expect(fetch.mock.calls.some(([url]) => String(url).endsWith('/evidence-wait'))).toBe(false)
})

it('keeps the saved campaign reason visible when a waiting campaign has no wait record, and then retries every episode', async () => {
  const saved = 'Waiting for verified Weave evidence: TRANSPORT (saved before automatic evidence retries existed).'
  const legacy: Campaign = { ...waiting, terminal_reason: saved }
  const generic = 'This campaign is waiting for evidence but has no recorded evidence wait (saved before automatic evidence retries existed, or its execution already ended). Retry evidence sync re-sends telemetry only; it does not restart execution.'
  const body = { ...needsOperator, declared: null, declared_note: 'Not declared: fixture.', message: generic, current: null, waits: [], waits_total: 0, automatic_retries_total: 0 }
  const fetch = vi.fn(async (url: string) => ({ ok: true, json: async () =>
    url.endsWith('/evidence-wait') ? body : url.endsWith('/retry-evidence') ? { request_id: 'evidence-retry-manual', status: 'QUEUED' } : fixtureResponse(url, legacy) }))
  vi.stubGlobal('fetch', fetch)
  render(h(RunControls, { config, campaign: legacy, replay: false, onCampaign: vi.fn(), onReplay: vi.fn() }))
  const region = await screen.findByRole('region', { name: 'Evidence wait' })
  await within(region).findByText(generic)
  expect(within(region).getByText(`Saved campaign reason: ${saved}`)).toBeTruthy()
  expect(within(region).queryByText('Automatic retries this campaign')).toBeNull()
  fireEvent.click(within(region).getByRole('button', { name: 'Retry evidence sync now' }))
  await within(region).findByText(/Retry accepted for every episode of this campaign/)
  const post = fetch.mock.calls.find(([, options]) => (options as RequestInit | undefined)?.method === 'POST')!
  expect(JSON.parse(String((post[1] as RequestInit).body))).toEqual({})
})
