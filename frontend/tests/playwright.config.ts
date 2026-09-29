import { defineConfig } from '@playwright/test'
import { existsSync } from 'node:fs'
import { browserIsolationArgs } from './browser-isolation'
import { localUrl } from '../local-ports'
const chrome = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
// FAULTLAB_DASHBOARD_PORT (default 5173) selects the dashboard these tests start and open. A dashboard
// already listening there is reused only when FAULTLAB_BROWSER_REUSE_DASHBOARD=1 asks for it; otherwise
// the run stops with Playwright's "already used" error instead of testing another checkout's dashboard.
const dashboard = localUrl('FAULTLAB_DASHBOARD_PORT')
export default defineConfig({
  testDir: '.', testMatch: '**/*.browser.ts', outputDir: '.results', timeout: 30000, fullyParallel: false, workers: 1,
  use: { baseURL: dashboard, headless: true, viewport: { width: 1440, height: 1000 }, launchOptions: { ...(existsSync(chrome) ? { executablePath: chrome } : {}), args: browserIsolationArgs }, trace: 'retain-on-failure' },
  webServer: { command: 'npm run dev', url: dashboard, reuseExistingServer: process.env.FAULTLAB_BROWSER_REUSE_DASHBOARD === '1', timeout: 30000 },
})
