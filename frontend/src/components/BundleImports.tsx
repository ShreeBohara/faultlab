import { useEffect, useId, useRef, useState } from 'react'
import { ApiError, type ConfigStatus, type ReadinessStatus } from '../api'
import { importApi, importFileError, matchingImportExecution, validatePendingImportRequest, type ImportedBundle, type ImportedBundleSummary, type ImportedExecution, type ImportExecutionRequest, type PendingImportRequest } from '../bundleImports'
import { useImportHistory } from '../useImportHistory'
import { useResource, type Resource } from '../useResource'
import { Empty, Field, Hash, Json, Panel, ResourceNote, label } from './common'
import { ImportedFreshEvidence, ImportedHistoricalEvidence } from './ImportedTrialEvidence'

const artifactLabel = { incident_fixture: 'Incident fixture', candidate_comparison: 'Candidate comparison', accepted_policy_bundle: 'Accepted source policy bundle' }
const message = (error: unknown) => error instanceof Error ? error.message : 'The request could not be completed.'
function savedChoice(key: string) { try { return localStorage.getItem(key) ?? '' } catch { return '' } }
function pendingChoice(key: string): PendingImportRequest | null { try { const raw = localStorage.getItem(key); return raw ? validatePendingImportRequest(JSON.parse(raw)) : null } catch { return null } }

const modeNames: Record<string, [string, string]> = {
  offline_fixture: ['Offline scripted fixture (no model calls)', 'offline scripted'],
  live: ['Live model run', 'live model run'],
  replay: ['Recorded playback (no new model calls)', 'recorded playback'],
}
/** How the imported source trials were produced, in words a first-time reader can act on. */
export function sourceTrialOrigin(source: ImportedBundleSummary['source'], short = false): string {
  const modes = source.source_modes ?? (source.source_mode ? [source.source_mode] : [])
  const name = (mode: string) => modeNames[mode]?.[short ? 1 : 0] ?? mode
  if (!modes.length) return short ? 'source trials not recorded' : 'Not recorded (this bundle carries no trial recording)'
  if (modes.length === 1) return name(modes[0])
  return `Mixed (${modes.map(mode => name(mode)).join(', ')})`
}

