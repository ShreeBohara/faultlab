// The two Learn-loop rules built after live run v2d (backend app/lab/loop_limits.py). Every new Learn plan freezes the
// Mechanic request-size rule. The challenge-pick rule (v2-candidate-reach) was withdrawn before any live run (both
// reviews, HIGH-1): the backend no longer offers or freezes it, but a plan that declares it still reads and shows it.
// Plans saved before the rules declare neither and keep today's behaviour; the texts below say so.
import { object } from './api'
import type { FaultSpec } from './generated/contracts'

export const MECHANIC_CONTEXT_V2 = 'faultlab-mechanic-context/v2-bounded' as const
export const CHALLENGE_SELECTION_V2 = 'faultlab-challenge-selection/v2-candidate-reach' as const
/** Native citation status (backend app/lab/citation_status.py), frozen into every new Learn plan of native adapter v2 only. */
export const MECHANIC_EVIDENCE_V2 = 'faultlab-mechanic-evidence/v2-native-citation-status' as const
export const COMPACTION_STAGES = ['IDENTICAL_CLEAN_ROWS', 'ONE_CLEAN_EPISODE_PER_OUTCOME_GROUP', 'NO_CLEAN_EPISODE_ROWS'] as const
export type CompactionStage = typeof COMPACTION_STAGES[number]

/** The Mechanic request-size rule exactly as the backend freezes it (mechanic_context_declaration()). */
export type MechanicContextDeclaration = { protocol: typeof MECHANIC_CONTEXT_V2; applies_to: ['mechanic_diagnosis', 'mechanic_proposal']; input_token_limit: 32000; format_repair_reserve_tokens: 4000; compaction_target_tokens: 28000; stages: CompactionStage[]; always_kept: string[]; when_unfit: 'END_SOURCE_CANDIDATE_SEARCH'; unsent_request_uses_candidate_request: false; requests_over_limit_sent: 0; rule: string }
/** The native citation-status rule exactly as the backend freezes it (citation_status.declaration()). */
export type MechanicEvidenceDeclaration = { protocol: typeof MECHANIC_EVIDENCE_V2; agents: ['smolagents-v2']; applies_to: ['mechanic_diagnosis', 'mechanic_proposal', 'explorer_challenge']; block: 'native_citation_status'; row_fields: ['episode_id', 'cited', 'decoded', 'undecoded']; source_event: 'report_submitted'; source_protocol: string; reads_scoring: false; compacted: false; discovery_requests_changed: false; meaning: string; memory_pointer: string; rule: string }
/** The challenge-pick rule exactly as the backend freezes it (challenge_selection_declaration()). */
export type ChallengeSelectionDeclaration = { protocol: typeof CHALLENGE_SELECTION_V2; basis: 'candidate_arm_source_validation_agent_calls'; caller_counted: 'actor'; target: 'tool_and_service'; replans_per_refused_pick: 1; explorer_requests_per_challenge: 8; refused_pick_runs_episodes: false; challenge_rules_changed: false; rule: string }

export type ReachBasis = { source_validation_episode_ids: string[]; tool_services_called_by_agent: string[]; called_only_by_candidate_policy: string[] }
/** One challenge pick's decision under the rule (GET …/experiments challenge_reach; saved on its selection record). */
export type ChallengeReachDecision = { selection_id: string; challenge_id: string | null; candidate_hash: string | null; recipe: string[] | null; protocol: typeof CHALLENGE_SELECTION_V2; proposal_index: number | null; slot_request: 1 | 2; replan_of: string | null; status: 'SELECTED' | 'REFUSED_UNREACHED' | 'INVALID_OUTPUT' | 'NOT_CHECKED'; targets: string[]; unreached: string[]; reason: string | null; basis: ReachBasis; refused_fault_spec: FaultSpec | null }
export type CompactionBlock = { field: string; episodes_total: number; episodes_in_full: number; episodes_omitted: number; omitted_by_stage: Record<string, number> }
/** One Mechanic request-size record (GET …/experiments mechanic_context; the recording's mechanic_context_records). */
export type MechanicContextRecord = { record_id: string; campaign_id: string; protocol: typeof MECHANIC_CONTEXT_V2; request_kind: 'mechanic_proposal' | 'mechanic_diagnosis'; counterexample_id: string; source_episode_id: string; outcome: 'COMPACTED' | 'SEARCH_ENDED'; stage?: 'BEFORE_SEND' | 'FORMAT_REPAIR'; input_token_limit: number; compaction_target_tokens: number; full_request_tokens?: number; compacted_request_tokens?: number | null; format_repair_tokens?: number | null; candidate_index?: number; stages_applied?: CompactionStage[]; blocks?: CompactionBlock[]; statement?: string | null; reason: string | null; provider_dispatch: boolean }

