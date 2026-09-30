// @vitest-environment jsdom
// The two diagnosis rules (backend app/lab/diagnosis_protocol.py and app/lab/diagnosis_guide.py, September 30). Review
// finding F2 / LOW-2 (fixer): the diagnosis repair-and-record rule (faultlab-mechanic-diagnosis/v1-repair-and-record) is frozen
// into every new Learn plan, for every agent, but the dashboard neither checked nor showed it before Start. The diagnosis guide
// (faultlab-diagnosis-guide/v1-kinds-and-checks) is built but not offered; a plan that declares it is checked and shown too.
// The diagnosis panel no longer calls a code-default proposed kind the model's. Offline fixtures only; nothing starts.
import { createElement as h } from 'react'
import { cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { runApi, validateCampaignPlan, validateRunOptions, type RunOptions } from '../src/runPlans'
import { CampaignPlan } from '../src/components/CampaignPlan'
import { RunSetup } from '../src/components/RunSetup'
import { DiagnosticPanel } from '../src/components/DiagnosticPanel'
import { validateExperiments } from '../src/experiments'
import { DIAGNOSIS_GUIDE_V1, MECHANIC_CONTEXT_V2, MECHANIC_DIAGNOSIS_V1, diagnosisGuideText, mechanicDiagnosisText,
  type DiagnosisGuideDeclaration, type MechanicContextDeclaration, type MechanicDiagnosisDeclaration } from '../src/loopLimits'
import { campaign, config, experiments, fixtureResponse, readiness, testedExperiment } from './fixtures'
import { planned, runOptions } from './run-fixtures'

beforeEach(() => { vi.stubGlobal('fetch', vi.fn(async (url: string) => ({ ok: true, json: async () => fixtureResponse(url) }))) })
afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals() })

/** As the backend freezes it (app/lab/diagnosis_protocol.py declaration()); the long texts are shortened here. */
const rule: MechanicDiagnosisDeclaration = { protocol: MECHANIC_DIAGNOSIS_V1, applies_to: ['mechanic_diagnosis'],
  repair_instruction: 'Your response failed output_schema or its supplied evidence/choice bindings. Correct formatting only. … A string_too_long error gives max_characters and your_characters: rewrite that same field in at most max_characters characters, keeping its meaning and adding no new claim.',
  repair_sentence: 'A string_too_long error gives max_characters and your_characters: rewrite that same field in at most max_characters characters, keeping its meaning and adding no new claim.',
  string_too_long_fields: ['max_characters', 'your_characters'], hypothesis_max_characters: 600, record_kind: 'diagnosis_requests',
  proposal_statuses: ['VALID_REQUESTED', 'VALID_NO_REQUEST', 'INVALID_OUTPUT'], kind_sources: ['model', 'code_default'],
  rule: "For a Learn plan that declares it, a Mechanic diagnosis request's one format-repair turn states the length limit.",
  first_turn_changed: false, model_text_edited: false, record_written_before_gate: true, reads_scoring: false, verdict_code_changed: false,
  semantics_hash: 'b'.repeat(64) }
const checks = Object.fromEntries(['C1', 'C2', 'C3', 'C4', 'C5', 'C6', 'C7', 'C8'].map(id => [id, `Public meaning of ${id}.`]))
/** As the backend would freeze it (app/lab/diagnosis_guide.py declaration()); not offered by today's backend. */
const guide: DiagnosisGuideDeclaration = { protocol: DIAGNOSIS_GUIDE_V1, applies_to: ['mechanic_diagnosis'], block: 'diagnosis_guide',
  checks_source: 'app.agents.explorer.PUBLIC_INVARIANTS', checks, checks_hash: 'c'.repeat(64), task_source: 'plan.task_text', reads_episodes: false,
  reads_scoring: false, compacted: false, system_prompt_changed: false, verdict_code_changed: false, interprets_checks: false,
  meaning: 'Fixed lab text for this diagnosis request.', kinds: { POLICY_GAP: 'p', CONTRACT_EVIDENCE_GAP: 'c', INCONCLUSIVE: 'i' },
  checks_note: 'Explain each failed check from its own meaning.',
  contract_note: 'runtime_contract is not a list of pass/fail rules.', use: 'Fixed code runs only the intervention you request.',
  hypothesis_length: 'hypothesis is at most 600 characters.', rule: 'For a Learn plan that declares it, each Mechanic diagnosis request gets one separate diagnosis_guide block.' }
