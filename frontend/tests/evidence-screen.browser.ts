import { test, expect } from '@playwright/test'
import { bundle, campaign, config, episode, fixtureResponse, matrix, readiness, registration, regressionCase, verifiedExperiments } from './fixtures'

test('saved evidence reload, exact trial drilldown and playback produce only reads', async ({ page }) => {
  const writes: string[] = []; const errors: string[] = []
  page.on('pageerror', e => errors.push(e.message))
  await page.addInitScript(id => localStorage.setItem('faultlab:campaign', id), campaign.campaign_id)
  await page.route('**/api/**', async route => { if (route.request().method() !== 'GET') writes.push(route.request().url()); await route.fulfill({ json: fixtureResponse(route.request().url()) }) })
  await page.goto('/')
  await expect(page.getByText('Backend connected')).toBeVisible()
  await expect(page.getByText('episode started', { exact: true })).toHaveCount(1)
  await page.getByRole('button', { name: `${episode.episode_id} ↗` }).click()
  await expect(page.getByText(episode.world_id, { exact: true })).toBeVisible()
  await page.getByRole('button', { name: 'Recorded playback', exact: true }).click()
  await expect(page.getByText('Recorded playback · read only')).toBeVisible()
  await expect(page.getByRole('button', { name: /Start campaign/ })).toBeDisabled()
  await page.reload()
  await expect(page.getByText('episode started', { exact: true })).toHaveCount(1)
  expect(writes).toEqual([]); expect(errors).toEqual([])
  await page.screenshot({ path: test.info().outputPath('recorded-evidence.png'), fullPage: true })
})

test('creation is separate from Start and duplicate clicks cannot enqueue extra starts', async ({ page }) => {
  const writes: string[] = []; let current = { ...campaign, state: 'IDLE', state_seq: 0, latest_episode_id: null }; let active: string | null = null
  await page.route('**/api/**', async route => {
    const request = route.request(); const path = new URL(request.url()).pathname
    if (request.method() === 'POST') {
      writes.push(path)
      if (path.endsWith('/start')) { current = { ...current, state: 'RUNNING', state_seq: 1 }; active = campaign.campaign_id }
      await route.fulfill({ json: current }); return
    }
    await route.fulfill({ json: path.endsWith('/config/status') ? { ...config, active_campaign_id: active } : fixtureResponse(request.url(), current as typeof campaign) })
  })
  await page.goto('/')
  await expect(page.getByRole('button', { name: 'Create campaign' })).toBeEnabled()
  await page.getByRole('button', { name: 'Create campaign' }).click()
  await expect(page.getByRole('button', { name: /Start campaign/ })).toBeEnabled()
  expect(writes).toEqual(['/api/planned-campaigns'])
  await page.getByRole('button', { name: /Start campaign/ }).dblclick({ force: true })
  await expect(page.getByRole('button', { name: /Start campaign/ })).toBeDisabled()
  expect(writes.filter(p => p.endsWith('/start'))).toHaveLength(1)
})

test('malformed response stays visible and keyboard access works at narrow width', async ({ page }) => {
  await page.route('**/api/**', async route => { await route.fulfill({ json: route.request().url().endsWith('/health') ? { status: 'ok', service: 'wrong-service' } : fixtureResponse(route.request().url()) }) })
  await page.setViewportSize({ width: 390, height: 844 }); await page.goto('/')
  await expect(page.getByText('Backend unavailable')).toBeVisible()
  await expect(page.getByText(/Malformed health response/)).toBeVisible()
  await page.keyboard.press('Tab'); await expect(page.getByRole('link', { name: 'Skip to evidence' })).toBeFocused()
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
})

