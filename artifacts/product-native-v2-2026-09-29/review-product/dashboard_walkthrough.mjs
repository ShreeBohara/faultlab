// Reviewer walk-through of the REAL dashboard (vite dev server) against the reviewer's offline scripted backend
// (serve_offline_backend.py). No page.route mocks: every /api call reaches the product backend through vite's proxy.
// Run with cwd faultlab/frontend so '@playwright/test' resolves from its node_modules:
//   DASHBOARD=http://127.0.0.1:54091 OUT=<review-product dir> node --input-type=module < <this file>
import { chromium } from '@playwright/test'
import { existsSync, writeFileSync } from 'node:fs'

const base = process.env.DASHBOARD
const out = process.env.OUT
const chrome = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
const args = ['--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE localhost, EXCLUDE 127.0.0.1', '--disable-background-networking',
  '--disable-component-update', '--disable-domain-reliability', '--disable-client-side-phishing-detection',
  '--safebrowsing-disable-auto-update', '--dns-prefetch-disable', '--no-pings', '--no-first-run', '--no-default-browser-check']
const browser = await chromium.launch({ headless: true, args, ...(existsSync(chrome) ? { executablePath: chrome } : {}) })
const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } })
const log = { steps: [], pageErrors: [], consoleErrors: [], requests: [], nonLocalRequests: [] }
page.on('pageerror', e => log.pageErrors.push(e.message))
page.on('console', m => { if (m.type() === 'error') log.consoleErrors.push(m.text()) })
page.on('request', r => { const u = new URL(r.url()); if (!['127.0.0.1', 'localhost'].includes(u.hostname)) log.nonLocalRequests.push(r.url()); if (u.pathname.startsWith('/api/') && r.method() !== 'GET') log.requests.push(`${r.method()} ${u.pathname}`) })
const step = (name, detail) => { log.steps.push({ name, ...(detail ?? {}) }); console.log('STEP', name, detail ? JSON.stringify(detail).slice(0, 300) : '') }
const shot = async name => page.screenshot({ path: `${out}/dashboard-${name}.png`, fullPage: true })
const setup = () => page.getByRole('region', { name: 'New campaign setup' })
const saved = () => page.getByRole('region', { name: 'Saved campaign plan' })
const V2 = 'smolagents ToolCallingAgent - adapter v2 (short evidence labels, strict final report turn)'

try {
  await page.goto(base + '/')
  await setup().getByRole('button', { name: 'Create campaign' }).waitFor()
  await setup().getByLabel('Execution profile').selectOption('live-v1')
  const agentSelect = setup().getByLabel('Reviewed agent')
  const agentOptions = await agentSelect.locator('option').allTextContents()
  await agentSelect.selectOption('smolagents-v2')
  const v2Note = await setup().getByText(/Adapter v2 is a separate agent from v1/).isVisible()
  const registrationBefore = await setup().getByText('Not registered for this setup').isVisible()
  step('choose v2', { agentOptions, v2Note, registrationBefore })
  await shot('01-v2-chosen-not-registered')
  await setup().getByRole('button', { name: 'Register configured agent' }).click()
  await setup().getByText('Registration saved. No agent execution or provider call was made.').waitFor()
  await setup().getByText(/smolagents-1\.26\.0-adapter-v2-/).waitFor()
  const registrationId = (await setup().getByText(/smolagents-1\.26\.0-adapter-v2-/).first().textContent()).trim()
  step('registered v2', { registrationId })
  // Baseline, dev-6 (two transient confirmation failures), then Create and Start.
  await setup().getByLabel('Campaign mode').selectOption('baseline')
  await setup().getByLabel('Public development case').selectOption('dev-6')
  const preview = await page.getByRole('region', { name: 'Current plan preview' }).textContent()
  step('baseline preview', { previewNamesV2: preview.includes(V2) })
  await setup().getByRole('button', { name: 'Create campaign' }).click()
  await saved().waitFor()
  await saved().getByText(V2).first().waitFor()
  const savedText = await saved().textContent()
  step('baseline plan saved', { names_v2: savedText.includes(V2), registration: savedText.includes(registrationId), case: savedText.includes('dev-6') })
  await shot('02-v2-baseline-plan-saved')
  await page.getByRole('button', { name: /Start campaign/ }).click()
  await page.locator('.history-selection').getByText('Completed').waitFor({ timeout: 60000 })
  await page.waitForTimeout(1500)
  const body = await page.locator('body').innerText()
  step('baseline completed', { completed: /Completed/.test(body), safeUnresolved: /SAFE_UNRESOLVED|Safe unresolved|safe unresolved/i.test(body) })
  await shot('03-v2-baseline-completed')
  writeFileSync(`${out}/dashboard-03-body.txt`, body)

  // Learn with discovery v3 history for v2; the pre-check protocols are disabled for this agent.
  await setup().getByLabel('Campaign mode').selectOption('learn')
  const discovery = setup().getByLabel('Discovery protocol')
  const protocolStates = await discovery.locator('option').evaluateAll(options => options.map(o => [o.value, o.disabled]))
  await discovery.selectOption('faultlab-discovery/v3-history')
  step('learn v3 chosen', { protocolStates })
  await setup().getByRole('button', { name: 'Create campaign' }).click()
  await page.waitForTimeout(1500)
  await saved().getByText(/v3/).first().waitFor()
  const learnText = await saved().textContent()
  step('learn plan saved', { names_v2: learnText.includes(V2), history_block: /history/i.test(learnText), no_prior: /No prior history|NO_PRIOR_HISTORY/i.test(learnText) })
  await shot('04-v2-learn-v3-plan-saved')
  await page.getByRole('button', { name: /Start campaign/ }).click()
  await page.getByRole('button', { name: 'Stop', exact: true }).click({ timeout: 10000 })
  await page.locator('.history-selection').getByText(/Stopped|Completed|No change/).waitFor({ timeout: 120000 })
  await page.waitForTimeout(1500)
  const after = await page.locator('.history-selection').textContent()
  step('learn started then stopped', { state: after.trim().slice(0, 200) })
  await shot('05-v2-learn-stopped')
} catch (error) {
  step('FAILED', { error: String(error).slice(0, 800) })
  await shot('99-failure')
  process.exitCode = 1
} finally {
  writeFileSync(`${out}/dashboard-walkthrough.out.json`, JSON.stringify(log, null, 1))
  await browser.close()
}
