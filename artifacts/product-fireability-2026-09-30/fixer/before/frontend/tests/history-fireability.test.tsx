// @vitest-environment jsdom
// History fireability (backend app/lab/fireability.py, faultlab-explorer-selection/v3-history-fireability) and automatic
// evidence retry v3: the validators, the saved plan (rule and frozen table), the Learn setup form, the fault-search panel
// (each discovery pick's check, a slot left without a request) and the challenge panel. Offline fixtures only; nothing starts.
import { createElement as h } from 'react'
import { cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { runApi, validateCampaignPlan, validateRunOptions, type DiscoveryDeclaration, type EvidenceRetryDeclaration, type RunOptions } from '../src/runPlans'
import { EXPLORER_SELECTION_V3, explorerSelectionText, refusedText, rowStatus, validateExplorerFireability, type ExplorerSelectionDeclaration, type ExplorerSelectionPlan, type FireabilityRow } from '../src/historyFireability'
import { validateSearchAttempts } from '../src/searchAttempts'
import { validateExperiments } from '../src/experiments'
import { CampaignPlan } from '../src/components/CampaignPlan'
import { RunSetup } from '../src/components/RunSetup'
import { SearchAttemptsPanel } from '../src/components/SearchAttemptsPanel'
import { ChallengePanel } from '../src/components/ChallengePanel'
import { campaign, config, fixtureResponse, hash, readiness } from './fixtures'
import { agentHistory, discoveryV1, discoveryV3, discoveryV3Precheck, discoveryV4, discoveryV4Option, evidenceRetryRule, historyReplay, planned, runOptions } from './run-fixtures'

beforeEach(() => { vi.stubGlobal('fetch', vi.fn(async (url: string) => ({ ok: true, json: async () => fixtureResponse(url) }))) })
afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals() })

/** As the backend offers it (app/lab/fireability.py declaration()). */
const offered: ExplorerSelectionDeclaration = { protocol: EXPLORER_SELECTION_V3, applies_to: ['explorer_discovery', 'explorer_challenge'],
  discovery_protocols: ['faultlab-discovery/v3-history', 'faultlab-discovery/v4-history-replay'], basis: 'frozen_agent_history_verified_episodes', target: 'fault_kind_service_tool',
  min_verified_episodes: 3, min_fired_share: '1/2', replans_per_refused_pick: 1, explorer_request_budget_changed: false, refused_pick_runs_episodes: false,
  candidate_dependent: false, challenge_rules_changed: false, rule: 'Before any episode runs, FaultLab checks every fault of each Explorer pick against this plan\'s frozen history fireability table.' }
const row = (kind: FireabilityRow['kind'], service: string, tool: string, verified: number, fired: number): FireabilityRow =>
  ({ kind, target_service: service, target_tool: tool, verified_episodes: verified, fired_episodes: fired, fired_share: `${fired}/${verified}`, status: rowStatus(verified, fired) })
const STATUS_ROW = row('F4', 'orders', 'get_operation_status', 3, 0)
const rows = [row('F2', 'orders', 'update_order', 3, 3), STATUS_ROW]
/** Frozen from run-fixtures agentHistory(): its summary hash, episode ids hash, cutoff and 6 verified episodes. */
const frozen: ExplorerSelectionPlan = { ...offered, table: { schema_version: 'faultlab-history-fireability/v1', meaning: 'Prior evidence from this plan\'s frozen agent history, not about any candidate.',
  history_summary_hash: 'e'.repeat(64), history_episode_ids_hash: 'd'.repeat(64), record_cutoff: 827, verified_episodes: 6, rows, refused_targets: [refusedText(STATUS_ROW)] }, table_hash: 'c'.repeat(64) }
const savedV3: DiscoveryDeclaration = { ...discoveryV3, history: agentHistory() }
const savedV4: DiscoveryDeclaration = { ...discoveryV4, history: agentHistory(), replay: historyReplay() }
const learnPlan = (discovery: DiscoveryDeclaration | null, patch: Record<string, unknown> = {}) => planned(campaign, { mode: 'learn', config_profile_id: 'live-v1', source_mode: 'live', agent: 'smolagents',
  selection: { kind: 'development_search', manifest_hash: runOptions.learn.manifest_hash, search_space: runOptions.learn.search_space }, discovery, ...patch })
