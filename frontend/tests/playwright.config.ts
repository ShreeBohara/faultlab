import { defineConfig } from '@playwright/test'
import { existsSync } from 'node:fs'
const chrome = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
export default defineConfig({
  testDir: '.', testMatch: '**/*.browser.ts', outputDir: '.results', timeout: 30000, fullyParallel: false, workers: 1,
  use: { baseURL: 'http://127.0.0.1:5173', headless: true, viewport: { width: 1440, height: 1000 }, launchOptions: existsSync(chrome) ? { executablePath: chrome } : {}, trace: 'retain-on-failure' },
  webServer: { command: 'npm run dev', url: 'http://127.0.0.1:5173', reuseExistingServer: true, timeout: 30000 },
})
