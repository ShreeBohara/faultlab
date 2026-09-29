// @vitest-environment jsdom
import { createElement as h } from 'react'
import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { ApiError, api } from '../src/api'
import { importApi, importFileError, matchingImportExecution, validateImport, validateImportCancellation, validateImportExecution, validateImportLookup, validateImportPage, validateImportProvenance, validateImportSummary } from '../src/bundleImports'
import { BundleImports } from '../src/components/BundleImports'
import { faultExposure, ImportedFreshEvidence } from '../src/components/ImportedTrialEvidence'
import { EvidenceScreen } from '../src/components/EvidenceScreen'
import { PolicyPanel } from '../src/components/PolicyPanel'
import { baseline, fixtureResponse } from './fixtures'
import { freshEpisode, freshExecution, imported, importConfig, importReadiness, importRequest, offlineImported, ownerCampaign, ownerMetadata, target } from './import-fixtures'
import { validateImportListPage, validateImportOwner } from '../src/bundleImports'
import { freshRunBlockers } from '../src/components/BundleImports'
import { freshVerdict } from '../src/components/ImportedTrialEvidence'

const historyPage = { items: [imported], has_more: false, next_before: null }
const pendingKey = `faultlab:import-request:${imported.data_store.identity}`
beforeEach(() => {
  const values = new Map<string, string>()
  const storage = { getItem: (key: string) => values.get(key) ?? null, setItem: (key: string, value: string) => values.set(key, value), removeItem: (key: string) => values.delete(key) }
  vi.stubGlobal('localStorage', storage); vi.stubGlobal('sessionStorage', storage)
  vi.stubGlobal('fetch', vi.fn(async (url: string) => ({ ok: true, json: async () => fixtureResponse(url) })))
  HTMLElement.prototype.scrollIntoView = vi.fn()
})
afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals(); vi.useRealTimers() })
function mockReads() {
  const list = vi.spyOn(importApi, 'list').mockResolvedValue(historyPage)
  const detail = vi.spyOn(importApi, 'detail').mockResolvedValue(imported)
  const history = vi.spyOn(importApi, 'executions').mockResolvedValue({ items: [], has_more: false, next_before: null })
  return { list, detail, history }
}
async function review(extra = {}) {
  const props = { config: importConfig, readiness: importReadiness, replay: false, onEpisode: vi.fn(), ...extra }
  const view = render(h(BundleImports, props))
  await screen.findByRole('option', { name: /import-browser-fixture/ })
  fireEvent.change(screen.getByLabelText('Saved imported bundles'), { target: { value: imported.import_id } })
  await screen.findByLabelText('Fresh target registration')
  return { props, view }
}
function chooseTarget() { fireEvent.change(screen.getByLabelText('Fresh target registration'), { target: { value: target.agent_registration_id } }) }
/** The billable run needs two explicit clicks: Run opens the confirmation, Confirm dispatches. */
function runAndConfirm() {
  fireEvent.click(screen.getByRole('button', { name: 'Run imported regression in fresh worlds' }))
  fireEvent.click(within(screen.getByRole('group', { name: 'Confirm billable fresh run' })).getByRole('button', { name: 'Confirm billable fresh run' }))
}

it('validates source, target, cursor and cancellation bindings without claiming a malformed POST did not execute', () => {
  expect(validateImport(imported, imported.import_id)).toEqual(imported)
  expect(validateImportExecution(freshExecution, imported.import_id)).toEqual(freshExecution)
  expect(validateImportPage(historyPage, validateImportSummary, item => item.import_id)).toEqual(historyPage)
  for (const value of [{ ...imported, provider_calls: 1 }, { ...imported, source: { ...imported.source, evidence_verification: 'VERIFIED' } }, { ...imported, targets: [target] }]) expect(() => validateImport(value)).toThrow('Malformed')
  expect(() => validateImport(imported, 'foreign')).toThrow('identity')
  expect(() => validateImportExecution({ ...freshExecution, target: { ...target, configuration_hash: 'd'.repeat(64) } }, imported.import_id)).toThrow('Check the saved request')
  expect(() => matchingImportExecution({ ...freshExecution, execution: { ...freshExecution.execution, manifest_hash: 'f'.repeat(64) } }, imported)).toThrow('identity')
  expect(() => validateImportPage({ ...historyPage, has_more: true, next_before: 9 }, validateImportSummary, item => item.import_id, 9)).toThrow('cursor')
  expect(validateImportLookup({ cancelled: true, import_id: imported.import_id, request_id: importRequest.request_id }, imported.import_id, importRequest.request_id)).toHaveProperty('cancelled', true)
  expect(validateImportCancellation({ cancelled: false, execution: freshExecution }, imported.import_id, importRequest.request_id)).toHaveProperty('cancelled', false)
  expect(() => validateImportProvenance({ imported: true, import_id: 'x', source_policy_version: 'v1', source_policy_hash: imported.policy.hash, historical_decision: 'ACCEPTED', local_acceptance: true })).toThrow('provenance')
})

