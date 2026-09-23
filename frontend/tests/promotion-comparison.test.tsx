// @vitest-environment jsdom
import { cleanup, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import { PromotionComparison, promotionComparison } from '../src/components/PromotionComparison'
import { RunSummary } from '../src/components/RunSummary'
import type { Matrix, MatrixCell } from '../src/api'
import type { EvaluationBatch, PolicyVersion } from '../src/generated/contracts'
import { baseline, campaign } from './fixtures'

afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals() })

function records(decision: PolicyVersion['decision'] = 'REJECTED') {
  const candidate: PolicyVersion = { ...baseline, version: 'policy-candidate', parent_version: baseline.version,
    policy_hash: 'b'.repeat(64), author: 'mechanic', decision, decision_ref: 'decision-promotion',
    development_episode_ids: ['episode-development'], evaluation_refs: ['batch-promotion'] }
  const cell = (id: string, before: boolean, index: number): MatrixCell => ({ episode_id: id,
    scenario_alias: `scenario-${Math.floor(index / 3)}`, arm: before ? 'B0' : 'L',
    policy_hash: before ? baseline.policy_hash! : candidate.policy_hash!,
    outcome: before && index % 2 === 0 ? 'VIOLATION' : 'COMPLETED', lifecycle: 'COMPLETED',
    fault_scheduled: true, fault_triggered: true, source_mode: 'live', telemetry_provenance: 'weave_verified',
    usage: { http_attempts: before ? 4 : 3, model_calls: 6 } })
  const cells: MatrixCell[] = []
  const pairs: [string, string][] = []
  for (let index = 0; index < 18; index++) {
    const previous = `episode-before-${index}`, proposed = `episode-after-${index}`
    cells.push(cell(previous, true, index), cell(proposed, false, index))
    pairs.push(index % 2 ? [proposed, previous] : [previous, proposed])
  }
  cells.push({ ...cell('episode-development', false, 0), outcome: 'VIOLATION', usage: { http_attempts: 900 } })
  cells.push({ ...cell('episode-unrelated', true, 0), outcome: 'COMPLETED', usage: { http_attempts: 1000 } })
  const matrix: Matrix = { campaign_id: campaign.campaign_id, cells, counts: { valid_attempted: 500, completed: 400, violations: 100 } }
  const batch: EvaluationBatch = { batch_id: 'batch-promotion', purpose: 'promotion', split: 'promotion',
    candidate_hash: candidate.policy_hash!, incumbent_hash: baseline.policy_hash!, manifest_hash: 'c'.repeat(64),
    scorer_hash: 'd'.repeat(64), contract_hash: 'e'.repeat(64), model_hash: 'f'.repeat(64),
    trial_pairs: pairs, trials: [], usage: { http_attempts: 2026 }, decision: 'NO_CHANGE',
    reason: 'Complete repeated evidence; fixed promotion predicate still required' }
  return { candidate, matrix, batch }
}

it('counts only exact pairs, maps reversed order by policy hash, and excludes unrelated trials and retry totals', () => {
  const { candidate, matrix, batch } = records()
  const result = promotionComparison(batch, matrix, candidate, baseline, campaign.campaign_id)
  expect(result).toEqual({ status: 'available', pairs: 18,
    before: { trials: 18, completed: 9, violations: 9, safeUnresolved: 0, correctlyRejected: 0, httpAttempts: 72 },
    after: { trials: 18, completed: 18, violations: 0, safeUnresolved: 0, correctlyRejected: 0, httpAttempts: 54 } })
})

it.each([
  ['missing paired episode', (matrix: Matrix) => { matrix.cells.shift() }],
  ['duplicate ledger episode', (matrix: Matrix) => { matrix.cells.push(matrix.cells[0]) }],
  ['wrong policy hash', (matrix: Matrix) => { matrix.cells[0].policy_hash = 'f'.repeat(64) }],
  ['offline reference', (matrix: Matrix) => { matrix.cells[0].source_mode = 'offline_fixture' }],
  ['replay', (matrix: Matrix) => { matrix.cells[0].source_mode = 'replay' }],
  ['unfinished episode', (matrix: Matrix) => { matrix.cells[0].lifecycle = 'RUNNING' }],
  ['missing outcome', (matrix: Matrix) => { matrix.cells[0].outcome = null }],
  ['untriggered fault', (matrix: Matrix) => { matrix.cells[0].fault_triggered = false }],
  ['missing HTTP usage', (matrix: Matrix) => { matrix.cells[0].usage = {} }],
  ['different paired scenario', (matrix: Matrix) => { matrix.cells[0].scenario_alias = 'other-scenario' }],
] as const)('withholds a comparison for %s', (_, change) => {
  const { candidate, matrix, batch } = records()
  change(matrix)
  const result = promotionComparison(batch, matrix, candidate, baseline, campaign.campaign_id)
  expect(result.status).toBe('unavailable')
  expect(result).not.toHaveProperty('before')
  expect(result).not.toHaveProperty('after')
})