export function BundleImports({ config, readiness, replay, onEpisode }: { config?: ConfigStatus; readiness?: Resource<ReadinessStatus>; replay: boolean; onEpisode: (owner: string, episode: string) => void }) {
  const fieldId = useId(); const store = config?.data_store
  const selectedKey = `faultlab:import:${store?.identity ?? 'unavailable'}`
  const pendingKey = `faultlab:import-request:${store?.identity ?? 'unavailable'}`
  const [selected, setSelected] = useState(() => savedChoice(selectedKey))
  const [pending, setPending] = useState(() => pendingChoice(pendingKey))
  const [file, setFile] = useState<File | null>(null)
  const [busy, setBusy] = useState(false)
  const [uploadError, setUploadError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const locked = useRef(false)
  const history = useImportHistory(store ? `imports:${store.identity}` : null, importApi.list, item => item.import_id)
  const detail = useResource(store && selected ? `import:${store.identity}:${selected}` : null, () => importApi.detail(selected), null)
  const fileProblem = file ? importFileError(file) : null
  const canSave = !!store && !store.read_only && !replay && !busy && !!file && !fileProblem
  function select(id: string) { setSelected(id); setUploadError(null); try { localStorage.setItem(selectedKey, id) } catch { /* Navigation is still available without local persistence. */ } }
  function persistPending(value: PendingImportRequest | null) {
    // Dispatch is refused if the nonce cannot survive a response timeout/reload.
    if (value) localStorage.setItem(pendingKey, JSON.stringify(value)); else localStorage.removeItem(pendingKey)
    setPending(value)
  }
  async function upload() {
    if (!canSave || !file || !store || locked.current) return
    locked.current = true; setBusy(true); setUploadError(null); setNotice(null)
    try {
      const { bundle: value, status } = await importApi.upload(file, store.identity)
      if (value.data_store.identity !== store.identity) throw new Error('The import response belongs to a different data store. Refresh before continuing.')
      select(value.import_id); history.refresh(); setFile(null)
      setNotice(status === 'existing' ? `This ZIP was already imported; showing the saved import ${value.import_id} (no duplicate was created).`
        : `Saved import ${value.import_id}. Review it below; nothing was run.`)
    } catch (reason) {
      // The refusal replaces the selection so the page never still invites Save.
      setUploadError(message(reason)); setFile(null)
    } finally { locked.current = false; setBusy(false) }
  }
  const skipped = history.page?.skipped ?? 0
  return <Panel title="Imported regressions" className="bundle-import-panel" aside={<span className="small-label">Save · review · explicit rerun</span>}>
    <p className="muted">Bring an exported regression ZIP into this local store. Saving an import preserves source evidence; it makes no provider calls, creates no trial, and never activates a policy. Campaign recording JSON is a different artifact.</p>
    <div className="import-inputs"><div className="setup-field"><label htmlFor={`${fieldId}-file`}>Regression bundle ZIP · up to 24 MiB</label><input id={`${fieldId}-file`} type="file" accept=".zip,application/zip" disabled={!store || store.read_only || busy || replay} onChange={event => { const value = event.target.files?.[0] ?? null; setFile(value); setUploadError(null); setNotice(null); event.target.value = '' }} /></div><button disabled={!canSave} onClick={() => void upload()}>{busy ? 'Saving import…' : 'Save imported bundle'}</button></div>
    {file && (fileProblem
      ? <p role="alert" className="error">Not accepted: {file.name}. {fileProblem}</p>
      : <p className="muted">Selected locally: {file.name} · {(file.size / 1024).toFixed(1)} KiB. Select Save imported bundle to upload it.</p>)}
    {uploadError && <p role="alert" className="error import-upload-error">{uploadError}</p>}
    {notice && <p role="status" className="notice">{notice}</p>}
    {store?.read_only && <p className="notice">Read-only archive: saved imports and executions remain available. Upload and fresh execution are disabled.</p>}
    {config?.active_campaign_id && <p className="muted">Fresh execution is paused while another campaign is active. Saving and reviewing imports remain available without provider calls.</p>}
    <div className="import-inputs"><div className="setup-field"><label htmlFor={`${fieldId}-saved`}>Saved imported bundles</label><select id={`${fieldId}-saved`} value={history.page?.items.some(item => item.import_id === selected) ? selected : ''} disabled={busy || !history.page?.items.length} onChange={event => select(event.target.value)}><option value="">Select an imported bundle</option>{history.page?.items.map(item => <option key={item.import_id} value={item.import_id}>{artifactLabel[item.artifact_kind]} · {item.import_id} · {sourceTrialOrigin(item.source, true)} · {item.source.model || 'Source model not recorded'}</option>)}</select></div><button className="text-button" disabled={!store || history.loading || busy} onClick={history.refresh}>Refresh imported bundles</button>{history.page?.has_more && <button className="text-button" disabled={history.loading || busy} onClick={() => void history.older()}>Load older imports</button>}</div>
    {history.loading && <p role="status" className="muted">Loading imported bundle history…</p>}
    {history.error && <p role="alert" className="error">{history.error} Refresh imported bundles to try again.</p>}
    {skipped > 0 && <p className="notice">{skipped} saved import {skipped === 1 ? 'summary' : 'summaries'} could not be verified and {skipped === 1 ? 'is' : 'are'} not listed. The other imports are unaffected.</p>}
    {history.page?.items.length === 0 && !skipped && <Empty>No regression bundles have been imported into this store.</Empty>}
    {!!history.page?.items.length && <p className="muted">{history.page.items.length} saved imports loaded · newest first. Older pages load only on request.</p>}
    {pending && pending.import_id !== selected && <div className="notice"><p>A previous execution request is unresolved. Resolve it before starting another imported regression.</p><button onClick={() => select(pending.import_id)}>Open unresolved request</button></div>}
    <ResourceNote resource={detail} />
    {detail.data && <ImportedBundleReview key={`${store?.identity}:${detail.data.import_id}`} bundle={detail.data} stale={!!detail.error || detail.loading} refresh={detail.refresh!} config={config} readiness={readiness} replay={replay} pending={pending} persistPending={persistPending} onEpisode={onEpisode} />}
  </Panel>
}

/** Every reason the fresh run is unavailable, each with what to do about it. */
export function freshRunBlockers({ bundle, config, readiness, replay, stale, storeMatches, target, pending, running }: { bundle: ImportedBundle; config?: ConfigStatus; readiness?: Resource<ReadinessStatus>; replay: boolean; stale: boolean; storeMatches: boolean; target?: ImportedBundle['targets'][number]; pending: boolean; running: boolean }): string[] {
  if (config?.data_store?.read_only === true || bundle.data_store.read_only) return ['This is a read-only archive. Saved imports stay readable; fresh runs need the writable workspace.']
  const blockers: string[] = []
  if (!storeMatches) blockers.push('The data store changed. Refresh this review before any action.')
  if (!bundle.runnable) blockers.push(`This import cannot run: ${bundle.runnable_reason ?? 'the current runtime is incompatible'}.`)
  if (!config?.live_enabled) blockers.push('Live execution is off in this workspace. Configure the live settings, then restart with ./scripts/start-local.sh --live --data-dir <this data directory>.')
  else {
    const live = readiness?.data?.live_configuration
    if (live?.missing_fields.length) blockers.push(`Live settings are missing: ${live.missing_fields.join(', ')}.`)
    else if (live && !live.ready) blockers.push('Live configuration is not ready. See Run readiness for details.')
    else if (!config.model_configured) blockers.push('The model or its credential is not configured for live runs.')
    if (!config.execution_profiles?.some(item => item.profile_id === 'sandbox-v1')) blockers.push('The sandbox-v1 execution profile is unavailable in this backend.')
  }
  if (!readiness || readiness.loading) blockers.push('Simulator readiness is still being checked.')
  else if (readiness.error || !readiness.data) blockers.push('Simulator readiness is unknown. Use Check again in Run readiness.')
  else if (!readiness.data.simulator.ready) blockers.push(`The simulator is not ready. ${readiness.data.simulator.message} Afterwards, use Check again in Run readiness.`)
  if (!target) blockers.push('Select a fresh target registration (register one in the Run desk if the list is empty).')
  else if (!target.compatible) blockers.push(`The selected target cannot run this bundle: ${target.reason ?? 'it is incompatible'}.`)
  if (config?.active_campaign_id) blockers.push('Another campaign is active. Wait for it to finish or stop it first.')
  if (pending) blockers.push('An earlier execution request is unresolved. Check, retry or cancel it first.')
  if (running) blockers.push('A fresh execution of this import is still running.')
  if (replay) blockers.push('Playback mode is on. Leave playback to run fresh trials.')
  if (stale) blockers.push('This review is refreshing or out of date. Refresh the import review.')
  return blockers
}

function ExecutionTaskFacts({ bundle }: { bundle: ImportedBundle }) {
  const task = bundle.execution_task
  if (!task) return <p className="notice">The task recorded in this bundle is malformed, so it cannot be sent to an agent. This import is stored for inspection only.</p>
  return <dl className="facts compact"><Field name="Exact task sent to the agent"><span className="task-text">{task.task_text}</span></Field><Field name="Authorized order">{task.order_id}</Field><Field name="Task origin">{task.origin === 'bundled' ? 'Recorded in this bundle by its source campaign; FaultLab did not write it' : 'FaultLab default task; this bundle records none'}</Field></dl>
}

function ImportedBundleReview({ bundle, stale, refresh, config, readiness, replay, pending, persistPending, onEpisode }: { bundle: ImportedBundle; stale: boolean; refresh: () => void; config?: ConfigStatus; readiness?: Resource<ReadinessStatus>; replay: boolean; pending: PendingImportRequest | null; persistPending: (value: PendingImportRequest | null) => void; onEpisode: (owner: string, episode: string) => void }) {
  const fieldId = useId()
  const [targetId, setTargetId] = useState(''); const [busy, setBusy] = useState(false); const [error, setError] = useState<string | null>(null)
  const [execution, setExecution] = useState<ImportedExecution>(); const [requestAbsent, setRequestAbsent] = useState(false)
  const [confirming, setConfirming] = useState(false); const [status, setStatus] = useState<string | null>(null)
  const locked = useRef(false)
  const target = bundle.targets.find(item => item.agent_registration_id === targetId)
  const readOnly = config?.data_store?.read_only === true || bundle.data_store.read_only
  const storeMatches = !!config?.data_store && config.data_store.identity === bundle.data_store.identity
  const ownPending = pending?.import_id === bundle.import_id ? pending : null
  const histories = useImportHistory(`import-executions:${bundle.import_id}`, async before => {
    const page = await importApi.executions(bundle.import_id, before)
    page.items.forEach(item => matchingImportExecution(item, bundle))
    return page
  }, item => item.execution.execution_id)
  const running = useResource(execution && ['PENDING', 'RUNNING'].includes(execution.execution.status) ? `import-request:${bundle.import_id}:${execution.request_id}` : null,
    async () => { const value = await importApi.lookup(bundle.import_id, execution!.request_id); if ('cancelled' in value) throw new Error('The saved execution identity unexpectedly refers to a cancelled request.'); return matchingImportExecution(value, bundle) }, 1500)
  // Keep the terminal response when the request poll stops, and reread the saved list
  // once so its status labels do not keep showing the run as still in progress.
  const refreshHistories = histories.refresh
  useEffect(() => {
    if (!running.data) return
    setExecution(running.data)
    if (!['PENDING', 'RUNNING'].includes(running.data.execution.status)) refreshHistories()
  }, [running.data])
  const latest = running.data ?? execution
  const inProgress = ['PENDING', 'RUNNING'].includes(latest?.execution.status ?? '')
  const blockers = freshRunBlockers({ bundle, config, readiness, replay, stale, storeMatches, target, pending: !!pending, running: inProgress })
  const canRun = !busy && blockers.length === 0 && !!target && !!bundle.execution_task
  const limits = bundle.limits
  const bound = `Up to ${limits.max_model_requests} billable model requests: ${limits.reserved_actor_turns} reserved actor turns (${limits.required_trials} trials × ${limits.episode_budget.actor_calls} turns) plus at most ${limits.transport_retry_allowance} charged transport retries.`
  async function action(work: () => Promise<void>) {
    if (locked.current) return
    locked.current = true; setBusy(true); setError(null); setStatus(null)
    try { await work() } catch (reason) { setError(message(reason)) }
    finally { locked.current = false; setBusy(false) }
  }
  function accept(value: ImportedExecution, expected?: ImportExecutionRequest) {
    matchingImportExecution(value, bundle)
    if (expected && (value.request_id !== expected.request_id || value.target.agent_registration_id !== expected.agent_registration_id || value.target.configuration_hash !== expected.expected_target_configuration_hash)) throw new Error('The returned execution does not match the saved request. Its nonce was retained.')
    setExecution(value); setRequestAbsent(false)
    if (ownPending?.request.request_id === value.request_id || expected) persistPending(null)
    histories.refresh()
  }
  async function execute(body: ImportExecutionRequest) {
    setRequestAbsent(false)
    accept(await importApi.execute(bundle.import_id, body), body)
  }
  async function checkRequest() {
    if (!ownPending) return
    setRequestAbsent(false)
    try {
      const value = await importApi.lookup(bundle.import_id, ownPending.request.request_id)
      if ('cancelled' in value) { persistPending(null); refresh(); setStatus('That request was cancelled before it started; nothing ran.') } else accept(value, ownPending.request)
    } catch (reason) { if (reason instanceof ApiError && reason.status === 404) setRequestAbsent(true); else throw reason }
  }
  async function cancelRequest() {
    if (!ownPending) return
    const result = await importApi.cancel(bundle.import_id, ownPending.request)
    if (result.cancelled) { persistPending(null); setRequestAbsent(false); refresh(); setStatus('Request cancelled before it started; nothing ran.') }
    else { accept(result.execution, ownPending.request); setStatus('The request had already started, so it was not cancelled. Its saved execution is shown below.') }
  }
  return <div className="import-review">
    <div className="split-heading"><h3>Review imported bundle · {bundle.import_id}</h3><button className="text-button" disabled={busy} onClick={refresh}>Refresh import review</button></div>
    <dl className="facts compact"><Field name="Artifact">{artifactLabel[bundle.artifact_kind]}</Field><Field name="Source decision">Historical {label(bundle.policy.decision)} · not local acceptance</Field><Field name="How source trials were produced">{sourceTrialOrigin(bundle.source)}</Field><Field name="Source model">{bundle.source.model || 'Not recorded'}</Field><Field name="Source agent registration">{bundle.source.agent_registration_malformed ? 'Malformed in the saved summary; not shown' : bundle.source.agent_registration_id ?? 'Not recorded'}</Field><Field name="Original policy version">{bundle.policy.version}</Field><Field name="Immutable source policy"><Hash value={bundle.policy.hash} /></Field><Field name="Source configuration"><Hash value={bundle.source.configuration_hash} /></Field><Field name="Manifest"><Hash value={bundle.manifest_hash} /></Field><Field name="Fixture / invariant">{bundle.recipe.fixture_id} · {bundle.recipe.target_invariant}</Field></dl>
    <ExecutionTaskFacts bundle={bundle} />
    <Json value={bundle.recipe} title="Immutable source and retained fault recipes" />
    <ImportedHistoricalEvidence bundle={bundle} />
    <section className="import-target" aria-label="Fresh imported regression setup"><h3>Separate fresh execution</h3><p className="muted">Choose a reviewed local target. This runs exactly the bundled policy and the task below in three new worlds; it does not activate the policy or rewrite original source results.</p>
      <p className={bundle.runnable ? 'muted' : 'notice'}>{bundle.runnable ? 'This bundle is eligible for local execution after target and runtime checks.' : `Stored for inspection; not runnable. ${bundle.runnable_reason ?? 'The current runtime is incompatible.'}`}</p>
      <div className="setup-field"><label htmlFor={`${fieldId}-target`}>Fresh target registration</label><select id={`${fieldId}-target`} value={targetId} disabled={busy || !!ownPending} onChange={event => { setTargetId(event.target.value); setConfirming(false); setError(null) }}><option value="">Select a reviewed local target</option>{bundle.targets.map(item => <option key={item.agent_registration_id} value={item.agent_registration_id}>{item.agent} · {item.model} · {item.agent_registration_id}{item.compatible ? '' : ' · incompatible'}</option>)}</select></div>
      {!bundle.targets.length && <p className="muted">No reviewed live target is registered yet. The built-in offline smoke agent cannot run imported regressions.</p>}
      {target && <dl className="facts compact"><Field name="Actual target agent">{target.agent}</Field><Field name="Actual target model">{target.model}</Field><Field name="Target configuration"><Hash value={target.configuration_hash} /></Field><Field name="Compatibility">{target.compatible ? 'Compatible installed source and task contract; provider access not checked' : target.reason ?? 'Incompatible'}</Field></dl>}
      <p className="muted"><a href="#new-campaign-setup">Configure or register a reviewed agent in the Run desk</a>, then refresh this review. Choose the live profile there to register configured source; registration makes no provider call and is not behavioral validation.</p>
      <dl className="facts compact"><Field name="Fresh trials">{limits.required_trials}</Field><Field name="Execution profile">sandbox-v1</Field><Field name="Per-trial limits">{limits.episode_budget.actor_calls ?? 'Not recorded'} actor turns · {limits.episode_budget.http_attempts ?? 'Not recorded'} HTTP attempts · {limits.episode_budget.wall_seconds ?? 'Not recorded'} seconds</Field><Field name="Spending bound for one run">{bound}</Field></dl><Json value={limits} title="All immutable fresh-trial limits" />
      <section aria-label="Task sent in fresh trials"><h4>Each fresh trial sends the agent this task</h4><ExecutionTaskFacts bundle={bundle} /></section>
      <p className="notice">Fresh execution makes billable model and telemetry calls. {bound} Selecting the button below asks for a separate confirmation.</p>
      {!(confirming && canRun) && <button className="primary" disabled={!canRun} onClick={() => { if (canRun) { setConfirming(true); setStatus(null) } }}>{busy ? 'Saving execution request…' : 'Run imported regression in fresh worlds'}</button>}
      {confirming && canRun && target && bundle.execution_task && <div className="notice" role="group" aria-label="Confirm billable fresh run"><p><strong>Confirm this billable run.</strong> Target: {target.agent} · {target.model} · <code>{target.agent_registration_id}</code>. Task: “{bundle.execution_task.task_text}” on order <code>{bundle.execution_task.order_id}</code>. {bound}</p><div className="controls"><button className="primary" onClick={() => void action(async () => {
        if (!canRun || !target) return
        const body: ImportExecutionRequest = { expected_store_identity: bundle.data_store.identity, expected_manifest_hash: bundle.manifest_hash, expected_target_configuration_hash: target.configuration_hash, agent_registration_id: target.agent_registration_id, request_id: `import-run-${crypto.randomUUID()}`, execution_profile_id: 'sandbox-v1', execute_live: true }
        persistPending({ import_id: bundle.import_id, request: body })
        setConfirming(false)
        await execute(body)
      })}>Confirm billable fresh run</button><button className="text-button" onClick={() => setConfirming(false)}>Back to review</button></div></div>}
      {blockers.length > 0 && <div className="muted" aria-label="Why fresh execution is unavailable"><p>Fresh execution is unavailable:</p><ul>{blockers.map(item => <li key={item}>{item}</li>)}</ul><p>Saved source review does not require any of these.</p></div>}
    </section>
    {ownPending && <section className="notice" aria-label="Unresolved imported execution request"><h3>Execution request awaiting a confirmed response</h3><p>The exact request was saved before dispatch. A timeout does not mean it failed. Check its saved result or retry this same request; neither creates a second execution for this nonce.</p><code>{ownPending.request.request_id}</code><div className="controls"><button disabled={busy} onClick={() => void action(checkRequest)}>Check saved request</button><button disabled={busy || readOnly || replay || !storeMatches} onClick={() => void action(() => execute(ownPending.request))}>Retry same execution request</button><button disabled={busy || readOnly || replay || !storeMatches} onClick={() => void action(cancelRequest)}>Cancel unadmitted request</button></div>{requestAbsent && <p>No saved execution was found at the last check. The original request may still be processing. Its nonce is retained until the backend confirms cancellation or returns the execution.</p>}<p>Cancelling prevents later admission only if this request has not started. If already admitted, its existing execution is returned; it is not stopped or rerun.</p></section>}
    {status && <p role="status" className="notice">{status}</p>}
    <section className="import-execution-history" aria-label="Imported regression execution history"><h3>Saved fresh executions for this import</h3><p className="muted">Opening a saved execution reads its result; it does not rerun it.</p><label htmlFor={`${fieldId}-execution`}>Saved imported executions</label><select id={`${fieldId}-execution`} value={histories.page?.items.some(item => item.execution.execution_id === latest?.execution.execution_id) ? latest!.execution.execution_id : ''} disabled={busy || !histories.page?.items.length} onChange={event => { const value = histories.page?.items.find(item => item.execution.execution_id === event.target.value); if (value) { setExecution(value); setError(null) } }}><option value="">Select a saved fresh execution</option>{histories.page?.items.map(item => <option key={item.execution.execution_id} value={item.execution.execution_id}>{item.execution.execution_id} · {label(item.execution.status)} · {item.target.agent} · {item.target.model}</option>)}</select><div className="controls"><button className="text-button" disabled={busy || histories.loading} onClick={histories.refresh}>Refresh imported executions</button>{histories.page?.has_more && <button className="text-button" disabled={busy || histories.loading} onClick={() => void histories.older()}>Load older imported executions</button>}</div>
      {histories.loading && <p role="status" className="muted">Loading imported execution history…</p>}{histories.error && <p role="alert" className="error">{histories.error}</p>}{histories.page?.items.length === 0 && <Empty>No fresh execution has been saved for this import.</Empty>}
    </section>
    <ResourceNote resource={running} />
    {latest && <ImportedFreshEvidence key={latest.execution.execution_id} value={latest} artifactKind={bundle.artifact_kind} faultCount={(bundle.recipe.retained ?? bundle.recipe.source).primitives.length} onEpisode={onEpisode} />}
    {error && <p role="alert" className="error">{error} No action is retried automatically.</p>}
  </div>
}