it('sends the selected ZIP bytes only on Save, independently of campaign selection, and never executes it', async () => {
  mockReads()
  const upload = vi.spyOn(importApi, 'upload').mockResolvedValue({ bundle: imported, status: 'created' })
  const execute = vi.spyOn(importApi, 'execute')
  render(h(BundleImports, { config: importConfig, readiness: importReadiness, replay: false, onEpisode: vi.fn() }))
  const file = new File(['PK fixture bytes'], 'regression.zip', { type: 'application/zip' })
  fireEvent.change(screen.getByLabelText(/Regression bundle ZIP/), { target: { files: [file] } })
  expect(upload).not.toHaveBeenCalled()
  fireEvent.click(screen.getByRole('button', { name: 'Save imported bundle' }))
  await screen.findByText(/Review imported bundle/)
  expect(upload).toHaveBeenCalledExactlyOnceWith(file, imported.data_store.identity)
  expect(execute).not.toHaveBeenCalled()
  expect(screen.queryByRole('button', { name: 'historical-trial', exact: true })).toBeNull()
  expect(screen.getByText('Original bundled reports, events and provenance')).toBeTruthy()
})

it('uploads raw ZIP bytes with the store identity header and preserves backend validation errors', async () => {
  const file = new File(['PK raw'], 'export.zip')
  const fetch = vi.fn().mockResolvedValueOnce({ ok: true, json: async () => ({ ...imported, import_status: 'existing' }) }).mockResolvedValueOnce({ ok: false, status: 400, json: async () => ({ error: { message: 'Not a regression bundle ZIP' } }) })
  vi.stubGlobal('fetch', fetch)
  await expect(importApi.upload(file, imported.data_store.identity)).resolves.toEqual({ bundle: { ...imported, import_status: 'existing' }, status: 'existing' })
  expect(fetch.mock.calls[0][1]).toMatchObject({ method: 'POST', headers: { 'Content-Type': 'application/zip', 'X-FaultLab-Store-Identity': imported.data_store.identity }, body: file })
  await expect(importApi.upload(file, imported.data_store.identity)).rejects.toThrow('Not a regression bundle ZIP')
})

it('rejects campaign recording JSON, empty and oversized uploads before sending bytes', async () => {
  mockReads(); const upload = vi.spyOn(importApi, 'upload')
  render(h(BundleImports, { config: importConfig, replay: false, onEpisode: vi.fn() }))
  fireEvent.change(screen.getByLabelText(/Regression bundle ZIP/), { target: { files: [new File(['{}'], 'campaign-recording.json')] } })
  expect(screen.getByRole('alert').textContent).toContain('Campaign recordings are JSON evidence archives')
  expect((screen.getByRole('button', { name: 'Save imported bundle' }) as HTMLButtonElement).disabled).toBe(true)
  expect(upload).not.toHaveBeenCalled()
  expect(importFileError(new File([], 'empty.zip'))).toContain('empty')
  expect(importFileError({ name: 'huge.zip', size: 24 * 1024 * 1024 + 1 } as File)).toContain('24 MiB')
})

it('keeps historical review available in an archive while all import mutations remain disabled', async () => {
  mockReads(); vi.mocked(importApi.detail).mockResolvedValue({ ...imported, data_store: { ...imported.data_store, read_only: true } })
  const upload = vi.spyOn(importApi, 'upload'); const execute = vi.spyOn(importApi, 'execute')
  await review({ config: { ...importConfig, data_store: { ...importConfig.data_store, read_only: true } } })
  chooseTarget()
  expect((screen.getByRole('button', { name: 'Run imported regression in fresh worlds' }) as HTMLButtonElement).disabled).toBe(true)
  expect((screen.getByRole('button', { name: 'Save imported bundle' }) as HTMLButtonElement).disabled).toBe(true)
  expect(screen.getByText(/not verified locally/)).toBeTruthy()
  expect(upload).not.toHaveBeenCalled(); expect(execute).not.toHaveBeenCalled()
})