test('history is read-only and Stop follows only the selected active campaign', async ({ page }) => {
  const writes: string[] = []; let stopped = false
  const activeId = 'campaign-running'
  const running = { ...campaign, campaign_id: activeId, state: 'RUNNING' as const, latest_episode_id: null }
  await page.addInitScript(id => localStorage.setItem('faultlab:campaign', id), campaign.campaign_id)
  await page.route('**/api/**', async route => {
    const request = route.request(); const path = new URL(request.url()).pathname
    const selected = path.includes(activeId) ? { ...running, ...(stopped ? { state: 'STOPPED' as const, state_seq: 4, stop_requested: true } : {}) } : campaign
    if (request.method() === 'POST') { writes.push(path); stopped = true; await route.fulfill({ json: { ...running, state: 'STOPPED', state_seq: 4, stop_requested: true } }); return }
    const response = path === '/api/campaigns' ? { campaigns: [running, campaign], next_before: null, has_more: false }
      : path.endsWith('/config/status') ? { ...config, active_campaign_id: activeId }
      : path.endsWith('/matrix') ? { ...matrix, campaign_id: selected.campaign_id, cells: selected.campaign_id === activeId ? [] : matrix.cells }
      : fixtureResponse(request.url(), selected)
    await route.fulfill({ json: response })
  })
  await page.goto('/')
  await expect(page.getByText(/2 saved campaigns loaded/)).toBeVisible()
  await expect(page.getByRole('button', { name: 'Stop', exact: true })).toBeDisabled()
  await page.getByLabel('Saved campaigns', { exact: true }).selectOption(campaign.campaign_id)
  await page.getByRole('button', { name: 'Open selected campaign' }).click()
  expect(writes).toEqual([])
  await page.getByRole('button', { name: 'Open active campaign' }).click()
  await expect(page.getByLabel('Open saved campaign', { exact: true })).toHaveValue(activeId)
  await expect(page.getByRole('button', { name: 'Stop', exact: true })).toBeEnabled()
  await page.getByRole('button', { name: 'Stop', exact: true }).click()
  await expect(page.getByText('Stop acknowledged by the next successful poll.')).toBeVisible()
  expect(writes).toEqual([`/api/campaigns/${activeId}/stop`])
  await page.screenshot({ path: test.info().outputPath('history-and-scoped-stop.png'), fullPage: true })
})

test('readiness distinguishes backend health from simulator access and rechecks without writes', async ({ page }) => {
  const writes: string[] = []; let checks = 0
  const readyCampaign = { ...campaign, state: 'IDLE' as const }
  await page.addInitScript(id => localStorage.setItem('faultlab:campaign', id), campaign.campaign_id)
  await page.route('**/api/**', async route => {
    if (route.request().method() !== 'GET') writes.push(route.request().url())
    if (route.request().url().endsWith('/readiness')) {
      checks++
      await route.fulfill({ json: checks === 1 ? { ...readiness, ready: false, simulator: { ready: false, code: 'SIMULATOR_UNAVAILABLE', message: 'Start the local simulator before executing a campaign.' } } : readiness }); return
    }
    await route.fulfill({ json: fixtureResponse(route.request().url(), readyCampaign) })
  })
  await page.goto('/')
  await expect(page.getByText('Backend connected')).toBeVisible()
  await expect(page.getByText('Simulator unavailable', { exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: /Start campaign/ })).toBeDisabled()
  await page.getByRole('button', { name: 'Check run readiness' }).click()
  await expect(page.getByText('Simulator ready', { exact: true })).toBeVisible()
  await expect(page.getByText('Live configuration incomplete')).toBeVisible()
  await expect(page.getByRole('button', { name: /Start campaign/ })).toBeEnabled()
  expect(checks).toBe(2); expect(writes).toEqual([])
  await page.screenshot({ path: test.info().outputPath('offline-readiness.png'), fullPage: true })
})

