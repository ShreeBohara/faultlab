// @vitest-environment jsdom
// Review fixes for history fireability (backend app/lab/fireability.py, fixer, September 30, 2026). Offline fixtures only.
// * MEDIUM-1 / F1: a pick is refused only when EVERY one of its faults targets a REFUSED row; an allowed pick may name a
//   REFUSED target that runs beside a fault on another target (a pending upgrade before the orders status read).
// * F2: under the rule, the saved plan and the setup preview no longer say "no re-plans" or leave the v1 dispatch text
//   unqualified.
// * F4: no "Refused: Refused" text, the REFUSED table row is marked, and the evidence retry rule id is named beside its cap.
import { createElement as h } from 'react'
import { cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { runApi, validateCampaignPlan, validateRunOptions, type DiscoveryDeclaration, type EvidenceRetryDeclaration, type RunOptions } from '../src/runPlans'
import { EXPLORER_SELECTION_V3, decisionText, explorerSelectionText, fireabilityDecision, refusedText, rowStatus, type ExplorerSelectionDeclaration, type ExplorerSelectionPlan, type FireabilityDecision, type FireabilityRow } from '../src/historyFireability'
import { validateExperiments } from '../src/experiments'
import { discoveryBudget } from '../src/components/DiscoveryProtocol'
import { CampaignPlan } from '../src/components/CampaignPlan'
import { RunSetup } from '../src/components/RunSetup'
import { ChallengePanel } from '../src/components/ChallengePanel'
import { campaign, config, fixtureResponse, readiness } from './fixtures'
import { agentHistory, discoveryV3, discoveryV4, discoveryV4Option, evidenceRetryRule, historyReplay, planned, runOptions } from './run-fixtures'

beforeEach(() => { vi.stubGlobal('fetch', vi.fn(async (url: string) => ({ ok: true, json: async () => fixtureResponse(url) }))) })
afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals() })

const offered: ExplorerSelectionDeclaration = { protocol: EXPLORER_SELECTION_V3, applies_to: ['explorer_discovery', 'explorer_challenge'],
  discovery_protocols: ['faultlab-discovery/v3-history', 'faultlab-discovery/v4-history-replay'], basis: 'frozen_agent_history_verified_episodes', target: 'fault_kind_service_tool',
  pick_refused_when: 'every_fault_on_a_refused_target', min_verified_episodes: 3, min_fired_share: '1/2', replans_per_refused_pick: 1, explorer_request_budget_changed: false,
  refused_pick_runs_episodes: false, candidate_dependent: false, challenge_rules_changed: false, rule: 'A pick is refused only if every one of its faults targets a REFUSED target.' }
const row = (kind: FireabilityRow['kind'], service: string, tool: string, verified: number, fired: number): FireabilityRow =>
  ({ kind, target_service: service, target_tool: tool, verified_episodes: verified, fired_episodes: fired, fired_share: `${fired}/${verified}`, status: rowStatus(verified, fired) })
const STATUS_ROW = row('F4', 'orders', 'get_operation_status', 3, 0)
const DELAY_ROW = row('F2', 'orders', 'update_order', 3, 3)
const frozen: ExplorerSelectionPlan = { ...offered, table: { schema_version: 'faultlab-history-fireability/v1', meaning: 'Prior evidence from this plan\'s frozen agent history, not about any candidate.',
  history_summary_hash: 'e'.repeat(64), history_episode_ids_hash: 'd'.repeat(64), record_cutoff: 827, verified_episodes: 6, rows: [DELAY_ROW, STATUS_ROW], refused_targets: [refusedText(STATUS_ROW)] }, table_hash: 'c'.repeat(64) }
const savedV4: DiscoveryDeclaration = { ...discoveryV4, history: agentHistory(), replay: historyReplay() }
const learnPlan = (discovery: DiscoveryDeclaration | null, patch: Record<string, unknown> = {}) => planned(campaign, { mode: 'learn', config_profile_id: 'live-v1', source_mode: 'live', agent: 'smolagents',
  selection: { kind: 'development_search', manifest_hash: runOptions.learn.manifest_hash, search_space: runOptions.learn.search_space }, discovery, ...patch })
const check = (plan: unknown) => validateCampaignPlan({ campaign_id: campaign.campaign_id, status: 'PLANNED', plan }, campaign.campaign_id)
const resource = (plan: unknown) => ({ data: { campaign_id: campaign.campaign_id, status: 'PLANNED' as const, plan: plan as ReturnType<typeof learnPlan> }, error: null, loading: false })