it('blocks stale or incompatible target review and requires a separate explicit fresh run', async () => {
  mockReads(); const execute = vi.spyOn(importApi, 'execute').mockImplementation(async (_, body) => ({ ...freshExecution, request_id: body.request_id }))
  await review(); expect(execute).not.toHaveBeenCalled(); chooseTarget()
  fireEvent.click(screen.getByRole('button', { name: 'Run imported regression in fresh worlds' }))
  expect(execute).not.toHaveBeenCalled()
  const confirm = screen.getByRole('group', { name: 'Confirm billable fresh run' })
  expect(confirm.textContent).toContain(imported.execution_task!.task_text)
  expect(confirm.textContent).toContain('Up to 48 billable model requests')
  fireEvent.click(within(confirm).getByRole('button', { name: 'Confirm billable fresh run' }))
  await screen.findByRole('heading', { name: /Fresh execution ·/ })
  expect(execute).toHaveBeenCalledOnce()
  expect(execute.mock.calls[0][1]).toMatchObject({ expected_store_identity: imported.data_store.identity, expected_manifest_hash: imported.manifest_hash, expected_target_configuration_hash: target.configuration_hash, agent_registration_id: target.agent_registration_id, execute_live: true })
  expect(localStorage.getItem(pendingKey)).toBeNull()
  expect(screen.getAllByText(target.model, { selector: 'dd' }).length).toBeGreaterThan(0)
})

it.each(['bundle', 'target', 'store', 'readiness'] as const)('refuses execution when %s no longer matches a runnable review', async kind => {
  mockReads()
  const changed = kind === 'bundle' ? { ...imported, runnable: false, runnable_reason: 'Incomplete source policy' }
    : kind === 'target' ? { ...imported, targets: [{ ...target, compatible: false, reason: 'Target changed' }] }
    : kind === 'store' ? { ...imported, data_store: { ...imported.data_store, identity: 'different-store' } } : imported
  vi.mocked(importApi.detail).mockResolvedValue(changed)
  const execute = vi.spyOn(importApi, 'execute')
  await review(kind === 'readiness' ? { readiness: { data: undefined, loading: false, error: 'Unavailable' } } : {})
  chooseTarget()
  const button = screen.getByRole('button', { name: 'Run imported regression in fresh worlds' }) as HTMLButtonElement
  expect(button.disabled).toBe(true); fireEvent.click(button)
  expect(execute).not.toHaveBeenCalled()
})

it('restores a pending request only after asynchronous config provides the actual store identity', async () => {
  mockReads()
  localStorage.setItem(`faultlab:import:${imported.data_store.identity}`, imported.import_id)
  localStorage.setItem(pendingKey, JSON.stringify({ import_id: imported.import_id, request: importRequest }))
  let finish!: (value: typeof importConfig) => void
  vi.spyOn(api, 'config').mockImplementation(() => new Promise(resolve => { finish = resolve }))
  const execute = vi.spyOn(importApi, 'execute')
  render(h(EvidenceScreen))
  expect(screen.queryByRole('button', { name: 'Check saved request' })).toBeNull()
  await act(async () => finish(importConfig))
  expect(await screen.findByRole('button', { name: 'Check saved request' })).toBeTruthy()
  expect(execute).not.toHaveBeenCalled()
})

it('keeps the import workflow visible when a remembered campaign is absent from this store', async () => {
  mockReads(); localStorage.setItem('faultlab:campaign', 'campaign-missing')
  vi.spyOn(api, 'config').mockResolvedValue(importConfig)
  vi.spyOn(api, 'campaign').mockRejectedValue(new ApiError(404, 'Unknown record'))
  render(h(EvidenceScreen))
  await screen.findByRole('heading', { name: 'Saved campaign unavailable' })
  expect(screen.getByLabelText(/Regression bundle ZIP/)).toBeTruthy()
  fireEvent.change(await screen.findByLabelText('Saved imported bundles'), { target: { value: imported.import_id } })
  expect(await screen.findByLabelText('Fresh target registration')).toBeTruthy()
})

it('preserves import history across an older-page failure and never polls all pages', async () => {
  const { list } = mockReads()
  const second = { ...imported, import_id: 'import-older' }
  list.mockResolvedValueOnce({ ...historyPage, has_more: true, next_before: 9 }).mockRejectedValueOnce(new Error('Read unavailable')).mockResolvedValueOnce({ items: [second], has_more: false, next_before: null })
  render(h(BundleImports, { config: importConfig, replay: false, onEpisode: vi.fn() }))
  fireEvent.click(await screen.findByRole('button', { name: 'Load older imports' }))
  await screen.findByRole('alert')
  expect(screen.getByRole('option', { name: /import-browser-fixture/ })).toBeTruthy()
  fireEvent.click(screen.getByRole('button', { name: 'Load older imports' }))
  await screen.findByRole('option', { name: /import-older/ })
  expect(list).toHaveBeenNthCalledWith(3, 9)
  vi.useFakeTimers(); await act(() => vi.advanceTimersByTimeAsync(10000))
  expect(list).toHaveBeenCalledTimes(3)
})