const check = (plan: unknown) => validateCampaignPlan({ campaign_id: campaign.campaign_id, status: 'PLANNED', plan }, campaign.campaign_id)
const resource = (plan: unknown) => ({ data: { campaign_id: campaign.campaign_id, status: 'PLANNED' as const, plan: plan as ReturnType<typeof learnPlan> }, error: null, loading: false })
const evidenceRetryV3: EvidenceRetryDeclaration = { ...evidenceRetryRule, protocol: 'faultlab-evidence-retry/v3', automatic_retries_per_campaign: 24,
  rule: 'While a Learn campaign waits for verified Weave evidence, FaultLab retries the evidence by itself at most 3 times per wait and at most 24 times per campaign.' }

it('accepts the offered rule without a table and a saved one only with a table bound to the plan\'s own frozen history', () => {
  const options: RunOptions = { ...runOptions, learn: { ...runOptions.learn, explorer_selection: offered } }
  expect(validateRunOptions(options)).toEqual(options)
  for (const bad of [frozen, { ...offered, candidate_dependent: true }, { ...offered, min_fired_share: '2/3' }, { ...offered, discovery_protocols: ['faultlab-discovery/v3-history'] }, { ...offered, rule: '' }])
    expect(() => validateRunOptions({ ...options, learn: { ...options.learn, explorer_selection: bad as ExplorerSelectionDeclaration } })).toThrow('Malformed')
  expect(check(learnPlan(savedV3, { explorer_selection: frozen })).status).toBe('PLANNED')
  expect(check(learnPlan(savedV4, { explorer_selection: frozen })).status).toBe('PLANNED')
  expect(check(learnPlan(savedV3)).status).toBe('PLANNED')                                                    // a v3 plan saved before the rule
  const table = frozen.table
  for (const [discovery, rule] of [
    [savedV3, offered],                                                                                       // a saved plan carries the table
    [savedV3, { ...frozen, table: { ...table, history_summary_hash: 'f'.repeat(64) } }],                     // frozen from another history
    [savedV3, { ...frozen, table: { ...table, record_cutoff: 900 } }],
    [savedV3, { ...frozen, table: { ...table, verified_episodes: 7 } }],
    [savedV3, { ...frozen, table: { ...table, rows: [rows[0], { ...STATUS_ROW, status: 'ALLOWED' }] } }],     // status must follow the counts
    // ...even when the refused list agrees with the wrong status (only the status-versus-counts check can see this one)
    [savedV3, { ...frozen, table: { ...table, rows: [{ ...rows[0], status: 'REFUSED' }, STATUS_ROW], refused_targets: [refusedText({ ...rows[0], status: 'REFUSED' }), refusedText(STATUS_ROW)] } }],
    [savedV3, { ...frozen, table: { ...table, rows: [rows[0], { ...STATUS_ROW, fired_share: '1/3' }] } }],
    [savedV3, { ...frozen, table: { ...table, refused_targets: [] } }],                                       // every refused row is listed
    [savedV3, { ...frozen, table: { ...table, rows: [STATUS_ROW, rows[0]] } }],                               // sorted, as the backend sorts
    [{ ...discoveryV1 }, frozen], [{ ...discoveryV3Precheck, history: agentHistory() }, frozen], [null, frozen],
  ] as [DiscoveryDeclaration | null, unknown][]) expect(() => check(learnPlan(discovery, { explorer_selection: rule }))).toThrow('Malformed')
  expect(() => check(planned(campaign, { explorer_selection: frozen }))).toThrow('Malformed')                // a baseline plan never declares it
  expect(rowStatus(2, 0)).toBe('ALLOWED_FEWER_THAN_3'); expect(rowStatus(4, 2)).toBe('ALLOWED'); expect(rowStatus(4, 1)).toBe('REFUSED')
})