const target = (item: FireabilityRow) => ({ kind: item.kind, target_service: item.target_service, target_tool: item.target_tool, table_row: item, status: item.status })
const STATUS_SPEC = { seed: 1, primitives: [{ kind: 'F4', target_tool: 'get_operation_status', target_service: 'orders', occurrence: 1, parameters: { failure_count: 1 } }] }
const base = { protocol: EXPLORER_SELECTION_V3, purpose: 'challenge', table_hash: 'c'.repeat(64), request_index: 0, slot_request: 1, replan_of: null, pick: 'model' }
const refusedLone = { ...base, status: 'REFUSED_LOW_FIRED_SHARE', targets: [target(STATUS_ROW)], refused_targets: [STATUS_ROW], refused_fault_spec: STATUS_SPEC,
  reason: `Refused before any episode ran: ${refusedText(STATUS_ROW)}. The next request in this challenge is its one re-plan (one of the challenge's 8 Explorer requests).` } as FireabilityDecision
const allowedBeside = { ...base, status: 'ALLOWED', targets: [target(DELAY_ROW), target(STATUS_ROW)], refused_targets: [], refused_fault_spec: null,
  reason: 'Allowed: F4 on get_operation_status (orders) is REFUSED (fired in 0 of 3 verified history episodes). This pick also has a fault on a target that is not REFUSED, so it runs beside it; its pairs still count only if every fault fires in both arms.' } as FireabilityDecision

it('declares that a pick is refused only when every fault targets a REFUSED row, and validates decisions that way', () => {
  const options: RunOptions = { ...runOptions, learn: { ...runOptions.learn, explorer_selection: offered } }
  expect(validateRunOptions(options)).toEqual(options)
  for (const bad of [{ ...offered, pick_refused_when: 'any_fault_on_a_refused_target' }, (({ pick_refused_when: _, ...rest }) => rest)(offered)])
    expect(() => validateRunOptions({ ...options, learn: { ...options.learn, explorer_selection: bad as ExplorerSelectionDeclaration } })).toThrow('Malformed')
  expect(check(learnPlan(savedV4, { explorer_selection: frozen })).status).toBe('PLANNED')
  expect(explorerSelectionText(frozen)).toContain('whose every fault targets')
  expect(fireabilityDecision(refusedLone)).toBe(true)
  expect(fireabilityDecision(allowedBeside)).toBe(true)                                                     // a REFUSED target beside another runs
  expect(fireabilityDecision({ ...allowedBeside, targets: [target(STATUS_ROW)] })).toBe(false)             // every target REFUSED cannot be allowed
  expect(fireabilityDecision({ ...refusedLone, targets: [target(DELAY_ROW), target(STATUS_ROW)] })).toBe(false) // a refusal needs every target REFUSED
  expect(fireabilityDecision({ ...allowedBeside, refused_targets: [STATUS_ROW] })).toBe(false)             // only a refusal lists refused rows
})

it('says what an allowed pick beside a REFUSED target and a refused pick mean, without "Refused: Refused"', () => {
  expect(decisionText(refusedLone)).toBe(refusedLone.reason)
  expect(decisionText(refusedLone)).not.toMatch(/Refused: Refused/)
  expect(decisionText({ ...refusedLone, slot_request: 2, replan_of: 'selection-1' })).toBe(`Re-plan. ${refusedLone.reason}`)
  expect(decisionText(allowedBeside)).toBe(allowedBeside.reason)
  expect(decisionText({ ...allowedBeside, targets: [target(DELAY_ROW)], reason: null })).toMatch(/^Allowed: no fault targets a REFUSED row/)
})