it('retains the exact nonce after timeout and reload; 404 cannot discard it; same-request retry is idempotent', async () => {
  mockReads()
  const execute = vi.spyOn(importApi, 'execute').mockRejectedValueOnce(new Error('Response timed out.')).mockImplementation(async (_, body) => ({ ...freshExecution, request_id: body.request_id }))
  vi.spyOn(importApi, 'lookup').mockRejectedValue(new ApiError(404, 'Not yet saved'))
  const { props, view } = await review(); chooseTarget()
  runAndConfirm()
  await screen.findByRole('region', { name: 'Unresolved imported execution request' })
  const saved = JSON.parse(localStorage.getItem(pendingKey)!)
  view.unmount(); render(h(BundleImports, props))
  await screen.findByRole('button', { name: 'Check saved request' })
  expect(execute).toHaveBeenCalledOnce()
  fireEvent.click(screen.getByRole('button', { name: 'Check saved request' }))
  await screen.findByText(/original request may still be processing/)
  expect(screen.queryByRole('button', { name: /Discard/ })).toBeNull()
  expect(JSON.parse(localStorage.getItem(pendingKey)!)).toEqual(saved)
  fireEvent.click(screen.getByRole('button', { name: 'Retry same execution request' }))
  await screen.findByRole('heading', { name: /Fresh execution ·/ })
  expect(execute.mock.calls[1][1]).toEqual(execute.mock.calls[0][1])
  expect(localStorage.getItem(pendingKey)).toBeNull()
})

it.each([true, false])('discards a nonce only after durable cancellation or resolved existing execution (cancelled=%s)', async cancelled => {
  mockReads(); localStorage.setItem(`faultlab:import:${imported.data_store.identity}`, imported.import_id); localStorage.setItem(pendingKey, JSON.stringify({ import_id: imported.import_id, request: importRequest }))
  const cancel = vi.spyOn(importApi, 'cancel').mockResolvedValue(cancelled ? { cancelled: true, import_id: imported.import_id, request_id: importRequest.request_id } : { cancelled: false, execution: freshExecution })
  render(h(BundleImports, { config: importConfig, readiness: importReadiness, replay: false, onEpisode: vi.fn() }))
  fireEvent.click(await screen.findByRole('button', { name: 'Cancel unadmitted request' }))
  await waitFor(() => expect(localStorage.getItem(pendingKey)).toBeNull())
  expect(cancel).toHaveBeenCalledExactlyOnceWith(imported.import_id, importRequest)
  if (!cancelled) expect(await screen.findByRole('heading', { name: /Fresh execution ·/ })).toBeTruthy()
  expect((await screen.findByText(cancelled ? 'Request cancelled before it started; nothing ran.' : /had already started, so it was not cancelled/)).getAttribute('role')).toBe('status')
})

it.each(['cancel', 'check'] as const)('keeps the "nothing ran" outcome on screen while the review rereads its detail (%s)', async path => {
  const { detail } = mockReads(); localStorage.setItem(`faultlab:import:${imported.data_store.identity}`, imported.import_id); localStorage.setItem(pendingKey, JSON.stringify({ import_id: imported.import_id, request: importRequest }))
  const cancelled = { cancelled: true as const, import_id: imported.import_id, request_id: importRequest.request_id }
  if (path === 'cancel') vi.spyOn(importApi, 'cancel').mockResolvedValue(cancelled); else vi.spyOn(importApi, 'lookup').mockResolvedValue(cancelled)
  render(h(BundleImports, { config: importConfig, readiness: importReadiness, replay: false, onEpisode: vi.fn() }))
  const button = await screen.findByRole('button', { name: path === 'cancel' ? 'Cancel unadmitted request' : 'Check saved request' })
  // Hold the reread open so the moment the old code unmounted the review is observable.
  let release!: () => void
  detail.mockImplementation(() => new Promise(resolve => { release = () => resolve(imported) }))
  fireEvent.click(button)
  const outcome = path === 'cancel' ? 'Request cancelled before it started; nothing ran.' : 'That request was cancelled before it started; nothing ran.'
  expect((await screen.findByText(outcome)).getAttribute('role')).toBe('status')
  await waitFor(() => expect(detail).toHaveBeenCalledTimes(2))
  expect(screen.getByText(outcome)).toBeTruthy()
  expect(screen.getByLabelText('Why fresh execution is unavailable').textContent).toContain('This review is refreshing or out of date')
  await act(async () => release())
  await waitFor(() => expect(screen.getByLabelText('Why fresh execution is unavailable').textContent).not.toContain('refreshing'))
  expect(screen.getByText(outcome).getAttribute('role')).toBe('status')
  expect(localStorage.getItem(pendingKey)).toBeNull()
})

