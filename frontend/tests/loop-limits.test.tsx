// @vitest-environment jsdom
// The two Learn-loop rules built after live run v2d (backend app/lab/loop_limits.py): the Mechanic request-size rule
// (faultlab-mechanic-context/v2-bounded), frozen into every new Learn plan, and the challenge-pick rule
// (faultlab-challenge-selection/v2-candidate-reach), withdrawn before any live run (both reviews, HIGH-1) but still shown
// for a plan that declares it. Validators, the saved plan, the Learn setup form and the challenge and diagnosis panels.
// Offline fixtures only; nothing starts.
import { createElement as h } from 'react'
import { cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { runApi, validateCampaignPlan, validateRunOptions, type RunOptions } from '../src/runPlans'
import { CampaignPlan } from '../src/components/CampaignPlan'
import { RunSetup } from '../src/components/RunSetup'
import { ChallengePanel } from '../src/components/ChallengePanel'
import { DiagnosticPanel } from '../src/components/DiagnosticPanel'
import { validateExperiments } from '../src/experiments'
import { CHALLENGE_SELECTION_V2, MECHANIC_CONTEXT_V2, challengeSelectionText, mechanicContextText, type ChallengeReachDecision, type ChallengeSelectionDeclaration,
  type MechanicContextDeclaration, type MechanicContextRecord } from '../src/loopLimits'
import { campaign, config, experiments, fixtureResponse, readiness } from './fixtures'
import { planned, runOptions } from './run-fixtures'

beforeEach(() => { vi.stubGlobal('fetch', vi.fn(async (url: string) => ({ ok: true, json: async () => fixtureResponse(url) }))) })
afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals() })

/** As the backend freezes them (app/lab/loop_limits.py mechanic_context_declaration(), challenge_selection_declaration()). */
const mechanicContext: MechanicContextDeclaration = { protocol: MECHANIC_CONTEXT_V2, applies_to: ['mechanic_diagnosis', 'mechanic_proposal'], input_token_limit: 32000,
  format_repair_reserve_tokens: 4000, compaction_target_tokens: 28000, stages: ['IDENTICAL_CLEAN_ROWS', 'ONE_CLEAN_EPISODE_PER_OUTCOME_GROUP', 'NO_CLEAN_EPISODE_ROWS'],
  always_kept: ['the source episode and its reproduction episodes', 'every episode with a failed check'], when_unfit: 'END_SOURCE_CANDIDATE_SEARCH',
  unsent_request_uses_candidate_request: false, requests_over_limit_sent: 0, rule: 'When a Mechanic candidate request (or diagnosis request) would exceed the 32,000-token model input limit, FaultLab compacts only the evidence tables it carries.' }
const challengeSelection: ChallengeSelectionDeclaration = { protocol: CHALLENGE_SELECTION_V2, basis: 'candidate_arm_source_validation_agent_calls', caller_counted: 'actor',
  target: 'tool_and_service', replans_per_refused_pick: 1, explorer_requests_per_challenge: 8, refused_pick_runs_episodes: false, challenge_rules_changed: false,
  rule: 'Before a challenge pick runs any pair, FaultLab checks every fault target (tool and service) against the calls the agent under test itself made.' }
const withRules: RunOptions = { ...runOptions, learn: { ...runOptions.learn, mechanic_context: mechanicContext, challenge_selection: challengeSelection } }
const learnPlan = (patch: Record<string, unknown> = {}) => planned(campaign, { mode: 'learn', config_profile_id: 'live-v1', source_mode: 'live', agent: 'smolagents-v2',
  selection: { kind: 'development_search', manifest_hash: runOptions.learn.manifest_hash, search_space: runOptions.learn.search_space }, discovery: null, ...patch })
const check = (plan: unknown) => validateCampaignPlan({ campaign_id: campaign.campaign_id, status: 'PLANNED', plan }, campaign.campaign_id)

