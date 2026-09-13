import { useRef, useState } from 'react'
import type { Campaign } from '../generated/contracts'
import { api, type ConfigStatus } from '../api'
import { Badge, Field, Panel } from './common'

export function RunControls({ config, campaign, replay, onCampaign, onReplay }: { config?: ConfigStatus; campaign?: Campaign; replay: boolean; onCampaign: (campaign: Campaign) => void; onReplay: (value: boolean) => void }) {
  const [task, setTask] = useState('Upgrade this order to express shipping, then send its confirmation.')
  const [order, setOrder] = useState('order-demo')
  const [profile, setProfile] = useState('offline-v1')
  const [mode, setMode] = useState<'baseline' | 'learn' | 'compare'>('baseline')
  const [busy, setBusy] = useState<string | null>(null)
  const [message, setMessage] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [stopSeq, setStopSeq] = useState<number | null>(null)
  const lock = useRef(false)
  const liveReady = !!config?.live_enabled && !!config.model_configured && config.profile_ids.includes('live-v1')
  const active = !!config?.active_campaign_id
  const canCreate = !!config && task.trim().length > 0 && order.trim().length > 0 && !busy && !active && !replay
  const liveProfile = profile === 'live-v1'
  const roleModels = config?.models ?? (config ? { actor: config.model, explorer: config.model, mechanic: config.model } : undefined)
  async function action(name: string, work: () => Promise<void>) {
    if (lock.current) return
    lock.current = true; setBusy(name); setError(null); setMessage(null)
    try { await work() } catch (e) { setError(e instanceof Error ? e.message : 'Action failed.') }
    finally { lock.current = false; setBusy(null) }
  }
  async function create(selectedMode: 'baseline' | 'learn' | 'compare', start: boolean) {
    const created = await api.create({ task_text: task.trim(), order_id: order.trim(), mode: selectedMode, config_profile_id: profile })
    onCampaign(created); setStopSeq(null)
    if (start) { onCampaign(await api.start(created.campaign_id)); setMessage('Start accepted. Following persisted execution state.') }
    else setMessage('Campaign created. Press Start campaign to execute it.')
  }
  const stopAcknowledged = stopSeq !== null && campaign?.stop_requested && (campaign.state_seq ?? 0) > stopSeq
  return <Panel title="Run desk" number="01" className="run-panel" aside={<span className="small-label">Explicit execution</span>}>
    <label>Task for new campaign<textarea rows={3} value={task} onChange={e => setTask(e.target.value)} maxLength={4000} disabled={!!busy} /></label>
    <div className="two-fields"><label>Authorized order<input value={order} onChange={e => setOrder(e.target.value)} pattern="[A-Za-z0-9][A-Za-z0-9_.:-]*" maxLength={128} /></label><label>Execution profile<select value={profile} onChange={e => { setProfile(e.target.value); if (e.target.value === 'offline-v1') setMode('baseline') }}><option value="offline-v1">Offline reference smoke</option><option value="live-v1" disabled={!liveReady}>Live · configured model</option></select></label></div>
    <label>Campaign mode<select value={mode} onChange={e => setMode(e.target.value as typeof mode)}><option value="baseline">Baseline</option><option value="learn" disabled={!liveProfile}>Learn</option><option value="compare" disabled={!liveProfile}>Compare</option></select></label>
    <p className="profile-note">{liveProfile ? `Live Start uses ${roleModels?.actor} as Actor and ${roleModels?.explorer} as Explorer/Mechanic. It can make bounded, billable provider calls and write to fresh synthetic worlds.` : 'Offline reference smoke runs the handwritten reference in a fresh synthetic world. It makes no model calls and does not measure learned improvement.'}</p>
    <div className="controls"><button disabled={!canCreate || (liveProfile && !liveReady)} onClick={() => void action('create', () => create(mode, false))}>Create campaign</button><button className="primary" disabled={!!busy || replay || active || campaign?.state !== 'IDLE' || (campaign.config_profile_id === 'live-v1' && !liveReady)} onClick={() => void action('start', async () => { if (campaign) { onCampaign(await api.start(campaign.campaign_id)); setMessage('Start accepted. Following persisted execution state.') } })}>Start campaign <span aria-hidden="true">↗</span></button></div>
    <div className="controls secondary-controls"><button disabled={!canCreate || (liveProfile && !liveReady)} onClick={() => void action('baseline', () => create('baseline', true))}>Run baseline</button><button disabled={!canCreate || !liveProfile || !liveReady} onClick={() => void action('compare', () => create('compare', true))}>Compare</button><button className="danger" disabled={!!busy || replay || !campaign || !active || campaign.stop_requested} onClick={() => { if (campaign) { setStopSeq(campaign.state_seq ?? 0); void action('stop', async () => { await api.stop(campaign.campaign_id); setMessage('Stop requested; waiting for the next successful state poll.') }) } }}>Stop</button></div>
    {campaign && <div className="run-receipt"><Badge value={campaign.state ?? 'IDLE'} /><dl className="facts"><Field name="Campaign"><code>{campaign.campaign_id}</code></Field><Field name="Recorded task">{campaign.task_text}</Field><Field name="Recorded order">{campaign.order_id}</Field><Field name="Actor model">{campaign.model}</Field><Field name="Call budget">{campaign.usage?.model_calls ?? 'Not recorded'} used / {campaign.caps?.model_calls ?? 'Not recorded'} cap · {campaign.reserved_calls ?? 'Not recorded'} reserved</Field><Field name="Cost">{campaign.usage?.cost_dollars == null ? 'Unknown' : `$${campaign.usage.cost_dollars.toFixed(4)}`} / ${campaign.caps?.dollars ?? 'not recorded'} cap</Field></dl>{campaign.terminal_reason && <p>{campaign.terminal_reason}</p>}</div>}
    <div className="controls bottom-controls"><button className="text-button" disabled={!!busy || active || replay} title={active ? 'Stop active execution before resetting.' : 'Prepare future clean worlds; policy and evidence history stays saved.'} onClick={() => void action('reset', async () => { await api.reset(); setMessage('Future world reset is ready. Existing policies and evidence remain saved.') })}>Reset future world</button><button className="text-button" disabled={!campaign || !!busy} onClick={() => onReplay(!replay)}>{replay ? 'Exit playback' : 'Recorded playback'}</button></div>
    {active && <p className="muted">Reset becomes available after active execution has stopped.</p>}
    <div role="status" aria-live="polite">{busy && <p className="muted">{busy === 'stop' ? 'Stop requested…' : 'Saving request…'}</p>}{stopAcknowledged ? <p className="notice">Stop acknowledged by the next successful poll.</p> : message && <p className="notice">{message}</p>}</div>
    {error && <p className="error" role="alert">{error}</p>}
  </Panel>
}