it('never shows the previous import while a different selection is still loading', async () => {
  const other = { ...imported, import_id: 'import-other-fixture' }
  vi.spyOn(importApi, 'list').mockResolvedValue({ items: [imported, other], has_more: false, next_before: null })
  vi.spyOn(importApi, 'detail').mockImplementation(async id => id === imported.import_id ? imported : new Promise<typeof imported>(() => {}))
  vi.spyOn(importApi, 'executions').mockResolvedValue({ items: [], has_more: false, next_before: null })
  await review()
  expect(screen.getByRole('heading', { name: `Review imported bundle · ${imported.import_id}` })).toBeTruthy()
  fireEvent.change(screen.getByLabelText('Saved imported bundles'), { target: { value: other.import_id } })
  await waitFor(() => expect(screen.queryByRole('heading', { name: /Review imported bundle/ })).toBeNull())
})

it('locks duplicate execute clicks while retaining a durable in-flight request', async () => {
  mockReads(); let finish!: (value: typeof freshExecution) => void
  const execute = vi.spyOn(importApi, 'execute').mockImplementation(() => new Promise(resolve => { finish = resolve }))
  await review(); chooseTarget()
  fireEvent.click(screen.getByRole('button', { name: 'Run imported regression in fresh worlds' }))
  const button = within(screen.getByRole('group', { name: 'Confirm billable fresh run' })).getByRole('button', { name: 'Confirm billable fresh run' })
  fireEvent.click(button); fireEvent.click(button)
  expect(execute).toHaveBeenCalledOnce(); expect(localStorage.getItem(pendingKey)).not.toBeNull()
  await act(async () => finish({ ...freshExecution, request_id: execute.mock.calls[0][1].request_id }))
})

it('shows fresh target identity, reports and download independently of the legacy accounting model', async () => {
  vi.spyOn(api, 'episode').mockResolvedValue(freshEpisode)
  const onEpisode = vi.fn()
  render(h(ImportedFreshEvidence, { value: { ...freshExecution, execution: { ...freshExecution.execution, episode_ids: [freshEpisode.episode_id], world_ids: [freshEpisode.world_id] } }, artifactKind: 'candidate_comparison', faultCount: 1, onEpisode }))
  fireEvent.click(await screen.findByRole('button', { name: freshEpisode.episode_id }))
  expect(onEpisode).toHaveBeenCalledExactlyOnceWith(ownerCampaign.campaign_id, freshEpisode.episode_id)
  expect(screen.getByText('Fully triggered · 1 / 1')).toBeTruthy()
  expect(screen.getByRole('button', { name: 'Download fresh execution recording' })).toBeTruthy()
  expect(screen.queryByText(ownerCampaign.model)).toBeNull()
})

it('does not expose fresh episode links when loaded evidence belongs to another target', async () => {
  vi.spyOn(api, 'episode').mockResolvedValue({ ...freshEpisode, agent_registration_id: 'foreign-target' })
  render(h(ImportedFreshEvidence, { value: { ...freshExecution, execution: { ...freshExecution.execution, episode_ids: [freshEpisode.episode_id] } }, artifactKind: 'candidate_comparison', faultCount: 1, onEpisode: vi.fn() }))
  await screen.findByRole('alert')
  expect(screen.queryByRole('button', { name: freshEpisode.episode_id })).toBeNull()
})

it('keeps imported owner contexts out of normal learning claims and Start after reload while retaining Stop', async () => {
  localStorage.setItem('faultlab:campaign', ownerCampaign.campaign_id)
  vi.stubGlobal('fetch', vi.fn(async (url: string) => ({ ok: true, json: async () => url.endsWith('/config/status') ? { ...importConfig, active_campaign_id: ownerCampaign.campaign_id } : url.endsWith('/import-owner') ? ownerMetadata : fixtureResponse(url, ownerCampaign) })))
  render(h(EvidenceScreen))
  await screen.findByRole('heading', { name: 'Budget and evidence owner for an imported regression' })
  expect((screen.getByRole('button', { name: /Start campaign/ }) as HTMLButtonElement).disabled).toBe(true)
  expect((screen.getByRole('button', { name: 'Stop', exact: true }) as HTMLButtonElement).disabled).toBe(false)
  expect(screen.queryByRole('heading', { name: 'Run summary' })).toBeNull()
  expect(screen.getByText('Actual execution target model').nextElementSibling?.textContent).toBe(target.model)
})

