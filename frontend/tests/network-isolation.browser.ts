import { test, expect } from '@playwright/test'
import { readFileSync } from 'node:fs'
import { HOST_RESOLVER_RULES } from './browser-isolation'
import { fixtureResponse } from './fixtures'

// A *.localhost name resolves to this machine without any DNS query, so the probe can
// never leave the machine: with the isolation rule it fails at name resolution,
// without it Chrome would resolve it locally and fail to connect instead.
const PROBE = 'http://faultlab-isolation-probe.localhost:47913/probe'
const IPV6_REACHABILITY_CHECK = '[2001:4860:4860::8888]:443'
const loopback = (address: string) => /^(127\.|\[::1\]|::1)/.test(address)

type NetLog = { constants: { logEventTypes: Record<string, number> }; events: { type: number; params?: Record<string, unknown> }[] }
function readNetLog(path: string): NetLog {
  const text = readFileSync(path, 'utf8').trim()
  // Chrome finishes the file on a normal close; tolerate a missing tail anyway.
  return JSON.parse(text.endsWith('}') ? text : `${text.replace(/,\s*$/, '')}]}`)
}

test('the test browser resolves no outside host name and opens no outside connection', async ({ playwright, baseURL }, testInfo) => {
  const launch = testInfo.project.use.launchOptions ?? {}
  expect(launch.args).toContain(`--host-resolver-rules=${HOST_RESOLVER_RULES}`)
  const netlog = testInfo.outputPath('chrome-netlog.json')
  const browser = await playwright.chromium.launch({ ...launch, args: [...(launch.args ?? []), `--log-net-log=${netlog}`] })
  const failures: string[] = []
  try {
    const page = await browser.newPage()
    page.on('requestfailed', request => { if (request.url() === PROBE) failures.push(request.failure()?.errorText ?? 'unknown') })
    await page.route('**/api/**', route => route.fulfill({ json: fixtureResponse(route.request().url()) }))
    await page.goto(`${baseURL}/`)
    await expect(page.getByText('Backend connected')).toBeVisible()
    await page.evaluate(url => fetch(url).then(() => 'reached', () => 'refused'), PROBE)
    await expect.poll(() => failures).toEqual(['net::ERR_NAME_NOT_RESOLVED'])
    // Give the browser's background services time to try their usual requests.
    await page.waitForTimeout(5000)
  } finally { await browser.close() }
  const log = readNetLog(netlog)
  const names = Object.fromEntries(Object.entries(log.constants.logEventTypes).map(([name, id]) => [id, name]))
  const outsideConnections: string[] = []; const unmappedNames: string[] = []; const refusedHosts = new Set<string>()
  for (const event of log.events) {
    const name = names[event.type]; const params = event.params ?? {}
    if (name === 'URL_REQUEST_START_JOB' && typeof params.url === 'string') {
      const host = new URL(params.url).hostname
      if (!/^(localhost|127\.0\.0\.1)$/.test(host)) refusedHosts.add(host)
    }
    // Every address a TCP or UDP (QUIC) connection was attempted to. The one exception is
    // Chrome's IPv6 reachability check: a UDP connect() to a fixed address that sends no packet.
    if (name === 'TCP_CONNECT' || name === 'TCP_CONNECT_ATTEMPT' || name === 'UDP_CONNECT' && params.address !== IPV6_REACHABILITY_CHECK) {
      for (const address of [params.address, ...(Array.isArray(params.address_list) ? params.address_list : [])]) {
        if (typeof address === 'string' && !loopback(address)) outsideConnections.push(`${name} ${address}`)
      }
    }
    // With the rule, every name except localhost reaches the resolver already mapped to ~notfound.
    if (name === 'HOST_RESOLVER_MANAGER_REQUEST' && typeof params.host === 'string') {
      const host = params.host.replace(/^[a-z]+:\/\//, '').replace(/:\d+$/, '')
      if (!['~notfound', 'localhost', '127.0.0.1'].includes(host)) unmappedNames.push(host)
    }
  }
  testInfo.annotations.push({ type: 'background hosts refused', description: [...refusedHosts].sort().join(', ') || 'none attempted' })
  expect(unmappedNames).toEqual([])
  expect(outsideConnections).toEqual([])
})
