import { test, expect } from '@playwright/test'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { config, fixtureResponse } from './fixtures'
import { imported, importConfig, importReadiness, importRequest } from './import-fixtures'

// The exact ZIP bytes of a real dashboard download (offline scripted incident, 16 episodes).
const zip = fileURLToPath(new URL('./fixtures/exported-regression.zip', import.meta.url))

test('a downloaded ZIP is saved only on explicit Save, reviewed as unverified history and reopened after reload without execution', async ({ page }) => {
  const writes: { path: string; type: string | undefined; bytes: number }[] = []; const errors: string[] = []
  const offline = { ...config, data_store: imported.data_store }
  let saved = false
  page.on('pageerror', error => errors.push(error.message))
  await page.route('**/api/**', async route => {
    const request = route.request(); const path = new URL(request.url()).pathname
    if (request.method() !== 'GET') {
      writes.push({ path, type: request.headers()['content-type'], bytes: request.postDataBuffer()?.length ?? 0 })
      saved = true
      await route.fulfill({ status: 201, json: imported }); return
    }
    if (path === '/api/config/status') { await route.fulfill({ json: offline }); return }
    if (path === '/api/bundle-imports') { await route.fulfill({ json: { items: saved ? [imported] : [], next_before: null, has_more: false } }); return }
    if (path === `/api/bundle-imports/${imported.import_id}`) { await route.fulfill({ json: imported }); return }
    if (path === `/api/bundle-imports/${imported.import_id}/executions`) { await route.fulfill({ json: { items: [], next_before: null, has_more: false } }); return }
    await route.fulfill({ json: fixtureResponse(request.url()) })
  })
  await page.goto('/')
  await expect(page.getByText('Backend connected')).toBeVisible()
  await expect(page.getByText('No regression bundles have been imported into this store.')).toBeVisible()
  const input = page.getByLabel(/Regression bundle ZIP/)
  await input.setInputFiles({ name: 'campaign-recording.json', mimeType: 'application/json', buffer: Buffer.from('{"recording_version":"faultlab-development-recording/v1"}') })
  await expect(page.getByText(/Campaign recordings are JSON evidence archives/)).toBeVisible()
  await expect(page.getByRole('button', { name: 'Save imported bundle' })).toBeDisabled()
  await input.setInputFiles(zip)
  await expect(page.getByRole('button', { name: 'Save imported bundle' })).toBeEnabled()
  expect(writes).toEqual([])
  await page.getByRole('button', { name: 'Save imported bundle' }).click()
  const heading = page.getByRole('heading', { name: `Review imported bundle · ${imported.import_id}` })
  await expect(heading).toBeVisible()
  await expect(page.getByText(/Imported historical observations; not verified locally/).first()).toBeVisible()
  await expect(page.getByLabel('Why fresh execution is unavailable')).toContainText('Live execution is off in this workspace')
  await expect(page.getByRole('button', { name: 'Run imported regression in fresh worlds' })).toBeDisabled()
  expect(writes).toEqual([{ path: '/api/bundle-imports', type: 'application/zip', bytes: readFileSync(zip).length }])
  await page.reload()
  await expect(heading).toBeVisible()
  await expect(page.getByRole('button', { name: 'Run imported regression in fresh worlds' })).toBeDisabled()
  expect(writes).toHaveLength(1); expect(errors).toEqual([])
  await page.screenshot({ path: test.info().outputPath('imported-bundle-review.png'), fullPage: true })
})

test('archive mode keeps saved imports readable while upload and fresh execution stay disabled', async ({ page }) => {
  const writes: string[] = []
  const archive = { ...imported, data_store: { ...imported.data_store, read_only: true } }
  await page.addInitScript(key => localStorage.setItem(key, 'import-browser-fixture'), `faultlab:import:${archive.data_store.identity}`)
  await page.route('**/api/**', async route => {
    const request = route.request(); const path = new URL(request.url()).pathname
    if (request.method() !== 'GET') writes.push(path)
    const response = path === '/api/config/status' ? { ...config, data_store: archive.data_store }
      : path === '/api/bundle-imports' ? { items: [archive], next_before: null, has_more: false }
      : path === `/api/bundle-imports/${archive.import_id}` ? archive
      : path === `/api/bundle-imports/${archive.import_id}/executions` ? { items: [], next_before: null, has_more: false }
      : fixtureResponse(request.url())
    await route.fulfill({ json: response })
  })
  await page.goto('/')
  await expect(page.getByRole('heading', { name: `Review imported bundle · ${archive.import_id}` })).toBeVisible()
  await expect(page.getByText(/Read-only archive: saved imports and executions remain available/)).toBeVisible()
  await expect(page.getByLabel(/Regression bundle ZIP/)).toBeDisabled()
  await expect(page.getByRole('button', { name: 'Run imported regression in fresh worlds' })).toBeDisabled()
  expect(writes).toEqual([])
})

