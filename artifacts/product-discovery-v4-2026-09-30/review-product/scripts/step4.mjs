import { open } from './common.mjs'
import { writeFileSync } from 'node:fs'
import { execFileSync } from 'node:child_process'
const OUT = '/Users/shree/Desktop/Coreweave_AGI_Hackthon/faultlab/artifacts/product-discovery-v4-2026-09-30/review-product/screenshots'
const { browser, page, errors, offsite } = await open()
const log = []
await page.goto('http://127.0.0.1:18432/')
await page.waitForTimeout(1500)
await page.getByLabel('Execution profile', { exact: true }).selectOption('live-v1')
await page.waitForTimeout(500)
await page.getByLabel('Reviewed agent', { exact: true }).selectOption('smolagents-v2')
await page.getByLabel('Campaign mode', { exact: true }).selectOption('learn')
await page.getByLabel('Discovery protocol', { exact: true }).selectOption('faultlab-discovery/v4-history-replay')
await page.getByRole('button', { name: 'Create campaign' }).click()
await page.waitForTimeout(2500)
const campaignId = (await page.locator('.run-receipt code').first().innerText()).trim()
log.push({ step: 'stale plan created', campaignId })
// Change one counted record (a baseline B0 episode's evidence) directly in the scratch store.
log.push({ step: 'mutate', out: execFileSync('/Users/shree/Desktop/Coreweave_AGI_Hackthon/faultlab/.venv/bin/python', ['/Users/shree/FaultLab_Scratch/review-product-v4/mutate_evidence.py']).toString() })
await page.getByRole('button', { name: 'Check against the store now' }).click()
await page.waitForTimeout(1500)
log.push({ step: 'history check', status: await page.getByRole('region', { name: 'Frozen agent history' }).locator('[role=status]').allInnerTexts() })
await page.getByRole('region', { name: 'Frozen agent history' }).screenshot({ path: OUT + '/07-v4-stale-plan-check-changed.png' })
await page.getByRole('button', { name: /Start campaign/ }).click()
await page.waitForTimeout(2000)
log.push({ step: 'after start', alerts: await page.locator('[role=alert]').allInnerTexts(), status: await page.locator('[role=status]').allInnerTexts() })
await page.locator('.run-receipt').screenshot({ path: OUT + '/08-v4-stale-plan-start-refused.png' })
log.push({ errors, offsite })
writeFileSync('/Users/shree/FaultLab_Scratch/review-product-v4/pw/step4.json', JSON.stringify(log, null, 2))
console.log(JSON.stringify(log, null, 2))
await browser.close()