const mechanicContext: MechanicContextDeclaration = { protocol: MECHANIC_CONTEXT_V2, applies_to: ['mechanic_diagnosis', 'mechanic_proposal'], input_token_limit: 32000,
  format_repair_reserve_tokens: 4000, compaction_target_tokens: 28000, stages: ['IDENTICAL_CLEAN_ROWS', 'ONE_CLEAN_EPISODE_PER_OUTCOME_GROUP', 'NO_CLEAN_EPISODE_ROWS'],
  always_kept: ['the source episode and its reproduction episodes'], when_unfit: 'END_SOURCE_CANDIDATE_SEARCH', unsent_request_uses_candidate_request: false,
  requests_over_limit_sent: 0, rule: 'When a Mechanic request would exceed the limit, FaultLab compacts only its evidence tables.' }
const learnPlan = (agent: 'reference' | 'smolagents' | 'smolagents-v2', patch: Record<string, unknown> = {}) => planned(campaign, { mode: 'learn', config_profile_id: 'live-v1', source_mode: 'live', agent,
  selection: { kind: 'development_search', manifest_hash: runOptions.learn.manifest_hash, search_space: runOptions.learn.search_space }, discovery: null, ...patch })
const check = (plan: unknown) => validateCampaignPlan({ campaign_id: campaign.campaign_id, status: 'PLANNED', plan }, campaign.campaign_id)
const resource = (plan: unknown) => ({ data: { campaign_id: campaign.campaign_id, status: 'PLANNED' as const, plan: plan as ReturnType<typeof learnPlan> }, error: null, loading: false })

it('accepts the repair-and-record rule exactly as frozen, only in a Learn plan, for every agent, and refuses anything else', () => {
  const offered: RunOptions = { ...runOptions, learn: { ...runOptions.learn, mechanic_diagnosis: rule } }
  expect(validateRunOptions(offered)).toEqual(offered)
  for (const bad of [{ ...rule, first_turn_changed: true }, { ...rule, model_text_edited: true }, { ...rule, record_written_before_gate: false },
    { ...rule, reads_scoring: true }, { ...rule, verdict_code_changed: true }, { ...rule, hypothesis_max_characters: 700 }, { ...rule, record_kind: 'diagnostics' },
    { ...rule, proposal_statuses: ['VALID_REQUESTED', 'VALID_NO_REQUEST', 'DECLINED'] }, { ...rule, kind_sources: ['model', 'default'] },
    { ...rule, string_too_long_fields: ['max_characters', 'length'] }, { ...rule, applies_to: ['mechanic_proposal'] }, { ...rule, semantics_hash: 'x' },
    { ...rule, rule: '' }, { ...rule, repair_sentence: '' }])
    expect(() => validateRunOptions({ ...offered, learn: { ...offered.learn, mechanic_diagnosis: bad } })).toThrow('Malformed')
  for (const agent of ['reference', 'smolagents', 'smolagents-v2'] as const) {
    expect(check(learnPlan(agent, { mechanic_diagnosis: rule })).status).toBe('PLANNED')
    expect(check(learnPlan(agent)).status).toBe('PLANNED')                                          // a Learn plan saved before the rule
    expect(() => check(learnPlan(agent, { mechanic_diagnosis: { ...rule, record_written_before_gate: false } }))).toThrow('Malformed')
  }
  expect(() => check(planned(campaign, { mechanic_diagnosis: rule }))).toThrow('Malformed')             // a baseline plan never declares it
})

it('checks a plan that declares the diagnosis guide (built, not offered) and refuses it outside Learn or with any flag changed', () => {
  expect(check(learnPlan('smolagents-v2', { mechanic_diagnosis: rule, diagnosis_guide: guide })).status).toBe('PLANNED')
  expect(() => check(planned(campaign, { diagnosis_guide: guide }))).toThrow('Malformed')
  const { C8: _dropped, ...seven } = checks
  for (const bad of [{ ...guide, interprets_checks: true }, { ...guide, reads_episodes: true }, { ...guide, reads_scoring: true }, { ...guide, compacted: true },
    { ...guide, checks: seven }, { ...guide, task_source: 'episode' }, { ...guide, checks_hash: 'x' }, { ...guide, kinds: { POLICY_GAP: 'p' } },
    { ...guide, checks_note: '' }])
    expect(() => check(learnPlan('reference', { diagnosis_guide: bad }))).toThrow('Malformed')
  expect(validateRunOptions({ ...runOptions, learn: { ...runOptions.learn, diagnosis_guide: guide } }).learn.diagnosis_guide).toEqual(guide)
  expect(() => validateRunOptions({ ...runOptions, learn: { ...runOptions.learn, diagnosis_guide: { ...guide, interprets_checks: true } } })).toThrow('Malformed')
})

