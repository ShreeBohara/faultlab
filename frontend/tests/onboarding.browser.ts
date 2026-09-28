import { readFile } from 'node:fs/promises'
import { test, expect } from '@playwright/test'
import type { Campaign } from '../src/generated/contracts'
import { campaign, config, fixtureResponse, matrix, readiness, registration } from './fixtures'
import { planned, runOptions } from './run-fixtures'

test('offline public-case preview saves an idle frozen plan before an explicit Start', async ({ page }) => {
  const writes: { path: string; body: Record<string, unknown> }[] = []
  const errors: string[] = []
  page.on('pageerror', error => errors.push(error.message))
  let current: Campaign = { ...campaign, campaign_id: 'campaign-offline-plan-fixture', state: 'IDLE', latest_episode_id: null, task_text: runOptions.task.task_text_default, order_id: 'order-demo', caps: runOptions.caps, usage: { model_calls: 0, http_attempts: 0, cost_dollars: 0 } }
  const item = runOptions.development.cases[3]
  const plan = planned(current, { selection: { kind: 'development_case', ...item, scenario_hash: 'd'.repeat(64), manifest_hash: runOptions.development.manifest_hash } })
  const options = { ...runOptions, agents: runOptions.agents.map(agent => ({ ...agent, status: 'UNAVAILABLE', reason_code: 'MODEL_UNCONFIGURED', message: 'Configure a model for live execution.', model: '', configuration_hash: null, proposed_registration_id: null, source_conformance: 'UNAVAILABLE' })) }
  await page.route('**/api/**', async route => {
    const request = route.request(); const path = new URL(request.url()).pathname
    if (request.method() === 'POST') {
      writes.push({ path, body: request.postDataJSON() ?? {} })
      if (path.endsWith('/start')) current = { ...current, state: 'RUNNING', state_seq: 4 }
      await route.fulfill({ json: current }); return
    }
    const json = path.endsWith('/run-options') ? options
      : path.endsWith('/config/status') ? { ...config, data_store: options.data_store, active_campaign_id: current.state === 'RUNNING' ? current.campaign_id : null }
      : path.endsWith('/plan') ? { campaign_id: current.campaign_id, status: 'PLANNED', plan }
      : path.endsWith('/matrix') ? { ...matrix, campaign_id: current.campaign_id, cells: [], counts: Object.fromEntries(Object.keys(matrix.counts).map(key => [key, 0])) }
      : fixtureResponse(request.url(), current)
    await route.fulfill({ json })
  })
  await page.goto('/')
  await expect(page.getByRole('button', { name: 'Create campaign' })).toBeEnabled()
  await expect(page.getByRole('button', { name: 'Register configured agent' })).toHaveCount(0)
  await page.getByLabel('Public development case', { exact: true }).selectOption(item.case_id)
  await expect(page.getByRole('region', { name: 'Current plan preview' })).toContainText(item.label)
  expect(writes).toEqual([])
  await page.getByRole('button', { name: 'Create campaign' }).click()
  const saved = page.getByRole('region', { name: 'Saved campaign plan' })
  await expect(saved).toContainText(`${item.case_id} · ${item.fixture_id}`)
  await expect(page.getByRole('button', { name: /Start campaign/ })).toBeEnabled()
  expect(writes).toHaveLength(1)
  expect(writes[0]).toMatchObject({ path: '/api/planned-campaigns', body: { development_case_id: item.case_id, config_profile_id: 'offline-v1', mode: 'baseline', expected_store_identity: options.data_store.identity } })
  expect(writes[0].body).not.toHaveProperty('agent_registration_id')
  await page.reload()
  await expect(saved).toContainText(`${item.case_id} · ${item.fixture_id}`)
  await expect(page.getByLabel('Public development case', { exact: true })).toHaveValue('dev-1')
  expect(writes).toHaveLength(1)
  await page.screenshot({ path: test.info().outputPath('offline-frozen-public-case.png'), fullPage: true })
  await page.getByRole('button', { name: /Start campaign/ }).click()
  await expect(page.getByRole('button', { name: 'Stop', exact: true })).toBeEnabled()
  expect(writes.map(item => item.path)).toEqual(['/api/planned-campaigns', `/api/campaigns/${current.campaign_id}/start`])
  await expect(page.getByRole('option', { name: /campaign-offline-plan-fixture/ })).toContainText('Running')
  current = { ...current, state: 'COMPLETED', state_seq: 5 }
  await expect(page.getByRole('option', { name: /campaign-offline-plan-fixture/ })).toContainText('Completed')
  await expect(page.locator('.history-selection')).toContainText('Completed')
  await page.screenshot({ path: test.info().outputPath('history-current-completed-state.png'), fullPage: true })
  expect(errors).toEqual([])
})