it('shows the rule and the frozen table in a saved v3 or v4 plan, says plainly when an older one has none, and says nothing for v1', () => {
  render(h(CampaignPlan, { campaign, resource: resource(learnPlan(savedV4, { explorer_selection: frozen })) }))
  const region = screen.getByRole('region', { name: 'History fireability' })
  expect(within(region).getByText(explorerSelectionText(frozen))).toBeTruthy()
  expect(explorerSelectionText(frozen)).toContain('never from a candidate')
  const table = within(region).getByRole('table', { name: 'History fireability table' })
  expect(within(table).getByText('F4 on get_operation_status (orders)').closest('tr')?.textContent).toBe('F4 on get_operation_status (orders)30/3Refused')
  expect(within(region).getByText(/6 verified history episodes .* 1 target refused/)).toBeTruthy()
  expect(within(region).getByText(`${EXPLORER_SELECTION_V3}: ${frozen.rule}`)).toBeTruthy()
  cleanup()
  render(h(CampaignPlan, { campaign, resource: resource(learnPlan(savedV3)) }))
  expect(screen.getByText(/^Not declared: this plan was saved before the history fireability rule\./)).toBeTruthy()
  cleanup()
  render(h(CampaignPlan, { campaign, resource: resource(learnPlan(discoveryV1)) }))
  expect(screen.queryByRole('region', { name: 'History fireability' })).toBeNull()
})

it('accepts evidence retry v3 (24 per campaign) in a Learn plan, keeps v2 (6), and shows the plan\'s own cap', () => {
  expect(check(learnPlan(discoveryV1, { evidence_retry: evidenceRetryV3 })).status).toBe('PLANNED')
  expect(check(learnPlan(discoveryV1, { evidence_retry: evidenceRetryRule })).status).toBe('PLANNED')
  for (const bad of [{ ...evidenceRetryV3, automatic_retries_per_campaign: 6 }, { ...evidenceRetryRule, automatic_retries_per_campaign: 24 }, { ...evidenceRetryV3, protocol: 'faultlab-evidence-retry/v4' }])
    expect(() => check(learnPlan(discoveryV1, { evidence_retry: bad }))).toThrow('Malformed')
  render(h(CampaignPlan, { campaign, resource: resource(learnPlan(discoveryV1, { evidence_retry: evidenceRetryV3 })) }))
  expect(screen.getByText(/^Up to 3 per evidence wait and 24 per campaign/)).toBeTruthy()
  cleanup()
  render(h(CampaignPlan, { campaign, resource: resource(learnPlan(discoveryV1, { evidence_retry: evidenceRetryRule })) }))
  expect(screen.getByText(/^Up to 3 per evidence wait and 6 per campaign/)).toBeTruthy()
})

it('offers the rule in the Learn setup only for v3 · agent history and v4', async () => {
  const options: RunOptions = { ...runOptions, learn: { ...runOptions.learn, explorer_selection: offered, discovery_protocols: [...runOptions.learn.discovery_protocols!, discoveryV4Option] },
    agents: runOptions.agents.map(agent => ({ ...agent, registered: true, registration_id: agent.proposed_registration_id })) }
  vi.spyOn(runApi, 'options').mockResolvedValue(options)
  const liveConfig = { ...config, live_enabled: true, model_configured: true, data_store: runOptions.data_store }
  render(h(RunSetup, { config: liveConfig, replay: false, readiness: { data: { ...readiness, live_configuration: { ready: true, missing_fields: [] } }, error: null, loading: false }, onCampaign: vi.fn() }))
  await screen.findByText('Current plan preview')
  fireEvent.change(screen.getByLabelText('Execution profile'), { target: { value: 'live-v1' } })
  fireEvent.change(screen.getByLabelText('Reviewed agent'), { target: { value: 'smolagents' } })
  fireEvent.change(screen.getByLabelText('Campaign mode'), { target: { value: 'learn' } })
  expect(screen.queryByText('History fireability')).toBeNull()                                                  // v1 (default)
  for (const [protocol, shown] of [['faultlab-discovery/v3-history', true], ['faultlab-discovery/v4-history-replay', true], ['faultlab-discovery/v1', false]] as const) {
    fireEvent.change(screen.getByLabelText('Discovery protocol'), { target: { value: protocol } })
    expect(!!screen.queryByText('History fireability')).toBe(shown)
  }
})

