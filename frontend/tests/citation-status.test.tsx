// @vitest-environment jsdom
// Native citation status (backend app/lab/citation_status.py, faultlab-mechanic-evidence/v2-native-citation-status): frozen
// into every new Learn plan of native adapter v2 only. The validators, the saved plan and the Learn setup form show it for
// that agent and say nothing about it for any other agent. Offline fixtures only; nothing starts.
import { createElement as h } from 'react'
import { cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { runApi, validateCampaignPlan, validateRunOptions, type RunOptions } from '../src/runPlans'
import { CampaignPlan } from '../src/components/CampaignPlan'
import { RunSetup } from '../src/components/RunSetup'
import { MECHANIC_EVIDENCE_V2, mechanicEvidenceText, type MechanicEvidenceDeclaration } from '../src/loopLimits'
import { campaign, config, fixtureResponse, readiness } from './fixtures'
import { planned, runOptions } from './run-fixtures'

beforeEach(() => { vi.stubGlobal('fetch', vi.fn(async (url: string) => ({ ok: true, json: async () => fixtureResponse(url) }))) })
afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals() })

/** As the backend freezes it (app/lab/citation_status.py declaration()). */
const rule: MechanicEvidenceDeclaration = { protocol: MECHANIC_EVIDENCE_V2, agents: ['smolagents-v2'], applies_to: ['mechanic_diagnosis', 'mechanic_proposal', 'explorer_challenge'],
  block: 'native_citation_status', row_fields: ['episode_id', 'cited', 'decoded', 'undecoded'], source_event: 'report_submitted',
  source_protocol: 'faultlab-native-adapter/v2.1-shown-order-labels', reads_scoring: false, compacted: false, discovery_requests_changed: false,
  meaning: "Each row is what the native adapter recorded when that episode's agent submitted its report.",
  memory_pointer: "This request's native_citation_status block lists, for each episode in its evidence, the adapter's recorded outcome of that decoding.",
  rule: 'For a native adapter v2 Learn plan, every Mechanic diagnosis or candidate request and every challenge Explorer request that carries evidence of at least one episode gets a separate native_citation_status block.' }
const learnPlan = (agent: 'reference' | 'smolagents' | 'smolagents-v2', patch: Record<string, unknown> = {}) => planned(campaign, { mode: 'learn', config_profile_id: 'live-v1', source_mode: 'live', agent,
  selection: { kind: 'development_search', manifest_hash: runOptions.learn.manifest_hash, search_space: runOptions.learn.search_space }, discovery: null, ...patch })
const check = (plan: unknown) => validateCampaignPlan({ campaign_id: campaign.campaign_id, status: 'PLANNED', plan }, campaign.campaign_id)
const resource = (plan: unknown) => ({ data: { campaign_id: campaign.campaign_id, status: 'PLANNED' as const, plan: plan as ReturnType<typeof learnPlan> }, error: null, loading: false })

it('accepts the rule exactly as frozen, only in a native adapter v2 Learn plan', () => {
  const offered: RunOptions = { ...runOptions, learn: { ...runOptions.learn, mechanic_evidence: rule } }
  expect(validateRunOptions(offered)).toEqual(offered)
  for (const bad of [{ ...rule, reads_scoring: true }, { ...rule, compacted: true }, { ...rule, agents: ['smolagents'] }, { ...rule, discovery_requests_changed: true },
    { ...rule, row_fields: ['episode_id', 'cited', 'decoded', 'failed'] }, { ...rule, applies_to: ['mechanic_diagnosis'] }, { ...rule, meaning: '' }])
    expect(() => validateRunOptions({ ...offered, learn: { ...offered.learn, mechanic_evidence: bad } })).toThrow('Malformed')
  expect(check(learnPlan('smolagents-v2', { mechanic_evidence: rule })).status).toBe('PLANNED')
  expect(check(learnPlan('smolagents-v2')).status).toBe('PLANNED')                              // a v2 plan saved before the rule
  expect(() => check(learnPlan('reference', { mechanic_evidence: rule }))).toThrow('Malformed')
  expect(() => check(learnPlan('smolagents', { mechanic_evidence: rule }))).toThrow('Malformed')
  expect(() => check(planned(campaign, { mechanic_evidence: rule }))).toThrow('Malformed')        // a baseline plan never declares it
})

it('shows the rule in a saved native adapter v2 Learn plan, says plainly when an older v2 plan has none, and says nothing for other agents', () => {
  render(h(CampaignPlan, { campaign, resource: resource(learnPlan('smolagents-v2', { mechanic_evidence: rule })) }))
  const saved = screen.getByRole('region', { name: 'Saved campaign plan' })
  expect(within(saved).getByText('Native citation status')).toBeTruthy()
  expect(within(saved).getByText(mechanicEvidenceText(rule))).toBeTruthy()
  expect(mechanicEvidenceText(rule)).toContain('nothing from scoring')
  expect(within(saved).getByText(`${MECHANIC_EVIDENCE_V2}: ${rule.rule}`)).toBeTruthy()
  cleanup()
  render(h(CampaignPlan, { campaign, resource: resource(learnPlan('smolagents-v2')) }))
  expect(screen.getByText(/^Not declared: this native adapter v2 plan was saved before the rule\./)).toBeTruthy()
  cleanup()
  for (const agent of ['reference', 'smolagents'] as const) {
    render(h(CampaignPlan, { campaign, resource: resource(learnPlan(agent)) }))
    expect(screen.queryByText('Native citation status')).toBeNull()
    cleanup()
  }
})

it('tells the operator in the Learn setup form only when native adapter v2 is chosen', async () => {
  const v2Agent = { ...runOptions.agents[1], agent: 'smolagents-v2' as const, label: 'smolagents ToolCallingAgent 1.26.0 · FaultLab adapter v2', proposed_registration_id: 'smolagents-v2-fixture' }
  const offered: RunOptions = { ...runOptions, learn: { ...runOptions.learn, mechanic_evidence: rule }, agents: [...runOptions.agents, v2Agent] }
  const registered: RunOptions = { ...offered, agents: offered.agents.map(agent => ({ ...agent, registered: true, registration_id: agent.proposed_registration_id })) }
  vi.spyOn(runApi, 'options').mockResolvedValue(registered)
  render(h(RunSetup, { config: { ...config, live_enabled: true, model_configured: true, data_store: runOptions.data_store }, replay: false,
    readiness: { data: { ...readiness, live_configuration: { ready: true, missing_fields: [] } }, error: null, loading: false }, onCampaign: vi.fn() }))
  await screen.findByText('Current plan preview')
  fireEvent.change(screen.getByLabelText('Execution profile'), { target: { value: 'live-v1' } })
  fireEvent.change(screen.getByLabelText('Campaign mode'), { target: { value: 'learn' } })
  expect(screen.queryByText('A new Learn plan for native adapter v2 also freezes:')).toBeNull()      // the reference Actor
  fireEvent.change(screen.getByLabelText('Reviewed agent'), { target: { value: 'smolagents' } })
  fireEvent.change(screen.getByLabelText('Campaign mode'), { target: { value: 'learn' } })
  expect(screen.queryByText('Native citation status')).toBeNull()                                    // native adapter v1
  fireEvent.change(screen.getByLabelText('Reviewed agent'), { target: { value: 'smolagents-v2' } })
  fireEvent.change(screen.getByLabelText('Campaign mode'), { target: { value: 'learn' } })
  expect(screen.getByText('A new Learn plan for native adapter v2 also freezes:')).toBeTruthy()
  expect(screen.getByText(mechanicEvidenceText(rule))).toBeTruthy()
})
