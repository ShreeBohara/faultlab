// @vitest-environment jsdom
// Product review: the dashboard's own validators and panels on REAL backend responses of a rule-v2 Learn campaign whose
// first discovery request lost two attempts (HTTP 503, then a timeout) and was answered on retry 2 (../ui-fixtures/,
// written by checks/test_r1_backoff_operator.py). No network: fetch is stubbed with the saved JSON.
import { createElement as h } from 'react'
import { readFileSync } from 'node:fs'
import { cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import { validateCampaignPlan, validateRunOptions } from '../../../../frontend/src/runPlans'
import { validateSearchAttempts } from '../../../../frontend/src/searchAttempts'
import { CampaignPlan } from '../../../../frontend/src/components/CampaignPlan'
import { SearchAttemptsPanel } from '../../../../frontend/src/components/SearchAttemptsPanel'

const FIXTURES = process.cwd() + "/../ui-fixtures/"
const fixture = (name: string) => JSON.parse(readFileSync(FIXTURES + name + ".json", "utf8"))
afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals() })

it('real rule-v2 responses pass the dashboard validators and render the retries', async () => {
  const campaign = fixture('campaign'), plan = fixture('plan'), attempts = fixture('search-attempts'), options = fixture('run-options')
  expect(validateRunOptions(options).learn.transport_retry?.protocol).toBe('faultlab-transport-retry/v2-lab-backoff')
  const saved = validateCampaignPlan(plan, campaign.campaign_id)
  expect(saved.status).toBe('PLANNED')
  const rows = validateSearchAttempts(attempts, campaign.campaign_id)
  const retried = rows.filter(row => row.transport_retries?.length)
  expect(retried).toHaveLength(1)
  render(h(CampaignPlan, { campaign, resource: { data: saved, error: null, loading: false } }))
  const region = screen.getByRole('region', { name: 'Saved campaign plan' })
  const retriesText = within(region).getByText('Model transport retries').nextElementSibling!.textContent
  console.log('PLAN TEXT:', retriesText)
  console.log('DISCOVERY TEXT:', within(region).getByText(/Explorer requests/).textContent)
  cleanup()
  vi.stubGlobal('fetch', vi.fn(async () => ({ ok: true, json: async () => attempts })))
  render(h(SearchAttemptsPanel, { campaignId: campaign.campaign_id, onEpisode: vi.fn() }))
  const summary = await screen.findByText(new RegExp(`^Selection ${retried[0].selection_index + 1}`))
  fireEvent.click(summary)
  const notes = screen.getAllByText(/Transport retry \d of at most 3/).map(note => note.textContent)
  console.log('PANEL NOTES:', JSON.stringify(notes, null, 1))
  expect(notes).toHaveLength(2)
  expect(notes[0]).toContain('(HTTP 503), so after waiting 5 s')
  expect(notes[1]).toContain('(request timeout), so after waiting 20 s')
})
