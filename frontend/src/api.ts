import type { Campaign, CampaignRequest, Episode, Event, PolicyVersion, Counterexample, RegressionCase, AgentRegistration, AriaAnalysis, RegressionBundle, RegressionExecution, DiagnosticResult, ChallengeResult, PortabilityResult, EvaluationBatch } from './generated/contracts'
import { validateContract, validateList } from './generated/validate'

export type ConfigStatus = { schema_version: 'faultlab/v1'; model: string; lab_model?: string; models?: { actor: string; explorer: string; mechanic: string }; actor_context_protocol?: string; model_configured: boolean; live_enabled: boolean; profile_ids: string[]; sponsor: { weave: string; aria: string }; active_campaign_id: string | null; data_store?: { identity: string; path: string; read_only: boolean }; execution_profiles?: { profile_id: string; caps: import('./generated/contracts').EpisodeBudget; requires_live: boolean }[] }
export type MatrixCell = { episode_id: string | null; scenario_alias: string; arm: 'B0' | 'B1' | 'L' | 'P1'; policy_hash: string; outcome: string | null; lifecycle: string; fault_scheduled: boolean; fault_triggered: boolean; fault_count?: number; triggered_fault_count?: number; source_mode: 'live' | 'replay' | 'offline_fixture'; telemetry_provenance: string; usage?: import('./generated/contracts').Usage }
export type Matrix = { campaign_id: string; cells: MatrixCell[]; counts: Record<string, number> }
export type EventPage = { events: Event[]; next_after: number; has_more: boolean }
export type CampaignPage = { campaigns: Campaign[]; next_before: number | null; has_more: boolean }
export type RegressionExecutionPage = { executions: RegressionExecution[]; next_before: number | null; has_more: boolean }
export type ReadinessStatus = { ready: boolean; simulator: { ready: boolean; code: string; message: string }; live_configuration: { ready: boolean; missing_fields: string[] }; provider_access: 'not_checked'; provider_calls: 0; models: { actor: string; explorer: string; mechanic: string } }
export type AriaInput = Omit<AriaAnalysis, 'schema_version' | 'analysis_id' | 'campaign_id' | 'verified_source_refs'>
const pending = new Map<string, Promise<unknown>>()
const id = encodeURIComponent
export const object = (v: unknown): v is Record<string, unknown> => !!v && typeof v === 'object' && !Array.isArray(v)
const strings = (v: unknown): v is string[] => Array.isArray(v) && v.every(x => typeof x === 'string')
const malformed = (label: string): never => { throw new Error(`Malformed ${label} response. The last verified data is retained.`) }
export class ApiError extends Error {
  constructor(readonly status: number, message: string) { super(message); this.name = 'ApiError' }
}

