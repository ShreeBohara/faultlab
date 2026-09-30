// @vitest-environment jsdom
// Discovery protocol v4 (history replay, regression-first discovery): the chooser, the saved-plan replay list, the
// replay labels in the fault-search and source panels, and the validators. Offline fixtures only; nothing starts.
import { createElement as h } from 'react'
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { api } from '../src/api'
import { REPLAY_PROTOCOL, runApi, validateCampaignPlan, validateRunOptions, type DiscoveryDeclaration, type DiscoveryOption, type HistoryReplay, type RunOptions } from '../src/runPlans'
import { RunSetup } from '../src/components/RunSetup'
import { CampaignPlan } from '../src/components/CampaignPlan'
import { NO_HISTORY_IS_STILL_V3, NO_HISTORY_IS_STILL_V4, REPLAY_AT_PLAN_TIME, REPLAY_CLAIM } from '../src/components/DiscoveryProtocol'
import { SearchAttemptsPanel } from '../src/components/SearchAttemptsPanel'
import { CounterexamplePanel } from '../src/components/CounterexamplePanel'
import { validateSearchAttempts } from '../src/searchAttempts'
import { validateExperiments } from '../src/experiments'
import { campaign, config, fixtureResponse, hash, readiness } from './fixtures'
import { agentHistory, discoveryV1, discoveryV3, discoveryV4, discoveryV4Option, historyReplay, planned, REPLAY_RULE, runOptions } from './run-fixtures'

beforeEach(() => { vi.stubGlobal('fetch', vi.fn(async (url: string) => ({ ok: true, json: async () => fixtureResponse(url) }))) })
afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals() })

const DEV5 = { kind: 'F2' as const, target_tool: 'update_order' as const, target_service: 'orders' as const, occurrence: 1, parameters: { completion_delay_ticks: 2, terminal_status: 'FAILED' as const, failure_code: 'UPGRADE_REJECTED' as const } }
const RULE = REPLAY_RULE
const v4Option = discoveryV4Option
const withV4: RunOptions = { ...runOptions, learn: { ...runOptions.learn, discovery_protocols: [...runOptions.learn.discovery_protocols!, v4Option] } }
const registered: RunOptions = { ...withV4, agents: withV4.agents.map(agent => ({ ...agent, registered: true, registration_id: agent.proposed_registration_id })) }
const liveConfig = { ...config, live_enabled: true, model_configured: true, data_store: runOptions.data_store }
const liveReadiness = { data: { ...readiness, live_configuration: { ready: true, missing_fields: [] } }, error: null, loading: false }

const replayList = historyReplay
const savedV4 = (available = true): DiscoveryDeclaration => ({ ...discoveryV4, history: agentHistory(available), replay: replayList(available) })
const learnPlan = (discovery: DiscoveryDeclaration | null, agent: 'reference' | 'smolagents' = 'smolagents') => planned(campaign, {
  mode: 'learn', config_profile_id: 'live-v1', source_mode: 'live', agent,
  selection: { kind: 'development_search', manifest_hash: runOptions.learn.manifest_hash, search_space: runOptions.learn.search_space }, discovery })
const check = (plan: ReturnType<typeof learnPlan>) => validateCampaignPlan({ campaign_id: campaign.campaign_id, status: 'PLANNED', plan }, campaign.campaign_id)
const options = (v4: DiscoveryOption) => ({ ...runOptions, learn: { ...runOptions.learn, discovery_protocols: [...runOptions.learn.discovery_protocols!, v4] } })

it('accepts the v4 option with history and replay list still unfrozen, and rejects an over-reaching one', () => {
  expect(validateRunOptions(withV4)).toEqual(withV4)
  const [v1] = runOptions.learn.discovery_protocols!
  for (const v4 of [
    { ...v4Option, default: true },                                                              // never the default...
    { ...v4Option, declaration: { ...discoveryV4, replay: replayList() } },                     // options never carry a frozen list
    { ...v4Option, declaration: { ...discoveryV4, replay: undefined } },                        // ...but say it has none yet
    { ...v4Option, declaration: { ...discoveryV4, explorer_requests_max: 16 } },                // v3-history's budget
    { ...v4Option, declaration: { ...discoveryV4, history: undefined } },                       // v4 carries the v3 history
  ] as DiscoveryOption[]) expect(() => validateRunOptions(v4.default ? { ...options(v4), learn: { ...options(v4).learn, discovery_protocols: [{ ...v1, default: false }, ...options(v4).learn.discovery_protocols!.slice(1)] } } : options(v4))).toThrow('Malformed')
  expect(() => validateRunOptions(options({ ...v4Option, declaration: { ...discoveryV4 } }))).not.toThrow()
  // Older protocols never carry the replay field.
  expect(() => validateRunOptions({ ...runOptions, learn: { ...runOptions.learn, discovery_protocols: [{ ...v1, declaration: { ...discoveryV1, replay: null } }, ...runOptions.learn.discovery_protocols!.slice(1)] } })).toThrow('Malformed')
})