test('saved regression execution history opens interrupted evidence without typing IDs or dispatching work', async ({ page }) => {
  const writes: string[] = []; const historyReads: string[] = []
  const saved = { execution_id: 'execution-browser-saved', bundle_id: bundle.bundle_id, manifest_hash: bundle.manifest_hash, registration_id: 'agent-fixture', profile_id: bundle.execution_profile_id, mode: 'FRESH_SANDBOX', explicit_action: true, policy_hash: bundle.policy_hash, configuration_hash: bundle.configuration_hash, declared_budget: bundle.caps, usage: { model_calls: 0, http_attempts: 4 }, status: 'INCOMPLETE', episode_ids: [episode.episode_id], world_ids: [episode.world_id], stop_reason: 'Interrupted by process restart; saved effects were retained.' }
  await page.addInitScript(id => localStorage.setItem('faultlab:campaign', id), campaign.campaign_id)
  await page.route('**/api/**', async route => {
    const request = route.request(); const path = new URL(request.url()).pathname
    if (request.method() !== 'GET') writes.push(path)
    if (path.endsWith('/executions')) { historyReads.push(request.url()); await route.fulfill({ json: { executions: [saved], next_before: null, has_more: false } }); return }
    const response = path.endsWith('/regressions') ? [regressionCase]
      : path.endsWith('/bundle') ? bundle
      : path === `/api/regression-executions/${saved.execution_id}` ? saved
      : fixtureResponse(request.url())
    await route.fulfill({ json: response })
  })
  await page.goto('/')
  await expect(page.getByText('Backend connected')).toBeVisible()
  expect(historyReads).toEqual([])
  await page.getByLabel('Saved regression').selectOption(regressionCase.regression_id)
  await page.getByRole('button', { name: 'Inspect saved bundle' }).click()
  await expect(page.getByText(/1 saved executions loaded/)).toBeVisible()
  await page.getByLabel('Saved executions', { exact: true }).selectOption(saved.execution_id)
  await expect(page.getByRole('heading', { name: `Saved execution · ${saved.execution_id}` })).toBeVisible()
  await expect(page.getByText(saved.stop_reason, { exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: /Run fresh regression/ })).toBeDisabled()
  expect(historyReads).toHaveLength(1); expect(writes).toEqual([])
  await page.screenshot({ path: test.info().outputPath('saved-regression-history.png'), fullPage: true })
})

test('actual local offline smoke creates fresh world and survives reload', async ({ page }) => {
  test.skip(process.env.FAULTLAB_BROWSER_LOCAL !== '1', 'Explicit local integration mode is opt-in; all other browser tests use labeled fixtures.')
  const writes: string[] = []
  page.on('request', request => { if (request.method() === 'POST') writes.push(request.url()) })
  await page.goto('/')
  await expect(page.getByText('Backend connected')).toBeVisible()
  await expect(page.getByLabel('Execution profile')).toHaveValue('offline-v1')
  await page.getByRole('button', { name: 'Create campaign', exact: true }).click()
  await page.getByRole('button', { name: /Start campaign/ }).click()
  await expect(page.getByText(/Start accepted/)).toBeVisible()
  await expect(page.locator('.matrix-panel tbody tr')).toHaveCount(1, { timeout: 20000 })
  await expect(page.locator('.matrix-panel tbody')).toContainText('Offline reference smoke')
  const id = await page.evaluate(() => localStorage.getItem('faultlab:campaign'))
  await page.reload()
  await expect(page.getByLabel('Open saved campaign')).toHaveValue(id!)
  const count = writes.length
  await page.getByRole('button', { name: 'Recorded playback', exact: true }).click()
  await expect(page.getByText('Recorded playback · read only')).toBeVisible()
  await page.waitForTimeout(1000)
  expect(writes.length).toBe(count)
  expect(writes).toHaveLength(2)
  await page.screenshot({ path: test.info().outputPath('actual-offline-evidence.png'), fullPage: true })
})