const text = (value: unknown): value is string => typeof value === 'string' && value.length > 0
const count = (value: unknown): value is number => Number.isInteger(value) && (value as number) >= 0
const strings = (value: unknown): value is string[] => Array.isArray(value) && value.every(item => typeof item === 'string')
const same = (value: unknown, expected: readonly string[]) => Array.isArray(value) && value.length === expected.length && value.every((item, index) => item === expected[index])

export function mechanicContextDeclaration(value: unknown): value is MechanicContextDeclaration {
  return object(value) && value.protocol === MECHANIC_CONTEXT_V2 && same(value.applies_to, ['mechanic_diagnosis', 'mechanic_proposal'])
    && value.input_token_limit === 32000 && value.format_repair_reserve_tokens === 4000 && value.compaction_target_tokens === 28000
    && same(value.stages, COMPACTION_STAGES) && strings(value.always_kept) && value.always_kept.length > 0 && value.when_unfit === 'END_SOURCE_CANDIDATE_SEARCH'
    && value.unsent_request_uses_candidate_request === false && value.requests_over_limit_sent === 0 && text(value.rule)
}
export function mechanicEvidenceDeclaration(value: unknown): value is MechanicEvidenceDeclaration {
  return object(value) && value.protocol === MECHANIC_EVIDENCE_V2 && same(value.agents, ['smolagents-v2'])
    && same(value.applies_to, ['mechanic_diagnosis', 'mechanic_proposal', 'explorer_challenge']) && value.block === 'native_citation_status'
    && same(value.row_fields, ['episode_id', 'cited', 'decoded', 'undecoded']) && value.source_event === 'report_submitted' && text(value.source_protocol)
    && value.reads_scoring === false && value.compacted === false && value.discovery_requests_changed === false
    && text(value.meaning) && text(value.memory_pointer) && text(value.rule)
}
export function challengeSelectionDeclaration(value: unknown): value is ChallengeSelectionDeclaration {
  return object(value) && value.protocol === CHALLENGE_SELECTION_V2 && value.basis === 'candidate_arm_source_validation_agent_calls'
    && value.caller_counted === 'actor' && value.target === 'tool_and_service' && value.replans_per_refused_pick === 1
    && value.explorer_requests_per_challenge === 8 && value.refused_pick_runs_episodes === false && value.challenge_rules_changed === false && text(value.rule)
}
function reachDecision(value: unknown): value is ChallengeReachDecision {
  if (!object(value) || !text(value.selection_id) || value.protocol !== CHALLENGE_SELECTION_V2 || ![1, 2].includes(value.slot_request as number)
    || !['SELECTED', 'REFUSED_UNREACHED', 'INVALID_OUTPUT', 'NOT_CHECKED'].includes(String(value.status)) || !strings(value.targets) || !strings(value.unreached)
    || !(value.reason === null || typeof value.reason === 'string') || !(value.replan_of === null || typeof value.replan_of === 'string')
    || !(value.recipe === null || strings(value.recipe)) || !object(value.basis) || !strings(value.basis.tool_services_called_by_agent)
    || !strings(value.basis.called_only_by_candidate_policy) || !strings(value.basis.source_validation_episode_ids)) return false
  // A refusal always names what the agent never called and why; a pick that ran never lists an unreached target.
  return value.status === 'REFUSED_UNREACHED' ? value.unreached.length > 0 && text(value.reason) : value.unreached.length === 0
}
function contextRecord(value: unknown): value is MechanicContextRecord {
  if (!object(value) || !text(value.record_id) || value.protocol !== MECHANIC_CONTEXT_V2 || !['mechanic_proposal', 'mechanic_diagnosis'].includes(String(value.request_kind))
    || !['COMPACTED', 'SEARCH_ENDED'].includes(String(value.outcome)) || typeof value.provider_dispatch !== 'boolean' || !count(value.input_token_limit) || !count(value.compaction_target_tokens)) return false
  // A compacted request was sent within the target and says what it omitted; an ended search sent nothing and says why.
  return value.outcome === 'COMPACTED'
    ? value.provider_dispatch && count(value.compacted_request_tokens) && (value.compacted_request_tokens as number) <= value.compaction_target_tokens && text(value.statement)
    : !value.provider_dispatch && text(value.reason) && ['BEFORE_SEND', 'FORMAT_REPAIR'].includes(String(value.stage))
}
export function validateChallengeReach(value: unknown): ChallengeReachDecision[] {
  if (!Array.isArray(value) || !value.every(reachDecision)) throw new Error('Malformed challenge pick decisions.')
  return value
}
export function validateMechanicContext(value: unknown): MechanicContextRecord[] {
  if (!Array.isArray(value) || !value.every(contextRecord)) throw new Error('Malformed Mechanic request-size records.')
  return value
}

