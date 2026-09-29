/**
 * Keeps browser tests on this machine.
 *
 * Installed Google Chrome contacts Google services in the background (component and
 * browser updates, account checks, gstatic/clients2 fetches) even with Playwright's
 * default switches. The dashboard under test is served from the IP literal 127.0.0.1,
 * which never goes through name resolution, and every API call in these tests is
 * answered by page.route. So every host name is mapped to "not found": no request can
 * leave the machine, and nothing the tests need is lost. The remaining switches stop
 * the background features from trying in the first place. (Playwright already passes
 * --disable-background-networking and --disable-component-update; they are repeated
 * here so this list states the whole intent. It adds no --disable-features switch,
 * which would replace Playwright's own list.)
 */
export const HOST_RESOLVER_RULES = 'MAP * ~NOTFOUND, EXCLUDE localhost, EXCLUDE 127.0.0.1'
export const browserIsolationArgs = [
  `--host-resolver-rules=${HOST_RESOLVER_RULES}`,
  '--disable-background-networking',
  '--disable-component-update',
  '--disable-domain-reliability',
  '--disable-client-side-phishing-detection',
  '--safebrowsing-disable-auto-update',
  '--dns-prefetch-disable',
  '--no-pings',
  '--no-first-run',
  '--no-default-browser-check',
]