it('under the rule, the saved plan\'s discovery budget and dispatch say that a refused pick gets one re-plan', () => {
  expect(discoveryBudget(savedV4)).toMatch(/no re-plans$/)                                                   // a v4 plan saved before the rule
  expect(discoveryBudget(savedV4, null, true)).not.toMatch(/no re-plans/)
  expect(discoveryBudget(savedV4, null, true)).toMatch(/one re-plan per pick refused by history fireability, inside the same 8 Explorer requests$/)
  render(h(CampaignPlan, { campaign, resource: resource(learnPlan(savedV4, { explorer_selection: frozen })) }))
  expect(screen.queryByText(/no re-plans/)).toBeNull()
  expect(screen.getByText(/^Under this plan's history fireability rule, a valid pick whose every fault targets a REFUSED row/)).toBeTruthy()
  cleanup()
  render(h(CampaignPlan, { campaign, resource: resource(learnPlan(savedV4)) }))
  expect(screen.getByText(/no re-plans$/)).toBeTruthy()
  expect(screen.queryByText(/^Under this plan's history fireability rule/)).toBeNull()
})

it('marks the REFUSED row of the frozen table and names the evidence retry rule beside its cap', () => {
  const v3Retry: EvidenceRetryDeclaration = { ...evidenceRetryRule, protocol: 'faultlab-evidence-retry/v3', automatic_retries_per_campaign: 24, rule: 'At most 3 times per wait and at most 24 times per campaign.' }
  render(h(CampaignPlan, { campaign, resource: resource(learnPlan(savedV4, { explorer_selection: frozen, evidence_retry: v3Retry })) }))
  const table = screen.getByRole('table', { name: 'History fireability table' })
  const refused = within(table).getByText('F4 on get_operation_status (orders)').closest('tr')!
  expect(refused.className).toBe('fireability-refused')
  expect(within(table).getByText('F2 on update_order (orders)').closest('tr')!.className).toBe('')
  expect(screen.getByText(/^Up to 3 per evidence wait and 24 per campaign under rule faultlab-evidence-retry\/v3 /)).toBeTruthy()
  cleanup()
  render(h(CampaignPlan, { campaign, resource: resource(learnPlan(savedV4, { evidence_retry: evidenceRetryRule })) }))
  expect(screen.getByText(/^Up to 3 per evidence wait and 6 per campaign under rule faultlab-evidence-retry\/v2 /)).toBeTruthy()
})

it('the setup preview under v4 with the rule offered does not say "no re-plans"', async () => {
  const options: RunOptions = { ...runOptions, learn: { ...runOptions.learn, explorer_selection: offered, discovery_protocols: [...runOptions.learn.discovery_protocols!, discoveryV4Option] },
    agents: runOptions.agents.map(agent => ({ ...agent, registered: true, registration_id: agent.proposed_registration_id })) }
  vi.spyOn(runApi, 'options').mockResolvedValue(options)
  const liveConfig = { ...config, live_enabled: true, model_configured: true, data_store: runOptions.data_store }
  render(h(RunSetup, { config: liveConfig, replay: false, readiness: { data: { ...readiness, live_configuration: { ready: true, missing_fields: [] } }, error: null, loading: false }, onCampaign: vi.fn() }))
  await screen.findByText('Current plan preview')
  fireEvent.change(screen.getByLabelText('Execution profile'), { target: { value: 'live-v1' } })
  fireEvent.change(screen.getByLabelText('Reviewed agent'), { target: { value: 'smolagents' } })
  fireEvent.change(screen.getByLabelText('Campaign mode'), { target: { value: 'learn' } })
  fireEvent.change(screen.getByLabelText('Discovery protocol'), { target: { value: 'faultlab-discovery/v4-history-replay' } })
  const preview = screen.getByRole('region', { name: 'Current plan preview' })
  expect(within(preview).queryByText(/no re-plans/)).toBeNull()
  expect(within(preview).getByText(/one re-plan per pick refused by history fireability/)).toBeTruthy()
  expect(screen.queryAllByText(/no re-plans/)).toEqual([])
  fireEvent.change(screen.getByLabelText('Discovery protocol'), { target: { value: 'faultlab-discovery/v3-history' } })
  expect(within(screen.getByRole('region', { name: 'Current plan preview' })).getByText(/one re-plan per pick refused by history fireability/)).toBeTruthy()
  expect(discoveryV3.replans_per_slot).toBe(0)
})

it('the challenge panel lists an allowed pick beside a REFUSED target and says which targets never ran alone', () => {
  const rowsOut = [{ ...refusedLone, selection_id: 'selection-1', challenge_id: 'challenge-1', recipe: ['F4 on get_operation_status:orders attempt 1'] },
    { ...allowedBeside, request_index: 1, selection_id: 'selection-2', challenge_id: 'challenge-1', recipe: ['F2 on update_order:orders attempt 1', 'F4 on get_operation_status:orders attempt 1'] }]
  const block = { protocol: EXPLORER_SELECTION_V3, table_hash: 'c'.repeat(64), refused_targets: [refusedText(STATUS_ROW)], picks_checked: 2, picks_refused: 1, decisions: rowsOut, slots_without_request: [] }
  const experiments = validateExperiments({ counterexamples: [], evidence: [], ingestions: [], portability_ids: [], explorer_fireability: block })
  render(h(ChallengePanel, { records: [], onEpisode: vi.fn(), fireability: experiments.explorer_fireability }))
  const region = screen.getByRole('region', { name: 'Challenge picks checked for history fireability' })
  expect(within(region).getByText(/^Explorer request 1: Refused before any episode ran: F4 on get_operation_status/)).toBeTruthy()
  expect(within(region).getByText(/^Explorer request 2: Allowed: F4 on get_operation_status \(orders\) is REFUSED/)).toBeTruthy()
  expect(within(region).getByText(/^Refused on their own in this campaign: F4 on get_operation_status \(orders\)/)).toBeTruthy()
  expect(within(region).getByText(/A pick made only of faults on them never runs/)).toBeTruthy()
})
