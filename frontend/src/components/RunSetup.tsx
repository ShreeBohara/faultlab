import { useEffect, useId, useRef, useState } from 'react'
import type { Campaign } from '../generated/contracts'
import type { ConfigStatus, ReadinessStatus } from '../api'
import { runApi, type AgentKind, type RunMode, type RunProfile } from '../runPlans'
import { useResource, type Resource } from '../useResource'
import { Field, ResourceNote } from './common'

export function RunSetup({ config, replay, readiness, onCampaign }: { config?: ConfigStatus; replay: boolean; readiness?: Resource<ReadinessStatus>; onCampaign: (campaign: Campaign) => void }) {
  const fieldId = useId()
  const options = useResource(config ? `run-options:${config.data_store?.identity ?? 'current'}` : null, runApi.options, null)
  const [profile, setProfile] = useState<RunProfile>('offline-v1')
  const [agentKind, setAgentKind] = useState<AgentKind>('reference')
  const [mode, setMode] = useState<RunMode>('baseline')
  const [caseId, setCaseId] = useState('dev-1')
  const [task, setTask] = useState('')
  const [order, setOrder] = useState('order-demo')
  const [busy, setBusy] = useState<'register' | 'create' | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [message, setMessage] = useState<string | null>(null)
  const locked = useRef(false)
  const value = options.data
  const live = profile === 'live-v1'
  const agent = value?.agents.find(item => item.agent === agentKind)
  const developmentCase = value?.development.cases.find(item => item.case_id === caseId)
  const readOnly = config?.data_store?.read_only === true || value?.data_store.read_only === true
  const storeChanged = !!value && !!config?.data_store && value.data_store.identity !== config.data_store.identity
  const blocked = readOnly || replay || !!config?.active_campaign_id || !!busy || !!options.error || options.loading || storeChanged
  const liveConfigured = !!config?.live_enabled && !!config.model_configured && readiness?.data?.live_configuration.ready !== false
  const canCreate = !blocked && !!value && !!task.trim() && task.trim().length <= 2000 && /^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$/.test(order.trim())
    && (mode !== 'baseline' || !!developmentCase) && (!live || liveConfigured && agent?.status === 'READY' && agent.registered)
    && (mode !== 'compare' || agent?.compare_available === true)
  useEffect(() => { if (value) setTask(previous => previous || value.task.task_text_default) }, [value])
  async function action(kind: 'register' | 'create', work: () => Promise<void>) {
    if (locked.current || blocked) return
    locked.current = true; setBusy(kind); setError(null); setMessage(null)
    try { await work() } catch (error) { setError(error instanceof Error ? error.message : 'The request was not accepted. Refresh run options before trying again.') }
    finally { locked.current = false; setBusy(null) }
  }
  return <section className="run-setup" aria-label="New campaign setup">
    <div className="split-heading"><h3>New campaign</h3><button className="text-button" disabled={!!busy || options.loading} onClick={options.refresh}>Refresh run options</button></div>
    <ResourceNote resource={options} />
    {value && <>
      <div className="setup-field"><label htmlFor={`${fieldId}-profile`}>Execution profile</label><select id={`${fieldId}-profile`} value={profile} disabled={!!busy} onChange={event => { const next = event.target.value as RunProfile; setProfile(next); if (next === 'offline-v1') setMode('baseline'); setError(null); setMessage(null) }}>{value.profiles.map(item => <option key={item.profile_id} value={item.profile_id}>{item.label}</option>)}</select></div>
      {live ? <div className="agent-selection">
        <div className="setup-field"><label htmlFor={`${fieldId}-agent`}>Reviewed agent</label><select id={`${fieldId}-agent`} value={agentKind} disabled={!!busy} onChange={event => { setAgentKind(event.target.value as AgentKind); setError(null); setMessage(null) }}>{value.agents.map(item => <option key={item.agent} value={item.agent}>{item.label}</option>)}</select></div>
        {agent && <><p className="muted">{agent.message}</p><dl className="facts compact"><Field name="Configured actor">{agent.model || 'Not configured'}</Field><Field name="Registration">{agent.registration_id ?? 'Not registered for this setup'}</Field></dl>
          {!agent.registered && <button disabled={blocked || agent.status !== 'READY'} onClick={() => void action('register', async () => { await runApi.register(value.data_store.identity, agent.agent); setMessage('Registration saved. No agent execution or provider call was made.'); options.refresh?.() })}>{busy === 'register' ? 'Registering…' : 'Register configured agent'}</button>}
          <p className="muted">{agent.source_conformance === 'VERIFIED' ? 'Installed source and adapter conformance verified.' : 'Installed source and adapter conformance unavailable.'} This is not behavioral validation. Provider access has not been checked.</p>
          {!!agent.limitations.length && <details><summary>Agent limitations</summary><ul className="muted">{agent.limitations.map(item => <li key={item}>{item}</li>)}</ul></details>}
          {agentKind === 'smolagents' && <p className="muted">Supports baseline, original Learn and compatible policy comparison. Separate reference-context and completion research studies are not supported.</p>}
        </>}
      </div> : <p className="profile-note">Offline smoke uses the handwritten reference in a fresh synthetic world. It makes no model calls and does not measure learned improvement.</p>}
      <div className="supported-task"><span className="small-label">SUPPORTED TASK</span><h3>{value.task.label}</h3><p className="muted">{value.task.description}</p></div>
      <div className="setup-field"><label htmlFor={`${fieldId}-task`}>Instructions within this task</label><textarea id={`${fieldId}-task`} rows={3} maxLength={2000} value={task} disabled={!!busy} onChange={event => setTask(event.target.value)} /></div>
      <div className="setup-field"><label htmlFor={`${fieldId}-order`}>Authorized order</label><input id={`${fieldId}-order`} value={order} disabled={!!busy} maxLength={128} pattern="[A-Za-z0-9][A-Za-z0-9_.:-]*" onChange={event => setOrder(event.target.value)} /></div>
      <div className="setup-field"><label htmlFor={`${fieldId}-mode`}>Campaign mode</label><select id={`${fieldId}-mode`} value={mode} disabled={!!busy} onChange={event => setMode(event.target.value as RunMode)}><option value="baseline">Baseline · one fresh trial</option><option value="learn" disabled={!live}>Learn · original learning workflow</option><option value="compare" disabled={!live || !agent?.compare_available}>Compare · accepted policy required</option></select></div>
      {mode === 'baseline' && <><div className="setup-field"><label htmlFor={`${fieldId}-case`}>Public development case</label><select id={`${fieldId}-case`} value={caseId} disabled={!!busy} onChange={event => setCaseId(event.target.value)}>{value.development.cases.map(item => <option key={item.case_id} value={item.case_id}>{item.label}</option>)}</select></div><p className="muted">{developmentCase?.description}</p></>}
      {mode === 'learn' && <p className="muted">Explorer selects from the fixed public development search space: {value.learn.search_space.kinds.join(', ')}, up to {value.learn.search_space.maximum_primitives} faults per recipe and {value.learn.selection_limit} selections. Reproduction, diagnosis, repair and challenge run only when their evidence gates qualify.</p>}
      {mode === 'compare' && <p className="muted">Compare the compatible accepted policy with the empty baseline using the fixed protected comparison: {value.compare.case_count} cases × {value.compare.trials_per_case} paired trials. Protected cases are not shown or used as development choices.</p>}
      <section className="plan-preview" aria-label="Current plan preview"><h3>Current plan preview</h3><dl className="facts compact">
        <Field name="Execution">{live ? 'Live provider execution' : 'Offline handwritten reference · B1'}</Field><Field name="Agent">{live ? agent?.label : 'Handwritten reference smoke'}</Field>
        <Field name="Task">{value.task.label}</Field><Field name="Mode / case">{mode === 'baseline' ? developmentCase?.label : mode === 'learn' ? 'Original learning workflow' : 'Accepted-policy comparison'}</Field>
        <Field name="Initial policy">{mode === 'compare' ? agent?.accepted_policy_version : mode === 'learn' ? agent?.accepted_policy_version ?? 'policy-v0' : 'policy-v0'}</Field>
        <Field name="Campaign limits">{value.caps.model_calls} model requests · {value.caps.tokens.toLocaleString()} tokens · ${value.caps.dollars.toFixed(2)}</Field>
        <Field name="Per-episode limits">{value.episode_budget.actor_calls} actor turns · {value.episode_budget.http_attempts} HTTP attempts · {value.episode_budget.wall_seconds} seconds</Field>
      </dl><p className="muted">{live ? 'Live execution can make bounded, billable provider calls. These are caps, not a predicted bill.' : 'Expected provider calls and model cost: zero.'} Creating the campaign saves an idle plan. Review that frozen plan before pressing Start.</p></section>
      <details className="new-campaign-config"><summary>Current setup for new live campaigns</summary><dl className="facts compact"><Field name="Actor">{value.models.actor}</Field><Field name="Explorer">{value.models.explorer}</Field><Field name="Mechanic">{value.models.mechanic}</Field><Field name="Actor context">{config?.actor_context_protocol ?? 'Not reported by this backend'}</Field><Field name="Setup hash"><code>{value.setup_hash}</code></Field></dl><p className="muted">Current settings do not rewrite a saved campaign's frozen plan.</p></details>
      {live && !liveConfigured && <p className="notice">Live execution is not configured. Check run readiness and server settings before creating a live campaign.</p>}
      {storeChanged && <p className="error" role="alert">The data store changed. Refresh run options before creating a campaign.</p>}
      <button disabled={!canCreate} onClick={() => void action('create', async () => {
        if (!canCreate) return
        const created = await runApi.create({ expected_store_identity: value.data_store.identity, expected_setup_hash: value.setup_hash, task_definition_id: value.task.task_definition_id, config_profile_id: profile, mode, task_text: task.trim(), order_id: order.trim(), ...(live ? { agent_registration_id: agent!.registration_id! } : {}), ...(mode === 'baseline' ? { development_case_id: caseId } : {}) })
        onCampaign(created); setMessage('Campaign created. Review its frozen plan, then press Start campaign.')
      })}>{busy === 'create' ? 'Creating campaign…' : 'Create campaign'}</button>
    </>}
    {message && <p className="notice" role="status">{message}</p>}{error && <p className="error" role="alert">{error} Refresh run options to review the current setup; the request will not be retried automatically.</p>}
  </section>
}