/** The saved plan's Mechanic request-size rule in one line (null or absent: a plan saved before it). */
export function mechanicContextText(rule: MechanicContextDeclaration | null | undefined): string {
  if (!rule) return 'Not declared: this plan was saved before the Mechanic request-size rule. A Mechanic request over the 32,000-token input limit is refused before sending and ends the campaign in ERROR, as before.'
  return `A Mechanic diagnosis or candidate request over ${rule.input_token_limit.toLocaleString()} input tokens is compacted in ${rule.stages.length} fixed stages to at most ${rule.compaction_target_tokens.toLocaleString()} (${rule.format_repair_reserve_tokens.toLocaleString()} kept for one format-repair turn) · only clean episodes' rows are omitted, each still named with its outcome · the source, its reproductions and every episode with a failed check stay in full · if it still does not fit, nothing is sent and that source's search ends with a recorded reason, never ERROR`
}
/** The saved plan's native citation-status rule in one line, for a native adapter v2 plan (null or absent: saved before it). */
export function mechanicEvidenceText(rule: MechanicEvidenceDeclaration | null | undefined): string {
  if (!rule) return 'Not declared: this native adapter v2 plan was saved before the rule. Its Mechanic and challenge requests carry no per-episode citation status, as before.'
  return 'Each Mechanic diagnosis or candidate request and each challenge Explorer request gets, per episode, what the adapter recorded when the agent submitted its report: tokens cited, how many decoded to delivered evidence, and any token not decoded · read only from the report_submitted event, nothing from scoring · never compacted · discovery requests unchanged'
}
/** The saved plan's challenge-pick rule in one line (null or absent: not declared, which is every new plan too). */
export function challengeSelectionText(rule: ChallengeSelectionDeclaration | null | undefined): string {
  if (!rule) return 'Not declared: every valid challenge pick runs its pairs, as before.'
  return `A challenge pick with a fault on a tool and service the agent never called in the candidate arm's source-validation episodes is refused before any pair runs · ${rule.replans_per_refused_pick} re-plan per refused pick, inside the challenge's ${rule.explorer_requests_per_challenge} Explorer requests (charged as before) · the challenge itself is unchanged: 4 schedules, 3 pairs each, every fault must fire`
}
/** What one challenge pick decision means, in plain words. */
export function reachDecisionText(row: ChallengeReachDecision): string {
  const request = `Explorer request ${row.proposal_index === null ? '?' : row.proposal_index + 1}${row.slot_request === 2 ? ' (re-plan)' : ''}`
  if (row.status === 'REFUSED_UNREACHED') return `${request}: ${row.reason ?? 'Refused before any pair ran.'}`
  if (row.status === 'INVALID_OUTPUT') return `${request}: invalid answer, nothing ran.`
  if (row.status === 'NOT_CHECKED') return `${request}: not checked (no source-validation episode of the candidate arm on record); it ran as before.`
  return `${request}: every fault targets a tool and service the agent called; it ran.`
}
/** What one Mechanic request-size record means, in plain words. */
export function contextRecordText(row: MechanicContextRecord): string {
  const kind = row.request_kind === 'mechanic_diagnosis' ? 'Diagnosis request' : `Candidate request${row.candidate_index === undefined ? '' : ` ${row.candidate_index + 1}`}`
  if (row.outcome === 'COMPACTED') return `${kind}: ${row.full_request_tokens?.toLocaleString() ?? '?'} tokens in full, over the ${row.input_token_limit.toLocaleString()}-token limit; compacted to ${row.compacted_request_tokens?.toLocaleString()} and sent.`
  // A refused format-repair turn: the first turn was sent and charged (its answer is saved); only the repair turn was not.
  if (row.stage === 'FORMAT_REPAIR') return `${kind}: first turn sent (its answer is saved); its format-repair turn was not sent. ${row.reason ?? ''}`.trim()
  return `${kind}: not sent. ${row.reason ?? ''}`.trim()
}
/** Badge text for a request-size record: what was and was not sent. */
export function contextRecordLabel(row: MechanicContextRecord): string {
  if (row.outcome === 'COMPACTED') return 'Compacted and sent'
  return row.stage === 'FORMAT_REPAIR' ? 'Search ended, repair turn not sent' : 'Search ended, not sent'
}
/** Badge text for a checked challenge pick (capitalised like every other badge). */
export const REACH_STATUS_LABELS: Record<ChallengeReachDecision['status'], string> = {
  SELECTED: 'Selected', REFUSED_UNREACHED: 'Refused: tool not reached', INVALID_OUTPUT: 'Invalid output', NOT_CHECKED: 'Not checked',
}
