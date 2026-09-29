import { readFile } from 'node:fs/promises'
import { test, expect } from '@playwright/test'
import type { Campaign } from '../src/generated/contracts'
import { campaign, config, fixtureResponse, matrix, readiness } from './fixtures'
import { agentHistory, discoveryV3, planned, runOptions } from './run-fixtures'

// Discovery v3 (September 29): the native agent declares history-informed discovery; the saved plan shows the
// frozen history (statement, per-recipe outcomes, summary hash, record cutoff) before Start, within the panel,
// and the recording carries it. Every API response is a fixture; nothing starts and no provider is called.
// Review fixes: the panel names each failed check, shows where the history comes from and which FaultLab builds
// each row ran under, and an on-demand check (never polled) shows a stale plan before Start.
test('native v3 plan shows the frozen agent history before Start and the recording carries it', async ({ page }) => {
  const writes: { path: string; body: Record<string, unknown> }[] = []
  const errors: string[] = []
  page.on('pageerror', error => errors.push(error.message))
  const current: Campaign = { ...campaign, campaign_id: 'campaign-v3-history-fixture', config_profile_id: 'live-v1', mode: 'learn', state: 'IDLE', latest_episode_id: null, model: 'fixture-model', task_text: runOptions.task.task_text_default, order_id: 'order-demo', caps: runOptions.caps, usage: { model_calls: 0, http_attempts: 0, cost_dollars: 0 } }
  const plan = planned(current, { agent: 'smolagents', agent_registration_id: 'smolagents-fixture', mode: 'learn', config_profile_id: 'live-v1', source_mode: 'live',
    selection: { kind: 'development_search', manifest_hash: runOptions.learn.manifest_hash, search_space: runOptions.learn.search_space }, discovery: { ...discoveryV3, history: agentHistory() } })
  const requests: string[] = []
  await page.route('**/api/**', async route => {
    const request = route.request(); const path = new URL(request.url()).pathname
    requests.push(path)
    if (request.method() === 'POST') { writes.push({ path, body: request.postDataJSON() ?? {} }); await route.fulfill({ json: current }); return }
    const json = path.endsWith('/run-options') ? { ...runOptions, agents: runOptions.agents.map(agent => ({ ...agent, registered: true, registration_id: agent.proposed_registration_id })) }
      : path.endsWith('/config/status') ? { ...config, data_store: runOptions.data_store, live_enabled: true, model_configured: true }
      : path.endsWith('/readiness') ? { ...readiness, live_configuration: { ready: true, missing_fields: [] } }
      : path.endsWith('/plan/history-check') ? { campaign_id: current.campaign_id, status: 'CHANGED', record_cutoff: 827, summary_hash: 'e'.repeat(64), message: 'The store\'s prior history for this agent changed at or before the plan\'s record cutoff (frozen summary eeeeeeeeeeee…, now ffffffffffff…); create a new plan' }
      : path.endsWith('/plan') ? { campaign_id: current.campaign_id, status: 'PLANNED', plan }
      : path.endsWith('/matrix') ? { ...matrix, campaign_id: current.campaign_id, cells: [], counts: Object.fromEntries(Object.keys(matrix.counts).map(key => [key, 0])) }
      : path.endsWith('/recording') ? { recording_version: 'faultlab-development-recording/v1', campaign_id: current.campaign_id, campaign: current, run_plan: { campaign_id: current.campaign_id, status: 'PLANNED', plan } }
      : fixtureResponse(request.url(), current)
    await route.fulfill({ json })
  })
  await page.goto('/')
  await page.getByLabel('Execution profile', { exact: true }).selectOption('live-v1')
  await page.getByLabel('Reviewed agent', { exact: true }).selectOption('smolagents')
  await page.getByLabel('Campaign mode', { exact: true }).selectOption('learn')
  await expect(page.getByRole('option', { name: 'v3 · agent history + reachability pre-check' })).toBeDisabled()
  await page.getByLabel('Discovery protocol', { exact: true }).selectOption('faultlab-discovery/v3-history')
  await expect(page.getByText(/frozen into the plan when you create the campaign/)).toBeVisible()
  await page.getByRole('button', { name: 'Create campaign' }).click()
  const history = page.getByRole('region', { name: 'Frozen agent history' })
  await expect(history).toContainText('Prior evidence, not an instruction')
  await expect(history).toContainText('e'.repeat(64))
  await expect(history).toContainText('store row 827')
  const dev5 = history.getByRole('listitem').filter({ hasText: 'dev-5' })
  await expect(dev5).toContainText('failed checks C3 (upgrade before confirmation) 3 · C5 (truthful report) 3')
  await expect(dev5).toContainText('every fault fired 3 of 3')
  await expect(dev5).toContainText('Ran under runtime a8a32234a45a, c0a8aad71dfe · adapter 61497db3ae1d, 8a579f997793')
  await expect(history).toContainText('2 baseline studies (6 episodes) · 0 learn campaigns\' discovery (0 episodes)')
  expect(requests.filter(path => path.endsWith('/history-check'))).toEqual([])  // never polled
  await history.getByRole('button', { name: 'Check against the store now' }).click()
  await expect(history.getByRole('status')).toContainText('Changed: Start will be refused.')
  await expect(history.getByRole('status')).toContainText('create a new plan')
  expect(requests.filter(path => path.endsWith('/history-check'))).toHaveLength(1)
  // Everything stays inside the (narrow) plan panel: a first build used a table that overflowed it.
  const saved = await page.getByRole('region', { name: 'Saved campaign plan' }).boundingBox()
  for (const part of [history, history.getByRole('list', { name: 'Recipes in the agent history' }), history.locator('code'), history.getByRole('status')]) {
    const box = await part.boundingBox()
    expect(box!.x + box!.width).toBeLessThanOrEqual(saved!.x + saved!.width + 1)
  }
  expect(await history.evaluate(node => node.scrollWidth <= node.clientWidth + 1)).toBe(true)
  expect(writes).toEqual([{ path: '/api/planned-campaigns', body: expect.objectContaining({ discovery_protocol: 'faultlab-discovery/v3-history', agent_registration_id: 'smolagents-fixture', mode: 'learn' }) }])
  const downloadEvent = page.waitForEvent('download')
  await page.getByRole('button', { name: 'Download campaign recording' }).click()
  const payload = JSON.parse(await readFile((await (await downloadEvent).path())!, 'utf8'))
  expect(payload.run_plan.plan.discovery.history.summary_hash).toBe('e'.repeat(64))
  expect(writes.some(item => item.path.endsWith('/start'))).toBe(false)
  expect(errors).toEqual([])
  await history.screenshot({ path: test.info().outputPath('v3-frozen-agent-history.png') })
})
