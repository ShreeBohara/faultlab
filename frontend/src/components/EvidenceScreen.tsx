import { useEffect, useState } from 'react'
import { api } from '../api'
import type { Campaign } from '../generated/contracts'
import { getExperiments } from '../experiments'
import { useEvents, useResource } from '../useResource'
import { RunControls } from './RunControls'
import { Timeline } from './Timeline'
import { PolicyPanel } from './PolicyPanel'
import { OutcomeMatrix } from './OutcomeMatrix'
import { CounterexamplePanel } from './CounterexamplePanel'
import { DiagnosticPanel } from './DiagnosticPanel'
import { ChallengePanel } from './ChallengePanel'
import { PortabilityPanel } from './PortabilityPanel'
import { RegressionControls } from './RegressionControls'
import { SponsorEvidence } from './SponsorEvidence'
import { ReplayView } from './ReplayView'
import { RunSummary } from './RunSummary'
import { ResourceNote } from './common'
const storedCampaign = () => { try { return localStorage.getItem('faultlab:campaign') || '' } catch { return '' } }
export function EvidenceScreen() {
  const [campaignId, setCampaignId] = useState(storedCampaign)
  const [campaignInput, setCampaignInput] = useState(campaignId)
  const [selectedEpisode, setSelectedEpisode] = useState<string | null>(null)
  const [replay, setReplay] = useState(false)
  const [optimistic, setOptimistic] = useState<Campaign>()
  const [healthAttempt, setHealthAttempt] = useState(0)
  const health = useResource(`health:${healthAttempt}`, api.health, 6000)
  const config = useResource('config', api.config)
  const campaignResource = useResource(campaignId ? `campaign:${campaignId}` : null, () => api.campaign(campaignId))
  const campaign = campaignResource.data?.campaign_id === campaignId && (!optimistic || (campaignResource.data.state_seq ?? 0) >= (optimistic.state_seq ?? 0)) ? campaignResource.data : optimistic?.campaign_id === campaignId ? optimistic : undefined
  const matrix = useResource(campaignId ? `matrix:${campaignId}` : null, () => api.matrix(campaignId))
  const policies = useResource('policies', api.policies)
  const regressions = useResource(campaignId ? `regressions:${campaignId}` : null, () => api.regressions(campaignId))
  const experiments = useResource(campaignId ? `experiments:${campaignId}` : null, () => getExperiments(campaignId))
  const registrations = useResource('registrations', api.registrations)
  const aria = useResource(campaignId ? `aria:${campaignId}` : null, () => api.aria(campaignId))
  const episodeId = selectedEpisode ?? campaign?.latest_episode_id ?? null
  const episode = useResource(episodeId ? `episode:${episodeId}` : null, () => api.episode(episodeId!))
  const events = useEvents(episodeId)
  function selectCampaign(id: string) { setCampaignId(id); setCampaignInput(id); setSelectedEpisode(null); setOptimistic(undefined); try { localStorage.setItem('faultlab:campaign', id) } catch { /* Persistence unavailable. */ } }
  function receiveCampaign(value: Campaign) { selectCampaign(value.campaign_id); setOptimistic(value); setReplay(false) }
  useEffect(() => { if (!campaignId && config.data?.active_campaign_id) selectCampaign(config.data.active_campaign_id) }, [campaignId, config.data?.active_campaign_id])
  function selectEpisode(id: string) { setSelectedEpisode(id); document.getElementById('evidence-workspace')?.scrollIntoView({ behavior: 'smooth', block: 'start' }) }
  return <main className="workspace"><a className="skip-link" href="#evidence-workspace">Skip to evidence</a><header className="masthead"><a className="brand" href="#"><span className="monogram" aria-hidden="true">F<span>∕</span>L</span><span>FaultLab<small>BY GATEKEEPER</small></span></a><div className="header-right"><span className="environment">LOCAL EXPERIMENT LAB</span><span className={`connection-state ${health.error ? 'disconnected' : health.data ? 'connected' : ''}`} role="status"><span aria-hidden="true" />{health.error ? 'Backend unavailable' : health.data ? 'Backend connected' : 'Checking connection…'}</span><button className="text-button" onClick={() => setHealthAttempt(v => v + 1)} disabled={health.loading}>Check again</button></div></header>
    <section className="intro"><div><p className="eyebrow">Evidence before confidence</p><h1>Find the fault.<br /><em>Prove the recovery.</em></h1><p className="description">Controlled failures. Fresh trials. Recovery policies that earn their place.</p></div><div className="lab-index"><span className="index-label">RESEARCH PROTOCOL / 001</span><ol><li>Discover <span>→</span> Reproduce</li><li>Reduce <span>→</span> Diagnose</li><li>Challenge <span>→</span> Evaluate</li></ol><p>Every decision follows persisted evidence.</p></div></section>
    {health.error && <div role="alert" className="error connection-error">{health.error} Start the local backend with <code>./scripts/start-backend.sh</code>, then check again.</div>}<ResourceNote resource={config} />
    <div className="campaign-bar"><form onSubmit={e => { e.preventDefault(); selectCampaign(campaignInput.trim()) }}><label htmlFor="campaign-id">Open saved campaign</label><input id="campaign-id" value={campaignInput} onChange={e => setCampaignInput(e.target.value)} placeholder="campaign ID" maxLength={128} /><button disabled={!campaignInput.trim()}>Load recording</button></form><span>{campaign ? `${campaign.mode.toUpperCase()} · ${campaign.config_profile_id}` : 'No campaign selected'} · faultlab/v1</span></div>
    <ResourceNote resource={campaignResource} />{replay && <ReplayView campaign={campaign} />}
    <RunSummary campaign={campaign} matrix={matrix.data} experiments={experiments.data} policies={policies.data} />
    <div className="evidence-grid" id="evidence-workspace"><RunControls config={config.data} campaign={campaign} replay={replay} onCampaign={receiveCampaign} onReplay={setReplay} /><Timeline episode={episode} events={events} /><PolicyPanel policies={policies} active={campaign?.active_policy_version} onEpisode={selectEpisode} /></div>
    <OutcomeMatrix matrix={matrix} selectedEpisode={episodeId} onEpisode={selectEpisode} />
    <ResourceNote resource={experiments} /><div className="section-caption"><span>FROM INCIDENT TO A TESTED REPAIR</span><span>Hypotheses, attempts and failed gates stay visible.</span></div><div className="experiment-grid"><CounterexamplePanel records={experiments.data?.counterexamples} onEpisode={selectEpisode} /><DiagnosticPanel records={experiments.data?.counterexamples} onEpisode={selectEpisode} /><ChallengePanel records={experiments.data?.counterexamples} onEpisode={selectEpisode} /></div>
    <ResourceNote resource={regressions} /><div className="support-grid"><RegressionControls key={campaignId} cases={regressions.data} registrations={registrations.data} policies={policies.data} config={config.data} replay={replay} onEpisode={selectEpisode} /><PortabilityPanel registrations={registrations} portabilityIds={experiments.data?.portability_ids} onEpisode={selectEpisode} /><SponsorEvidence config={config.data} campaign={campaign} experiments={experiments.data} aria={aria} replay={replay} /></div>
    <footer><span>FaultLab / Gatekeeper</span><span>Read-only startup · fixed Referee · durable local evidence</span><code>GET /api/health → {health.data?.service ?? 'pending'}</code></footer>
  </main>
}