it('marks an imported accepted policy as historical and never links foreign proposal or episode IDs locally', async () => {
  vi.spyOn(importApi, 'provenance').mockResolvedValue({ imported: true, import_id: imported.import_id, source_policy_version: 'foreign-v1', source_policy_hash: imported.policy.hash, historical_decision: 'ACCEPTED', local_acceptance: false })
  render(h(PolicyPanel, { policies: { data: [{ ...baseline, version: 'local-import-alias', decision: 'ACCEPTED', raw_proposal_ref: 'foreign-proposal', development_episode_ids: ['foreign-episode'] }], error: null, loading: false }, active: 'policy-v0', onEpisode: vi.fn() }))
  await screen.findByText('Imported historical decision · ACCEPTED')
  expect(screen.queryByRole('button', { name: 'foreign-episode' })).toBeNull()
  expect(screen.queryByRole('button', { name: 'Read original model proposal' })).toBeNull()
  expect(within(screen.getByLabelText('Immutable version')).getAllByRole('option')[0].textContent).not.toContain('ACCEPTED')
})

it('distinguishes full, partial, none, absent and incomplete fault exposure without inventing a healthy case', () => {
  const fault = (triggered: boolean) => ({ scheduled: true, triggered })
  expect(faultExposure({ fault_executions: [fault(true), fault(true)] }, true, true)).toContain('Fully triggered · 2 / 2')
  expect(faultExposure({ fault_executions: [fault(true), fault(false)] }, true, false)).toContain('Partially triggered · 1 / 2')
  expect(faultExposure({ fault_executions: [fault(false)] }, true, false)).toContain('None triggered')
  expect(faultExposure({ fault_executions: [] }, true, false)).toContain('exposure record unavailable')
  expect(faultExposure({ fault_executions: [] }, undefined, undefined, 2)).toContain('exposure record unavailable')
  expect(faultExposure({ fault_executions: [fault(true)] }, true, true, 2)).toContain('record incomplete')
  expect(faultExposure(undefined, true, false)).toContain('counts unavailable')
})

it('rereads saved execution labels once a watched run finishes instead of leaving it shown as running', async () => {
  mockReads()
  let serverStatus: 'RUNNING' | 'COMPLETED' | null = null
  let requestId = importRequest.request_id
  const saved = () => ({ ...freshExecution, request_id: requestId, execution: { ...freshExecution.execution, status: serverStatus! } })
  vi.mocked(importApi.executions).mockImplementation(async () => ({ items: serverStatus ? [saved()] : [], has_more: false, next_before: null }))
  vi.spyOn(importApi, 'execute').mockImplementation(async (_, body) => { requestId = body.request_id; serverStatus = 'RUNNING'; return saved() })
  vi.spyOn(importApi, 'lookup').mockImplementation(async () => { serverStatus = 'COMPLETED'; return saved() })
  await review(); chooseTarget()
  runAndConfirm()
  await screen.findByRole('option', { name: /Running/ })
  expect(await screen.findByRole('option', { name: /Completed/ }, { timeout: 5000 })).toBeTruthy()
  expect(screen.queryByRole('option', { name: /Running/ })).toBeNull()
})

// Review fixes, September 28: exact task, source origin, blockers, bound and feedback.

it('shows the exact bundled task and order next to the review and the run, never a fixed task label', async () => {
  mockReads(); await review()
  expect(screen.queryByText('Supported task')).toBeNull()
  expect(screen.getAllByText(imported.execution_task!.task_text, { selector: 'span.task-text' })).toHaveLength(2)
  const task = within(screen.getByRole('region', { name: 'Task sent in fresh trials' }))
  expect(task.getByText('order-7')).toBeTruthy()
  expect(task.getByText(/Recorded in this bundle by its source campaign/)).toBeTruthy()
})

it('labels the default task as a FaultLab default and refuses a malformed recorded task', async () => {
  mockReads(); vi.mocked(importApi.detail).mockResolvedValue({ ...imported, execution_task: { task_text: 'Default text', order_id: 'order-regression', origin: 'default' } })
  await review()
  expect(screen.getAllByText(/FaultLab default task; this bundle records none/)).toHaveLength(2)
  cleanup(); mockReads()
  vi.mocked(importApi.detail).mockResolvedValue({ ...imported, execution_task: null, runnable: false, runnable_reason: 'The recorded execution task is malformed; stored for inspection only' })
  await review(); chooseTarget()
  expect(screen.getAllByText(/task recorded in this bundle is malformed/).length).toBeGreaterThan(0)
  expect((screen.getByRole('button', { name: 'Run imported regression in fresh worlds' }) as HTMLButtonElement).disabled).toBe(true)
  expect(() => validateImport({ ...imported, execution_task: null })).toThrow('Malformed')
  expect(() => validateImport({ ...imported, execution_task: { ...imported.execution_task, order_id: '../x' } })).toThrow('Malformed')
})

