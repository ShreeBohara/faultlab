// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import { CompletionStudyPanel } from '../src/components/CompletionStudyPanel'
import { completionGroups, validateCompletionStudies, validateCompletionStudy } from '../src/completion'
import type { CompletionStudy, CompletionTrial } from '../src/completion'
import { campaign, hash } from './fixtures'

afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals() })

function row(id: string, arm: 'B0' | 'L', outcome: 'COMPLETED' | 'SAFE_UNRESOLVED' | 'VIOLATION' = 'COMPLETED', stage = 'validation'): CompletionTrial {
  return { stage, case_id: 'notification-2', trial: { episode_id: id, world_id: `world-${id}`, scenario_hash: hash,
    policy_hash: arm === 'B0' ? hash : 'b'.repeat(64), arm, trial_index: 0,
    lifecycle: 'COMPLETED', outcome, fault_scheduled: true, fault_triggered: true,
    failed_checks: outcome === 'VIOLATION' ? ['C6'] : [], usage: { model_calls: 8 } } }
}
function study(): CompletionStudy {
  return { schema_version: 'faultlab-completion-study/v1', study_id: 'completion-study-fixture', campaign_id: campaign.campaign_id,
    status: 'COMPLETED', stage: 'validation', decision: 'NO_CHANGE', reason: 'Candidate truthfulness check failed.',
    ordinary_policy_accepted: false, configuration_hash: hash, incumbent_hash: hash, model: 'fixture-model',
    trial_rows: [row('episode-before', 'B0', 'SAFE_UNRESOLVED'), row('episode-after', 'L', 'VIOLATION'), row('episode-control', 'B0', 'COMPLETED', 'controls')],
    candidates: [{ proposal_ref: 'proposal-fixture', policy_version: 'policy-candidate', policy_hash: 'b'.repeat(64), decision: 'NO_CHANGE', reason: 'C6 failed.' }],
    validation_assessment: { decision: 'NO_CHANGE', reason: 'The generated report cites an unknown receipt.', by_case: {} },
    evidence: { 'episode-before': 'weave_verified', 'episode-after': 'weave_verified' }, charged_model_calls: 25, usage: { model_calls: 24 } }
}

it('keeps stage, case and exact policy counts separate, including unfinished and untriggered attempts', () => {
  const rows = study().trial_rows
  rows.push({ ...row('episode-untriggered', 'B0'), trial: { ...row('episode-untriggered', 'B0').trial, fault_triggered: false } })
  rows.push({ ...row('episode-error', 'L'), trial: { ...row('episode-error', 'L').trial, lifecycle: 'LAB_ERROR', outcome: null } })
  const groups = completionGroups(rows)
  expect(groups).toHaveLength(3)
  expect(groups[0]).toMatchObject({ stage: 'validation', arm: 'B0', attempted: 2, valid: 1, completed: 1, unresolved: 1, triggered: 1, scheduled: 2 })
  expect(groups[1]).toMatchObject({ stage: 'validation', arm: 'L', attempted: 2, valid: 1, completed: 0, violations: 1 })
  expect(groups[2]).toMatchObject({ stage: 'controls', arm: 'B0', attempted: 1, completed: 1 })
})

it.each([
  ['wrong campaign', (s: Record<string, unknown>) => { s.campaign_id = 'other-campaign' }],
  ['ordinary acceptance claim', (s: Record<string, unknown>) => { s.ordinary_policy_accepted = true }],
  ['invalid usage', (s: Record<string, unknown>) => { s.usage = { model_calls: -1 } }],
  ['invalid trial', (s: Record<string, unknown>) => { (s.trial_rows as CompletionTrial[])[0].trial.trial_index = 99 }],
  ['duplicate trial', (s: Record<string, unknown>) => { (s.trial_rows as CompletionTrial[]).push((s.trial_rows as CompletionTrial[])[0]) }],
  ['unlinked candidate', (s: Record<string, unknown>) => { s.candidates = [] }],
  ['wrong incumbent', (s: Record<string, unknown>) => { s.incumbent_hash = 'c'.repeat(64) }],
  ['unrelated remote evidence', (s: Record<string, unknown>) => { s.evidence = { 'episode-other': 'weave_verified' } }],
  ['replay hash without replay_of', (s: Record<string, unknown>) => { s.replay_policy_hash = 'd'.repeat(64) }],
  ['replay_of without its hash', (s: Record<string, unknown>) => { s.replay_of = 'policy-x' }],
] as const)('rejects %s instead of displaying a completion gain', (_, change) => {
  const saved = study(); change(saved as unknown as Record<string, unknown>)
  expect(() => validateCompletionStudies([saved], campaign.campaign_id)).toThrow(/Malformed/)
})