const spec = (primitive: Record<string, unknown>) => ({ seed: 1, primitives: [primitive] })
const STATUS = { kind: 'F4', target_tool: 'get_operation_status', target_service: 'orders', occurrence: 1, parameters: { failure_count: 1 } }
const DELAYED = { kind: 'F2', target_tool: 'update_order', target_service: 'orders', occurrence: 1, parameters: { completion_delay_ticks: 9, terminal_status: 'SUCCEEDED', failure_code: null } }
const decision = (status: string, patch: Record<string, unknown> = {}) => ({ protocol: EXPLORER_SELECTION_V3, purpose: 'discovery', table_hash: 'c'.repeat(64), request_index: 0, slot_request: 1, replan_of: null, pick: 'model',
  status, targets: status === 'REFUSED_LOW_FIRED_SHARE' ? [{ kind: 'F4', target_service: 'orders', target_tool: 'get_operation_status', table_row: STATUS_ROW, status: 'REFUSED' }]
    : status === 'ALLOWED' ? [{ kind: 'F2', target_service: 'orders', target_tool: 'update_order', table_row: rows[0], status: 'ALLOWED' }] : [],
  refused_targets: status === 'REFUSED_LOW_FIRED_SHARE' ? [STATUS_ROW] : [], refused_fault_spec: status === 'REFUSED_LOW_FIRED_SHARE' ? spec(STATUS) : null,
  reason: status === 'REFUSED_LOW_FIRED_SHARE' ? `Refused before any episode ran: ${refusedText(STATUS_ROW)}. The next request is this slot's one re-plan.` : null, ...patch })
const attempt = (ref: string, status: string, check: Record<string, unknown>, output: Record<string, unknown>) => ({ selection_ref: ref, campaign_id: campaign.campaign_id, selection_index: 0, configuration_hash: hash, policy_hash: hash,
  raw_response: 'Model text', usage: { model_calls: 1, input_tokens: 100, output_tokens: 20, cost_dollars: null }, provenance: 'model', error: null, transport_retries: [],
  output: { fault_spec: output, hypothesis: 'h' }, selected_output: status === 'SELECTED' ? { fault_spec: output, hypothesis: 'h' } : null,
  search_decision: { status, schedule_hash: hash, reason: status === 'SKIPPED_UNFIREABLE' ? 'HISTORY_FIRED_SHARE_BELOW_HALF' : null, prior_selection_refs: [], prior_episode_refs: [],
    ...(status === 'SKIPPED_UNFIREABLE' ? { refused_fault_spec: output } : {}) }, matches_history_row: null, fireability: check })
const refusedAttempt = attempt('selection-refused', 'SKIPPED_UNFIREABLE', decision('REFUSED_LOW_FIRED_SHARE'), spec(STATUS))
const replanAttempt = attempt('selection-replan', 'SELECTED', decision('ALLOWED', { slot_request: 2, replan_of: 'selection-refused' }), spec(DELAYED))
const unrequested = { record_id: 'explorer-slot-1', campaign_id: campaign.campaign_id, protocol: EXPLORER_SELECTION_V3, selection_index: 7, status: 'NO_EXPLORER_REQUEST', explorer_requests_used: 8, explorer_requests_max: 8, replans_after_refusals: 1,
  reason: 'This discovery slot sent no Explorer request and ran no episode: the plan declares at most 8 discovery Explorer requests, and all 8 were used, including re-plans after picks the history fireability rule refused.' }