test('an absent remembered campaign pauses once and recovers through explicit retry or saved history', async ({ page }) => {
  const missing = 'campaign-from-another-store'
  const missingReads: string[] = []; const writes: string[] = []; const errors: string[] = []
  page.on('pageerror', error => errors.push(error.message))
  await page.clock.install()
  await page.addInitScript(id => localStorage.setItem('faultlab:campaign', id), missing)
  await page.route('**/api/**', async route => {
    const request = route.request()
    if (request.method() !== 'GET') writes.push(request.url())
    if (request.url().includes(missing)) {
      missingReads.push(new URL(request.url()).pathname)
      await route.fulfill({ status: 404, json: { error: { message: 'Unknown record' } } }); return
    }
    await route.fulfill({ json: fixtureResponse(request.url()) })
  })
  await page.goto('/')
  await expect(page.getByRole('heading', { name: 'Saved campaign unavailable' })).toBeVisible()
  await expect(page.getByRole('alert')).toHaveCount(1)
  await expect(page.getByText(/Retrying with backoff/)).toHaveCount(0)
  await page.clock.fastForward(30000)
  expect(missingReads).toEqual([`/api/campaigns/${missing}`])
  await expect(page.getByLabel('Open saved campaign', { exact: true })).toHaveValue(missing)
  await page.getByRole('button', { name: 'Retry saved campaign' }).click()
  await expect(page.getByRole('heading', { name: 'Saved campaign unavailable' })).toBeVisible()
  expect(missingReads).toHaveLength(2)
  await page.screenshot({ path: test.info().outputPath('missing-campaign-recovery.png'), fullPage: true })
  await page.getByLabel('Saved campaigns', { exact: true }).selectOption(campaign.campaign_id)
  await page.getByRole('button', { name: 'Open selected campaign' }).click()
  await expect(page.getByText('episode started', { exact: true })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Saved campaign unavailable' })).toHaveCount(0)
  expect(writes).toEqual([]); expect(errors).toEqual([])
})

test('archive browsing shows its location, verified source evidence and disabled mutations while downloads and playback work', async ({ page }) => {
  const writes: string[] = []; const errors: string[] = []
  const archivePath = '/local/historical-evidence/lab.sqlite3'
  const current = { ...campaign, state: 'IDLE' as const }
  const savedSources = { ...verifiedExperiments, evidence: Array.from({ length: 7 }, (_, index) => ({ ...verifiedExperiments.evidence[0], episode_id: `episode-verified-${index}` })) }
  page.on('pageerror', error => errors.push(error.message))
  await page.addInitScript(id => localStorage.setItem('faultlab:campaign', id), campaign.campaign_id)
  await page.route('**/api/**', async route => {
    const request = route.request(); const path = new URL(request.url()).pathname
    if (request.method() !== 'GET') writes.push(path)
    if (path.endsWith('/download')) { await route.fulfill({ contentType: 'application/zip', body: Buffer.from('PK\u0005\u0006' + '\u0000'.repeat(18)) }); return }
    const response = path.endsWith('/config/status') ? { ...config, data_store: { identity: 'archive-fixture', path: archivePath, read_only: true } }
      : path.endsWith('/readiness') ? { ...readiness, ready: false, simulator: { ready: false, code: 'READ_ONLY_ARCHIVE', message: 'This archive cannot start work.' } }
      : path.endsWith('/experiments') ? savedSources
      : path.endsWith('/regressions') ? [regressionCase]
      : path.endsWith('/agent-registrations') ? [registration]
      : path.endsWith('/bundle') ? bundle
      : fixtureResponse(request.url(), current)
    await route.fulfill({ json: response })
  })
  await page.goto('/')
  await expect(page.getByRole('heading', { name: 'Read-only archive' })).toBeVisible()
  await expect(page.getByText(archivePath, { exact: true })).toBeVisible()
  await expect(page.getByText('Fresh execution disabled', { exact: true })).toBeVisible()
  await expect(page.getByText('7 verified source episodes', { exact: true })).toBeVisible()
  await expect(page.getByText(/Campaign telemetry:/)).toContainText('Locally recorded')
  for (const name of ['Create campaign', /Start campaign/, 'Stop', 'Reset future world', 'Retry evidence sync']) {
    await expect(page.getByRole('button', { name, exact: typeof name === 'string' })).toBeDisabled()
  }
  await page.getByLabel('Saved regression').selectOption(regressionCase.regression_id)
  await page.getByRole('button', { name: 'Inspect saved bundle' }).click()
  await expect(page.getByText('No saved executions for this bundle.')).toBeVisible()
  await page.getByLabel('Reviewed agent').selectOption(registration.registration_id)
  await page.getByLabel('Immutable policy').selectOption('policy-v0')
  await expect(page.getByRole('button', { name: /Run fresh regression/ })).toBeDisabled()
  const download = page.waitForEvent('download')
  await page.getByRole('button', { name: 'Download regression' }).click()
  expect((await download).suggestedFilename()).toMatch(/\.zip$/)
  await page.getByText('Capture observed Aria evidence', { exact: true }).click()
  await expect(page.getByRole('button', { name: 'Save evidence capture' })).toBeDisabled()
  await page.getByRole('button', { name: 'Recorded playback', exact: true }).click()
  await expect(page.getByText('Recorded playback · read only')).toBeVisible()
  expect(writes).toEqual([]); expect(errors).toEqual([])
  await page.screenshot({ path: test.info().outputPath('archive-and-verified-sources.png'), fullPage: true })
})
