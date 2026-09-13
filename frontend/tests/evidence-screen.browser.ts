import { test, expect } from '@playwright/test'
import { campaign, config, episode, fixtureResponse } from './fixtures'

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
  expect(writes).toEqual(['/api/campaigns'])
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

test('actual local offline smoke creates fresh world and survives reload', async ({ page }) => {
  test.skip(process.env.FAULTLAB_BROWSER_LOCAL !== '1', 'Explicit local integration mode is opt-in; all other browser tests use labeled fixtures.')
  const writes: string[] = []
  page.on('request', request => { if (request.method() === 'POST') writes.push(request.url()) })
  await page.goto('/')
  await expect(page.getByText('Backend connected')).toBeVisible()
  await expect(page.getByLabel('Execution profile')).toHaveValue('offline-v1')
  await page.getByRole('button', { name: 'Run baseline', exact: true }).click()
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