it('validates a saved v4 plan only with its frozen history and a consistent replay list', () => {
  for (const discovery of [savedV4(), savedV4(false)]) expect(check(learnPlan(discovery)).status).toBe('PLANNED')
  const good = replayList(), row = good.rows[0]
  for (const replay of [
    undefined,                                                                                   // not frozen
    { ...good, history_summary_hash: 'd'.repeat(64) },                                           // frozen from another history
    { ...good, status: 'EMPTY' },                                                                // status disagrees with its rows
    { ...good, rows: [{ ...row, violations: 1, violation_share: '1/3', outcomes: { VIOLATION: 1, COMPLETED: 2 } }] },   // share below 2/3
    { ...good, rows: [{ ...row, every_fault_fired: 2 }] },                                       // a fault did not fire
    { ...good, rows: [{ ...row, verified_episodes: 1, violations: 1, violation_share: '1/1', every_fault_fired: 1, outcomes: { VIOLATION: 1 } }] },  // fewer than 2 verified
    { ...good, rows: [{ ...row, history_row: 1 }] },                                             // row 1 is dev-1, not dev-5
    { ...good, rows: [{ ...row, replay: 2 }] },                                                  // replay numbers start at 1
    { ...good, rows: [{ ...row, fault_spec: { ...row.fault_spec, primitives: [] } }] },          // a no-fault row is never replayed
    { ...good, rows: [row, { ...row, replay: 2 }, { ...row, replay: 3 }, { ...row, replay: 4 }] },  // at most 3, each row once
  ]) expect(() => check(learnPlan({ ...savedV4(), replay: replay as HistoryReplay }))).toThrow('Malformed')
  expect(() => check(learnPlan({ ...discoveryV3, history: agentHistory(), replay: replayList() }))).toThrow('Malformed')   // v3 never carries a list
})