it('validates the requested study identity, accepts null pending assessment, and rejects duplicate studies', () => {
  const saved = { ...study(), status: 'RUNNING', decision: 'PENDING', validation_assessment: null }
  expect(validateCompletionStudy(saved, campaign.campaign_id, saved.study_id).validation_assessment).toBeNull()
  expect(() => validateCompletionStudy(saved, campaign.campaign_id, 'wrong-id')).toThrow(/identity/)
  expect(() => validateCompletionStudies([saved, saved], campaign.campaign_id)).toThrow(/Malformed/)
})

function observedStudy(): CompletionStudy {
  const saved = study()
  saved.decision = 'OBSERVED_IMPROVEMENT'
  saved.validation_assessment = { decision: 'OBSERVED_IMPROVEMENT', reason: 'Recorded fixed development validation decision.', by_case: {} }
  saved.selected_candidate_version = 'policy-candidate'; saved.selected_candidate_hash = 'b'.repeat(64)
  saved.trial_rows[1] = row('episode-after', 'L', 'COMPLETED')
  return saved
}

function observedReplay(): CompletionStudy {
  const saved = observedStudy()
  saved.candidates = []
  saved.replay_of = 'policy-replayed'
  saved.replay_policy_hash = saved.selected_candidate_hash
  delete saved.selected_candidate_version
  delete saved.selected_candidate_hash
  // A replay runs only validation; it does not repeat controls or propose a policy.
  saved.trial_rows = saved.trial_rows.filter(row => row.stage === 'validation')
  return saved
}

it('allows an observed completion result with original baseline violations and candidate safety preserved', () => {
  const saved = observedStudy()
  saved.trial_rows[0] = row('episode-before', 'B0', 'VIOLATION')
  expect(validateCompletionStudy(saved, campaign.campaign_id).decision).toBe('OBSERVED_IMPROVEMENT')
  expect(saved.trial_rows[0].trial.failed_checks).toEqual(['C6'])
})

it('accepts observed improvement from the exact replayed policy without inventing a selected candidate', () => {
  const saved = observedReplay()
  const parsed = validateCompletionStudy(saved, campaign.campaign_id, saved.study_id)
  expect(parsed.decision).toBe('OBSERVED_IMPROVEMENT')
  expect(parsed.replay_policy_hash).toBe('b'.repeat(64))
  expect(parsed.selected_candidate_hash).toBeUndefined()
  expect(parsed.candidates).toEqual([])
  expect(parsed.ordinary_policy_accepted).toBe(false)
})

it.each([
  ['mismatched replay hash', (s: CompletionStudy) => { s.replay_policy_hash = 'c'.repeat(64) }],
  ['malformed replay hash', (s: CompletionStudy) => { s.replay_policy_hash = 'not-a-policy-hash' }],
  ['missing replay identity', (s: CompletionStudy) => { delete s.replay_of }],
  ['missing replay hash', (s: CompletionStudy) => { delete s.replay_policy_hash }],
  ['a different candidate trial', (s: CompletionStudy) => { s.trial_rows[1].trial.policy_hash = 'c'.repeat(64) }],
  ['missing candidate evidence', (s: CompletionStudy) => { delete s.evidence['episode-after'] }],
  ['missing baseline evidence', (s: CompletionStudy) => { delete s.evidence['episode-before'] }],
  ['local-only candidate evidence', (s: CompletionStudy) => { s.evidence['episode-after'] = 'local_only' }],
  ['a candidate check failure', (s: CompletionStudy) => { s.trial_rows[1].trial.failed_checks = ['C6'] }],
  ['an untriggered candidate fault', (s: CompletionStudy) => { s.trial_rows[1].trial.fault_triggered = false }],
  ['an unfinished baseline trial', (s: CompletionStudy) => { s.trial_rows[0].trial.lifecycle = 'INTERRUPTED' }],
  ['a negative validation decision', (s: CompletionStudy) => { s.validation_assessment!.decision = 'NO_CHANGE' }],
  ['ordinary proposals attached', (s: CompletionStudy) => { s.candidates = study().candidates }],
] as const)('withholds a positive replay with %s', (_, change) => {
  const saved = observedReplay(); change(saved)
  expect(() => validateCompletionStudy(saved, campaign.campaign_id)).toThrow(/Malformed/)
})

it('renders a saved successful replay read-only without a malformed-data warning', async () => {
  const saved = observedReplay()
  vi.stubGlobal('fetch', vi.fn(async () => ({ ok: true, json: async () => [saved] })))
  render(<CompletionStudyPanel campaignId={campaign.campaign_id} activePolicy="policy-v0" onEpisode={vi.fn()} />)
  await screen.findByRole('table')
  expect(screen.getByText(/^Study decision:/).textContent).toContain('observed improvement')
  expect(screen.queryByRole('alert')).toBeNull()
  expect(screen.queryByText('Generated candidates')).toBeNull()
  expect(vi.mocked(fetch).mock.calls.every(([, options]) => options?.method === 'GET')).toBe(true)
})