it('shows the rule in a saved Learn plan, says plainly when an older plan has none, and shows the guide only when declared', () => {
  render(h(CampaignPlan, { campaign, resource: resource(learnPlan('reference', { mechanic_diagnosis: rule })) }))
  const saved = screen.getByRole('region', { name: 'Saved campaign plan' })
  expect(within(saved).getByText('Diagnosis repair and record')).toBeTruthy()
  expect(within(saved).getByText(mechanicDiagnosisText(rule))).toBeTruthy()
  expect(mechanicDiagnosisText(rule)).toContain('max_characters 600')
  expect(mechanicDiagnosisText(rule)).toContain('before the POLICY_GAP gate')
  expect(within(saved).getByText(`${MECHANIC_DIAGNOSIS_V1}: ${rule.rule}`)).toBeTruthy()
  expect(within(saved).queryByText('Diagnosis guide')).toBeNull()
  cleanup()
  render(h(CampaignPlan, { campaign, resource: resource(learnPlan('smolagents')) }))
  expect(screen.getByText(/^Not declared: this plan was saved before the diagnosis repair-and-record rule\./)).toBeTruthy()
  cleanup()
  render(h(CampaignPlan, { campaign, resource: resource(learnPlan('smolagents-v2', { mechanic_diagnosis: rule, diagnosis_guide: guide })) }))
  const withGuide = screen.getByRole('region', { name: 'Saved campaign plan' })
  expect(within(withGuide).getByText('Diagnosis guide')).toBeTruthy()
  expect(within(withGuide).getByText(diagnosisGuideText(guide))).toBeTruthy()
  expect(within(withGuide).getByText(`${DIAGNOSIS_GUIDE_V1}: ${guide.rule}`)).toBeTruthy()
  cleanup()
  render(h(CampaignPlan, { campaign, resource: resource(planned(campaign)) }))                      // a baseline plan says nothing about it
  expect(screen.queryByText('Diagnosis repair and record')).toBeNull()
})

it('tells the operator in the Learn setup form that every new Learn plan freezes the rule, for any agent', async () => {
  const offered: RunOptions = { ...runOptions, learn: { ...runOptions.learn, mechanic_context: mechanicContext, mechanic_diagnosis: rule } }
  const registered: RunOptions = { ...offered, agents: offered.agents.map(agent => ({ ...agent, registered: true, registration_id: agent.proposed_registration_id })) }
  vi.spyOn(runApi, 'options').mockResolvedValue(registered)
  render(h(RunSetup, { config: { ...config, live_enabled: true, model_configured: true, data_store: runOptions.data_store }, replay: false,
    readiness: { data: { ...readiness, live_configuration: { ready: true, missing_fields: [] } }, error: null, loading: false }, onCampaign: vi.fn() }))
  await screen.findByText('Current plan preview')
  fireEvent.change(screen.getByLabelText('Execution profile'), { target: { value: 'live-v1' } })
  fireEvent.change(screen.getByLabelText('Campaign mode'), { target: { value: 'learn' } })
  expect(screen.getByText('Every new Learn plan also freezes these two rules:')).toBeTruthy()
  expect(screen.getByText('Diagnosis repair and record')).toBeTruthy()
  expect(screen.getByText(mechanicDiagnosisText(rule))).toBeTruthy()
  expect(screen.queryByText('Diagnosis guide')).toBeNull()                                           // not offered
  fireEvent.change(screen.getByLabelText('Reviewed agent'), { target: { value: 'smolagents' } })
  fireEvent.change(screen.getByLabelText('Campaign mode'), { target: { value: 'learn' } })
  expect(screen.getByText(mechanicDiagnosisText(rule))).toBeTruthy()                                 // every agent
})

it('labels the recorded proposed kind as recorded, not as the model\'s, since a code default is stored when no answer is valid', () => {
  const records = validateExperiments({ ...experiments, counterexamples: [testedExperiment] }).counterexamples
  render(h(DiagnosticPanel, { records, onEpisode: vi.fn() }))
  expect(screen.queryByText('Model proposed kind')).toBeNull()
  expect(screen.getByText('Recorded proposed kind')).toBeTruthy()
  expect(screen.getByText(/INCONCLUSIVE by default when it gave no valid answer/)).toBeTruthy()
})
