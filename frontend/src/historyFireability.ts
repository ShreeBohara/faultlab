// History fireability (backend app/lab/fireability.py, faultlab-explorer-selection/v3-history-fireability). Frozen, with a
// per-target table computed from the plan's frozen agent history, into every new Learn plan whose discovery protocol is
// v3 · agent history or v4 · history replay. A pick is refused only when EVERY one of its faults targets a REFUSED row
// (fixer, review finding MEDIUM-1); a pick with a fault on any other target runs, even beside a REFUSED target. Shown in the Learn setup form (the rule offered for those protocols), the saved
// plan (the rule and its table), the fault-search panel (each discovery pick's check, and any slot left without a request)
// and the challenge panel (each challenge pick's check). Plans saved before it declare none and keep today's behaviour.
import { object } from './api'
import type { FaultSpec } from './generated/contracts'

export const EXPLORER_SELECTION_V3 = 'faultlab-explorer-selection/v3-history-fireability' as const
export const FIREABILITY_PROTOCOLS = ['faultlab-discovery/v3-history', 'faultlab-discovery/v4-history-replay'] as const
export type FireabilityRowStatus = 'REFUSED' | 'ALLOWED' | 'ALLOWED_FEWER_THAN_3'
/** One target of the frozen table: verified history episodes that scheduled a fault there, and how many fired every such fault. */
export type FireabilityRow = { kind: 'F1' | 'F2' | 'F3' | 'F4'; target_service: string; target_tool: string; verified_episodes: number; fired_episodes: number; fired_share: string; status: FireabilityRowStatus }
export type FireabilityTable = { schema_version: 'faultlab-history-fireability/v1'; meaning: string; history_summary_hash: string; history_episode_ids_hash: string; record_cutoff: number; verified_episodes: number; rows: FireabilityRow[]; refused_targets: string[] }
type RuleFields = { protocol: typeof EXPLORER_SELECTION_V3; applies_to: ['explorer_discovery', 'explorer_challenge']; discovery_protocols: ['faultlab-discovery/v3-history', 'faultlab-discovery/v4-history-replay']; basis: 'frozen_agent_history_verified_episodes'; target: 'fault_kind_service_tool'; pick_refused_when: 'every_fault_on_a_refused_target'; min_verified_episodes: 3; min_fired_share: '1/2'; replans_per_refused_pick: 1; explorer_request_budget_changed: false; refused_pick_runs_episodes: false; candidate_dependent: false; challenge_rules_changed: false; rule: string }
/** The rule as the run options offer it (no table: the table is computed from the history when a plan is saved). */
export type ExplorerSelectionDeclaration = RuleFields
/** The rule and its frozen table, as a saved plan carries it. */
export type ExplorerSelectionPlan = RuleFields & { table: FireabilityTable; table_hash: string }
export type TargetCheck = { kind: string; target_service: string; target_tool: string; table_row: FireabilityRow | null; status: FireabilityRowStatus | 'NOT_IN_HISTORY' }
export type FireabilityDecisionStatus = 'ALLOWED' | 'REFUSED_LOW_FIRED_SHARE' | 'INVALID_OUTPUT' | 'NOT_CHECKED_DUPLICATE'
/** One pick's check, saved on its selection record (field fireability). */
export type FireabilityDecision = { protocol: typeof EXPLORER_SELECTION_V3; purpose: 'discovery' | 'challenge'; table_hash: string; request_index: number | null; slot_request: 1 | 2; replan_of: string | null; pick: string; status: FireabilityDecisionStatus; targets: TargetCheck[]; refused_targets: FireabilityRow[]; refused_fault_spec: FaultSpec | null; reason: string | null }
export type FireabilityDecisionRow = FireabilityDecision & { selection_id: string; challenge_id: string | null; recipe: string[] | null }
export type UnrequestedSlot = { record_id: string; campaign_id: string; protocol: typeof EXPLORER_SELECTION_V3; selection_index: number; status: 'NO_EXPLORER_REQUEST'; explorer_requests_used: number; explorer_requests_max: number; replans_after_refusals: number; reason: string }
/** GET …/experiments explorer_fireability (only for a campaign whose plan declares the rule); the recording's explorer_selection_rule. */
export type ExplorerFireability = { protocol: typeof EXPLORER_SELECTION_V3; table_hash: string; refused_targets: string[]; picks_checked: number; picks_refused: number; decisions: FireabilityDecisionRow[]; slots_without_request: UnrequestedSlot[] }

const text = (value: unknown): value is string => typeof value === 'string' && value.trim().length > 0
const count = (value: unknown): value is number => Number.isSafeInteger(value) && (value as number) >= 0
const digest = (value: unknown): value is string => typeof value === 'string' && /^[a-f0-9]{64}$/.test(value)
const same = (value: unknown, expected: readonly string[]) => Array.isArray(value) && value.length === expected.length && value.every((item, index) => item === expected[index])
/** The backend's rule: at least 3 verified episodes and a fired share below 1/2 is REFUSED; fewer than 3 is allowed. */
export const rowStatus = (verified: number, fired: number): FireabilityRowStatus => verified < 3 ? 'ALLOWED_FEWER_THAN_3' : 2 * fired < verified ? 'REFUSED' : 'ALLOWED'
export const targetText = (row: { kind: string; target_tool: string; target_service: string }) => `${row.kind} on ${row.target_tool} (${row.target_service})`
/** Exactly the backend's refused_text(): one line per REFUSED row. */
export const refusedText = (row: FireabilityRow) => `${targetText(row)}: fired in ${row.fired_episodes} of ${row.verified_episodes} verified history episodes (below 1/2 of at least 3)`

