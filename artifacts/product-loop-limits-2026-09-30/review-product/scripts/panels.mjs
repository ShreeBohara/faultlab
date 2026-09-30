// Open a campaign in the dashboard and capture the saved plan's two rule fields, the challenge panel and the diagnosis panel.
import { open, OUT, PW } from './common.mjs'
import { writeFileSync, readFileSync } from 'node:fs'
const [port, cid, tag, download] = process.argv.slice(2)
const { browser, page, errors, offsite } = await open()
const log = { tag, cid }
await page.goto(`http://127.0.0.1:${port}/`)
await page.waitForTimeout(1500)
await page.getByLabel('Saved campaigns', { exact: true }).selectOption(cid)
await page.getByRole('button', { name: 'Open selected campaign' }).click()
await page.waitForTimeout(3500)
const saved = page.getByRole('region', { name: 'Saved campaign plan' })
if (await saved.count()) {
  const t = await saved.innerText()
  const grab = (name) => { const i = t.indexOf(name); return i < 0 ? null : t.slice(i, i + 420).split('\n').slice(0, 2).join(' | ') }
  log.plan = { mechanic: grab('MECHANIC REQUEST SIZE'), picks: grab('CHALLENGE PICKS') }
  const f = saved.locator('dt:has-text("Mechanic request size")').first()
  if (await f.count()) { await f.scrollIntoViewIfNeeded(); await saved.screenshot({ path: `${OUT}/${tag}-saved-plan.png` }) }
}
const challenge = page.locator('section.panel').filter({ has: page.getByRole('heading', { name: /Adversarial challenge/ }) }).first()
log.challenge = await challenge.innerText()
const reach = challenge.getByRole('region', { name: "Challenge picks checked against the candidate's reach" })
log.reachListPresent = (await reach.count()) > 0
if (log.reachListPresent) { await reach.scrollIntoViewIfNeeded(); await reach.screenshot({ path: `${OUT}/${tag}-challenge-reach.png` }) }
const diag = page.locator('section.panel').filter({ has: page.getByRole('heading', { name: /Tested diagnosis/ }) }).first()
const size = diag.getByRole('region', { name: 'Mechanic request size' })
log.mechanicListPresent = (await size.count()) > 0
if (log.mechanicListPresent) { log.mechanicList = await size.innerText(); await size.scrollIntoViewIfNeeded(); await size.screenshot({ path: `${OUT}/${tag}-mechanic-size.png` }) }
if (download) {
  const dl = page.waitForEvent('download')
  await page.getByRole('button', { name: 'Download campaign recording' }).click()
  const rec = JSON.parse(readFileSync(await (await dl).path(), 'utf8'))
  log.recording = { mechanic_context_records: rec.mechanic_context_records?.map(r => [r.outcome, r.stage, r.request_kind, r.full_request_tokens, r.compacted_request_tokens]) ?? 'ABSENT',
                    challenge_selection_rule: rec.challenge_selection_rule ? { protocol: rec.challenge_selection_rule.protocol, refused: rec.challenge_selection_rule.refused_selection_ids.length } : 'ABSENT',
                    selection_reach: rec.selections.filter(s => s.challenge).map(s => s.challenge_reach?.status ?? 'ABSENT') }
}
// Phone width: the new lists must not force horizontal scroll
await page.setViewportSize({ width: 390, height: 900 })
await page.waitForTimeout(600)
log.phoneHorizontalOverflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1)
if (log.reachListPresent) { await reach.scrollIntoViewIfNeeded(); await reach.screenshot({ path: `${OUT}/${tag}-challenge-reach-phone.png` }) }
if (log.mechanicListPresent) { await size.scrollIntoViewIfNeeded(); await size.screenshot({ path: `${OUT}/${tag}-mechanic-size-phone.png` }) }
log.errors = errors; log.offsite = offsite
writeFileSync(`${PW}/${tag}-panels.json`, JSON.stringify(log, null, 2))
console.log(JSON.stringify({ ...log, challenge: log.challenge.slice(0, 2500) }, null, 2))
await browser.close()
