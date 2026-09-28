// @vitest-environment jsdom
import { createElement as h } from 'react'
import { cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import type { Matrix } from '../src/api'
import { OutcomeMatrix } from '../src/components/OutcomeMatrix'
import { matrix } from './fixtures'

afterEach(cleanup)

it('distinguishes full, partial and absent fault triggers while preserving the recorded outcomes and drilldown', () => {
  const selected = vi.fn()
  const base = matrix.cells[0]
  const current: Matrix = { ...matrix, counts: { ...matrix.counts, scheduled: 3, triggered: 1, untriggered: 2, partially_triggered: 1, none_triggered: 1 }, cells: [
    { ...base, episode_id: 'episode-full', scenario_alias: 'full', fault_scheduled: true, fault_triggered: true, fault_count: 2, triggered_fault_count: 2 },
    { ...base, episode_id: 'episode-partial', scenario_alias: 'partial', fault_scheduled: true, fault_triggered: false, fault_count: 2, triggered_fault_count: 1 },
    { ...base, episode_id: 'episode-none', scenario_alias: 'none', fault_scheduled: true, fault_triggered: false, fault_count: 2, triggered_fault_count: 0, outcome: 'VIOLATION' },
    { ...base, episode_id: 'episode-healthy', scenario_alias: 'healthy', fault_count: 0, triggered_fault_count: 0 },
  ] }
  render(h(OutcomeMatrix, { matrix: { data: current, error: null, loading: false }, selectedEpisode: null, onEpisode: selected }))
  expect(screen.getByText('All scheduled faults triggered')).toBeTruthy()
  expect(screen.getByText('Partially triggered · 1 / 2')).toBeTruthy()
  expect(screen.getByText('Scheduled · none triggered')).toBeTruthy()
  expect(screen.getByText('Healthy / no scheduled fault')).toBeTruthy()
  expect(screen.getByText(/fully triggered: 1 · partially triggered: 1 · none triggered: 1/)).toBeTruthy()
  expect(screen.queryByText(/untriggered:/)).toBeNull()
  const partialRow = screen.getByRole('row', { name: /episode-partial/ })
  expect(within(partialRow).getByText('Completed')).toBeTruthy()
  expect(within(screen.getByRole('row', { name: /episode-none/ })).getByText('Violation')).toBeTruthy()
  fireEvent.click(within(partialRow).getByRole('button'))
  expect(selected).toHaveBeenCalledExactlyOnceWith('episode-partial')
})

it.each([{}, { fault_count: 2 }, { triggered_fault_count: 1 }])('does not infer none triggered from a legacy or incomplete count projection %j', optionalCounts => {
  const current: Matrix = { ...matrix, counts: { ...matrix.counts, scheduled: 3, triggered: 1, untriggered: 2 }, cells: [
    { ...matrix.cells[0], fault_scheduled: true, fault_triggered: false, ...optionalCounts },
  ] }
  render(h(OutcomeMatrix, { matrix: { data: current, error: null, loading: false }, selectedEpisode: null, onEpisode: vi.fn() }))
  expect(screen.getByText('Not fully triggered')).toBeTruthy()
  expect(screen.getByText(/fully triggered: 1 · not fully triggered: 2/)).toBeTruthy()
  expect(screen.queryByText(/none triggered/)).toBeNull()
  expect(screen.queryByText(/partially triggered:/)).toBeNull()
})

it('keeps fully triggered legacy rows explicit without requiring new fields', () => {
  const current = { ...matrix, cells: [{ ...matrix.cells[0], fault_scheduled: true, fault_triggered: true }] }
  render(h(OutcomeMatrix, { matrix: { data: current, error: null, loading: false }, selectedEpisode: null, onEpisode: vi.fn() }))
  expect(screen.getByText('All scheduled faults triggered')).toBeTruthy()
})
