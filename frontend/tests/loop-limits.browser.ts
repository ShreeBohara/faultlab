import { readFile } from 'node:fs/promises'
import { test, expect } from '@playwright/test'
import type { Campaign } from '../src/generated/contracts'
// Literal ids (a browser spec imports only types from src/: runtime modules there need the Vite dev server).
const MECHANIC_CONTEXT_V2 = 'faultlab-mechanic-context/v2-bounded'
import { campaign, config, experiments, fixtureResponse, matrix, readiness } from './fixtures'
import { planned, runOptions } from './run-fixtures'

// The Learn-loop rules after live run v2d, as the backend now offers them: every new Learn plan freezes the Mechanic
// request-size rule; the challenge-pick rule is withdrawn before any live run (both reviews, HIGH-1), so it is neither
// offered nor claimed. The setup form and the saved plan show this before Start; the diagnosis panel shows each
// request-size record; the recording carries the plan. Every API response is a fixture; nothing starts and no provider is called.
const mechanicContext = { protocol: MECHANIC_CONTEXT_V2, applies_to: ['mechanic_diagnosis', 'mechanic_proposal'], input_token_limit: 32000, format_repair_reserve_tokens: 4000,
  compaction_target_tokens: 28000, stages: ['IDENTICAL_CLEAN_ROWS', 'ONE_CLEAN_EPISODE_PER_OUTCOME_GROUP', 'NO_CLEAN_EPISODE_ROWS'], always_kept: ['the source episode and its reproduction episodes'],
  when_unfit: 'END_SOURCE_CANDIDATE_SEARCH', unsent_request_uses_candidate_request: false, requests_over_limit_sent: 0, rule: 'When a Mechanic candidate request would exceed the limit, FaultLab compacts only its evidence tables.' }
const compacted = { record_id: 'mechanic-context-1', campaign_id: 'campaign-loop-limits-fixture', protocol: MECHANIC_CONTEXT_V2, request_kind: 'mechanic_proposal', counterexample_id: 'counterexample-1',
  source_episode_id: 'episode-source', outcome: 'COMPACTED', input_token_limit: 32000, compaction_target_tokens: 28000, full_request_tokens: 33223, compacted_request_tokens: 27990, candidate_index: 1,
  blocks: [{ field: 'development_evidence', episodes_total: 16, episodes_in_full: 12, episodes_omitted: 4, omitted_by_stage: {} }, { field: 'challenge_counterexamples[0].evidence', episodes_total: 18, episodes_in_full: 7, episodes_omitted: 11, omitted_by_stage: {} }],
  statement: 'This request was compacted under faultlab-mechanic-context/v2-bounded: in full it was 33,223 input tokens, over the 32,000-token model input limit.', reason: null, provider_dispatch: true }

test('a new Learn plan shows the Mechanic rule before Start, says no challenge-pick rule is declared, and shows its records', async ({ page }) => {
  const writes: { path: string; body: Record<string, unknown> }[] = []
  const errors: string[] = []
  page.on('pageerror', error => errors.push(error.message))
  const current: Campaign = { ...campaign, campaign_id: 'campaign-loop-limits-fixture', config_profile_id: 'live-v1', mode: 'learn', state: 'IDLE', latest_episode_id: null, model: 'fixture-model', task_text: runOptions.task.task_text_default, order_id: 'order-demo', caps: runOptions.caps, usage: { model_calls: 0, http_attempts: 0, cost_dollars: 0 } }
  const plan = planned(current, { agent: 'smolagents', agent_registration_id: 'smolagents-fixture', mode: 'learn', config_profile_id: 'live-v1', source_mode: 'live',
    selection: { kind: 'development_search', manifest_hash: runOptions.learn.manifest_hash, search_space: runOptions.learn.search_space }, discovery: null,
    mechanic_context: mechanicContext as never })
  const options = { ...runOptions, learn: { ...runOptions.learn, mechanic_context: mechanicContext },
    agents: runOptions.agents.map(agent => ({ ...agent, registered: true, registration_id: agent.proposed_registration_id })) }
  await page.route('**/api/**', async route => {
    const request = route.request(); const path = new URL(request.url()).pathname
    if (request.method() === 'POST') { writes.push({ path, body: request.postDataJSON() ?? {} }); await route.fulfill({ json: current }); return }
    const json = path.endsWith('/run-options') ? options
      : path.endsWith('/config/status') ? { ...config, data_store: runOptions.data_store, live_enabled: true, model_configured: true }
      : path.endsWith('/readiness') ? { ...readiness, live_configuration: { ready: true, missing_fields: [] } }
      : path.endsWith('/plan') ? { campaign_id: current.campaign_id, status: 'PLANNED', plan }
      : path.endsWith('/experiments') ? { ...experiments, mechanic_context: [compacted] }
      : path.endsWith('/matrix') ? { ...matrix, campaign_id: current.campaign_id, cells: [], counts: Object.fromEntries(Object.keys(matrix.counts).map(key => [key, 0])) }
      : path.endsWith('/recording') ? { recording_version: 'faultlab-development-recording/v1', campaign_id: current.campaign_id, campaign: current, run_plan: { campaign_id: current.campaign_id, status: 'PLANNED', plan }, mechanic_context_records: [compacted] }
      : fixtureResponse(request.url(), current)
    await route.fulfill({ json })
  })
  await page.goto('/')
  await page.getByLabel('Execution profile', { exact: true }).selectOption('live-v1')
  await page.getByLabel('Reviewed agent', { exact: true }).selectOption('smolagents')
  await page.getByLabel('Campaign mode', { exact: true }).selectOption('learn')
  await expect(page.getByText('Every new Learn plan also freezes this rule:')).toBeVisible()
  await page.getByRole('button', { name: 'Create campaign' }).click()
  const saved = page.getByRole('region', { name: 'Saved campaign plan' })
  await expect(saved).toContainText('Mechanic request size')
  await expect(saved).toContainText('compacted in 3 fixed stages to at most 28,000 (4,000 kept for one format-repair turn)')
  await expect(saved).toContainText('never ERROR')
  await expect(saved).toContainText('Challenge picks')
  await expect(saved).toContainText('Not declared: every valid challenge pick runs its pairs, as before.')
  await expect(page.getByRole('region', { name: "Challenge picks checked against the candidate's reach" })).toHaveCount(0)
  const size = page.getByRole('region', { name: 'Mechanic request size' })
  await expect(size).toContainText('Candidate request 2: 33,223 tokens in full, over the 32,000-token limit; compacted to 27,990 and sent.')
  // Nothing spills out of its panel.
  for (const region of [saved, size]) expect(await region.evaluate(node => node.scrollWidth <= node.clientWidth + 1)).toBe(true)
  const downloadEvent = page.waitForEvent('download')
  await page.getByRole('button', { name: 'Download campaign recording' }).click()
  const payload = JSON.parse(await readFile((await (await downloadEvent).path())!, 'utf8'))
  expect(payload.run_plan.plan.mechanic_context.protocol).toBe(MECHANIC_CONTEXT_V2)
  expect(payload.run_plan.plan.challenge_selection).toBeUndefined()
  expect(writes.map(item => item.path)).toEqual(['/api/planned-campaigns'])
  expect(writes.some(item => item.path.endsWith('/start'))).toBe(false)
  expect(errors).toEqual([])
  await saved.screenshot({ path: test.info().outputPath('loop-limits-saved-plan.png') })
  await size.screenshot({ path: test.info().outputPath('loop-limits-mechanic-request-size.png') })
})
