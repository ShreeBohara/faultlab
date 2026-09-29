import { object, request } from './api'
import { evidenceRetry, type EvidenceRetryDeclaration } from './runPlans'

/** GET /campaigns/{id}/evidence-wait (backend app/lab/evidence_wait.py): saved records only, read once per campaign state change. */
export type EvidenceWaitStatus = 'NOT_WAITING' | 'WAITING' | 'AUTOMATIC_RETRY_SCHEDULED' | 'AUTOMATIC_RETRY_RUNNING' | 'READING_EVIDENCE' | 'NEEDS_OPERATOR' | 'MANUAL_RETRY_ONLY'
export type EvidenceWaitRecordStatus = Exclude<EvidenceWaitStatus, 'NOT_WAITING'> | 'RESOLVED' | 'STOPPED' | 'INTERRUPTED' | 'ENDED'
export type AutomaticEvidenceRetry = { attempt: number; request_id: string | null; scheduled_for: string | null; started_at: string; ended_at: string | null; status: string; episode_ids: string[]; verified: number | null; still_pending: number | null }
export type EvidenceWaitRecord = {
  wait_id: string; campaign_id: string; status: EvidenceWaitRecordStatus; message: string | null; episode_id: string; pending_episode_ids: string[]
  state_before: string; started_at: string; ended_at: string | null; resolution: string | null; failed_reads: number; last_read_result: string | null
  automatic_retries_max: number; delays_seconds: number[]; automatic_attempts: AutomaticEvidenceRetry[]; manual_retry_request_ids: string[]; next_automatic_retry_at: string | null
  /** Rule v2 records only: the campaign's automatic retry limit, and which limit made the wait need an operator. */
  automatic_retries_campaign_max?: number | null; limit_reached?: 'PER_WAIT' | 'PER_CAMPAIGN' | null
}
export type EvidenceWait = {
  schema_version: 'faultlab-evidence-wait/v1'; campaign_id: string; campaign_state: string; declared: EvidenceRetryDeclaration | null; declared_note: string | null
  status: EvidenceWaitStatus; needs_operator: boolean; message: string; current: EvidenceWaitRecord | null; waits: EvidenceWaitRecord[]; waits_total: number; automatic_retries_total: number
}

const STATUSES: EvidenceWaitStatus[] = ['NOT_WAITING', 'WAITING', 'AUTOMATIC_RETRY_SCHEDULED', 'AUTOMATIC_RETRY_RUNNING', 'READING_EVIDENCE', 'NEEDS_OPERATOR', 'MANUAL_RETRY_ONLY']
const RECORD_STATUSES: string[] = [...STATUSES.filter(status => status !== 'NOT_WAITING'), 'RESOLVED', 'STOPPED', 'INTERRUPTED', 'ENDED']
const text = (value: unknown): value is string => typeof value === 'string' && value.trim().length > 0
const nullableText = (value: unknown) => value === null || text(value)
const count = (value: unknown): value is number => Number.isSafeInteger(value) && (value as number) >= 0
const nullableCount = (value: unknown) => value === null || count(value)
const texts = (value: unknown): value is string[] => Array.isArray(value) && value.every(text)
const malformed = (): never => { throw new Error('Malformed evidence wait response. The last verified data is retained.') }

function attempt(value: unknown): boolean {
  return object(value) && count(value.attempt) && (value.attempt as number) >= 1 && nullableText(value.request_id) && nullableText(value.scheduled_for) && text(value.started_at)
    && nullableText(value.ended_at) && text(value.status) && texts(value.episode_ids) && nullableCount(value.verified) && nullableCount(value.still_pending)
}
function waitRecord(value: unknown, campaignId: string): boolean {
  if (!object(value) || !text(value.wait_id) || value.campaign_id !== campaignId || !RECORD_STATUSES.includes(String(value.status)) || !nullableText(value.message)
    || !text(value.episode_id) || !texts(value.pending_episode_ids) || !text(value.state_before) || !text(value.started_at) || !nullableText(value.ended_at)
    || !nullableText(value.resolution) || !count(value.failed_reads) || !nullableText(value.last_read_result) || !count(value.automatic_retries_max)
    || !Array.isArray(value.delays_seconds) || !value.delays_seconds.every(count) || !Array.isArray(value.automatic_attempts) || !value.automatic_attempts.every(attempt)
    || value.automatic_attempts.length > (value.automatic_retries_max as number) || !texts(value.manual_retry_request_ids) || !nullableText(value.next_automatic_retry_at)
    || !(value.automatic_retries_campaign_max === undefined || nullableCount(value.automatic_retries_campaign_max))
    || !(value.limit_reached === undefined || value.limit_reached === null || value.limit_reached === 'PER_WAIT' || value.limit_reached === 'PER_CAMPAIGN')) return false
  return (value.ended_at === null) === !['RESOLVED', 'STOPPED', 'INTERRUPTED', 'ENDED'].includes(String(value.status))
}
export function validateEvidenceWait(value: unknown, campaignId: string): EvidenceWait {
  if (!object(value) || value.schema_version !== 'faultlab-evidence-wait/v1' || value.campaign_id !== campaignId || !text(value.campaign_state)
    || !STATUSES.includes(value.status as EvidenceWaitStatus) || value.needs_operator !== (value.status === 'NEEDS_OPERATOR') || !text(value.message)
    || !(value.declared === null || evidenceRetry(value.declared)) || !nullableText(value.declared_note) || (value.declared === null && !text(value.declared_note))
    || !(value.current === null || waitRecord(value.current, campaignId)) || !Array.isArray(value.waits) || !value.waits.every(item => waitRecord(item, campaignId))
    || !count(value.waits_total) || value.waits_total < value.waits.length || !count(value.automatic_retries_total)) return malformed()
  if (value.current !== null && (value.current as EvidenceWaitRecord).ended_at !== null) return malformed()
  return value as EvidenceWait
}
export const evidenceWaitApi = {
  get: (campaignId: string) => request(`/campaigns/${encodeURIComponent(campaignId)}/evidence-wait`, value => validateEvidenceWait(value, campaignId)),
}