it('shows the frozen replay list first in the saved plan, and says plainly when it is empty', () => {
  render(h(CampaignPlan, { campaign, resource: { data: { campaign_id: campaign.campaign_id, status: 'PLANNED', plan: learnPlan(savedV4()) }, error: null, loading: false } }))
  expect(screen.getByText('v4 · history replay first, then v3 · agent history')).toBeTruthy()
  const region = screen.getByRole('region', { name: 'Frozen history replay list' })
  expect(within(region).getByText('History replay list · runs first')).toBeTruthy()
  const item = within(region).getByRole('list', { name: 'Recipes replayed first' }).children[0]
  expect(item.textContent).toContain('Replay 1 · agent history row 2 (dev-5)')
  expect(item.textContent).toContain('violated in 3/3 verified episodes · every fault fired 3 of 3 · failed checks C3 (upgrade before confirmation) 3 · C5 (truthful report) 3')
  expect(within(region).getByText('1 slot of this campaign\'s discovery slots · 1 agent episode · no Explorer request')).toBeTruthy()
  expect(within(region).getByText(REPLAY_CLAIM)).toBeTruthy()
  expect(within(region).getByText('e'.repeat(64))).toBeTruthy()
  expect(within(region).getByText(RULE)).toBeTruthy()
  // The replay list comes before the frozen history it was computed from; both are shown.
  const history = screen.getByRole('region', { name: 'Frozen agent history' })
  expect(region.compareDocumentPosition(history) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
  cleanup()
  render(h(CampaignPlan, { campaign, resource: { data: { campaign_id: campaign.campaign_id, status: 'PLANNED', plan: learnPlan(savedV4(false)) }, error: null, loading: false } }))
  const empty = screen.getByRole('region', { name: 'Frozen history replay list' })
  expect(within(empty).getByText(/^Replay list empty: this store has no prior history for this agent/)).toBeTruthy()
  expect(within(empty).queryByRole('list', { name: 'Recipes replayed first' })).toBeNull()
  expect(within(empty).getByText('none')).toBeTruthy()
  expect(screen.getByText(NO_HISTORY_IS_STILL_V4)).toBeTruthy()
  expect(screen.queryByText(NO_HISTORY_IS_STILL_V3)).toBeNull()
})

it('offers v4 in the chooser with one plain sentence for every agent and sends the declared id; nothing starts', async () => {
  vi.spyOn(runApi, 'options').mockResolvedValue(registered)
  const create = vi.spyOn(runApi, 'create').mockResolvedValue({ ...campaign, mode: 'learn', state: 'IDLE', config_profile_id: 'live-v1' })
  const start = vi.spyOn(api, 'start')
  render(h(RunSetup, { config: liveConfig, replay: false, readiness: liveReadiness, onCampaign: vi.fn() }))
  await screen.findByText('Current plan preview')
  fireEvent.change(screen.getByLabelText('Execution profile'), { target: { value: 'live-v1' } })
  fireEvent.change(screen.getByLabelText('Reviewed agent'), { target: { value: 'smolagents' } })
  fireEvent.change(screen.getByLabelText('Campaign mode'), { target: { value: 'learn' } })
  expect((screen.getByRole('option', { name: 'v4 · history replay first' }) as HTMLOptionElement).disabled).toBe(false)
  fireEvent.change(screen.getByLabelText('Discovery protocol'), { target: { value: 'faultlab-discovery/v4-history-replay' } })
  expect(screen.getByText(v4Option.description)).toBeTruthy()
  expect(v4Option.description.split('. ')).toHaveLength(1)   // one plain sentence
  expect(screen.getByText(REPLAY_AT_PLAN_TIME)).toBeTruthy()
  const preview = screen.getByRole('region', { name: 'Current plan preview' })
  expect(within(preview).getByText(/v4 · history replay first · 8 slots · at most 8 Explorer requests · .* · at most 8 Actor episodes · no re-plans/)).toBeTruthy()
  await waitFor(() => expect((screen.getByRole('button', { name: 'Create campaign' }) as HTMLButtonElement).disabled).toBe(false))
  fireEvent.click(screen.getByRole('button', { name: 'Create campaign' }))
  await waitFor(() => expect(create).toHaveBeenCalledOnce())
  expect(create.mock.calls[0][0]).toMatchObject({ mode: 'learn', discovery_protocol: 'faultlab-discovery/v4-history-replay', agent_registration_id: 'smolagents-fixture' })
  expect(start).not.toHaveBeenCalled()
})

const spec = { seed: 105, primitives: [DEV5] }
const slot = { label: 'history replay', protocol: REPLAY_PROTOCOL, replay: 1, of: 1, history_row: 2, development_case_id: 'dev-5', recipe: ['F2 in words'], verified_episodes: 3, violations: 3,
  violation_share: '3/3', every_fault_fired: 3, failed_checks: { C3: 3, C5: 3 }, schedule_identity_v2: 'f'.repeat(64), basis: 'faultlab-schedule-identity/v2-order-aware', episode_id: 'episode-replay', explorer_request: false }
const replayAttempt = (patch: Record<string, unknown> = {}, decision: Record<string, unknown> = {}) => ({ selection_ref: 'selection-replay', campaign_id: campaign.campaign_id, selection_index: 0, configuration_hash: hash, policy_hash: hash,
  // Exactly the fields the backend's search-attempts API sends (app/lab/api.py), transport_retries [] included.
  raw_response: '', usage: { model_calls: 0, input_tokens: 0, output_tokens: 0, cost_dollars: 0 }, provenance: 'history_replay', error: null, transport_retries: [], output: { fault_spec: spec, hypothesis: 'History replay 1 of 1' }, selected_output: { fault_spec: spec, hypothesis: 'History replay 1 of 1' },
  search_decision: { status: 'SELECTED', schedule_hash: hash, reason: null, prior_selection_refs: [], prior_episode_refs: [], history_replay: { replay: 1, history_row: 2, development_case_id: 'dev-5' }, ...decision },
  matches_history_row: { row: 2, development_case_id: 'dev-5', basis: 'faultlab-schedule-identity/v2-order-aware' }, history_replay: slot, ...patch })
const explorerAttempt = { selection_ref: 'selection-pick', campaign_id: campaign.campaign_id, selection_index: 1, configuration_hash: hash, policy_hash: hash, raw_response: 'Model text',
  usage: { model_calls: 1, input_tokens: 100, output_tokens: 20, cost_dollars: null }, provenance: 'model', error: null, transport_retries: [], output: { fault_spec: spec, hypothesis: 'h' }, selected_output: null,
  search_decision: { status: 'SKIPPED_DUPLICATE', schedule_hash: hash, reason: 'DUPLICATE_DISCOVERY_SCHEDULE', prior_selection_refs: ['selection-replay'], prior_episode_refs: ['episode-replay'] }, matches_history_row: null }

it('labels a replay slot as a history replay with no Explorer request, and rejects a replay record that claims otherwise', async () => {
  const rows = validateSearchAttempts([replayAttempt(), explorerAttempt], campaign.campaign_id)
  expect(validateSearchAttempts([replayAttempt({ transport_retries: undefined })], campaign.campaign_id)).toHaveLength(1)   // older shape: field absent
  expect(rows[0].history_replay?.history_row).toBe(2)
  expect('history_replay' in rows[1]).toBe(false)
  for (const bad of [
    replayAttempt({ usage: { model_calls: 1, input_tokens: 100, output_tokens: 20, cost_dollars: null } }),   // a replay sends no request
    replayAttempt({ provenance: 'model' }),
    replayAttempt({ raw_response: 'Model text' }),
    replayAttempt({ transport_retries: [{ retry_id: 'retry-1', code: 'CONNECTION_ERROR', attempt: 1, provider_failure_id: 'failure-1' }] }),   // no request, so no retry
    replayAttempt({ history_replay: { ...slot, explorer_request: true } }),
    replayAttempt({ history_replay: { ...slot, label: 'independent discovery' } }),
    replayAttempt({}, { history_replay: { replay: 1, history_row: 3, development_case_id: 'dev-5' } }),      // record and decision disagree
    replayAttempt({}, { status: 'SKIPPED_DUPLICATE' }),
    replayAttempt({ history_replay: undefined }),                                                           // provenance says replay, no block
    { ...explorerAttempt, search_decision: { ...explorerAttempt.search_decision, history_replay: { replay: 1, history_row: 2, development_case_id: 'dev-5' } } },
  ]) expect(() => validateSearchAttempts([bad], campaign.campaign_id)).toThrow('Malformed')
  vi.stubGlobal('fetch', vi.fn(async () => ({ ok: true, json: async () => [replayAttempt(), explorerAttempt] })))
  render(h(SearchAttemptsPanel, { campaignId: campaign.campaign_id, onEpisode: vi.fn() }))
  expect(await screen.findByText('Selection 1 · History replay 1 of 1 · agent history row 2 (dev-5) · no Explorer request')).toBeTruthy()
  expect(screen.getByText(/^History replay 1 of 1 · agent history row 2 \(dev-5\): FaultLab re-ran this recorded recipe, which violated in 3\/3 verified episodes .*never independent discovery\.$/)).toBeTruthy()
  expect(screen.getByText('History replays · no Explorer request').previousSibling?.textContent).toBe('1')
  expect(screen.getByText('Recorded selection responses').previousSibling?.textContent).toBe('1')
  expect(screen.getByText(/^Discovery protocol v4: the first slot was a history replay/)).toBeTruthy()
  expect(screen.getByText('Selection 2 · Duplicate declined · no Actor trial')).toBeTruthy()
})

it('names the history replay that found a source, and an Explorer pick in a v4 campaign as not a replay', () => {
  const counterexample = { counterexample_id: 'counterexample-1', campaign_id: campaign.campaign_id, agent_registration_id: 'smolagents-fixture', source_episode_id: 'episode-replay', target_invariant: 'C3', scenario_hash: hash, configuration_hash: hash, report_ref: null, verdict_ref: 'verdict-1', created_at: '2026-09-30T00:00:00Z', reproduction_trial_ids: [], target_violation_count: 0, valid_count: 0, attempted_count: 0, reproduced: false }
  const experiments = (extra: Record<string, unknown>, source = 'episode-replay') => ({ counterexamples: [{ counterexample: { ...counterexample, source_episode_id: source }, source_recipe: spec, retained_recipe: null, reduction: null, diagnostics: [], interventions: [], challenges: [], ...extra }], evidence: [], ingestions: [], portability_ids: [] })
  const match = { row: 2, development_case_id: 'dev-5', basis: 'faultlab-schedule-identity/v2-order-aware' }
  const found = validateExperiments(experiments({ matches_history_row: match, history_replay: { ...slot, selection_id: 'selection-replay' } })).counterexamples
  expect(found[0].history_replay?.history_row).toBe(2)
  expect(validateExperiments(experiments({ matches_history_row: null, history_replay: null }, 'episode-pick')).counterexamples[0].history_replay).toBeNull()
  expect('history_replay' in validateExperiments(experiments({ matches_history_row: match })).counterexamples[0]).toBe(false)   // v3: absent
  expect(() => validateExperiments(experiments({ history_replay: slot }, 'episode-other'))).toThrow('Malformed')                 // another episode's replay
  expect(() => validateExperiments(experiments({ history_replay: { ...slot, explorer_request: true } }))).toThrow('Malformed')
  render(h(CounterexamplePanel, { records: found, onEpisode: vi.fn() }))
  expect(screen.getByText('Found by')).toBeTruthy()
  expect(screen.getByText(/^History replay 1 of 1 · agent history row 2 \(dev-5\): FaultLab re-ran this recorded recipe/)).toBeTruthy()
  expect(screen.queryByText('Agent history (v3)')).toBeNull()   // the replay label replaces the weaker history-informed one
  cleanup()
  render(h(CounterexamplePanel, { records: validateExperiments(experiments({ matches_history_row: null, history_replay: null }, 'episode-pick')).counterexamples, onEpisode: vi.fn() }))
  expect(screen.getByText('An Explorer pick in this discovery v4 campaign, not a history replay slot.')).toBeTruthy()
})