it('validates and shows a refused discovery pick, its re-plan and a slot left without a request', async () => {
  const listed = validateSearchAttempts([refusedAttempt, replanAttempt], campaign.campaign_id)
  expect(listed[0].fireability?.status).toBe('REFUSED_LOW_FIRED_SHARE')
  for (const bad of [
    { ...refusedAttempt, fireability: undefined },                                                              // a refusal by the rule needs its check
    { ...refusedAttempt, fireability: decision('ALLOWED') },                                                   // the check and the decision disagree
    { ...refusedAttempt, fireability: { ...decision('REFUSED_LOW_FIRED_SHARE'), refused_targets: [] } },
    { ...replanAttempt, fireability: decision('ALLOWED', { slot_request: 2 }) },                               // a re-plan names what it re-plans
    { ...replanAttempt, fireability: decision('ALLOWED', { request_index: 3 }) },                              // another slot's check
  ]) expect(() => validateSearchAttempts([bad], campaign.campaign_id)).toThrow('Malformed')
  vi.stubGlobal('fetch', vi.fn(async () => ({ ok: true, json: async () => [refusedAttempt, replanAttempt] })))
  const summary = validateExplorerFireability({ protocol: EXPLORER_SELECTION_V3, table_hash: 'c'.repeat(64), refused_targets: [refusedText(STATUS_ROW)], picks_checked: 2, picks_refused: 1,
    decisions: [{ ...decision('REFUSED_LOW_FIRED_SHARE'), selection_id: 'selection-refused', challenge_id: null, recipe: ['F4 in words'] }, { ...decision('ALLOWED', { slot_request: 2, replan_of: 'selection-refused' }), selection_id: 'selection-replan', challenge_id: null, recipe: ['F2 in words'] }],
    slots_without_request: [unrequested] })
  render(h(SearchAttemptsPanel, { campaignId: campaign.campaign_id, onEpisode: vi.fn(), fireability: summary }))
  expect(await screen.findByText('Selection 1 · Refused by the history fireability rule · no Actor trial')).toBeTruthy()
  expect(screen.getByText('Selection 1 · re-plan · Selected for execution')).toBeTruthy()
  expect(screen.getByText('Refused by history fireability').previousSibling?.textContent).toBe('1')
  expect(screen.getAllByText(/fired in 0 of 3 verified history episodes/).length).toBeGreaterThan(0)
  expect(screen.getByText(/^Selection 8 · no Explorer request, no Actor trial: This discovery slot sent no Explorer request/)).toBeTruthy()
})

it('validates the experiments block and lists each challenge pick\'s check in the challenge panel', () => {
  const challengeDecision = { ...decision('REFUSED_LOW_FIRED_SHARE', { purpose: 'challenge', reason: `Refused before any episode ran: ${refusedText(STATUS_ROW)}. The next request in this challenge is its one re-plan (one of the challenge's 8 Explorer requests).` }),
    selection_id: 'selection-challenge-1', challenge_id: 'challenge-1', recipe: ['F4 on get_operation_status:orders attempt 1: transient 503 before the request is accepted'] }
  const block = { protocol: EXPLORER_SELECTION_V3, table_hash: 'c'.repeat(64), refused_targets: [refusedText(STATUS_ROW)], picks_checked: 1, picks_refused: 1, decisions: [challengeDecision], slots_without_request: [] }
  const experiments = validateExperiments({ counterexamples: [], evidence: [], ingestions: [], portability_ids: [], explorer_fireability: block })
  expect(experiments.explorer_fireability?.picks_refused).toBe(1)
  expect('explorer_fireability' in validateExperiments({ counterexamples: [], evidence: [], ingestions: [], portability_ids: [] })).toBe(false)
  for (const bad of [{ ...block, picks_refused: 0 }, { ...block, table_hash: 'x' }, { ...block, decisions: [{ ...challengeDecision, table_hash: 'b'.repeat(64) }] },
    { ...block, slots_without_request: [{ ...unrequested, explorer_requests_used: 7 }] }])
    expect(() => validateExperiments({ counterexamples: [], evidence: [], ingestions: [], portability_ids: [], explorer_fireability: bad })).toThrow('Malformed')
  render(h(ChallengePanel, { records: [], onEpisode: vi.fn(), fireability: experiments.explorer_fireability }))
  const region = screen.getByRole('region', { name: 'Challenge picks checked for history fireability' })
  expect(within(region).getByText(/^1 challenge pick checked, 1 refused before any pair ran\./)).toBeTruthy()
  expect(within(region).getByText(/^Explorer request 1: Refused: Refused before any episode ran: F4 on get_operation_status \(orders\): fired in 0 of 3/)).toBeTruthy()
  expect(within(region).getByText('Refused: seldom fired')).toBeTruthy()
})