export async function request<T>(path: string, decode: (value: unknown) => T, body?: unknown): Promise<T> {
  // Shared GETs preserve one outstanding fetch per resource across StrictMode mounts.
  // Mutations are never retried here and are called only by explicit event handlers.
  const method = body === undefined ? 'GET' : 'POST'
  const key = `${method} ${path}`
  let operation = method === 'GET' ? pending.get(key) : undefined
  if (!operation) {
    operation = (async () => {
      const controller = new AbortController()
      const timeout = window.setTimeout(() => controller.abort(), 8000)
      try {
        const response = await fetch(`/api${path}`, { method, signal: controller.signal, headers: body === undefined ? undefined : { 'Content-Type': 'application/json' }, body: body === undefined ? undefined : JSON.stringify(body) })
        const data: unknown = await response.json().catch(error => {
          if (!response.ok) throw new ApiError(response.status, `The backend returned HTTP ${response.status}.`)
          throw error
        })
        if (!response.ok) {
          const message = object(data) && object(data.error) && typeof data.error.message === 'string' ? data.error.message : `The backend returned HTTP ${response.status}.`
          throw new ApiError(response.status, message)
        }
        return data
      } catch (error) {
        if (error instanceof Error && error.name === 'AbortError') throw new Error('The backend did not respond within 8 seconds.')
        throw error
      } finally { window.clearTimeout(timeout) }
    })()
    if (method === 'GET') { pending.set(key, operation); void operation.finally(() => pending.delete(key)).catch(() => {}) }
  }
  return decode(await operation)
}
export function validateConfig(v: unknown): ConfigStatus {
  if (!object(v) || v.schema_version !== 'faultlab/v1' || typeof v.model !== 'string' || typeof v.model_configured !== 'boolean' || typeof v.live_enabled !== 'boolean' || !strings(v.profile_ids) || !object(v.sponsor) || typeof v.sponsor.weave !== 'string' || typeof v.sponsor.aria !== 'string' || !(v.active_campaign_id === null || typeof v.active_campaign_id === 'string')) return malformed('configuration')
  if (v.models !== undefined && (!object(v.models) || typeof v.models.actor !== 'string' || typeof v.models.explorer !== 'string' || typeof v.models.mechanic !== 'string')) return malformed('role models')
  if (v.actor_context_protocol !== undefined && (typeof v.actor_context_protocol !== 'string' || !v.actor_context_protocol.trim())) return malformed('Actor context protocol')
  if (v.data_store !== undefined && (!object(v.data_store) || typeof v.data_store.identity !== 'string' || !v.data_store.identity.trim() || typeof v.data_store.path !== 'string' || !v.data_store.path.trim() || typeof v.data_store.read_only !== 'boolean')) return malformed('data store')
  if (v.execution_profiles !== undefined) {
    if (!Array.isArray(v.execution_profiles)) return malformed('execution profiles')
    for (const profile of v.execution_profiles) { if (!object(profile) || typeof profile.profile_id !== 'string' || typeof profile.requires_live !== 'boolean') return malformed('execution profile'); validateContract('EpisodeBudget', profile.caps) }
  }
  return v as ConfigStatus
}
export function validateReadiness(value: unknown): ReadinessStatus {
  if (!object(value) || typeof value.ready !== 'boolean' || !object(value.simulator)
    || typeof value.simulator.ready !== 'boolean' || value.ready !== value.simulator.ready
    || typeof value.simulator.code !== 'string' || typeof value.simulator.message !== 'string'
    || !object(value.live_configuration) || typeof value.live_configuration.ready !== 'boolean'
    || !strings(value.live_configuration.missing_fields) || value.provider_access !== 'not_checked' || value.provider_calls !== 0
    || !object(value.models) || typeof value.models.actor !== 'string' || typeof value.models.explorer !== 'string' || typeof value.models.mechanic !== 'string') return malformed('run readiness')
  return value as ReadinessStatus
}
export function validateMatrix(v: unknown): Matrix {
  const outcomes = ['COMPLETED', 'VIOLATION', 'SAFE_UNRESOLVED', 'CORRECTLY_REJECTED', 'LAB_ERROR']
  if (!object(v) || typeof v.campaign_id !== 'string' || !Array.isArray(v.cells) || !object(v.counts) || !Object.values(v.counts).every(n => Number.isInteger(n) && (n as number) >= 0)) return malformed('matrix')
  for (const c of v.cells) {
    if (!object(c) || !(c.episode_id === null || typeof c.episode_id === 'string') || typeof c.scenario_alias !== 'string' || typeof c.policy_hash !== 'string' || !['B0', 'B1', 'L', 'P1'].includes(String(c.arm)) || !(c.outcome === null || outcomes.includes(String(c.outcome))) || !['CREATED', 'RUNNING', 'SCORING', 'COMPLETED', 'INTERRUPTED', 'LAB_ERROR', 'NOT_RUN'].includes(String(c.lifecycle)) || typeof c.fault_scheduled !== 'boolean' || typeof c.fault_triggered !== 'boolean' || !['live', 'replay', 'offline_fixture'].includes(String(c.source_mode)) || typeof c.telemetry_provenance !== 'string') return malformed('matrix cell')
    for (const key of ['fault_count', 'triggered_fault_count']) if (c[key] !== undefined && (!Number.isSafeInteger(c[key]) || (c[key] as number) < 0)) return malformed('matrix fault count')
    if (typeof c.fault_count === 'number' && typeof c.triggered_fault_count === 'number' && c.triggered_fault_count > c.fault_count) return malformed('matrix fault counts')
    if (c.usage) validateContract('Usage', c.usage)
  }
  return v as Matrix
}
export function validateEvents(value: unknown, episodeId: string, after: number): EventPage {
  if (!object(value) || !Number.isInteger(value.next_after) || (value.next_after as number) < after || typeof value.has_more !== 'boolean') return malformed('event page')
  const events = validateList<Event>('Event', value.events)
  let seq = after
  for (const e of events) {
    if (e.episode_id !== episodeId || e.seq <= seq || e.seq > (value.next_after as number) || e.visibility === 'PRIVATE_EVALUATOR') return malformed('event ordering or identity')
    seq = e.seq
  }
  if (value.has_more && value.next_after === after) return malformed('event cursor')
  return { events, next_after: value.next_after as number, has_more: value.has_more }
}
export function validateCampaignPage(value: unknown, before?: number): CampaignPage {
  if (!object(value) || typeof value.has_more !== 'boolean'
    || !(value.next_before === null || (Number.isSafeInteger(value.next_before) && (value.next_before as number) > 0))) return malformed('campaign history')
  const campaigns = validateList<Campaign>('Campaign', value.campaigns)
  if (new Set(campaigns.map(campaign => campaign.campaign_id)).size !== campaigns.length
    || value.has_more !== (value.next_before !== null)
    || (value.has_more && (!campaigns.length || (before !== undefined && (value.next_before as number) >= before)))) return malformed('campaign history cursor or identity')
  return { campaigns, next_before: value.next_before as number | null, has_more: value.has_more }
}
export function validateExecutionPage(value: unknown, before?: number): RegressionExecutionPage {
  if (!object(value) || typeof value.has_more !== 'boolean'
    || !(value.next_before === null || (Number.isSafeInteger(value.next_before) && (value.next_before as number) > 0))) return malformed('regression execution history')
  const executions = validateList<RegressionExecution>('RegressionExecution', value.executions)
  if (new Set(executions.map(execution => execution.execution_id)).size !== executions.length
    || value.has_more !== (value.next_before !== null)
    || (value.has_more && (!executions.length || (before !== undefined && (value.next_before as number) >= before)))) return malformed('regression execution history cursor or identity')
  return { executions, next_before: value.next_before as number | null, has_more: value.has_more }
}
export function validateRecording(value: unknown, campaignId: string): Record<string, unknown> {
  // The backend owns sanitization and historical schema compatibility. Preserve
  // its complete archive while refusing a recording for another campaign.
  if (!object(value) || value.recording_version !== 'faultlab-development-recording/v1' || value.campaign_id !== campaignId) return malformed('campaign recording identity')
  return value
}

