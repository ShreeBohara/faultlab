import { object, request } from './api'
import { validateContract } from './generated/validate'
import type { ExplorerOutput, FaultSpec, Usage } from './generated/contracts'

export type FaultLabel = { index: number; fault: string; kind: string; target: string; attempt: number; agent_attempts_seen: number; rule: string | null; verdict: 'FORCED' | 'NOT_FORCED' | 'IMPOSSIBLE'; reason_code: string; explanation: string }
export type Reachability = { labeller: string; all_forced: boolean; recipe: string[]; faults: FaultLabel[]; agent_path: string[]; agent_business_calls: number; fixture_id: string; caller_model: Record<string, unknown> }
export type SearchDecisionStatus = 'SELECTED' | 'SKIPPED_DUPLICATE' | 'INVALID_OUTPUT' | 'SKIPPED_UNREACHABLE' | 'PRECHECK_FAILED'
export type SearchAttempt = {
  selection_ref: string; campaign_id: string; selection_index: number; configuration_hash: string; policy_hash: string
  search_decision: {
    status: SearchDecisionStatus; schedule_hash: string | null; reason: string | null; prior_selection_refs: string[]; prior_episode_refs: string[]
    // Present only under the declared discovery protocol v2.
    discovery_protocol?: 'faultlab-discovery/v2-reachability'; identity_version?: string; slot_request?: 1 | 2; replan_of?: string | null
    refused_fault_spec?: FaultSpec | null; reachability?: Reachability | null
  }
  selected_output: ExplorerOutput | null; output: ExplorerOutput | null; raw_response: string; usage: Usage; provenance: string; error: string | null
  /** A charged blind retry of this request after it received no answer (at most one). */
  transport_retries?: TransportRetry[]
}
export type TransportRetry = { retry_id: string; code: 'CONNECTION_ERROR' | 'REQUEST_TIMEOUT' | 'HTTP_ERROR'; attempt: 1; http_status?: 503; retry_delay_seconds?: 1; provider_failure_id: string }
function transportRetries(value: unknown): value is TransportRetry[] {
  return Array.isArray(value) && value.length <= 1 && value.every(retry => object(retry) && nonempty(retry.retry_id) && nonempty(retry.provider_failure_id) && retry.attempt === 1
    && (retry.code === 'HTTP_ERROR' ? retry.http_status === 503 && retry.retry_delay_seconds === 1 : ['CONNECTION_ERROR', 'REQUEST_TIMEOUT'].includes(String(retry.code)) && retry.http_status === undefined))
}
const nonempty = (value: unknown): value is string => typeof value === 'string' && value.length > 0
const hash = (value: unknown): value is string => typeof value === 'string' && /^[a-f0-9]{64}$/.test(value)
const references = (value: unknown): value is string[] => Array.isArray(value) && value.every(nonempty)
const malformed = (): never => { throw new Error('Malformed search attempts or campaign identity. The last verified data is retained.') }
const V1_STATUSES = ['SELECTED', 'SKIPPED_DUPLICATE', 'INVALID_OUTPUT']
const V2_STATUSES = [...V1_STATUSES, 'SKIPPED_UNREACHABLE', 'PRECHECK_FAILED']

function reachability(value: unknown): value is Reachability {
  if (!object(value) || !nonempty(value.labeller) || typeof value.all_forced !== 'boolean' || !Array.isArray(value.faults) || !value.faults.length
    || !Array.isArray(value.recipe) || !value.recipe.every(nonempty) || !Array.isArray(value.agent_path)) return false
  const faults = value.faults as unknown[]
  const valid = faults.every((fault, index) => object(fault) && fault.index === index && nonempty(fault.fault) && nonempty(fault.explanation) && nonempty(fault.reason_code)
    && ['FORCED', 'NOT_FORCED', 'IMPOSSIBLE'].includes(String(fault.verdict)))
  return valid && value.all_forced === faults.every(fault => object(fault) && fault.verdict === 'FORCED')
}

function validateV2(decision: Record<string, unknown>) {
  if (decision.discovery_protocol !== 'faultlab-discovery/v2-reachability' || !nonempty(decision.identity_version) || ![1, 2].includes(decision.slot_request as number)
    || !(decision.replan_of === null || nonempty(decision.replan_of)) || (decision.slot_request === 2) !== nonempty(decision.replan_of)) return malformed()
  const refusedStatus = ['SKIPPED_DUPLICATE', 'SKIPPED_UNREACHABLE', 'PRECHECK_FAILED'].includes(String(decision.status))
  if (refusedStatus !== (decision.refused_fault_spec !== null && decision.refused_fault_spec !== undefined)) return malformed()
  if (decision.refused_fault_spec) validateContract<FaultSpec>('FaultSpec', decision.refused_fault_spec)
  if (!(decision.reachability === null || reachability(decision.reachability))) return malformed()
  const label = decision.reachability as Reachability | null
  // A selected v2 pick ran only because every fault was FORCED; a pre-check refusal had at least one that was not.
  if (decision.status === 'SELECTED' && !label?.all_forced) return malformed()
  if (decision.status === 'SKIPPED_UNREACHABLE' && (!label || label.all_forced)) return malformed()
}

export function validateSearchAttempts(value: unknown, campaignId: string): SearchAttempt[] {
  if (!Array.isArray(value)) return malformed()
  const refs = new Set<string>()
  return value.map(row => {
    if (!object(row) || row.campaign_id !== campaignId || !nonempty(row.selection_ref) || refs.has(row.selection_ref)
      || !Number.isInteger(row.selection_index) || (row.selection_index as number) < 0
      || !hash(row.configuration_hash) || !hash(row.policy_hash) || !object(row.search_decision)
      || typeof row.raw_response !== 'string' || !nonempty(row.provenance) || !(row.error === null || typeof row.error === 'string')
      || !(row.transport_retries === undefined || transportRetries(row.transport_retries))) return malformed()
    const decision = row.search_decision
    const v2 = decision.discovery_protocol !== undefined
    if (!(v2 ? V2_STATUSES : V1_STATUSES).includes(String(decision.status))
      || !(decision.schedule_hash === null || hash(decision.schedule_hash))
      || !(decision.reason === null || typeof decision.reason === 'string')
      || !references(decision.prior_selection_refs) || !references(decision.prior_episode_refs)) return malformed()
    if (v2) validateV2(decision)
    const selected_output = row.selected_output === null ? null : validateContract<ExplorerOutput>('ExplorerOutput', row.selected_output)
    const output = row.output === null ? null : validateContract<ExplorerOutput>('ExplorerOutput', row.output)
    if ((decision.status === 'SELECTED') !== !!selected_output || (decision.status !== 'INVALID_OUTPUT' && !decision.schedule_hash)) return malformed()
    refs.add(row.selection_ref)
    const usage = validateContract<Usage>('Usage', row.usage)
    // Both requests of a retried selection are charged, and the saved usage says so.
    if ((usage.model_calls ?? 1) !== 1 + ((row.transport_retries as TransportRetry[] | undefined)?.length ?? 0)) return malformed()
    return { ...row, selected_output, output, usage } as SearchAttempt
  })
}
export const getSearchAttempts = (campaignId: string) => request(`/campaigns/${encodeURIComponent(campaignId)}/search-attempts`, value => validateSearchAttempts(value, campaignId))