it.each([
  ['running study', (s: CompletionStudy) => { s.status = 'RUNNING' }],
  ['missing validation assessment', (s: CompletionStudy) => { s.validation_assessment = null }],
  ['negative validation decision', (s: CompletionStudy) => { s.validation_assessment!.decision = 'NO_CHANGE' }],
  ['missing selected version', (s: CompletionStudy) => { delete s.selected_candidate_version }],
  ['wrong selected hash', (s: CompletionStudy) => { s.selected_candidate_hash = 'c'.repeat(64) }],
  ['ambiguous selected candidate', (s: CompletionStudy) => { s.candidates.push(s.candidates[0]) }],
  ['empty validation', (s: CompletionStudy) => { s.trial_rows.forEach(row => { row.stage = 'controls' }) }],
  ['local-only validation', (s: CompletionStudy) => { s.evidence['episode-after'] = 'local_only' }],
  ['candidate violation', (s: CompletionStudy) => { s.trial_rows[1].trial.outcome = 'VIOLATION' }],
  ['candidate failed check', (s: CompletionStudy) => { s.trial_rows[1].trial.failed_checks = ['C6'] }],
  ['unfinished baseline trial', (s: CompletionStudy) => { s.trial_rows[0].trial.lifecycle = 'INTERRUPTED' }],
  ['untriggered baseline', (s: CompletionStudy) => { s.trial_rows[0].trial.fault_triggered = false }],
] as const)('withholds an inconsistent positive result with %s', (_, change) => {
  const saved = observedStudy(); change(saved)
  expect(() => validateCompletionStudy(saved, campaign.campaign_id)).toThrow(/Malformed/)
})

it('loads saved evidence read-only, keeps completion and invariant repair separate, and opens original episodes', async () => {
  const requests: { url: string; method: string }[] = []
  const select = vi.fn()
  vi.stubGlobal('fetch', vi.fn(async (url: string, options: RequestInit) => { requests.push({ url: String(url), method: options.method! }); return { ok: true, json: async () => [study()] } }))
  render(<CompletionStudyPanel campaignId={campaign.campaign_id} activePolicy="policy-v0" onEpisode={select} />)
  const table = await screen.findByRole('table')
  expect(within(table).getAllByRole('row')).toHaveLength(4)
  expect(screen.getByText(/does not accept a policy through the invariant-repair gates/).textContent).toContain('policy-v0')
  expect(screen.getByText(/A completed study is not a completed task/)).toBeTruthy()
  expect(screen.getByText(/2 verified \/ 3 recorded trials/)).toBeTruthy()
  expect(screen.getByRole('link', { name: /Open saved proposal/ }).getAttribute('href')).toBe('/api/policies/policy-candidate/proposal')
  fireEvent.click(screen.getByText('Open original trial evidence · 3 recorded'))
  fireEvent.click(screen.getByRole('button', { name: 'episode-after', exact: true }))
  expect(select).toHaveBeenCalledWith('episode-after')
  expect(requests).toEqual([{ url: `/api/campaigns/${campaign.campaign_id}/completion-studies`, method: 'GET' }])
  expect(screen.queryByRole('button', { name: /start|run|accept|promote/i })).toBeNull()
})

it('does not display another campaign and hides old results immediately after switching campaigns', async () => {
  let resolveNext!: (value: unknown) => void
  const next = new Promise(resolve => { resolveNext = resolve })
  vi.stubGlobal('fetch', vi.fn(async (url: string) => ({ ok: true, json: async () => url.includes('campaign-other') ? next : [study()] })))
  const view = render(<CompletionStudyPanel campaignId={campaign.campaign_id} activePolicy="policy-v0" onEpisode={vi.fn()} />)
  await screen.findByRole('table')
  view.rerender(<CompletionStudyPanel campaignId="campaign-other" activePolicy="policy-v0" onEpisode={vi.fn()} />)
  expect(screen.queryByRole('table')).toBeNull()
  resolveNext([study()])
  await screen.findByRole('alert')
  expect(screen.queryByRole('table')).toBeNull()
  expect(vi.mocked(fetch).mock.calls.every(([, options]) => options?.method === 'GET')).toBe(true)
})

it('shows a pending or empty study without inventing a result or launching work', async () => {
  vi.stubGlobal('fetch', vi.fn(async () => ({ ok: true, json: async () => [] })))
  render(<CompletionStudyPanel campaignId={campaign.campaign_id} activePolicy="policy-v0" onEpisode={vi.fn()} />)
  await screen.findByText('No completion study recorded for this campaign.')
  expect(screen.queryByRole('table')).toBeNull()
  await waitFor(() => expect(vi.mocked(fetch).mock.calls.every(([, options]) => options?.method === 'GET')).toBe(true))
})

