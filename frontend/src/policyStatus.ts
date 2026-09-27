import { object, request } from './api'

export type UnseenCheck = {
  check_id: string; campaign_id: string; source_study_id: string; policy_hash: string
  status: 'QUEUED' | 'RUNNING' | 'COMPLETED' | 'INCOMPLETE' | 'INTERRUPTED'
  decision: 'PENDING' | 'NO_HARM' | 'HARM' | 'INCOMPLETE'
  predicate: 'faultlab-heldout-no-harm/v1' | 'faultlab-heldout-no-harm/v2'
}
export type StudyPolicyStatus = {
  study_id: string; source_campaign_id: string; policy_hash: string | null; policy_version: string | null
  development: { status: 'QUALIFIED' | 'NOT_QUALIFIED' | 'REPLAY_ONLY' | 'INCOMPLETE'; reason: string }
  unseen_checks: UnseenCheck[]
}
export type CampaignPolicyStatus = {
  schema_version: 'faultlab-policy-status/v1'; campaign_id: string
  active_policy: { version: string | null; hash: string | null }
  studies: StudyPolicyStatus[]
}

const text = (value: unknown): value is string => typeof value === 'string' && value.trim().length > 0
const hash = (value: unknown): value is string => typeof value === 'string' && /^[a-f0-9]{64}$/.test(value)
const malformed = (): never => { throw new Error('Malformed policy status or campaign identity. No new qualification is shown.') }

export function validatePolicyStatus(value: unknown, campaignId: string): CampaignPolicyStatus {
  if (!object(value) || value.schema_version !== 'faultlab-policy-status/v1' || value.campaign_id !== campaignId
    || !object(value.active_policy) || !Array.isArray(value.studies)) return malformed()
  const active = value.active_policy
  if (!(active.version === null || text(active.version)) || !(active.hash === null || hash(active.hash))
    || (active.version === null && active.hash !== null)) return malformed()
  const studyIds = new Set<string>(); const checkIds = new Set<string>()
  const studies: StudyPolicyStatus[] = value.studies.map(item => {
    if (!object(item) || !text(item.study_id) || studyIds.has(item.study_id) || !text(item.source_campaign_id)
      || !(item.policy_hash === null || hash(item.policy_hash)) || !(item.policy_version === null || text(item.policy_version))
      || !object(item.development) || !['QUALIFIED', 'NOT_QUALIFIED', 'REPLAY_ONLY', 'INCOMPLETE'].includes(String(item.development.status))
      || !text(item.development.reason) || !Array.isArray(item.unseen_checks)) return malformed()
    if (['QUALIFIED', 'REPLAY_ONLY'].includes(String(item.development.status)) && (!hash(item.policy_hash) || !text(item.policy_version))) return malformed()
    studyIds.add(item.study_id)
    const unseen_checks: UnseenCheck[] = item.unseen_checks.map(check => {
      if (!object(check) || !text(check.check_id) || checkIds.has(check.check_id) || !text(check.campaign_id)
        || check.source_study_id !== item.study_id || !hash(check.policy_hash) || check.policy_hash !== item.policy_hash
        || !['QUEUED', 'RUNNING', 'COMPLETED', 'INCOMPLETE', 'INTERRUPTED'].includes(String(check.status))
        || !['PENDING', 'NO_HARM', 'HARM', 'INCOMPLETE'].includes(String(check.decision))
        || !['faultlab-heldout-no-harm/v1', 'faultlab-heldout-no-harm/v2'].includes(String(check.predicate))) return malformed()
      if (['NO_HARM', 'HARM'].includes(String(check.decision)) && check.status !== 'COMPLETED') return malformed()
      checkIds.add(check.check_id)
      // Keep only the public projection. Case definitions, observations and private
      // held-out evidence must never become part of the dashboard's status record.
      return { check_id: check.check_id, campaign_id: check.campaign_id, source_study_id: item.study_id,
        policy_hash: check.policy_hash, status: check.status, decision: check.decision, predicate: check.predicate } as UnseenCheck
    })
    if (item.source_campaign_id !== campaignId && !unseen_checks.some(check => check.campaign_id === campaignId)) return malformed()
    return { study_id: item.study_id, source_campaign_id: item.source_campaign_id,
      policy_hash: item.policy_hash, policy_version: item.policy_version,
      development: { status: item.development.status, reason: item.development.reason }, unseen_checks } as StudyPolicyStatus
  })
  return { schema_version: 'faultlab-policy-status/v1', campaign_id: campaignId,
    active_policy: { version: active.version, hash: active.hash }, studies } as CampaignPolicyStatus
}

export const getPolicyStatus = (campaignId: string) => request(`/campaigns/${encodeURIComponent(campaignId)}/policy-status`, value => validatePolicyStatus(value, campaignId))

export function unseenResult(check: UnseenCheck): { label: string; tone: 'neutral' | 'good' | 'bad'; detail: string } {
  if (check.status === 'QUEUED' || check.status === 'RUNNING') return { label: 'Still running', tone: 'neutral', detail: 'No final unseen-case result yet.' }
  if (check.status === 'COMPLETED' && check.decision === 'HARM') return { label: 'Harm detected', tone: 'bad', detail: 'The check failed its no-harm rule. This does not by itself prove that the policy caused the failure.' }
  if (check.status === 'COMPLETED' && check.decision === 'NO_HARM') return { label: 'No harm observed', tone: 'good', detail: 'Only the cases and repetitions in this check were assessed. This is not policy activation.' }
  return { label: 'Incomplete', tone: 'neutral', detail: 'This check did not establish an unseen-case result.' }
}
