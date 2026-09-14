// Capture the dashboard for docs and posts. Requires the simulator, backend and frontend to be running
// (see README quick start) and Google Chrome. Only GET requests are allowed; any write attempt fails the capture.
//   node scripts/capture-dashboard.mjs [campaign-id] [dark|light] [output-dir]
import { fileURLToPath } from 'node:url'
import { dirname, resolve } from 'node:path'
import { mkdir } from 'node:fs/promises'
const root = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const { chromium, expect } = await import(resolve(root, 'frontend/node_modules/@playwright/test/index.mjs'))
const [campaign = 'campaign-44085f54a24144b78252d8eea211ebb8', theme = 'dark', outDir = resolve(root, 'docs/assets')] = process.argv.slice(2)
const chrome = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
const browser = await chromium.launch({ headless: true, ...(process.platform === 'darwin' ? { executablePath: chrome } : {}) })
try {
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 }, deviceScaleFactor: 2 })
  const errors = [], writes = []
  page.on('pageerror', e => errors.push(e.message))
  await page.route('**/api/**', route => { if (route.request().method() !== 'GET') { writes.push(route.request().url()); return route.abort() } return route.continue() })
  await page.addInitScript(([id, t]) => { localStorage.setItem('faultlab:campaign', id); localStorage.setItem('faultlab:theme', t) }, [campaign, theme])
  await page.goto('http://127.0.0.1:5173/', { waitUntil: 'domcontentloaded' })
  const summary = page.locator('.summary-panel')
  await expect(page.getByText('Backend connected', { exact: true })).toBeVisible()
  await expect(summary).toContainText('Trials recorded')
  await expect(summary.locator('.stat-strip strong').first()).not.toHaveText('—')
  await expect(page.locator('[role="alert"]')).toHaveCount(0)
  await expect(page.locator('html')).toHaveAttribute('data-theme', theme)
  await page.evaluate(() => document.fonts.ready)
  await page.waitForTimeout(800)
  await mkdir(outDir, { recursive: true })
  const box = await summary.boundingBox()
  const pad = 24
  const summaryPath = resolve(outDir, `faultlab-run-summary-${theme}.png`)
  await page.screenshot({ path: summaryPath, fullPage: true, clip: { x: box.x - pad, y: box.y - pad, width: box.width + pad * 2, height: box.height + pad * 2 } })
  await page.setViewportSize({ width: 1440, height: Math.ceil(box.y + box.height + 36) })
  await page.evaluate(() => scrollTo(0, 0))
  await page.waitForTimeout(300)
  const topPath = resolve(outDir, `faultlab-dashboard-${theme}.png`)
  await page.screenshot({ path: topPath })
  if (errors.length || writes.length) throw new Error(`Capture rejected. Page errors: ${JSON.stringify(errors)}. Write attempts: ${JSON.stringify(writes)}`)
  console.log(JSON.stringify({ campaign, theme, files: [topPath, summaryPath], summary: (await summary.innerText()).replaceAll('\n', ' | ') }, null, 2))
} finally { await browser.close() }
