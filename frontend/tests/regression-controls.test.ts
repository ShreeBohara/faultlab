// @vitest-environment jsdom
import { createElement as h } from 'react'
import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import { api } from '../src/api'
import { RegressionControls } from '../src/components/RegressionControls'
import type { AgentRegistration, PolicyVersion, RegressionBundle, RegressionExecution } from '../src/generated/contracts'
import { validateContract } from '../src/generated/validate'
import { baseline, bundle, config, registration, regressionCase } from './fixtures'

afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals(); vi.useRealTimers() })

const candidate = (decision: PolicyVersion['decision'], version = 'candidate'): PolicyVersion => ({ ...baseline, version, decision, author: 'mechanic' })
async function inspect(kind: RegressionBundle['artifact_kind'], policies: PolicyVersion[], replay = false) {
  const saved = validateContract<RegressionBundle>('RegressionBundle', { ...bundle, ...(kind ? { artifact_kind: kind } : {}) })
  const registered = validateContract<AgentRegistration>('AgentRegistration', registration)
  const execution: RegressionExecution = { execution_id: 'fresh-execution', bundle_id: saved.bundle_id, manifest_hash: saved.manifest_hash, registration_id: registered.registration_id, profile_id: saved.execution_profile_id, mode: 'FRESH_SANDBOX', explicit_action: true, policy_hash: saved.policy_hash, configuration_hash: saved.configuration_hash, declared_budget: saved.caps, usage: {}, episode_ids: [], world_ids: [], status: 'COMPLETED' }
  vi.spyOn(api, 'bundle').mockResolvedValue(saved)
  const execute = vi.spyOn(api, 'execute').mockResolvedValue(execution)
  vi.spyOn(api, 'execution').mockResolvedValue(execution)
  const props = { cases: [{ ...regressionCase, ...(kind ? { artifact_kind: kind } : {}) }], registrations: [registered], policies, config: { ...config, live_enabled: true, model_configured: true, execution_profiles: [{ profile_id: 'sandbox-v1', caps: saved.caps, requires_live: true }] }, replay, onEpisode: vi.fn() }
  const view = render(h(RegressionControls, props))
  fireEvent.change(screen.getByLabelText('Saved regression'), { target: { value: regressionCase.regression_id } })
  fireEvent.click(screen.getByRole('button', { name: 'Inspect saved bundle' }))
  await screen.findByText('sandbox-v1')
  expect(execute).not.toHaveBeenCalled()
  fireEvent.change(screen.getByLabelText('Reviewed agent'), { target: { value: registered.registration_id } })
  return { execute, props, view }
}

it.each(['REJECTED', 'INCOMPLETE', 'NO_CHANGE'] as const)('explicitly reruns the exact bundled %s candidate without promoting it', async decision => {
  const saved = candidate(decision)
  const { execute } = await inspect('candidate_comparison', [saved, candidate('PROPOSED', 'pending'), { ...baseline, version: 'other-hash', policy_hash: 'b'.repeat(64) }])
  expect(screen.getByText('Candidate comparison', { selector: 'dd' })).toBeTruthy()
  expect(screen.getByText(/does not accept or promote/)).toBeTruthy()
  const selector = screen.getByLabelText('Immutable policy')
  expect(within(selector).getAllByRole('option').map(option => (option as HTMLOptionElement).value)).toEqual(['', saved.version])
  const run = screen.getByRole('button', { name: /Run fresh regression/ }) as HTMLButtonElement
  expect(run.disabled).toBe(true)
  fireEvent.change(selector, { target: { value: saved.version } })
  expect(execute).not.toHaveBeenCalled()
  expect(run.disabled).toBe(false)
  fireEvent.click(run)
  await waitFor(() => expect(execute).toHaveBeenCalledExactlyOnceWith(regressionCase.regression_id, registration.registration_id, 'sandbox-v1', saved.version))
})

it('keeps accepted-policy bundles restricted to the exact accepted policy', async () => {
  const accepted = candidate('ACCEPTED', 'accepted')
  await inspect('accepted_policy_bundle', [baseline, accepted, candidate('REJECTED'), candidate('INCOMPLETE'), candidate('NO_CHANGE')])
  expect(screen.getByText('Accepted policy bundle', { selector: 'dd' })).toBeTruthy()
  expect(within(screen.getByLabelText('Immutable policy')).getAllByRole('option').map(option => (option as HTMLOptionElement).value)).toEqual(['', accepted.version])
})

it('does not offer pending, missing-content, or different-hash policies', async () => {
  const { execute } = await inspect('candidate_comparison', [candidate('PROPOSED'), { ...candidate('REJECTED', 'missing'), content: null }, { ...candidate('ACCEPTED', 'foreign'), policy_hash: 'b'.repeat(64) }])
  expect(within(screen.getByLabelText('Immutable policy')).getAllByRole('option')).toHaveLength(1)
  const run = screen.getByRole('button', { name: /Run fresh regression/ }) as HTMLButtonElement
  expect(run.disabled).toBe(true)
  fireEvent.click(run)
  expect(execute).not.toHaveBeenCalled()
})

it('keeps replay read-only even with a runnable rejected candidate selected', async () => {
  const saved = candidate('REJECTED')
  const { execute } = await inspect('candidate_comparison', [saved], true)
  fireEvent.change(screen.getByLabelText('Immutable policy'), { target: { value: saved.version } })
  const run = screen.getByRole('button', { name: /Run fresh regression/ }) as HTMLButtonElement
  expect(run.disabled).toBe(true)
  fireEvent.click(run)
  expect(execute).not.toHaveBeenCalled()
})