function rule(value: unknown): value is RuleFields {
  return object(value) && value.protocol === EXPLORER_SELECTION_V3 && same(value.applies_to, ['explorer_discovery', 'explorer_challenge'])
    && same(value.discovery_protocols, FIREABILITY_PROTOCOLS) && value.basis === 'frozen_agent_history_verified_episodes' && value.target === 'fault_kind_service_tool'
    && value.pick_refused_when === 'every_fault_on_a_refused_target'
    && value.min_verified_episodes === 3 && value.min_fired_share === '1/2' && value.replans_per_refused_pick === 1 && value.explorer_request_budget_changed === false
    && value.refused_pick_runs_episodes === false && value.candidate_dependent === false && value.challenge_rules_changed === false && text(value.rule)
}
function row(value: unknown): value is FireabilityRow {
  if (!object(value) || !['F1', 'F2', 'F3', 'F4'].includes(String(value.kind)) || !text(value.target_service) || !text(value.target_tool)
    || !count(value.verified_episodes) || (value.verified_episodes as number) < 1 || !count(value.fired_episodes)) return false
  const verified = value.verified_episodes as number, fired = value.fired_episodes as number
  return fired <= verified && value.fired_share === `${fired}/${verified}` && value.status === rowStatus(verified, fired)
}
/** A frozen table, with the backend model's consistency rules (sorted unique targets, statuses from the counts, refused lines). */
export function fireabilityTable(value: unknown): value is FireabilityTable {
  if (!object(value) || value.schema_version !== 'faultlab-history-fireability/v1' || !text(value.meaning) || !digest(value.history_summary_hash)
    || !digest(value.history_episode_ids_hash) || !count(value.record_cutoff) || !count(value.verified_episodes) || !Array.isArray(value.rows) || !value.rows.every(row)
    || !Array.isArray(value.refused_targets) || !value.refused_targets.every(text)) return false
  const rows = value.rows as FireabilityRow[]
  const keys = rows.map(item => `${item.kind}\u0000${item.target_service}\u0000${item.target_tool}`)
  return keys.every((key, index) => index === 0 || keys[index - 1] < key) && rows.every(item => item.verified_episodes <= (value.verified_episodes as number))
    && same(value.refused_targets, rows.filter(item => item.status === 'REFUSED').map(refusedText))
}
/** The offered rule (saved = false: no table) or a saved plan's block (saved = true: the rule and its frozen table). */
export function explorerSelectionDeclaration(value: unknown, saved = false): value is ExplorerSelectionDeclaration | ExplorerSelectionPlan {
  if (!rule(value)) return false
  const block = value as RuleFields & { table?: unknown; table_hash?: unknown }
  if (!saved) return !('table' in block) && !('table_hash' in block)
  return fireabilityTable(block.table) && digest(block.table_hash)
}
function target(value: unknown): value is TargetCheck {
  return object(value) && text(value.kind) && text(value.target_service) && text(value.target_tool) && (value.table_row === null || row(value.table_row))
    && (value.table_row === null ? value.status === 'NOT_IN_HISTORY' : value.status === (value.table_row as FireabilityRow).status)
}
/** One saved pick decision: a refusal has every target REFUSED and names those rows and why; an allowed pick has at least one
 * target that is not REFUSED (a REFUSED target beside it is named only in its targets and reason) and lists no refused rows. */