it('accepts the run options and a Learn plan with both rules exactly as frozen, and refuses anything else', () => {
  expect(validateRunOptions(withRules)).toEqual(withRules)
  expect(validateRunOptions(runOptions)).toEqual(runOptions)                                 // an older backend: no rules offered
  for (const bad of [{ ...mechanicContext, compaction_target_tokens: 30000 }, { ...mechanicContext, when_unfit: 'ERROR' }, { ...mechanicContext, requests_over_limit_sent: 1 },
    { ...mechanicContext, stages: ['NO_CLEAN_EPISODE_ROWS'] }, { ...mechanicContext, rule: '' }])
    expect(() => validateRunOptions({ ...withRules, learn: { ...withRules.learn, mechanic_context: bad } })).toThrow('Malformed')
  for (const bad of [{ ...challengeSelection, explorer_requests_per_challenge: 16 }, { ...challengeSelection, challenge_rules_changed: true },
    { ...challengeSelection, caller_counted: 'policy' }, { ...challengeSelection, replans_per_refused_pick: 2 }])
    expect(() => validateRunOptions({ ...withRules, learn: { ...withRules.learn, challenge_selection: bad } })).toThrow('Malformed')
  expect(check(learnPlan({ mechanic_context: mechanicContext, challenge_selection: challengeSelection })).status).toBe('PLANNED')
  expect(check(learnPlan()).status).toBe('PLANNED')                                         // a Learn plan saved before the rules
  expect(() => check(learnPlan({ mechanic_context: { ...mechanicContext, input_token_limit: 64000 } }))).toThrow('Malformed')
  expect(() => check(planned(campaign, { mechanic_context: mechanicContext }))).toThrow('Malformed')             // a baseline plan never declares them
  expect(() => check(planned(campaign, { challenge_selection: challengeSelection }))).toThrow('Malformed')
})

it('shows both rules in a saved Learn plan, and says plainly when an older plan has neither', () => {
  const resource = (plan: unknown) => ({ data: { campaign_id: campaign.campaign_id, status: 'PLANNED' as const, plan: plan as ReturnType<typeof learnPlan> }, error: null, loading: false })
  render(h(CampaignPlan, { campaign, resource: resource(learnPlan({ mechanic_context: mechanicContext, challenge_selection: challengeSelection })) }))
  const saved = screen.getByRole('region', { name: 'Saved campaign plan' })
  expect(within(saved).getByText(mechanicContextText(mechanicContext))).toBeTruthy()
  expect(within(saved).getByText(challengeSelectionText(challengeSelection))).toBeTruthy()
  expect(mechanicContextText(mechanicContext)).toContain('at most 28,000 (4,000 kept for one format-repair turn)')
  expect(mechanicContextText(mechanicContext)).toContain('never ERROR')
  expect(challengeSelectionText(challengeSelection)).toContain("inside the challenge's 8 Explorer requests")
  cleanup()
  render(h(CampaignPlan, { campaign, resource: resource(learnPlan()) }))
  expect(screen.getByText(/Not declared: this plan was saved before the Mechanic request-size rule\..*ends the campaign in ERROR, as before\./)).toBeTruthy()
  expect(screen.getByText('Not declared: every valid challenge pick runs its pairs, as before.')).toBeTruthy()
  cleanup()
  // A new Learn plan: the Mechanic rule only (the challenge-pick rule is withdrawn), and no claim that it predates the rule.
  render(h(CampaignPlan, { campaign, resource: resource(learnPlan({ mechanic_context: mechanicContext })) }))
  const current = screen.getByRole('region', { name: 'Saved campaign plan' })
  expect(within(current).getByText(mechanicContextText(mechanicContext))).toBeTruthy()
  expect(within(current).getByText('Not declared: every valid challenge pick runs its pairs, as before.')).toBeTruthy()
  expect(within(current).queryByText(/saved before the challenge-pick rule/)).toBeNull()
  cleanup()
  render(h(CampaignPlan, { campaign, resource: resource(planned(campaign)) }))                 // a baseline plan shows neither
  expect(screen.queryByText(/Mechanic request size/)).toBeNull()
})

