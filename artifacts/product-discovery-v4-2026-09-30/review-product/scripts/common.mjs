import { chromium } from '/Users/shree/Desktop/Coreweave_AGI_Hackthon/faultlab/frontend/node_modules/playwright/index.mjs'
// Same isolation as the repo's browser tests (frontend/tests/browser-isolation.ts): every host name maps to NOTFOUND except loopback.
export const args = ['--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE localhost, EXCLUDE 127.0.0.1', '--disable-background-networking',
  '--disable-component-update', '--disable-domain-reliability', '--disable-client-side-phishing-detection', '--safebrowsing-disable-auto-update',
  '--dns-prefetch-disable', '--no-pings', '--no-first-run', '--no-default-browser-check']
export async function open() {
  const browser = await chromium.launch({ headless: true, executablePath: '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', args })
  const context = await browser.newContext({ viewport: { width: 1440, height: 1000 }, acceptDownloads: true })
  const page = await context.newPage()
  const errors = [], offsite = []
  page.on('pageerror', e => errors.push(e.message))
  page.on('request', r => { const u = new URL(r.url()); if (!['127.0.0.1', 'localhost'].includes(u.hostname) && u.protocol !== 'data:' && u.protocol !== 'blob:') offsite.push(r.url()) })
  return { browser, page, errors, offsite }
}