it('shows actual running progress instead of repeating the original no-calls admission note', async () => {
  const saved = { ...study(), status: 'RUNNING', stage: 'controls', decision: 'PENDING', validation_assessment: null,
    reason: 'Complete conditional experiment admitted; no calls started' }
  vi.stubGlobal('fetch', vi.fn(async () => ({ ok: true, json: async () => [saved] })))
  render(<CompletionStudyPanel campaignId={campaign.campaign_id} activePolicy="policy-v0" onEpisode={vi.fn()} />)
  const progress = await screen.findByText(/^Study decision:/)
  expect(progress.textContent).toContain('Current stage: controls; 3 trial results saved. The study is still running.')
  expect(progress.textContent).not.toContain('no calls started')
  expect(screen.getByText('Inspect complete saved completion study').parentElement?.textContent).toContain(saved.reason)
  expect(saved.reason).toBe('Complete conditional experiment admitted; no calls started')
})

it('shows the recorded source-assessment reason when no separate candidate reason was saved', async () => {
  const saved = study()
  delete saved.candidates[0].reason
  saved.candidates[0].source_assessment = { decision: 'NO_CHANGE', reason: 'Completion gap or candidate recovery did not reproduce in all three pairs', by_case: {} }
  vi.stubGlobal('fetch', vi.fn(async () => ({ ok: true, json: async () => [saved] })))
  render(<CompletionStudyPanel campaignId={campaign.campaign_id} activePolicy="policy-v0" onEpisode={vi.fn()} />)
  expect(await screen.findByText(saved.candidates[0].source_assessment.reason, { exact: true })).toBeTruthy()
  expect(screen.queryByText('No further reason recorded.')).toBeNull()
  expect(saved.candidates[0].reason).toBeUndefined()
  expect(() => validateCompletionStudy({ ...saved, candidates: [{ ...saved.candidates[0], source_assessment: { reason: 42 } }] }, campaign.campaign_id)).toThrow(/Malformed/)
})

it('explains an incomplete study with an untriggered fault without changing its original task result', async () => {
  const saved = study()
  saved.status = 'INCOMPLETE'; saved.decision = 'INCOMPLETE'
  saved.reason = 'Execution or evidence failed; every attempted trial retained without retry'
  saved.validation_assessment = null
  saved.trial_rows = [{ ...row('episode-untriggered', 'B0', 'SAFE_UNRESOLVED', 'controls'), trial: { ...row('episode-untriggered', 'B0', 'SAFE_UNRESOLVED').trial, fault_triggered: false } }]
  saved.evidence = {}
  vi.stubGlobal('fetch', vi.fn(async () => ({ ok: true, json: async () => [saved] })))
  render(<CompletionStudyPanel campaignId={campaign.campaign_id} activePolicy="policy-v0" onEpisode={vi.fn()} />)
  await screen.findByText('A scheduled fault did not trigger; the study stopped without replacing that trial. Its original task result is preserved below.')
  fireEvent.click(screen.getByText('Open original trial evidence · 1 recorded'))
  expect(screen.getAllByText('Safe unresolved')).toHaveLength(2)
  expect(screen.getByText('Inspect complete saved completion study').parentElement?.textContent).toContain(saved.reason)
  expect(saved.trial_rows[0].trial.outcome).toBe('SAFE_UNRESOLVED')
  expect(saved.reason).toBe('Execution or evidence failed; every attempted trial retained without retry')
})

it('accepts a replay study, whose candidate-arm trials carry the replayed policy hash and whose candidates list is empty', () => {
  const saved = study() as unknown as Record<string, unknown>
  const replayHash = (saved.trial_rows as CompletionTrial[])
    .filter(row => row.trial.arm === 'L').map(row => row.trial.policy_hash)[0]
  saved.candidates = []
  saved.replay_of = 'policy-replayed'
  saved.replay_policy_hash = replayHash
  delete saved.selected_candidate_version
  delete saved.selected_candidate_hash
  const parsed = validateCompletionStudy(saved, campaign.campaign_id, saved.study_id as string)
  expect(parsed.candidates).toHaveLength(0)
  expect(parsed.trial_rows.some(row => row.trial.arm === 'L')).toBe(true)
  // An ordinary study with an empty candidates list is still malformed.
  const ordinary = study() as unknown as Record<string, unknown>
  ordinary.candidates = []
  expect(() => validateCompletionStudy(ordinary, campaign.campaign_id, ordinary.study_id as string)).toThrow(/Malformed/)
})