const contract = <T,>(name: string) => (v: unknown) => validateContract<T>(name, v)
const identified = <T,>(name: string, key: string, expected: string) => (value: unknown) => { const record = validateContract<T>(name, value); if (!object(value) || value[key] !== expected) return malformed(`${name} identity`); return record }
const list = <T,>(name: string) => (v: unknown) => validateList<T>(name, v)
export const api = {
  health: () => request('/health', v => { if (!object(v) || v.status !== 'ok' || v.service !== 'faultlab-backend') return malformed('health'); return { status: 'ok', service: 'faultlab-backend' } }),
  config: () => request('/config/status', validateConfig),
  readiness: () => request('/readiness', validateReadiness),
  campaigns: (before?: number) => request(`/campaigns?limit=20${before === undefined ? '' : `&before=${before}`}`, value => validateCampaignPage(value, before)),
  campaign: (campaignId: string) => request(`/campaigns/${id(campaignId)}`, identified<Campaign>('Campaign', 'campaign_id', campaignId)),
  recording: (campaignId: string) => request(`/campaigns/${id(campaignId)}/recording`, value => validateRecording(value, campaignId)),
  create: (input: CampaignRequest) => request('/campaigns', contract<Campaign>('Campaign'), input),
  start: (campaignId: string) => request(`/campaigns/${id(campaignId)}/start`, contract<Campaign>('Campaign'), {}),
  stop: (campaignId: string) => request(`/campaigns/${id(campaignId)}/stop`, contract<Campaign>('Campaign'), {}),
  matrix: (campaignId: string) => request(`/campaigns/${id(campaignId)}/matrix`, v => { const matrix = validateMatrix(v); if (matrix.campaign_id !== campaignId) return malformed('matrix identity'); return matrix }),
  episode: (episodeId: string) => request(`/episodes/${id(episodeId)}`, identified<Episode>('Episode', 'episode_id', episodeId)),
  events: (episodeId: string, after: number) => request(`/episodes/${id(episodeId)}/events?after=${after}&limit=200`, v => validateEvents(v, episodeId, after)),
  policies: () => request('/policies', list<PolicyVersion>('PolicyVersion')),
  counterexamples: (campaignId: string) => request(`/campaigns/${id(campaignId)}/counterexamples`, list<Counterexample>('Counterexample')),
  regressions: (campaignId: string) => request(`/campaigns/${id(campaignId)}/regressions`, list<RegressionCase>('RegressionCase')),
  registrations: () => request('/agent-registrations', list<AgentRegistration>('AgentRegistration')),
  aria: (campaignId: string) => request(`/campaigns/${id(campaignId)}/aria-evidence`, list<AriaAnalysis>('AriaAnalysis')),
  saveAria: (campaignId: string, input: AriaInput) => request(`/campaigns/${id(campaignId)}/aria-evidence`, contract<AriaAnalysis>('AriaAnalysis'), input),
  bundle: (regressionId: string) => request(`/regressions/${id(regressionId)}/bundle`, contract<RegressionBundle>('RegressionBundle')),
  download: async (regressionId: string) => {
    const controller = new AbortController(); const timeout = window.setTimeout(() => controller.abort(), 8000)
    try {
      const response = await fetch(`/api/regressions/${id(regressionId)}/download`, { method: 'GET', signal: controller.signal })
      if (!response.ok) { const error: unknown = await response.json(); throw new Error(object(error) && object(error.error) && typeof error.error.message === 'string' ? error.error.message : `Download failed: HTTP ${response.status}.`) }
      const file = await response.blob()
      if (!file.type.includes('application/zip')) throw new Error('Malformed regression archive response.')
      return file
    } finally { window.clearTimeout(timeout) }
  },
  execute: (regressionId: string, agentId: string, profileId: string, policy: string) => request(`/regressions/${id(regressionId)}/execute`, contract<RegressionExecution>('RegressionExecution'), { agent_registration_id: agentId, execution_profile_id: profileId, policy_version: policy, execute_live: true }),
  execution: (executionId: string) => request(`/regression-executions/${id(executionId)}`, identified<RegressionExecution>('RegressionExecution', 'execution_id', executionId)),
  executions: (regressionId: string, before?: number) => request(`/regressions/${id(regressionId)}/executions?limit=20${before === undefined ? '' : `&before=${before}`}`, value => validateExecutionPage(value, before)),
  diagnostic: (diagnosticId: string) => request(`/diagnostics/${id(diagnosticId)}`, contract<DiagnosticResult>('DiagnosticResult')),
  challenge: (challengeId: string) => request(`/challenges/${id(challengeId)}`, contract<ChallengeResult>('ChallengeResult')),
  portability: (portabilityId: string) => request(`/portability/${id(portabilityId)}`, contract<PortabilityResult>('PortabilityResult')),
  evaluation: (batchId: string) => request(`/evaluations/${id(batchId)}`, contract<EvaluationBatch>('EvaluationBatch')),
  retry: (campaignId: string) => request(`/campaigns/${id(campaignId)}/retry-evidence`, v => { if (!object(v)) return malformed('retry'); return v }, {}),
  reset: () => request('/reset-demo', v => { if (!object(v) || typeof v.reset_id !== 'string' || v.status !== 'READY_FOR_FRESH_RUN') return malformed('reset'); return v }, { fixture_profile_id: 'standard-v1' }),
}
export function safeEvidenceUrl(value: string | null | undefined): string | null {
  if (!value) return null
  try { const url = new URL(value); return url.protocol === 'https:' && ['wandb.ai', 'weave.wandb.ai'].includes(url.hostname) && !url.username && !url.password && (!url.port || url.port === '443') && url.pathname !== '/' ? url.href : null } catch { return null }
}