export function fireabilityDecision(value: unknown): value is FireabilityDecision {
  if (!object(value) || value.protocol !== EXPLORER_SELECTION_V3 || !['discovery', 'challenge'].includes(String(value.purpose)) || !digest(value.table_hash)
    || ![1, 2].includes(value.slot_request as number) || !(value.replan_of === null || text(value.replan_of)) || (value.slot_request === 2) !== text(value.replan_of) || !text(value.pick)
    || !['ALLOWED', 'REFUSED_LOW_FIRED_SHARE', 'INVALID_OUTPUT', 'NOT_CHECKED_DUPLICATE'].includes(String(value.status))
    || !(value.request_index === null || count(value.request_index)) || !Array.isArray(value.targets) || !value.targets.every(target)
    || !Array.isArray(value.refused_targets) || !value.refused_targets.every(row) || !(value.reason === null || typeof value.reason === 'string')) return false
  const targets = value.targets as TargetCheck[]
  const refusedRows = targets.filter(item => item.status === 'REFUSED').length
  if (value.status === 'REFUSED_LOW_FIRED_SHARE') return refusedRows > 0 && refusedRows === targets.length && (value.refused_targets as FireabilityRow[]).length === refusedRows && object(value.refused_fault_spec) && text(value.reason)
  if ((value.refused_targets as unknown[]).length !== 0 || value.refused_fault_spec !== null) return false
  // An allowed pick was checked target by target and has at least one target that is not REFUSED (a REFUSED target beside
  // it comes with its reason); a duplicate or an invalid answer has nothing checked.
  if (value.status === 'ALLOWED') return targets.length > 0 && refusedRows < targets.length && (refusedRows === 0 || text(value.reason))
  return targets.length === 0
}
function unrequested(value: unknown): value is UnrequestedSlot {
  return object(value) && text(value.record_id) && value.protocol === EXPLORER_SELECTION_V3 && count(value.selection_index) && value.status === 'NO_EXPLORER_REQUEST'
    && count(value.explorer_requests_used) && count(value.explorer_requests_max) && value.explorer_requests_used === value.explorer_requests_max
    && count(value.replans_after_refusals) && text(value.reason)
}
export function validateExplorerFireability(value: unknown): ExplorerFireability {
  if (!object(value) || value.protocol !== EXPLORER_SELECTION_V3 || !digest(value.table_hash) || !Array.isArray(value.refused_targets) || !value.refused_targets.every(text)
    || !count(value.picks_checked) || !count(value.picks_refused) || !Array.isArray(value.decisions) || !Array.isArray(value.slots_without_request)
    || !value.slots_without_request.every(unrequested)) throw new Error('Malformed history fireability records.')
  for (const item of value.decisions as unknown[]) {
    if (!object(item) || !fireabilityDecision(item)) throw new Error('Malformed history fireability records.')
    const listed = item as Record<string, unknown>
    if (!text(listed.selection_id) || !(listed.challenge_id === null || text(listed.challenge_id))
      || !(listed.recipe === null || (Array.isArray(listed.recipe) && listed.recipe.every(text))) || listed.table_hash !== value.table_hash) throw new Error('Malformed history fireability records.')
  }
  const decisions = value.decisions as FireabilityDecisionRow[]
  if (value.picks_refused !== decisions.filter(item => item.status === 'REFUSED_LOW_FIRED_SHARE').length
    || value.picks_checked !== decisions.filter(item => item.status === 'ALLOWED' || item.status === 'REFUSED_LOW_FIRED_SHARE').length) throw new Error('Malformed history fireability records.')
  return value as ExplorerFireability
}

/** The rule in one line (a v3-history or v4 plan saved before it: plainly not declared). */
export function explorerSelectionText(declared: ExplorerSelectionDeclaration | null | undefined): string {
  if (!declared) return 'Not declared: this plan was saved before the history fireability rule. Every valid Explorer pick runs, as before.'
  return `Before any episode, a discovery or challenge pick whose every fault targets a target that fired in fewer than ${declared.min_fired_share} of at least ${declared.min_verified_episodes} verified episodes of this agent's frozen history is refused; a pick with a fault on any other target runs, even beside such a target · ${declared.replans_per_refused_pick} re-plan per refused pick, inside the Explorer requests already declared (charged as before) · the table comes only from the frozen history, never from a candidate, and is the same for every candidate · the challenge itself is unchanged`
}
export const ROW_STATUS_LABELS: Record<FireabilityRowStatus, string> = { REFUSED: 'Refused', ALLOWED: 'Allowed', ALLOWED_FEWER_THAN_3: 'Allowed (fewer than 3 episodes)' }
export const DECISION_LABELS: Record<FireabilityDecisionStatus, string> = {
  ALLOWED: 'Allowed', REFUSED_LOW_FIRED_SHARE: 'Refused: seldom fired', INVALID_OUTPUT: 'Invalid output', NOT_CHECKED_DUPLICATE: 'Duplicate (not checked)',
}
/** What one pick decision means, in plain words. The backend's reasons already start with "Refused before…" or "Allowed:". */
export function decisionText(decision: FireabilityDecision): string {
  const replan = decision.slot_request === 2 ? ' (re-plan)' : ''
  if (decision.status === 'REFUSED_LOW_FIRED_SHARE') {
    const reason = decision.reason ?? 'Refused before any episode ran: every fault targets a target that seldom fired in the frozen history.'
    return decision.slot_request === 2 ? `Re-plan. ${reason}` : reason
  }
  if (decision.status === 'ALLOWED' && decision.reason) return decision.slot_request === 2 ? `Re-plan. ${decision.reason}` : decision.reason
  if (decision.status === 'INVALID_OUTPUT') return `Invalid answer${replan}: nothing to check, nothing ran.`
  if (decision.status === 'NOT_CHECKED_DUPLICATE') return `Declined as a duplicate${replan} before this rule ran (discovery's unchanged duplicate rule).`
  const unlisted = decision.targets.filter(item => item.status === 'NOT_IN_HISTORY').length
  return `Allowed${replan}: no fault targets a REFUSED row${unlisted ? ` (${unlisted} target${unlisted === 1 ? '' : 's'} not in the history, allowed)` : ''}${decision.pick === 'fixed_invalid_output_fallback' ? ' · this was the fixed fallback after an invalid answer' : ''}.`
}
