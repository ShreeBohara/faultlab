// @vitest-environment jsdom
import { cleanup, render, screen, waitFor } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import { ContextStudyPanel } from '../src/components/ContextStudyPanel'
import { contextGroups, validateContextStudies, validateContextStudy } from '../src/contextStudy'
import type { ContextStudy, ContextTrial } from '../src/contextStudy'
import { campaign, hash } from './fixtures'

afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals() })

const V1 = 'faultlab-actor-context/v1'
const V2 = 'faultlab-actor-context/v2-attempted-writes'

function row(id: string, arm: 'B0' | 'P1', outcome: 'COMPLETED' | 'SAFE_UNRESOLVED' | 'VIOLATION' = 'COMPLETED',
             caseId = 'notification-2'): ContextTrial {
  return { case_id: caseId, actor_context_protocol: arm === 'B0' ? V1 : V2,
    trial: { episode_id: id, world_id: `world-${id}`, scenario_hash: hash, policy_hash: hash, arm,
      trial_index: 0, lifecycle: 'COMPLETED', outcome, fault_scheduled: true, fault_triggered: true,
      failed_checks: outcome === 'VIOLATION' ? ['C5'] : [], usage: { model_calls: 8 } } }
}

function study(): ContextStudy {
  return { schema_version: 'faultlab-context-study/v1', study_id: 'context-study-fixture',
    campaign_id: campaign.campaign_id, status: 'COMPLETED', stage: 'assessment', decision: 'NO_CHANGE',
    reason: 'No strict pooled completion gain on the predeclared primary cases.',
    ordinary_policy_accepted: false, configuration_hash: hash, policy_hash: hash,
    policy_version: 'policy-v0', model: 'fixture-model', arms: ['B0', 'P1'],
    protocol_by_arm: { B0: V1, P1: V2 },
    trial_rows: [row('episode-b0', 'B0', 'SAFE_UNRESOLVED'), row('episode-p1', 'P1', 'SAFE_UNRESOLVED'),
                 row('episode-control-b0', 'B0', 'COMPLETED', 'healthy'),
                 row('episode-control-p1', 'P1', 'COMPLETED', 'healthy')],
    assessment: { decision: 'NO_CHANGE', reason: 'No strict pooled completion gain.', by_case: {},
      incomplete_case_ids: [], comparable_case_ids: ['notification-2', 'healthy'],
      primary_case_ids: ['notification-2'], primary_completions: { B0: 0, P1: 0 },
      primary_denominator: 3, violations: { B0: 0, P1: 0 }, regressed_case_ids: [] },
    action_profile_totals: { B0: { notifications: { episodes: 2, write_requests: 1, status_reads: 4,
      status_reads_before_any_write: 1, episodes_with_no_write_request: 1, write_transport_attempts: 2,
      episodes_with_status_read_before_any_write: 1 } } },
    evidence: { 'episode-b0': 'weave_verified', 'episode-p1': 'weave_verified' },
    charged_model_calls: 32, usage: { model_calls: 32 } }
}

function improved(): ContextStudy {
  const saved = study()
  saved.decision = 'OBSERVED_IMPROVEMENT'
  saved.reason = 'Strict pooled completion gain; baseline engineering, not a learned repair.'
  saved.trial_rows = [row('episode-b0', 'B0', 'SAFE_UNRESOLVED'), row('episode-p1', 'P1', 'COMPLETED'),
                      row('episode-control-b0', 'B0', 'COMPLETED', 'healthy'),
                      row('episode-control-p1', 'P1', 'COMPLETED', 'healthy')]
  saved.assessment = { ...saved.assessment!, decision: 'OBSERVED_IMPROVEMENT',
    reason: 'Strict pooled completion gain.', primary_completions: { B0: 0, P1: 1 } }
  return saved
}

it('groups counts by case and arm without combining protocols or cases', () => {
  const rows = improved().trial_rows
  rows.push({ ...row('episode-untriggered', 'B0'),
    trial: { ...row('episode-untriggered', 'B0').trial, fault_triggered: false } })
  const groups = contextGroups(rows)
  expect(groups).toHaveLength(4)
  expect(groups[0]).toMatchObject({ caseId: 'notification-2', arm: 'B0', protocol: V1, attempted: 2,
    valid: 1, completed: 1, unresolved: 1, triggered: 1, scheduled: 2 })
  expect(groups[1]).toMatchObject({ caseId: 'notification-2', arm: 'P1', protocol: V2, attempted: 1, completed: 1 })
  expect(groups[2]).toMatchObject({ caseId: 'healthy', arm: 'B0', attempted: 1, completed: 1 })
})