it('rejects duplicated pair IDs, unrelated batch identities and a different campaign ledger', () => {
  const { candidate, matrix, batch } = records()
  expect(promotionComparison({ ...batch, trial_pairs: [batch.trial_pairs[0], ...batch.trial_pairs.slice(0, 17)] }, matrix, candidate, baseline, campaign.campaign_id).status).toBe('unavailable')
  expect(promotionComparison({ ...batch, batch_id: 'unlinked-batch' }, matrix, candidate, baseline, campaign.campaign_id).status).toBe('unavailable')
  expect(promotionComparison(batch, matrix, candidate, { ...baseline, policy_hash: 'f'.repeat(64) }, campaign.campaign_id).status).toBe('unavailable')
  expect(promotionComparison(batch, { ...matrix, campaign_id: 'other-campaign' }, candidate, baseline, campaign.campaign_id).status).toBe('unavailable')
})

it('separates an incomplete batch from a complete comparison without partial gain claims', () => {
  const { candidate, matrix, batch } = records()
  const result = promotionComparison({ ...batch, decision: 'INCOMPLETE', trial_pairs: batch.trial_pairs.slice(0, 2) }, matrix, candidate, baseline, campaign.campaign_id)
  expect(result.status).toBe('incomplete')
  expect(result.pairs).toBe(2)
  expect(result).not.toHaveProperty('before')
  expect(result).not.toHaveProperty('after')
})

it.each(['REJECTED', 'NO_CHANGE', 'INCOMPLETE'] as const)('shows that promotion was reached for a %s policy', decision => {
  const { candidate, matrix } = records(decision)
  render(<RunSummary campaign={campaign} matrix={matrix} policies={[baseline, candidate]} />)
  const stages = screen.getByRole('list', { name: 'Learning cycle evidence' })
  const promotion = within(stages).getAllByRole('listitem').at(-1)!
  expect(promotion.textContent).toContain('reached promotion')
  expect(promotion.textContent).not.toContain('Not run')
  expect(promotion.textContent).toContain(decision.toLowerCase().replaceAll('_', ' '))
  expect(screen.getByText(/Main-loop counts mix discovery/)).toBeTruthy()
  expect(screen.getByText(/No recovery policy has been accepted in this campaign/)).toBeTruthy()
})

it('loads only the existing read-only evaluation endpoint and displays exact before/after counts', async () => {
  const { candidate, matrix, batch } = records()
  const requests: { url: string; method: string }[] = []
  vi.stubGlobal('fetch', vi.fn(async (url: string, options: RequestInit) => {
    requests.push({ url: String(url), method: options.method! })
    return { ok: true, json: async () => batch }
  }))
  render(<PromotionComparison campaignId={campaign.campaign_id} matrix={matrix} policies={[baseline, candidate]} />)
  const table = await screen.findByRole('table')
  expect(within(table).getByText('Before · policy-v0')).toBeTruthy()
  expect(within(table).getByText('After · policy-candidate')).toBeTruthy()
  const rows = within(table).getAllByRole('row')
  expect(rows.find(row => row.textContent?.includes('HTTP requests'))?.textContent).toBe('HTTP requests7254')
  expect(screen.getByText('Recorded policy decision: rejected.', { exact: false })).toBeTruthy()
  expect(requests).toEqual([{ url: '/api/evaluations/batch-promotion', method: 'GET' }])
  expect(table.textContent).not.toContain('900')
  expect(table.textContent).not.toContain('2026')
  expect(table.textContent).not.toContain('%')
})

it('shows unavailable evidence instead of a table when an exact paired result is absent', async () => {
  const { candidate, matrix, batch } = records()
  matrix.cells.shift()
  vi.stubGlobal('fetch', vi.fn(async () => ({ ok: true, json: async () => batch })))
  const view = render(<PromotionComparison campaignId={campaign.campaign_id} matrix={matrix} policies={[baseline, candidate]} />)
  await screen.findByText('Comparison unavailable.')
  expect(screen.queryByRole('table')).toBeNull()
  expect(view.container.textContent).not.toContain('improved')
  expect(view.container.textContent).not.toContain('%')
})

it('does not request unrelated policies or interpret a missing evaluation reference as not run', async () => {
  const { candidate, matrix } = records()
  const fetch = vi.fn()
  vi.stubGlobal('fetch', fetch)
  render(<PromotionComparison campaignId={campaign.campaign_id} matrix={matrix} policies={[baseline,
    { ...candidate, evaluation_refs: [] },
    { ...candidate, version: 'unrelated-policy', development_episode_ids: ['episode-another-campaign'] }]} />)
  expect(screen.getByText(/Promotion was reached, but its evaluation reference is unavailable/)).toBeTruthy()
  await waitFor(() => expect(fetch).not.toHaveBeenCalled())
})