it('names an offline scripted source in the review and the saved-import list', async () => {
  vi.spyOn(importApi, 'list').mockResolvedValue({ items: [offlineImported], has_more: false, next_before: null })
  vi.spyOn(importApi, 'detail').mockResolvedValue(offlineImported)
  vi.spyOn(importApi, 'executions').mockResolvedValue({ items: [], has_more: false, next_before: null })
  render(h(BundleImports, { config: importConfig, readiness: importReadiness, replay: false, onEpisode: vi.fn() }))
  const option = await screen.findByRole('option', { name: /import-offline-fixture/ })
  expect(option.textContent).toContain('offline scripted')
  fireEvent.change(screen.getByLabelText('Saved imported bundles'), { target: { value: offlineImported.import_id } })
  expect((await screen.findByText('How source trials were produced')).nextElementSibling?.textContent).toBe('Offline scripted fixture (no model calls)')
})

it('skips one malformed saved summary instead of hiding every import', async () => {
  const bad = { ...imported, import_id: 'import-bad', source: { ...imported.source, agent_registration_id: 12345 } }
  const page = validateImportListPage({ items: [bad, imported], has_more: false, next_before: null })
  expect(page.items.map(item => item.import_id)).toEqual([imported.import_id]); expect(page.skipped).toBe(1)
  for (const value of ['', { nested: true }]) expect(validateImportListPage({ items: [{ ...bad, source: { ...bad.source, agent_registration_id: value } }, imported], has_more: false, next_before: null }).skipped).toBe(1)
  expect(() => validateImportListPage({ items: [], has_more: true, next_before: 3 })).toThrow('cursor')
  vi.spyOn(importApi, 'list').mockResolvedValue(page)
  render(h(BundleImports, { config: importConfig, replay: false, onEpisode: vi.fn() }))
  expect(await screen.findByRole('option', { name: /import-browser-fixture/ })).toBeTruthy()
  expect(screen.getByText(/1 saved import summary could not be verified/)).toBeTruthy()
})