it('tells the operator in the Learn setup form which rule every new Learn plan freezes (the Mechanic rule only)', async () => {
  // As the backend now offers it: the Mechanic rule; the withdrawn challenge-pick rule is not offered.
  const offered: RunOptions = { ...runOptions, learn: { ...runOptions.learn, mechanic_context: mechanicContext } }
  const registered: RunOptions = { ...offered, agents: offered.agents.map(agent => ({ ...agent, registered: true, registration_id: agent.proposed_registration_id })) }
  vi.spyOn(runApi, 'options').mockResolvedValue(registered)
  render(h(RunSetup, { config: { ...config, live_enabled: true, model_configured: true, data_store: runOptions.data_store }, replay: false,
    readiness: { data: { ...readiness, live_configuration: { ready: true, missing_fields: [] } }, error: null, loading: false }, onCampaign: vi.fn() }))
  await screen.findByText('Current plan preview')
  expect(screen.queryByText('Every new Learn plan also freezes this rule:')).toBeNull()      // baseline: not shown
  fireEvent.change(screen.getByLabelText('Execution profile'), { target: { value: 'live-v1' } })
  fireEvent.change(screen.getByLabelText('Campaign mode'), { target: { value: 'learn' } })
  expect(screen.getByText('Every new Learn plan also freezes this rule:')).toBeTruthy()
  expect(screen.getByText(mechanicContextText(mechanicContext))).toBeTruthy()
  expect(screen.queryByText('Challenge picks')).toBeNull()                                    // nothing is claimed about a rule not offered
  expect(screen.queryByText(/challenge pick/)).toBeNull()
})

const basis = { source_validation_episode_ids: ['episode-sv-1', 'episode-sv-2', 'episode-sv-3'], tool_services_called_by_agent: ['get_order:orders', 'update_order:orders'],
  called_only_by_candidate_policy: ['get_operation_status:orders'] }
const refused: ChallengeReachDecision = { selection_id: 'selection-refused', challenge_id: 'challenge-x', candidate_hash: 'c'.repeat(64), recipe: ['F4 on get_operation_status:orders attempt 1: 1 transient failure'],
  protocol: CHALLENGE_SELECTION_V2, proposal_index: 2, slot_request: 1, replan_of: null, status: 'REFUSED_UNREACHED', targets: ['get_operation_status:orders'], unreached: ['get_operation_status:orders'],
  reason: "Refused before any pair ran: this pick puts a fault on get_operation_status (orders), which the agent never called in the candidate arm's 3 source-validation episode(s) of this campaign (only the candidate policy's own hook steps read it there; those are not agent calls). The next request in this challenge is its one re-plan.",
  basis, refused_fault_spec: null }
const replan: ChallengeReachDecision = { ...refused, selection_id: 'selection-replan', proposal_index: 3, slot_request: 2, replan_of: 'selection-refused', status: 'SELECTED',
  recipe: ['F2 on update_order:orders attempt 1'], targets: ['update_order:orders'], unreached: [], reason: null }
const compacted: MechanicContextRecord = { record_id: 'mechanic-context-1', campaign_id: campaign.campaign_id, protocol: MECHANIC_CONTEXT_V2, request_kind: 'mechanic_proposal',
  counterexample_id: 'counterexample-1', source_episode_id: 'episode-source', outcome: 'COMPACTED', input_token_limit: 32000, compaction_target_tokens: 28000, full_request_tokens: 33223,
  compacted_request_tokens: 27990, candidate_index: 1, stages_applied: ['IDENTICAL_CLEAN_ROWS', 'ONE_CLEAN_EPISODE_PER_OUTCOME_GROUP'],
  blocks: [{ field: 'development_evidence', episodes_total: 16, episodes_in_full: 12, episodes_omitted: 4, omitted_by_stage: {} }],
  statement: 'This request was compacted under faultlab-mechanic-context/v2-bounded: in full it was 33,223 input tokens.', reason: null, provider_dispatch: true }
const ended: MechanicContextRecord = { ...compacted, record_id: 'mechanic-context-2', request_kind: 'mechanic_diagnosis', outcome: 'SEARCH_ENDED', stage: 'BEFORE_SEND',
  compacted_request_tokens: null, statement: null, provider_dispatch: false, candidate_index: undefined,
  blocks: [{ field: 'observations', episodes_total: 10, episodes_in_full: 7, episodes_omitted: 3, omitted_by_stage: {} }],
  reason: 'The Mechanic diagnosis request is 40,000 input tokens (limit 32,000). Nothing was sent; the diagnosis and candidate search for this source ended here.' }