test('review shows the bundled task beside a confirmed billable run, a refused upload stays in view with a review open, and phone width keeps outcomes visible', async ({ page }) => {
  const writes: string[] = []; const errors: string[] = []
  page.on('pageerror', error => errors.push(error.message))
  await page.addInitScript(key => localStorage.setItem(key, 'import-browser-fixture'), `faultlab:import:${imported.data_store.identity}`)
  await page.route('**/api/**', async route => {
    const request = route.request(); const path = new URL(request.url()).pathname
    if (request.method() !== 'GET') {
      writes.push(path)
      await route.fulfill({ status: 422, json: { error: { code: 'INVALID_REQUEST', message: 'Import refused; nothing was saved. Contents do not match: the files differ from the checksums and identities recorded inside the bundle, so it may have been edited or be incomplete.' } } }); return
    }
    const response = path === '/api/config/status' ? importConfig
      : path === '/api/readiness' ? importReadiness.data
      : path === '/api/bundle-imports' ? { items: [imported], next_before: null, has_more: false }
      : path === `/api/bundle-imports/${imported.import_id}` ? imported
      : path === `/api/bundle-imports/${imported.import_id}/executions` ? { items: [], next_before: null, has_more: false }
      : fixtureResponse(request.url())
    await route.fulfill({ json: response })
  })
  await page.goto('/')
  await expect(page.getByRole('heading', { name: `Review imported bundle · ${imported.import_id}` })).toBeVisible()
  const task = imported.execution_task!.task_text
  await expect(page.getByText(task, { exact: true }).first()).toBeVisible()
  await expect(page.locator('.bundle-import-panel').getByText(/Supported task/i)).toHaveCount(0)
  await page.getByLabel('Fresh target registration').selectOption(imported.targets[0].agent_registration_id)
  await page.getByRole('button', { name: 'Run imported regression in fresh worlds' }).click()
  const confirm = page.getByRole('group', { name: 'Confirm billable fresh run' })
  await expect(confirm).toContainText(task)
  await expect(confirm).toContainText('Up to 48 billable model requests')
  await confirm.getByRole('button', { name: 'Back to review' }).click()
  expect(writes).toEqual([])
  const input = page.getByLabel(/Regression bundle ZIP/)
  await input.setInputFiles({ name: 'tampered-copy.zip', mimeType: 'application/zip', buffer: Buffer.from('PK tampered bytes') })
  await page.getByRole('button', { name: 'Save imported bundle' }).click()
  const alert = page.locator('.import-upload-error')
  await expect(alert).toContainText('Import refused; nothing was saved.')
  await expect(alert).toBeInViewport()
  await expect(page.getByText(/Select Save imported bundle to upload it/)).toHaveCount(0)
  await expect(page.getByRole('button', { name: 'Save imported bundle' })).toBeDisabled()
  expect(writes).toEqual(['/api/bundle-imports'])
  await page.setViewportSize({ width: 390, height: 900 })
  const outcome = page.locator('.import-trials td[data-label="Recorded outcome"]').first()
  await outcome.scrollIntoViewIfNeeded()
  await expect(outcome).toBeInViewport()
  const box = await page.locator('.import-trials table').first().boundingBox()
  expect(box && box.x + box.width).toBeLessThanOrEqual(390)
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390)
  await page.screenshot({ path: test.info().outputPath('imported-review-narrow.png'), fullPage: false })
  expect(errors).toEqual([])
})

test('cancelling an unadmitted request keeps "nothing ran" on screen after the review rereads its detail', async ({ page }) => {
  const writes: string[] = []; const errors: string[] = []; let detailReads = 0
  const cancelPath = `/api/bundle-imports/${imported.import_id}/requests/${importRequest.request_id}/cancel`
  page.on('pageerror', error => errors.push(error.message))
  await page.addInitScript(([selectedKey, pendingKey, pending]) => { localStorage.setItem(selectedKey, 'import-browser-fixture'); localStorage.setItem(pendingKey, pending) },
    [`faultlab:import:${imported.data_store.identity}`, `faultlab:import-request:${imported.data_store.identity}`, JSON.stringify({ import_id: imported.import_id, request: importRequest })])
  await page.route('**/api/**', async route => {
    const request = route.request(); const path = new URL(request.url()).pathname
    if (request.method() !== 'GET') {
      writes.push(path)
      if (path === cancelPath) { await route.fulfill({ json: { cancelled: true, import_id: imported.import_id, request_id: importRequest.request_id } }); return }
      await route.fulfill({ status: 500, json: { error: { code: 'UNEXPECTED', message: 'Unexpected write' } } }); return
    }
    if (path === `/api/bundle-imports/${imported.import_id}`) detailReads++
    const response = path === '/api/config/status' ? importConfig
      : path === '/api/readiness' ? importReadiness.data
      : path === '/api/bundle-imports' ? { items: [imported], next_before: null, has_more: false }
      : path === `/api/bundle-imports/${imported.import_id}` ? imported
      : path === `/api/bundle-imports/${imported.import_id}/executions` ? { items: [], next_before: null, has_more: false }
      : fixtureResponse(request.url())
    await route.fulfill({ json: response })
  })
  await page.goto('/')
  const unresolved = page.getByRole('region', { name: 'Unresolved imported execution request' })
  await expect(unresolved).toBeVisible()
  const readsBefore = detailReads
  await unresolved.getByRole('button', { name: 'Cancel unadmitted request' }).click()
  const outcome = page.getByRole('status').filter({ hasText: 'Request cancelled before it started; nothing ran.' })
  await expect(outcome).toBeVisible()
  await expect.poll(() => detailReads).toBeGreaterThan(readsBefore)
  await page.waitForTimeout(2000)
  await expect(outcome).toBeVisible()
  await expect(page.getByRole('heading', { name: `Review imported bundle · ${imported.import_id}` })).toBeVisible()
  await expect(unresolved).toHaveCount(0)
  expect(await page.evaluate(key => localStorage.getItem(key), `faultlab:import-request:${imported.data_store.identity}`)).toBeNull()
  expect(writes).toEqual([cancelPath]); expect(errors).toEqual([])
})