it('shows a server refusal directly under the file input, even with a review open, and withdraws the Save hint', async () => {
  mockReads(); await review()
  vi.spyOn(importApi, 'upload').mockRejectedValue(new ApiError(422, 'Import refused; nothing was saved. Contents do not match: edited.'))
  fireEvent.change(screen.getByLabelText(/Regression bundle ZIP/), { target: { files: [new File(['PK'], 'tampered.zip')] } })
  expect(screen.getByText(/Select Save imported bundle to upload it/)).toBeTruthy()
  fireEvent.click(screen.getByRole('button', { name: 'Save imported bundle' }))
  const alert = await screen.findByRole('alert')
  expect(alert.textContent).toContain('Import refused; nothing was saved.')
  const input = screen.getByLabelText(/Regression bundle ZIP/); const heading = screen.getByRole('heading', { name: /Review imported bundle/ })
  expect(input.compareDocumentPosition(alert) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
  expect(alert.compareDocumentPosition(heading) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
  expect(screen.queryByText(/Select Save imported bundle to upload it/)).toBeNull()
  expect((screen.getByRole('button', { name: 'Save imported bundle' }) as HTMLButtonElement).disabled).toBe(true)
})

it('never invites Save for a file refused in the browser', async () => {
  mockReads(); render(h(BundleImports, { config: importConfig, replay: false, onEpisode: vi.fn() }))
  fireEvent.change(screen.getByLabelText(/Regression bundle ZIP/), { target: { files: [new File(['text'], 'notes.txt')] } })
  expect(screen.getByRole('alert').textContent).toContain('Not accepted: notes.txt. Choose an exported regression bundle ZIP.')
  expect(screen.queryByText(/Select Save imported bundle/)).toBeNull()
})

it('says when a re-saved ZIP was already imported instead of silently reopening it', async () => {
  mockReads(); vi.spyOn(importApi, 'upload').mockResolvedValue({ bundle: imported, status: 'existing' })
  render(h(BundleImports, { config: importConfig, readiness: importReadiness, replay: false, onEpisode: vi.fn() }))
  fireEvent.change(screen.getByLabelText(/Regression bundle ZIP/), { target: { files: [new File(['PK'], 'again.zip')] } })
  fireEvent.click(screen.getByRole('button', { name: 'Save imported bundle' }))
  expect((await screen.findByText(/already imported; showing the saved import/)).getAttribute('role')).toBe('status')
})

it('names each actual blocker for a disabled fresh run with what to do next', () => {
  const base = { bundle: imported, config: importConfig, readiness: importReadiness, replay: false, stale: false, storeMatches: true, target: imported.targets[0], pending: false, running: false }
  expect(freshRunBlockers(base)).toEqual([])
  expect(freshRunBlockers({ ...base, config: { ...importConfig, live_enabled: false } }).join(' ')).toContain('start-local.sh --live')
  expect(freshRunBlockers({ ...base, readiness: { ...importReadiness, data: { ...importReadiness.data, live_configuration: { ready: false, missing_fields: ['WANDB_API_KEY'] } } } })).toEqual(['Live settings are missing: WANDB_API_KEY.'])
  expect(freshRunBlockers({ ...base, readiness: { ...importReadiness, data: { ...importReadiness.data, simulator: { ready: false, code: 'SIMULATOR_UNAVAILABLE', message: 'The simulator did not answer.' } } } })[0]).toContain('The simulator is not ready')
  expect(freshRunBlockers({ ...base, target: undefined })[0]).toContain('Select a fresh target registration')
  expect(freshRunBlockers({ ...base, config: { ...importConfig, active_campaign_id: 'campaign-other' } })[0]).toContain('Another campaign is active')
  expect(freshRunBlockers({ ...base, config: { ...importConfig, data_store: { ...importConfig.data_store, read_only: true } }, target: undefined })).toEqual(['This is a read-only archive. Saved imports stay readable; fresh runs need the writable workspace.'])
})

it('lists the blockers on screen for the default offline workspace', async () => {
  mockReads(); await review({ config: { ...importConfig, live_enabled: false } })
  const reasons = screen.getByLabelText('Why fresh execution is unavailable')
  expect(reasons.textContent).toContain('Live execution is off in this workspace')
  expect(reasons.textContent).toContain('Select a fresh target registration')
})

it('gives a plain verdict that matches the artifact kind', () => {
  const done = (assertions: Record<string, unknown>, status: 'COMPLETED' | 'INCOMPLETE' = 'COMPLETED') => ({ ...freshExecution, execution: { ...freshExecution.execution, status }, assertions: { target_invariant: 'C3', required_trials: 3, ...assertions } })
  expect(freshVerdict('incident_fixture', done({ valid_trials: 3, target_failures: 3, reproduced: true }))).toContain('Incident reproduced as expected in 3 of 3 fresh trials')
  expect(freshVerdict('incident_fixture', done({ valid_trials: 3, target_failures: 1, reproduced: false }))).toContain('Incident did not reproduce in every trial')
  expect(freshVerdict('candidate_comparison', done({ valid_trials: 3, target_failures: 2, reproduced: false }))).toContain('did not prevent the C3 violation in 2 of 3')
  expect(freshVerdict('accepted_policy_bundle', done({ valid_trials: 3, target_failures: 0, reproduced: false }))).toContain('prevented the C3 violation in all 3 fresh trials')
  expect(freshVerdict('incident_fixture', done({ valid_trials: 1, target_failures: 1, reproduced: false }, 'INCOMPLETE'))).toContain('No verdict')
  expect(freshVerdict('incident_fixture', { ...freshExecution, assertions: null })).toBeNull()
})

it('shows the accounting ledger charges, including retries, beside recorded trial usage', () => {
  render(h(ImportedFreshEvidence, { value: freshExecution, artifactKind: 'incident_fixture', faultCount: 1, onEpisode: vi.fn() }))
  expect(screen.getByText('Charged to its accounting ledger').nextElementSibling?.textContent).toContain('14 model requests (includes any transport retries; at most 48)')
  expect(screen.getByText('Recorded trial usage')).toBeTruthy()
})

it('shows the owner receipt as this execution budget and hides the ordinary Portable regression panel', async () => {
  localStorage.setItem('faultlab:campaign', ownerCampaign.campaign_id)
  vi.stubGlobal('fetch', vi.fn(async (url: string) => ({ ok: true, json: async () => url.endsWith('/config/status') ? importConfig : url.endsWith('/import-owner') ? ownerMetadata : fixtureResponse(url, ownerCampaign) })))
  render(h(EvidenceScreen))
  const budget = await screen.findByText('Imported execution budget')
  expect(budget.nextElementSibling?.textContent).toContain('at most 48 for this one execution')
  expect(screen.queryByText('Call budget')).toBeNull()
  expect(screen.queryByRole('heading', { name: /Portable regression/ })).toBeNull()
  expect(() => validateImportOwner({ ...ownerMetadata, request_ceiling: -1 })).toThrow('accounting owner')
})