test('native source registration is explicit and NO_CHANGE recording retains its frozen identity after reload', async ({ page }) => {
  const writes: { path: string; body: Record<string, unknown> }[] = []
  const reads: string[] = []; const errors: string[] = []
  page.on('pageerror', error => errors.push(error.message))
  let registered = false
  let current: Campaign = { ...campaign, campaign_id: 'campaign-native-plan-fixture', config_profile_id: 'live-v1', mode: 'learn', state: 'IDLE', latest_episode_id: null, model: 'saved-native-fixture-model', task_text: runOptions.task.task_text_default, order_id: 'order-demo', caps: runOptions.caps, usage: { model_calls: 0, http_attempts: 0, cost_dollars: 0 } }
  const plan = planned(current, { agent: 'smolagents', agent_registration_id: 'smolagents-fixture', mode: 'learn', config_profile_id: 'live-v1', source_mode: 'live', selection: { kind: 'development_search', manifest_hash: runOptions.learn.manifest_hash, search_space: runOptions.learn.search_space } })
  await page.route('**/api/**', async route => {
    const request = route.request(); const path = new URL(request.url()).pathname
    if (request.method() === 'POST') {
      writes.push({ path, body: request.postDataJSON() ?? {} })
      if (path === '/api/agent-registrations') { registered = true; await route.fulfill({ json: registration }); return }
      await route.fulfill({ json: current }); return
    }
    reads.push(path)
    const json = path.endsWith('/run-options') ? { ...runOptions, agents: runOptions.agents.map(agent => agent.agent === 'smolagents' && registered ? { ...agent, registered: true, registration_id: agent.proposed_registration_id } : agent) }
      : path.endsWith('/config/status') ? { ...config, data_store: runOptions.data_store, live_enabled: true, model_configured: true }
      : path.endsWith('/readiness') ? { ...readiness, live_configuration: { ready: true, missing_fields: [] } }
      : path.endsWith('/plan') ? { campaign_id: current.campaign_id, status: 'PLANNED', plan }
      : path.endsWith('/matrix') ? { ...matrix, campaign_id: current.campaign_id, cells: [], counts: Object.fromEntries(Object.keys(matrix.counts).map(key => [key, 0])) }
      : path.endsWith('/recording') ? { recording_version: 'faultlab-development-recording/v1', campaign_id: current.campaign_id, campaign: current, run_plan: { campaign_id: current.campaign_id, status: 'PLANNED', plan }, historical_extra: { first_outcome_retained: true } }
      : fixtureResponse(request.url(), current)
    await route.fulfill({ json })
  })
  await page.goto('/')
  await page.getByLabel('Execution profile', { exact: true }).selectOption('live-v1')
  await page.getByLabel('Reviewed agent', { exact: true }).selectOption('smolagents')
  await page.getByLabel('Campaign mode', { exact: true }).selectOption('learn')
  await expect(page.getByText(/This is not behavioral validation/)).toBeVisible()
  await expect(page.getByText(/Separate reference-context and completion research studies are not supported/)).toBeVisible()
  await expect(page.getByRole('option', { name: 'Compare · accepted policy required' })).toBeDisabled()
  await expect(page.getByLabel('Public development case', { exact: true })).toHaveCount(0)
  await expect(page.getByRole('button', { name: 'Create campaign' })).toBeDisabled()
  expect(writes).toEqual([])
  await page.getByRole('button', { name: 'Register configured agent' }).click()
  await expect(page.getByText('smolagents-fixture', { exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Create campaign' })).toBeEnabled()
  expect(writes).toEqual([{ path: '/api/agent-registrations', body: { expected_store_identity: runOptions.data_store.identity, agent: 'smolagents' } }])
  await page.getByRole('button', { name: 'Create campaign' }).click()
  await expect(page.getByRole('region', { name: 'Saved campaign plan' })).toContainText('smolagents ToolCallingAgent')
  expect(writes[1]).toMatchObject({ path: '/api/planned-campaigns', body: { agent_registration_id: 'smolagents-fixture', mode: 'learn', config_profile_id: 'live-v1' } })
  expect(writes[1].body).not.toHaveProperty('development_case_id')
  current = { ...current, state: 'NO_CHANGE', state_seq: 5 }
  await page.reload()
  const saved = page.getByRole('region', { name: 'Saved campaign plan' })
  await expect(saved).toContainText('saved-native-fixture-model')
  await expect(saved).toContainText('smolagents-fixture')
  await expect(page.getByLabel('Execution profile', { exact: true })).toHaveValue('offline-v1')
  await expect(page.getByRole('button', { name: /Start campaign/ })).toBeDisabled()
  expect(reads.some(path => path.endsWith('/recording'))).toBe(false)
  const downloadEvent = page.waitForEvent('download')
  await page.getByRole('button', { name: 'Download campaign recording' }).click()
  const download = await downloadEvent
  expect(download.suggestedFilename()).toBe(`${current.campaign_id}-development-recording.json`)
  const payload = JSON.parse(await readFile((await download.path())!, 'utf8'))
  expect(payload.campaign.state).toBe('NO_CHANGE')
  expect(payload.run_plan.plan.agent_registration_id).toBe('smolagents-fixture')
  expect(payload.historical_extra).toEqual({ first_outcome_retained: true })
  expect(writes).toHaveLength(2)
  expect(writes.some(item => item.path.endsWith('/start'))).toBe(false)
  expect(errors).toEqual([])
  await page.screenshot({ path: test.info().outputPath('native-no-change-recording.png'), fullPage: true })
})
