import { test, expect } from '@playwright/test'
import type { Campaign } from '../src/generated/contracts'
import { campaign, config, fixtureResponse, matrix, readiness } from './fixtures'
import { discoveryV1, evidenceRetryRule, planned, runOptions } from './run-fixtures'

// Evidence dependability (September 29): a Learn campaign that waits for Weave evidence shows the declared automatic
// telemetry retries and, after the last one, "needs operator" in the Run desk, with a one-click evidence retry. The
// wait is read once per campaign state change, never on a timer. Every API response is a fixture; nothing runs.
test('a waiting campaign shows automatic retries, then needs operator, and retries only on request', async ({ page }) => {
  const errors: string[] = []; const writes: string[] = []; const bodies: unknown[] = []; const waitReads: number[] = []
  page.on('pageerror', error => errors.push(error.message))
  const reason = 'Needs operator: Weave evidence for 6 episodes is still unverified after 3 automatic telemetry retries (last ingestion result: TRANSPORT). The campaign keeps waiting. Press Retry evidence sync, or Stop.'
  const current: Campaign = { ...campaign, campaign_id: 'campaign-evidence-wait-fixture', mode: 'learn', config_profile_id: 'live-v1', state: 'WAITING_EVIDENCE', state_seq: 40,
    model: 'fixture-model', latest_episode_id: null, caps: runOptions.caps, usage: { model_calls: 747, http_attempts: 0, cost_dollars: null }, terminal_reason: reason }
  const plan = planned(current, { mode: 'learn', config_profile_id: 'live-v1', source_mode: 'live', agent_registration_id: 'smolagents-fixture', agent: 'smolagents',
    selection: { kind: 'development_search', manifest_hash: runOptions.learn.manifest_hash, search_space: runOptions.learn.search_space }, discovery: discoveryV1, evidence_retry: evidenceRetryRule })
  const attempt = (n: number) => ({ attempt: n, request_id: `evidence-retry-${n}`, scheduled_for: '2026-09-29T10:23:00+00:00', started_at: '2026-09-29T10:23:00+00:00',
    ended_at: '2026-09-29T10:23:05+00:00', status: 'COMPLETED', episode_ids: ['episode-a'], verified: 0, still_pending: 6 })
  const wait = { wait_id: 'evidence-wait-fixture', campaign_id: current.campaign_id, status: 'NEEDS_OPERATOR', message: reason, episode_id: 'episode-61dec8dfc6434db08cc2836df9ecd622',
    pending_episode_ids: ['a', 'b', 'c', 'd', 'e', 'f'].map(x => `episode-${x}`), state_before: 'CHALLENGING', started_at: '2026-09-29T10:22:28+00:00', ended_at: null, resolution: null,
    failed_reads: 4, last_read_result: 'TRANSPORT', automatic_retries_max: 3, delays_seconds: [30, 120, 300], automatic_attempts: [1, 2, 3].map(attempt), manual_retry_request_ids: [], next_automatic_retry_at: null }
  const evidenceWait = { schema_version: 'faultlab-evidence-wait/v1', campaign_id: current.campaign_id, campaign_state: 'WAITING_EVIDENCE', declared: evidenceRetryRule, declared_note: null,
    status: 'NEEDS_OPERATOR', needs_operator: true, message: reason, current: wait, waits: [wait], waits_total: 1, automatic_retries_total: 3 }
  await page.addInitScript(id => localStorage.setItem('faultlab:campaign', id), current.campaign_id)
  await page.route('**/api/**', async route => {
    const request = route.request(); const path = new URL(request.url()).pathname
    if (request.method() === 'POST') { writes.push(path); bodies.push(request.postDataJSON()); await route.fulfill({ status: 202, json: { request_id: 'evidence-retry-manual', campaign_id: current.campaign_id, status: 'QUEUED', trigger: 'manual' } }); return }
    if (path.endsWith('/evidence-wait')) waitReads.push(Date.now())
    const json = path.endsWith('/evidence-wait') ? evidenceWait
      : path.endsWith('/config/status') ? { ...config, data_store: runOptions.data_store, live_enabled: true, model_configured: true, active_campaign_id: current.campaign_id }
      : path.endsWith('/readiness') ? { ...readiness, live_configuration: { ready: true, missing_fields: [] } }
      : path.endsWith('/plan') ? { campaign_id: current.campaign_id, status: 'PLANNED', plan }
      : path.endsWith('/matrix') ? { ...matrix, campaign_id: current.campaign_id, cells: [], counts: Object.fromEntries(Object.keys(matrix.counts).map(key => [key, 0])) }
      : fixtureResponse(request.url(), current)
    await route.fulfill({ json })
  })
  await page.goto('/')
  const notice = page.getByRole('region', { name: 'Evidence wait' })
  await expect(notice.getByRole('heading', { name: 'Needs operator: evidence still unverified' })).toBeVisible()
  await expect(notice.getByText(reason)).toBeVisible()
  await expect(notice.getByText('3 of 3 made')).toBeVisible()
  await expect(notice.getByText('3 of 6', { exact: true })).toBeVisible()      // automatic retries this campaign
  await expect(notice.getByRole('listitem')).toHaveText([1, 2, 3].map(n => `Retry ${n} · Still unverified · 0 verified, 6 still pending`))
  await expect(page.getByText('Automatic evidence retries', { exact: true })).toBeVisible()
  await page.waitForTimeout(3000)                 // about four campaign polls at an unchanged state
  expect(waitReads).toHaveLength(1)
  await notice.scrollIntoViewIfNeeded()
  await page.screenshot({ path: test.info().outputPath('evidence-wait-needs-operator.png'), fullPage: false })
  await notice.getByRole('button', { name: 'Retry evidence sync now' }).click()
  await expect(notice.getByText(/Retry accepted for the 6 episodes this wait needs/)).toBeVisible()
  expect(writes).toEqual([`/api/campaigns/${current.campaign_id}/retry-evidence`])
  expect(bodies).toEqual([{ episode_ids: wait.pending_episode_ids }])      // the wait's own episodes, blocked episode first
  expect(errors).toEqual([])
})