it.each([
  ['wrong campaign', (s: Record<string, unknown>) => { s.campaign_id = 'other-campaign' }],
  ['ordinary acceptance claim', (s: Record<string, unknown>) => { s.ordinary_policy_accepted = true }],
  ['a policy differing between arms', (s: Record<string, unknown>) => { (s.trial_rows as ContextTrial[])[1].trial.policy_hash = 'b'.repeat(64) }],
  ['a protocol that does not match its arm', (s: Record<string, unknown>) => { (s.trial_rows as ContextTrial[])[1].actor_context_protocol = V1 }],
  ['two arms sharing one protocol', (s: Record<string, unknown>) => { s.protocol_by_arm = { B0: V1, P1: V1 } }],
  ['a trial from an undeclared arm', (s: Record<string, unknown>) => { (s.trial_rows as ContextTrial[])[1].trial.arm = 'L' }],
  ['duplicate trial', (s: Record<string, unknown>) => { (s.trial_rows as ContextTrial[]).push((s.trial_rows as ContextTrial[])[0]) }],
  ['invalid trial', (s: Record<string, unknown>) => { (s.trial_rows as ContextTrial[])[0].trial.trial_index = 99 }],
  ['invalid usage', (s: Record<string, unknown>) => { s.usage = { model_calls: -1 } }],
  ['unrelated remote evidence', (s: Record<string, unknown>) => { s.evidence = { 'episode-other': 'weave_verified' } }],
] as const)('rejects %s instead of displaying a context comparison', (_, change) => {
  const saved = study(); change(saved as unknown as Record<string, unknown>)
  expect(() => validateContextStudies([saved], campaign.campaign_id)).toThrow(/Malformed/)
})

it.each([
  ['an unfinished study', (s: Record<string, unknown>) => { s.status = 'RUNNING' }],
  ['a disagreeing assessment', (s: Record<string, unknown>) => { (s.assessment as Record<string, unknown>).decision = 'NO_CHANGE' }],
  ['no completion advantage', (s: Record<string, unknown>) => { (s.assessment as Record<string, unknown>).primary_completions = { B0: 1, P1: 1 } }],
  ['a recorded case regression', (s: Record<string, unknown>) => { (s.assessment as Record<string, unknown>).regressed_case_ids = ['healthy'] }],
  ['a violation in the changed arm', (s: Record<string, unknown>) => { (s.trial_rows as ContextTrial[])[1].trial.outcome = 'VIOLATION' }],
  ['no comparable primary case', (s: Record<string, unknown>) => { (s.assessment as Record<string, unknown>).primary_case_ids = [] }],
] as const)('rejects a claimed improvement with %s', (_, change) => {
  const saved = improved(); change(saved as unknown as Record<string, unknown>)
  expect(() => validateContextStudies([saved], campaign.campaign_id)).toThrow(/Malformed/)
})

it('validates the requested study identity, accepts a pending assessment, and rejects duplicate studies', () => {
  const saved = { ...study(), status: 'RUNNING' as const, decision: 'PENDING' as const, assessment: null }
  expect(validateContextStudy(saved, campaign.campaign_id, saved.study_id).assessment).toBeNull()
  expect(() => validateContextStudy(saved, campaign.campaign_id, 'wrong-id')).toThrow(/identity/)
  expect(() => validateContextStudies([saved, saved], campaign.campaign_id)).toThrow(/Malformed/)
})

function stub(payload: unknown) {
  const calls: { url: string; method: string }[] = []
  vi.stubGlobal('fetch', vi.fn(async (url: string, options?: { method?: string }) => {
    calls.push({ url, method: options?.method ?? 'GET' })
    return { ok: true, json: async () => payload }
  }))
  return calls
}

it('shows both protocols, the mechanism counts and the honesty disclaimer, and issues no writes', async () => {
  const calls = stub([improved()])
  render(<ContextStudyPanel campaignId={campaign.campaign_id} onEpisode={() => {}} />)
  await screen.findByText('context-study-fixture')
  expect(screen.getByText(/baseline engineering on the agent's input/i)).toBeTruthy()
  expect(screen.getByText(/Nothing here proposes, accepts or activates a recovery policy/i)).toBeTruthy()
  expect(screen.getAllByText(V1).length).toBeGreaterThan(0)
  expect(screen.getAllByText(V2).length).toBeGreaterThan(0)
  expect(screen.getByText(/Status reads before any write/i)).toBeTruthy()
  expect(screen.getByText(/B0 0 · P1 1 of 3 paired trials/)).toBeTruthy()
  await waitFor(() => expect(calls.length).toBeGreaterThan(0))
  expect(calls.every(call => call.method === 'GET')).toBe(true)
  expect(calls[0].url).toBe(`/api/campaigns/${campaign.campaign_id}/context-studies`)
  expect(screen.queryByRole('button', { name: /start|run|accept|promote/i })).toBeNull()
})

it('names incomplete cases instead of hiding them, and empties on a campaign change', async () => {
  const saved = study()
  saved.assessment = { ...saved.assessment!, incomplete_case_ids: ['notification-18'] }
  stub([saved])
  const view = render(<ContextStudyPanel campaignId={campaign.campaign_id} onEpisode={() => {}} />)
  const notice = await screen.findByText(/excluded from the decision/i)
  expect(notice.textContent).toContain('notification-18')
  view.rerender(<ContextStudyPanel campaignId="campaign-other" onEpisode={() => {}} />)
  expect(screen.queryByText('context-study-fixture')).toBeNull()
})

it('reports an empty study list without inventing a result', async () => {
  stub([])
  render(<ContextStudyPanel campaignId={campaign.campaign_id} onEpisode={() => {}} />)
  await screen.findByText(/No attempt-context study recorded/i)
})