it('blocks a previously selected policy if it is no longer an eligible bundled decision', async () => {
  const saved = candidate('REJECTED')
  const { execute, view, props } = await inspect('candidate_comparison', [saved])
  fireEvent.change(screen.getByLabelText('Immutable policy'), { target: { value: saved.version } })
  view.rerender(h(RegressionControls, { ...props, policies: [candidate('PROPOSED')] }))
  const run = screen.getByRole('button', { name: /Run fresh regression/ }) as HTMLButtonElement
  expect(run.disabled).toBe(true)
  fireEvent.click(run)
  expect(execute).not.toHaveBeenCalled()
})

it('labels incident fixtures and preserves baseline execution eligibility', async () => {
  await inspect('incident_fixture', [baseline])
  expect(screen.getByText('Incident fixture', { selector: 'dd' })).toBeTruthy()
  fireEvent.change(screen.getByLabelText('Immutable policy'), { target: { value: baseline.version } })
  expect((screen.getByRole('button', { name: /Run fresh regression/ }) as HTMLButtonElement).disabled).toBe(false)
})

it('uses the backend-compatible interpretation of a legacy rejected-candidate bundle', async () => {
  const saved = candidate('REJECTED')
  await inspect(undefined, [saved])
  expect(screen.getByText('Candidate comparison', { selector: 'dd' })).toBeTruthy()
  fireEvent.change(screen.getByLabelText('Immutable policy'), { target: { value: saved.version } })
  expect((screen.getByRole('button', { name: /Run fresh regression/ }) as HTMLButtonElement).disabled).toBe(false)
})

const savedExecution: RegressionExecution = {
  execution_id: 'execution-saved', bundle_id: bundle.bundle_id, manifest_hash: bundle.manifest_hash,
  registration_id: registration.registration_id, profile_id: bundle.execution_profile_id,
  mode: 'FRESH_SANDBOX', explicit_action: true, policy_hash: bundle.policy_hash,
  configuration_hash: bundle.configuration_hash, declared_budget: bundle.caps,
  usage: { model_calls: 24, http_attempts: 21 }, status: 'COMPLETED',
  episode_ids: ['episode-saved-1', 'episode-saved-2', 'episode-saved-3'],
  world_ids: ['world-saved-1', 'world-saved-2', 'world-saved-3'],
}

async function requestSaved(value = savedExecution, replay = false) {
  const inspected = await inspect('incident_fixture', [baseline], replay)
  vi.mocked(api.execution).mockRestore()
  const fetch = vi.fn(async () => ({ ok: true, json: async () => value }))
  vi.stubGlobal('fetch', fetch)
  fireEvent.change(screen.getByLabelText('Saved execution ID'), { target: { value: savedExecution.execution_id } })
  fireEvent.click(screen.getByRole('button', { name: 'Open saved execution' }))
  return { ...inspected, fetch }
}

it.each([false, true])('opens a persisted execution with one GET and no future dispatch or polling (replay=%s)', async replay => {
  const { execute, props, fetch } = await requestSaved(savedExecution, replay)
  await screen.findByRole('heading', { name: 'Saved execution · execution-saved' })
  expect(screen.queryByRole('heading', { name: /New execution/ })).toBeNull()
  expect(screen.getByText('Recorded trials').nextElementSibling?.textContent).toBe('3')
  expect(screen.getByText('24 model calls · 21 HTTP attempts')).toBeTruthy()
  for (const id of savedExecution.episode_ids) expect(screen.getByRole('button', { name: id, exact: true })).toBeTruthy()
  fireEvent.click(screen.getByRole('button', { name: 'episode-saved-2', exact: true }))
  expect(props.onEpisode).toHaveBeenCalledExactlyOnceWith('episode-saved-2')
  expect(fetch).toHaveBeenCalledExactlyOnceWith('/api/regression-executions/execution-saved', expect.objectContaining({ method: 'GET' }))
  vi.useFakeTimers()
  await act(() => vi.advanceTimersByTimeAsync(10000))
  expect(fetch).toHaveBeenCalledTimes(1)
  expect(execute).not.toHaveBeenCalled()
})

it.each([
  ['execution ID', { execution_id: 'execution-foreign' }, /RegressionExecution identity/],
  ['bundle ID', { bundle_id: 'bundle-foreign' }, /does not match the selected bundle and manifest/],
  ['manifest hash', { manifest_hash: 'b'.repeat(64) }, /does not match the selected bundle and manifest/],
] as const)('rejects a mismatched saved %s without showing or executing it', async (_, changes, message) => {
  const { execute, fetch } = await requestSaved({ ...savedExecution, ...changes })
  expect((await screen.findByRole('alert')).textContent).toMatch(message)
  expect(screen.queryByRole('heading', { name: /Saved execution ·/ })).toBeNull()
  expect(screen.queryByRole('button', { name: 'episode-saved-1', exact: true })).toBeNull()
  vi.useFakeTimers()
  await act(() => vi.advanceTimersByTimeAsync(10000))
  expect(fetch).toHaveBeenCalledTimes(1)
  expect(execute).not.toHaveBeenCalled()
})

it('clears saved execution state when the campaign key changes', async () => {
  const { view, props, fetch, execute } = await requestSaved()
  await screen.findByRole('heading', { name: 'Saved execution · execution-saved' })
  view.rerender(h(RegressionControls, { ...props, key: 'another-campaign' }))
  expect(screen.queryByRole('heading', { name: /Saved execution ·/ })).toBeNull()
  expect((screen.getByLabelText('Saved regression') as HTMLSelectElement).value).toBe('')
  expect(screen.queryByLabelText('Saved execution ID')).toBeNull()
  expect(fetch).toHaveBeenCalledTimes(1)
  expect(execute).not.toHaveBeenCalled()
})
