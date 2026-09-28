import { useRef, useState } from 'react'
import type { Campaign } from '../generated/contracts'
import { api, type ConfigStatus, type ReadinessStatus } from '../api'
import { runApi } from '../runPlans'
import { useResource, type Resource } from '../useResource'
import { Badge, Field, Panel } from './common'
import { RunReadiness } from './RunReadiness'
import { RunSetup } from './RunSetup'
import { CampaignPlan } from './CampaignPlan'
import { RecordingDownload } from './RecordingDownload'

export function RunControls({ config, campaign, replay, onCampaign, onReplay, onOpenCampaign, readiness, onCheckReadiness }: { config?: ConfigStatus; campaign?: Campaign; replay: boolean; onCampaign: (campaign: Campaign) => void; onReplay: (value: boolean) => void; onOpenCampaign?: (id: string) => void; readiness?: Resource<ReadinessStatus>; onCheckReadiness?: () => void }) {
  const [busy, setBusy] = useState<string | null>(null)
  const [message, setMessage] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [stopRequest, setStopRequest] = useState<{ campaignId: string; seq: number } | null>(null)
  const lock = useRef(false)
  const readOnly = config?.data_store?.read_only === true
  const plan = useResource(campaign ? `plan:${config?.data_store?.identity ?? 'current'}:${campaign.campaign_id}` : null, () => runApi.plan(campaign!.campaign_id), null)
  const liveReady = !!config?.live_enabled && !!config.model_configured && readiness?.data?.live_configuration.ready !== false
  const simulatorReady = readiness ? !readiness.loading && !readiness.error && readiness.data?.simulator.ready === true : true
  const active = !!config?.active_campaign_id
  const selectedActive = !!campaign && config?.active_campaign_id === campaign.campaign_id
  const otherActive = active && !selectedActive
  const startBlocked = !config || readOnly || !!busy || replay || active || !simulatorReady || !plan.data || !!plan.error || plan.loading || campaign?.state !== 'IDLE' || (campaign.config_profile_id === 'live-v1' && !liveReady)
  async function action(name: string, work: () => Promise<void>) {
    if (readOnly || lock.current) return
    lock.current = true; setBusy(name); setError(null); setMessage(null)
    try { await work() } catch (e) { setError(e instanceof Error ? e.message : 'Action failed.') }
    finally { lock.current = false; setBusy(null) }
  }
  const stopAcknowledged = stopRequest?.campaignId === campaign?.campaign_id && !!stopRequest && campaign?.stop_requested && (campaign.state_seq ?? 0) > stopRequest.seq
  return <Panel title="Run desk" number="01" className="run-panel" aside={<span className="small-label">Explicit execution</span>}>
    {readiness && onCheckReadiness && <RunReadiness resource={readiness} onCheck={onCheckReadiness} />}
    <RunSetup config={config} replay={replay} readiness={readiness} onCampaign={value => { onCampaign(value); setStopRequest(null); setMessage(null); setError(null) }} />
    {otherActive && <div className="notice"><p>Another campaign is active: <code>{config!.active_campaign_id}</code>. Open it to inspect progress or request Stop.</p>{onOpenCampaign && <button className="text-button" disabled={!!busy} onClick={() => onOpenCampaign(config!.active_campaign_id!)}>Open active campaign</button>}</div>}
    {campaign && <div className="run-receipt"><Badge value={campaign.state ?? 'IDLE'} /><dl className="facts"><Field name="Campaign"><code>{campaign.campaign_id}</code></Field><Field name="Recorded task">{campaign.task_text}</Field><Field name="Recorded order">{campaign.order_id}</Field><Field name="Actor model">{campaign.model}</Field><Field name="Call budget">{campaign.usage?.model_calls ?? 'Not recorded'} used / {campaign.caps?.model_calls ?? 'Not recorded'} cap · {campaign.reserved_calls ?? 'Not recorded'} reserved</Field><Field name="Cost">{campaign.usage?.cost_dollars == null ? 'Unknown' : `$${campaign.usage.cost_dollars.toFixed(4)}`} / ${campaign.caps?.dollars ?? 'not recorded'} cap</Field></dl>{campaign.terminal_reason && <p>{campaign.terminal_reason}</p>}<CampaignPlan campaign={campaign} resource={plan} /></div>}
    <div className="controls secondary-controls"><button className="primary" disabled={startBlocked} onClick={() => void action('start', async () => { if (campaign && !startBlocked) { onCampaign(await api.start(campaign.campaign_id)); setMessage('Start accepted. Following persisted execution state.') } })}>Start campaign <span aria-hidden="true">↗</span></button><button className="danger" disabled={readOnly || !!busy || replay || !selectedActive || campaign?.stop_requested} onClick={() => { if (!readOnly && campaign && selectedActive) { setStopRequest({ campaignId: campaign.campaign_id, seq: campaign.state_seq ?? 0 }); void action('stop', async () => { await api.stop(campaign.campaign_id); setMessage('Stop requested; waiting for the next successful state poll.') }) } }}>Stop</button></div>
    <div className="controls bottom-controls"><button className="text-button" disabled={readOnly || !!busy || active || replay} title={active ? 'Stop active execution before resetting.' : 'Prepare future clean worlds; policy and evidence history stays saved.'} onClick={() => void action('reset', async () => { await api.reset(); setMessage('Future world reset is ready. Existing policies and evidence remain saved.') })}>Reset future world</button><button className="text-button" disabled={!campaign || !!busy} onClick={() => onReplay(!replay)}>{replay ? 'Exit playback' : 'Recorded playback'}</button></div>
    {campaign && <RecordingDownload key={campaign.campaign_id} campaignId={campaign.campaign_id} />}
    {active && <p className="muted">Reset becomes available after active execution has stopped.</p>}
    <div role="status" aria-live="polite">{busy && <p className="muted">{busy === 'stop' ? 'Stop requested…' : 'Saving request…'}</p>}{stopAcknowledged ? <p className="notice">Stop acknowledged by the next successful poll.</p> : message && <p className="notice">{message}</p>}</div>
    {error && <p className="error" role="alert">{error}</p>}
  </Panel>
}