const repair: MechanicContextRecord = { ...ended, record_id: 'mechanic-context-3', request_kind: 'mechanic_proposal', stage: 'FORMAT_REPAIR', candidate_index: 0, blocks: undefined,
  full_request_tokens: undefined, format_repair_tokens: 32150,
  reason: "The Mechanic candidate request's format-repair turn would exceed the 32,000-token model input limit (32,150 tokens) and was refused before sending; the first turn was sent and its answer is saved. The candidate search for this source ended here." }

it('validates the checked challenge picks and request-size records, refusing incoherent ones', () => {
  const body = { ...experiments, challenge_reach: [refused, replan], mechanic_context: [compacted, ended] }
  const valid = validateExperiments(body)
  expect(valid.challenge_reach).toEqual([refused, replan])
  expect(valid.mechanic_context).toEqual([compacted, ended])
  expect(validateExperiments(experiments)).not.toHaveProperty('challenge_reach')           // older plans: absent
  for (const bad of [{ ...refused, reason: null }, { ...refused, unreached: [] }, { ...replan, unreached: ['x:y'] }, { ...refused, status: 'MAYBE' }, { ...refused, slot_request: 3 }])
    expect(() => validateExperiments({ ...experiments, challenge_reach: [bad] })).toThrow('Malformed')
  for (const bad of [{ ...compacted, compacted_request_tokens: 28001 }, { ...compacted, provider_dispatch: false }, { ...compacted, statement: null },
    { ...ended, provider_dispatch: true }, { ...ended, reason: null }, { ...ended, stage: undefined }])
    expect(() => validateExperiments({ ...experiments, mechanic_context: [bad] })).toThrow('Malformed')
})

it('shows each checked challenge pick and each request-size record in the evidence panels', () => {
  render(h(ChallengePanel, { records: [], onEpisode: vi.fn(), reach: [refused, replan] }))
  const panel = screen.getByRole('region', { name: "Challenge picks checked against the candidate's reach" })
  expect(within(panel).getByText('2 picks checked, 1 refused before any pair ran.', { exact: false })).toBeTruthy()
  expect(within(panel).getByText(/^Explorer request 3: Refused before any pair ran: this pick puts a fault on get_operation_status \(orders\)/)).toBeTruthy()
  expect(within(panel).queryByText(/refused, no pair ran/)).toBeNull()                        // said once, not twice
  expect(within(panel).getByText('Explorer request 4 (re-plan): every fault targets a tool and service the agent called; it ran.')).toBeTruthy()
  expect(within(panel).getByText('Selected')).toBeTruthy()                                     // capitalised like every other badge
  expect(within(panel).getByText(/The agent called: get_order:orders, update_order:orders · read only by the candidate policy: get_operation_status:orders · 3 source-validation episode\(s\)/)).toBeTruthy()
  expect(within(panel).getByText('Refused: tool not reached')).toBeTruthy()
  cleanup()
  render(h(ChallengePanel, { records: [], onEpisode: vi.fn() }))                               // older plans: no section
  expect(screen.queryByText('Challenge picks · candidate reach check')).toBeNull()
  cleanup()
  render(h(DiagnosticPanel, { records: [], onEpisode: vi.fn(), mechanicContext: [compacted, ended, repair] }))
  const size = screen.getByRole('region', { name: 'Mechanic request size' })
  expect(within(size).getByText('Candidate request 2: 33,223 tokens in full, over the 32,000-token limit; compacted to 27,990 and sent.')).toBeTruthy()
  expect(within(size).getByText(/Diagnosis request: not sent\. The Mechanic diagnosis request is 40,000 input tokens/)).toBeTruthy()
  expect(within(size).getByText('development_evidence: 12 of 16 episodes in full')).toBeTruthy()
  expect(within(size).queryByText('observations: 7 of 10 episodes in full')).toBeNull()        // a request that was never sent has no "in full" line
  expect(within(size).getByText('Compacted and sent')).toBeTruthy()
  expect(within(size).getByText('Search ended, not sent')).toBeTruthy()
  // Product review LOW-2: a refused format-repair turn is not "not sent": its first turn was sent and charged.
  expect(within(size).getByText(/^Candidate request 1: first turn sent \(its answer is saved\); its format-repair turn was not sent\./)).toBeTruthy()
  expect(within(size).queryByText(/Candidate request 1: not sent/)).toBeNull()
  expect(within(size).getByText('Search ended, repair turn not sent')).toBeTruthy()
})
