import { readFile } from 'node:fs/promises'
import { test, expect } from '@playwright/test'
import type { Campaign } from '../src/generated/contracts'
import { campaign, config, fixtureResponse, matrix, readiness } from './fixtures'
import { agentHistory, discoveryV4, discoveryV4Option, historyReplay, planned, runOptions } from './run-fixtures'

// Discovery v4 (September 30, history replay first): the native agent declares regression-first discovery; the saved
// plan shows the frozen replay list (row, recipe, counts, rule) before the frozen history, inside the narrow plan panel,
// and the recording carries it. Every API response is a fixture; nothing starts and no provider is called.
test('native v4 plan shows the frozen replay list before Start and the recording carries it', async ({ page }) => {
  const writes: { path: string; body: Record<string, unknown> }[] = []
  const errors: string[] = []
  page.on('pageerror', error => errors.push(error.message))
  const current: Campaign = { ...campaign, campaign_id: 'campaign-v4-replay-fixture', config_profile_id: 'live-v1', mode: 'learn', state: 'IDLE', latest_episode_id: null, model: 'fixture-model', task_text: runOptions.task.task_text_default, order_id: 'order-demo', caps: runOptions.caps, usage: { model_calls: 0, http_attempts: 0, cost_dollars: 0 } }
  const plan = planned(current, { agent: 'smolagents', agent_registration_id: 'smolagents-fixture', mode: 'learn', config_profile_id: 'live-v1', source_mode: 'live',
    selection: { kind: 'development_search', manifest_hash: runOptions.learn.manifest_hash, search_space: runOptions.learn.search_space }, discovery: { ...discoveryV4, history: agentHistory(), replay: historyReplay() } })
  const options = { ...runOptions, learn: { ...runOptions.learn, discovery_protocols: [...runOptions.learn.discovery_protocols!, discoveryV4Option] },
    agents: runOptions.agents.map(agent => ({ ...agent, registered: true, registration_id: agent.proposed_registration_id })) }
  await page.route('**/api/**', async route => {
    const request = route.request(); const path = new URL(request.url()).pathname
    if (request.method() === 'POST') { writes.push({ path, body: request.postDataJSON() ?? {} }); await route.fulfill({ json: current }); return }
    const json = path.endsWith('/run-options') ? options
      : path.endsWith('/config/status') ? { ...config, data_store: runOptions.data_store, live_enabled: true, model_configured: true }
      : path.endsWith('/readiness') ? { ...readiness, live_configuration: { ready: true, missing_fields: [] } }
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
  await expect(page.getByRole('option', { name: 'v4 · history replay first' })).toBeEnabled()
  await page.getByLabel('Discovery protocol', { exact: true }).selectOption('faultlab-discovery/v4-history-replay')
  await expect(page.getByText(discoveryV4Option.description)).toBeVisible()
  await expect(page.getByText(/replay list is computed from this agent history and frozen into the plan/)).toBeVisible()
  await page.getByRole('button', { name: 'Create campaign' }).click()
  const replay = page.getByRole('region', { name: 'Frozen history replay list' })
  await expect(replay).toContainText('History replay list · runs first')
  const row = replay.getByRole('listitem').filter({ hasText: 'dev-5' })
  await expect(row).toContainText('Replay 1 · agent history row 2 (dev-5)')
  await expect(row).toContainText('violated in 3/3 verified episodes · every fault fired 3 of 3')
  await expect(replay).toContainText('1 slot of this campaign\'s discovery slots · 1 agent episode · no Explorer request')
  await expect(replay).toContainText('never as independent discovery')
  await expect(page.getByRole('region', { name: 'Frozen agent history' })).toContainText('e'.repeat(64))
  // Everything stays inside the (narrow) plan panel.
  const saved = await page.getByRole('region', { name: 'Saved campaign plan' }).boundingBox()
  for (const part of [replay, replay.getByRole('list', { name: 'Recipes replayed first' }), replay.locator('code')]) {
    const box = await part.boundingBox()
    expect(box!.x + box!.width).toBeLessThanOrEqual(saved!.x + saved!.width + 1)
  }
  expect(await replay.evaluate(node => node.scrollWidth <= node.clientWidth + 1)).toBe(true)
  expect(writes).toEqual([{ path: '/api/planned-campaigns', body: expect.objectContaining({ discovery_protocol: 'faultlab-discovery/v4-history-replay', agent_registration_id: 'smolagents-fixture', mode: 'learn' }) }])
  const downloadEvent = page.waitForEvent('download')
  await page.getByRole('button', { name: 'Download campaign recording' }).click()
  const payload = JSON.parse(await readFile((await (await downloadEvent).path())!, 'utf8'))
  expect(payload.run_plan.plan.discovery.replay.rows[0].history_row).toBe(2)
  expect(writes.some(item => item.path.endsWith('/start'))).toBe(false)
  expect(errors).toEqual([])
  await replay.screenshot({ path: test.info().outputPath('v4-frozen-replay-list.png') })
})
