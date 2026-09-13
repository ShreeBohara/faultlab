import { describe, expect, it } from 'vitest'
import { safeEvidenceUrl, validateConfig, validateEvents, validateMatrix } from '../src/api'
import { validateContract } from '../src/generated/validate'
import { pollDelay } from '../src/useResource'
import { cellOutcome } from '../src/components/OutcomeMatrix'
import { validateExperiments } from '../src/experiments'
import { baseline, campaign, config, episode, events, experiments, matrix } from './fixtures'

describe('canonical API contracts', () => {
  it('validates reviewed records and rejects nested corruption, unknown fields and bad timestamps', () => {
    expect(validateContract('Campaign', campaign)).toEqual(campaign)
    expect(validateContract('Episode', episode)).toEqual(episode)
    expect(validateContract('PolicyVersion', baseline)).toEqual(baseline)
    expect(() => validateContract('Campaign', { ...campaign, created_at: 'yesterday' })).toThrow('Malformed')
    expect(() => validateContract('Episode', { ...episode, report: { ...episode.report, overall: 'ASSUMED_SUCCESS' } })).toThrow('Malformed')
    expect(() => validateContract('Campaign', { ...campaign, secret: 'must never render' })).toThrow('Malformed')
    expect(() => validateContract('Campaign', { ...campaign, usage: { model_calls: -1 } })).toThrow('Malformed')
  })
  it('keeps every distinct outcome, pending and not-run state, without fabricating counts', () => {
    for (const outcome of ['COMPLETED', 'VIOLATION', 'SAFE_UNRESOLVED', 'CORRECTLY_REJECTED', 'LAB_ERROR']) {
      const cell = { ...matrix.cells[0], outcome }
      expect(validateMatrix({ ...matrix, cells: [cell] }).cells[0].outcome).toBe(outcome)
    }
    expect(cellOutcome({ ...matrix.cells[0], lifecycle: 'RUNNING', outcome: null })).toBe('RUNNING')
    expect(cellOutcome({ ...matrix.cells[0], episode_id: null, outcome: null })).toBe('NOT_RUN')
    expect(cellOutcome({ ...matrix.cells[0], lifecycle: 'INTERRUPTED', outcome: null })).toBe('INTERRUPTED')
    expect(() => validateMatrix({ ...matrix, counts: { valid_attempted: -1 } })).toThrow('Malformed')
    expect(() => validateMatrix({ ...matrix, cells: [{ ...matrix.cells[0], outcome: 'PROBABLY_GOOD' }] })).toThrow('Malformed')
  })
  it('preserves sequence gaps from hidden events but rejects duplicates, cross-episode events and stalls', () => {
    expect(validateEvents({ events, next_after: 5, has_more: false }, episode.episode_id, 0).next_after).toBe(5)
    expect(() => validateEvents({ events: [...events].reverse(), next_after: 5, has_more: false }, episode.episode_id, 0)).toThrow('ordering')
    expect(() => validateEvents({ events: [events[0], events[0]], next_after: 5, has_more: false }, episode.episode_id, 0)).toThrow('ordering')
    expect(() => validateEvents({ events, next_after: 5, has_more: false }, 'other-episode', 0)).toThrow('identity')
    expect(() => validateEvents({ events: [], next_after: 5, has_more: true }, episode.episode_id, 5)).toThrow('cursor')
    expect(() => validateEvents({ events: [{ ...events[0], visibility: 'PRIVATE_EVALUATOR' }], next_after: 1, has_more: false }, episode.episode_id, 0)).toThrow('identity')
  })
  it('renders empty experiments and rejects malformed projections', () => {
    expect(validateExperiments(experiments)).toEqual(experiments)
    expect(() => validateExperiments({ ...experiments, counterexamples: [{ counterexample: {} }] })).toThrow('Malformed')
    expect(validateConfig(config)).toEqual(config)
    expect(() => validateConfig({ ...config, live_enabled: 'true' })).toThrow('Malformed')
  })
  it('allows actual HTTPS W&B record links only', () => {
    expect(safeEvidenceUrl('https://wandb.ai/team/project/runs/record')).toBe('https://wandb.ai/team/project/runs/record')
    for (const value of ['javascript:alert(1)', 'https://wandb.ai.evil.com/run', 'https://wandb.ai/', 'https://user:pass@wandb.ai/run', 'http://wandb.ai/run']) expect(safeEvidenceUrl(value)).toBeNull()
  })
  it('uses the declared polling cadence and capped error backoff', () => { expect([0, 1, 2, 3, 4].map(pollDelay)).toEqual([750, 1500, 3000, 6000, 6000]) })
})

import { testedExperiment } from './fixtures'
it('retains reduction failures, exact diagnosis scope and challenge counterexample lineage', () => {
  const result = validateExperiments({ ...experiments, counterexamples: [testedExperiment] })
  expect(result.counterexamples[0].reduction?.attempts[0].retained).toBe(false)
  expect(result.counterexamples[0].counterexample.reproduction_trial_ids).toHaveLength(3)
  expect(result.counterexamples[0].diagnostics[0].kind).toBe('INCONCLUSIVE')
  expect(result.counterexamples[0].challenges[0].status).toBe('COUNTEREXAMPLE_FOUND')
  for (const status of ['REDUCED', 'LOCALLY_MINIMAL', 'FLAKY', 'INCOMPLETE', 'NO_REDUCTION']) expect(validateContract('ReductionResult', { ...testedExperiment.reduction, status })).toBeTruthy()
})
