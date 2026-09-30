import { object, request } from './api'
import type { AgentRegistration, Campaign, CampaignBudget, EpisodeBudget, FaultSpec } from './generated/contracts'
import { validateContract } from './generated/validate'
import { challengeSelectionDeclaration, diagnosisGuideDeclaration, mechanicContextDeclaration, mechanicDiagnosisDeclaration, mechanicEvidenceDeclaration, type ChallengeSelectionDeclaration,
  type DiagnosisGuideDeclaration, type MechanicContextDeclaration, type MechanicDiagnosisDeclaration, type MechanicEvidenceDeclaration } from './loopLimits'
import { FIREABILITY_PROTOCOLS, explorerSelectionDeclaration, type ExplorerSelectionDeclaration, type ExplorerSelectionPlan } from './historyFireability'

export const TASK_DEFINITION = 'orders.upgrade_then_confirm/v1' as const
/** 'smolagents' is native adapter v1 (unchanged); 'smolagents-v2' is the declared native adapter v2. */
export type AgentKind = 'reference' | 'smolagents' | 'smolagents-v2'
export const AGENT_KINDS: readonly AgentKind[] = ['reference', 'smolagents', 'smolagents-v2']
export const NATIVE_AGENT_KINDS: readonly AgentKind[] = ['smolagents', 'smolagents-v2']
export const NATIVE_V2_LABEL = 'smolagents ToolCallingAgent - adapter v2 (short evidence labels, strict final report turn)'
const AGENT_NAMES: Record<AgentKind, string> = { reference: 'FaultLab reference actor', smolagents: 'smolagents ToolCallingAgent', 'smolagents-v2': NATIVE_V2_LABEL }
export const isAgentKind = (value: unknown): value is AgentKind => AGENT_KINDS.includes(value as AgentKind)
export const isNativeAgent = (value: unknown): boolean => NATIVE_AGENT_KINDS.includes(value as AgentKind)
/** Display name of a saved agent kind; an unknown kind (e.g. 'unsupported') is shown as recorded. */
export const agentName = (value: string): string => isAgentKind(value) ? AGENT_NAMES[value] : value
export type RunMode = 'baseline' | 'learn' | 'compare'
export type RunProfile = 'offline-v1' | 'live-v1'
export type RunCaps = Required<CampaignBudget>
export type SearchSpace = { maximum_primitives: number; kinds: string[]; occurrence: number[]; f1_milliseconds: number[]; f2_ticks: number[]; f3_versions: number[]; f4_count: number[]; preflight_required: boolean }
export type DevelopmentCase = { case_id: string; label: string; description: string; fixture_id: string; expected_version: number; fault_spec: FaultSpec }
export type DiscoveryProtocolId = 'faultlab-discovery/v1' | 'faultlab-discovery/v2-reachability' | 'faultlab-discovery/v3-history' | 'faultlab-discovery/v3-history-reachability' | 'faultlab-discovery/v4-history-replay'
/** The two product paths a history row can come from (backend agent_history.SOURCES); single-case baseline runs never count. */
export type HistorySource = 'baseline_study' | 'learn_discovery'
export const HISTORY_SOURCES: Record<HistorySource, string> = { baseline_study: 'baseline study', learn_discovery: 'learn discovery' }
/** Discovery v3: one recipe row of the frozen same-agent history (backend app/lab/agent_history.py). runtime_hashes and
 * adapter_hashes are 12-character prefixes of the FaultLab builds its episodes ran under ('unrecorded' when not saved). */
export type AgentHistoryRow = { development_case_id: string | null; recipe: string[]; primitives: FaultSpec['primitives']; sources: HistorySource[]; verified_episodes: number; every_fault_fired: number | null; outcomes: Record<string, number>; failed_checks: Record<string, number>; excluded: Record<string, number>; runtime_hashes: string[]; adapter_hashes: string[] }
export type HistoryComposition = { baseline_studies: number; baseline_study_episodes: number; learn_campaigns: number; learn_discovery_episodes: number }
export type HistoryBuild = { runtime_hash: string; adapter_hash: string; verified_episodes: number }
export type AgentHistorySummary = { schema_version: 'faultlab-agent-history/v2'; status: 'AVAILABLE' | 'NO_PRIOR_HISTORY'; statement: string; scope: string; agent: { adapter_entrypoint_id: string | null; model: string | null }; verified_episodes: number; recipes_total: number; composition: HistoryComposition; builds: HistoryBuild[]; excluded: Record<string, number>; recipes: AgentHistoryRow[]; recipes_omitted: number; excluded_only_recipes: number }
/** Frozen when the plan is saved: exactly what the Explorer reads (summary), its hash and the store record cutoff. */
export type AgentHistory = { schema_version: 'faultlab-agent-history/v2'; status: 'AVAILABLE' | 'NO_PRIOR_HISTORY'; rule: string; agent_identity: Record<string, unknown>; policy_hash: string; record_cutoff: number; episode_ids_hash: string; summary: AgentHistorySummary; summary_hash: string }
/** The on-demand check of a saved v3 plan's history against the store (GET …/plan/history-check; never polled). */
export type HistoryCheck = { campaign_id: string; status: 'CURRENT' | 'CHANGED' | 'NOT_CHECKED' | 'NOT_APPLICABLE'; message: string; record_cutoff: number | null; summary_hash: string | null }
/** A pick or source that re-tries a listed history row (order-aware schedule identity, seed ignored). */
export type HistoryRowMatch = { row: number; development_case_id: string | null; basis: string }
/** Discovery v4: one frozen replay row (backend app/lab/history_replay.py): the history row it re-runs first, and its counts. */
export type HistoryReplayRow = { replay: number; history_row: number; development_case_id: string | null; recipe: string[]; fault_spec: FaultSpec; schedule_identity_v2: string; verified_episodes: number; violations: number; violation_share: string; every_fault_fired: number; outcomes: Record<string, number>; failed_checks: Record<string, number>; sources: HistorySource[] }
/** Discovery v4: the replay list frozen from the plan's frozen history when the plan is saved (EMPTY says so plainly). */
export type HistoryReplay = { schema_version: 'faultlab-history-replay/v1'; status: 'AVAILABLE' | 'EMPTY'; statement: string; rule: string; basis: 'faultlab-schedule-identity/v2-order-aware'; max_rows: 3; min_verified_episodes: 2; min_violation_share: '2/3'; history_summary_hash: string; rows: HistoryReplayRow[] }
/** Discovery v4: a replay slot as its selection record, the fault-search panel, the source panel and the recording name it. No Explorer request was sent. */
export type HistoryReplaySlot = { label: 'history replay'; protocol: 'faultlab-discovery/v4-history-replay'; replay: number; of: number; history_row: number; development_case_id: string | null; recipe: string[]; verified_episodes: number; violations: number; violation_share: string; every_fault_fired: number; failed_checks: Record<string, number>; schedule_identity_v2: string; basis: string; episode_id: string; explorer_request: false; selection_id?: string }
export type CallerModel = { caller_id: string; agent: 'reference'; max_business_calls: number; adapter_attempts: number; client_timeout_seconds: number; wait_action: boolean; ticks_per_http_attempt: number; http_attempts: number; ticks: number; polling: string; unknown_status_checks?: number; resends_failed_writes?: boolean; validated_against: string; facts: string[] }
/** explorer_transport_retries_max: one charged retry per Explorer request that got no answer; not a request itself. Absent or null in plans saved before it existed (none declared). */
export type DiscoveryDeclaration = { protocol: DiscoveryProtocolId; schedule_identity: string; slots: number; explorer_requests_max: number; explorer_transport_retries_max?: number | null; actor_episodes_max: number; replans_per_slot: number; dispatch_rule: string; pre_check: null | { labeller: string; caller_model: CallerModel }
  /** Discovery v3 and v4: null in the run options (frozen when a plan is saved), the frozen block in a saved plan; absent for v1/v2. */
  history?: AgentHistory | null
  /** Discovery v4 only: null in the run options, the frozen replay list in a saved plan; absent for every other protocol. */
  replay?: HistoryReplay | null }
/** The shared model-request retry rule frozen into a plan (backend app/agents/transport_retry.py): rule v1, one blind retry for every role. */
export type TransportRetryDeclarationV1 = { protocol: 'faultlab-transport-retry/v1'; retries_per_request: 1; roles: ['actor', 'explorer', 'mechanic']; retryable: ['CONNECTION_ERROR', 'REQUEST_TIMEOUT', 'HTTP_503']; service_unavailable_delay_seconds: 1; actor_retries_per_episode_max: number; rule: string }
/** Rule v2, frozen into every new Learn plan: the agent roles keep rule v1; the Explorer and Mechanic back off (5 s, 20 s, 60 s) and retry up to 3 times, at most 12 per campaign. */
export type TransportRetryDeclarationV2 = { protocol: 'faultlab-transport-retry/v2-lab-backoff'; retryable: ['CONNECTION_ERROR', 'REQUEST_TIMEOUT', 'HTTP_503']; agent_roles: ['actor']; agent_retries_per_request: 1; service_unavailable_delay_seconds: 1; actor_retries_per_episode_max: number
  lab_roles: ['explorer', 'mechanic']; lab_retries_per_request: 3; lab_backoff_seconds: [5, 20, 60]; lab_retries_per_campaign_max: 12; stop_during_wait: 'STOPPED'; rule: string }
export type TransportRetryDeclaration = TransportRetryDeclarationV1 | TransportRetryDeclarationV2
export const TRANSPORT_RETRY_V2 = 'faultlab-transport-retry/v2-lab-backoff'
export const isLabBackoff = (value: TransportRetryDeclaration | null | undefined): value is TransportRetryDeclarationV2 => value?.protocol === TRANSPORT_RETRY_V2
/** The automatic evidence retry rule frozen into a Learn plan (backend app/lab/evidence_wait.py): telemetry only, bounded per wait
 * and (v2, v3) per campaign. v3 (24 per campaign) is frozen into every new Learn plan since September 30; a saved v2 plan (6 per
 * campaign) still starts and keeps its cap. v1 had no campaign limit; it was never run live, and Start refuses a saved v1 plan. */
type EvidenceRetryBase = { trigger: 'WAITING_EVIDENCE'; automatic_retries_per_wait: 3; delays_seconds: [30, 120, 300]; path: 'retry-evidence'; telemetry_only: true; repeats_model_requests: false; repeats_business_actions: false; charged_model_calls: 0; after_last_retry: 'NEEDS_OPERATOR'; rule: string }
export type EvidenceRetryDeclaration = (EvidenceRetryBase & { protocol: 'faultlab-evidence-retry/v1'; automatic_retries_per_campaign?: undefined })
  | (EvidenceRetryBase & { protocol: 'faultlab-evidence-retry/v2'; automatic_retries_per_campaign: 6 })
  | (EvidenceRetryBase & { protocol: 'faultlab-evidence-retry/v3'; automatic_retries_per_campaign: 24 })
export type DiscoveryOption = { protocol_id: DiscoveryProtocolId; default: boolean; label: string; description: string; supported_agents: AgentKind[]; unsupported_reason?: string; declaration: DiscoveryDeclaration }
export type RunAgent = { agent: AgentKind; label: string; status: 'READY' | 'UNAVAILABLE'; reason_code: string; message: string; configuration_hash: string | null; proposed_registration_id: string | null; registered: boolean; registration_id: string | null; model: string; source_conformance: 'VERIFIED' | 'UNAVAILABLE'; provider_access: 'not_checked'; behavior_verified: false; compare_available: boolean; accepted_policy_version: string | null; limitations: string[] }
export type RunOptions = {
  schema_version: 'faultlab-run-options/v1'; setup_hash: string; data_store: { identity: string; path: string; read_only: boolean }
  task: { task_definition_id: typeof TASK_DEFINITION; label: string; description: string; task_text_default: string }
  profiles: { profile_id: RunProfile; label: string; source_mode: 'offline_fixture' | 'live'; arm: 'B1' | 'B0'; registration_required: boolean }[]
  development: { manifest_hash: string; cases: DevelopmentCase[] }
  /** transport_retry: the rule every new Learn plan freezes (rule v2); absent from backends that predate it.
   * mechanic_context and challenge_selection: the two loop-limit rules every new Learn plan freezes; absent from older backends. */
  learn: { manifest_hash: string; search_space: SearchSpace; selection_limit: number; discovery_protocols?: DiscoveryOption[]; transport_retry?: TransportRetryDeclarationV2; mechanic_context?: MechanicContextDeclaration; challenge_selection?: ChallengeSelectionDeclaration
    /** Frozen only into a new Learn plan of native adapter v2; absent from older backends. */
    mechanic_evidence?: MechanicEvidenceDeclaration
    /** Diagnosis repair and record: frozen into every new Learn plan, every agent; absent from older backends. */
    mechanic_diagnosis?: MechanicDiagnosisDeclaration
    /** Diagnosis guide: built but not offered by today's backend (absent); checked if a later backend offers it. */
    diagnosis_guide?: DiagnosisGuideDeclaration
    /** History fireability: frozen, with its table, only into a new Learn plan with discovery v3 · agent history or v4 · history
     * replay (the declaration names them); offered here without a table. Absent from older backends. */
    explorer_selection?: ExplorerSelectionDeclaration }
  compare: { partition: 'promotion'; manifest_hash: string; case_count: number; trials_per_case: number }
  agents: RunAgent[]; offline: { agent: 'reference'; configuration_hash: string; registration_required: false }
  caps: RunCaps; episode_budget: Required<EpisodeBudget>; models: { actor: string; explorer: string; mechanic: string }; provider_calls: 0
}
export type PlanSelection =
  | { kind: 'development_case'; case_id: string; fixture_id: string; expected_version: number; fault_spec: FaultSpec; scenario_hash: string; manifest_hash: string }
  | { kind: 'development_search'; manifest_hash: string; search_space: SearchSpace }
  | { kind: 'protected_comparison'; partition: 'promotion'; manifest_hash: string; case_count: number; trials_per_case: number }
export type RunPlan = { schema_version: 'faultlab-run-plan/v1'; campaign_id: string; setup_hash: string; task_definition_id: typeof TASK_DEFINITION; mode: RunMode; config_profile_id: RunProfile; task_text: string; order_id: string; configuration_hash: string; agent_registration_id: string; agent: AgentKind; source_mode: 'live' | 'offline_fixture'; caps: RunCaps; episode_budget: Required<EpisodeBudget>; initial_policy_version: string; initial_policy_hash: string; selection: PlanSelection; discovery?: DiscoveryDeclaration | null; transport_retry?: TransportRetryDeclaration | null; evidence_retry?: EvidenceRetryDeclaration | null
  /** Learn only; absent from every plan saved before these rules and from every baseline or compare plan. */
  mechanic_context?: MechanicContextDeclaration | null; challenge_selection?: ChallengeSelectionDeclaration | null
  /** A native adapter v2 Learn plan only; absent from every other plan and from every plan saved before the rule. */
  mechanic_evidence?: MechanicEvidenceDeclaration | null
  /** Learn only, every agent; absent from every baseline or compare plan and from every Learn plan saved before the rule. */
  mechanic_diagnosis?: MechanicDiagnosisDeclaration | null
  /** Learn only; no plan saved by today's backend declares it (built, not offered). */
  diagnosis_guide?: DiagnosisGuideDeclaration | null
  /** A Learn plan with discovery v3 · agent history or v4 · history replay only, every new one; absent from every other plan
   * and from every plan saved before the rule. */
  explorer_selection?: ExplorerSelectionPlan | null; plan_hash: string }
export type CampaignPlan = { campaign_id: string; status: 'PLANNED'; plan: RunPlan } | { campaign_id: string; status: 'LEGACY'; plan: null }
export type PlannedCampaignRequest = { expected_store_identity: string; expected_setup_hash: string; task_definition_id: typeof TASK_DEFINITION; agent_registration_id?: string; mode: RunMode; config_profile_id: RunProfile; task_text: string; order_id: string; development_case_id?: string; discovery_protocol?: DiscoveryProtocolId }

const text = (value: unknown): value is string => typeof value === 'string' && value.trim().length > 0
const digest = (value: unknown): value is string => typeof value === 'string' && /^[a-f0-9]{64}$/.test(value)
const positive = (value: unknown): value is number => Number.isSafeInteger(value) && (value as number) > 0
const nullableText = (value: unknown) => value === null || text(value)
const stringList = (value: unknown) => Array.isArray(value) && value.every(text)
const malformed = (part: string): never => { throw new Error(`Malformed ${part} response. No execution was started.`) }
function searchSpace(value: unknown): value is SearchSpace {
  return object(value) && positive(value.maximum_primitives) && stringList(value.kinds) && (value.kinds as string[]).every(kind => ['F1', 'F2', 'F3', 'F4'].includes(kind))
    && ['occurrence', 'f1_milliseconds', 'f2_ticks', 'f3_versions', 'f4_count'].every(key => Array.isArray(value[key]) && (value[key] as unknown[]).length > 0 && (value[key] as unknown[]).every(positive)) && typeof value.preflight_required === 'boolean'
}
function comparison(value: unknown): boolean {
  return object(value) && value.partition === 'promotion' && digest(value.manifest_hash) && positive(value.case_count) && positive(value.trials_per_case)
}
const DISCOVERY_PROTOCOLS = ['faultlab-discovery/v1', 'faultlab-discovery/v2-reachability', 'faultlab-discovery/v3-history', 'faultlab-discovery/v3-history-reachability', 'faultlab-discovery/v4-history-replay']
/** Protocols whose plan freezes the agent history: the v3 forms add only it to their base (v3-history is v1, v3-history-reachability
 * is v2); v4 is v3-history plus a frozen replay list. */
export const HISTORY_PROTOCOLS: string[] = ['faultlab-discovery/v3-history', 'faultlab-discovery/v3-history-reachability', 'faultlab-discovery/v4-history-replay']
/** Discovery v4 (regression-first): replays up to three frozen history rows before the Explorer's slots. */
export const REPLAY_PROTOCOL = 'faultlab-discovery/v4-history-replay'
export const preChecked = (protocol: unknown) => protocol === 'faultlab-discovery/v2-reachability' || protocol === 'faultlab-discovery/v3-history-reachability'
const count = (value: unknown): value is number => Number.isSafeInteger(value) && (value as number) >= 0
const counts = (value: unknown) => object(value) && Object.values(value).every(count)
const buildHash = (value: unknown) => typeof value === 'string' && /^([a-f0-9]{12}|unrecorded)$/.test(value)
function historyRow(value: unknown): value is AgentHistoryRow {
  return object(value) && (value.development_case_id === null || (text(value.development_case_id) && /^dev-[1-6]$/.test(value.development_case_id)))
    && stringList(value.recipe) && (value.recipe as string[]).length > 0 && Array.isArray(value.primitives) && stringList(value.sources) && (value.sources as string[]).length > 0
    && (value.sources as string[]).every(source => source in HISTORY_SOURCES)
    && positive(value.verified_episodes) && (value.every_fault_fired === null || count(value.every_fault_fired)) && counts(value.outcomes) && counts(value.failed_checks) && counts(value.excluded)
    && [value.runtime_hashes, value.adapter_hashes].every(list => Array.isArray(list) && list.length > 0 && list.every(buildHash))
}
function composition(value: unknown): value is HistoryComposition {
  return object(value) && ['baseline_studies', 'baseline_study_episodes', 'learn_campaigns', 'learn_discovery_episodes'].every(key => count(value[key]))
}
function builds(value: unknown): value is HistoryBuild[] {
  return Array.isArray(value) && value.every(item => object(item) && buildHash(item.runtime_hash) && buildHash(item.adapter_hash) && positive(item.verified_episodes))
}
/** An optional derived flag on a v3 selection or source: null means checked with no match. */
export function historyRowMatch(value: unknown): value is HistoryRowMatch | null {
  return value === null || (object(value) && positive(value.row) && (value.development_case_id === null || (text(value.development_case_id) && /^dev-[1-6]$/.test(value.development_case_id))) && text(value.basis))
}
const caseId = (value: unknown) => value === null || (text(value) && /^dev-[1-6]$/.test(value))
const share = (violations: number, verified: number) => Number.isSafeInteger(verified) && verified >= 2 && count(violations) && 3 * violations >= 2 * verified
/** One frozen replay row, with the same consistency rules the backend model enforces (share at least 2/3, every fault fired). */
function historyReplayRow(value: unknown, index: number): value is HistoryReplayRow {
  if (!object(value) || value.replay !== index + 1 || !positive(value.history_row) || !caseId(value.development_case_id) || !stringList(value.recipe) || !(value.recipe as string[]).length
    || !object(value.fault_spec) || !Array.isArray(value.fault_spec.primitives) || !value.fault_spec.primitives.length || !digest(value.schedule_identity_v2)
    || !counts(value.outcomes) || !counts(value.failed_checks) || !stringList(value.sources) || !(value.sources as string[]).length || !(value.sources as string[]).every(source => source in HISTORY_SOURCES)) return false
  const verified = value.verified_episodes as number, violations = value.violations as number
  return share(violations, verified) && value.violation_share === `${violations}/${verified}` && value.every_fault_fired === verified && (value.outcomes as Record<string, number>).VIOLATION === violations
}
/** The frozen replay list of a saved v4 plan: computed from, and bound to, the plan's frozen history (the backend recomputes it before any replay). */
export function historyReplay(value: unknown, history: unknown): value is HistoryReplay {
  if (!object(value) || value.schema_version !== 'faultlab-history-replay/v1' || !['AVAILABLE', 'EMPTY'].includes(String(value.status)) || !text(value.statement) || !text(value.rule)
    || value.basis !== 'faultlab-schedule-identity/v2-order-aware' || value.max_rows !== 3 || value.min_verified_episodes !== 2 || value.min_violation_share !== '2/3'
    || !agentHistory(history) || value.history_summary_hash !== history.summary_hash || !Array.isArray(value.rows) || value.rows.length > 3 || !value.rows.every(historyReplayRow)) return false
  const rows = value.rows as HistoryReplayRow[], listed = history.summary.recipes
  // Each replayed row is a listed history row, once, with the same development case.
  return (value.status === 'AVAILABLE') === rows.length > 0 && new Set(rows.map(row => row.history_row)).size === rows.length
    && rows.every(row => row.history_row <= listed.length && listed[row.history_row - 1].development_case_id === row.development_case_id)
}
/** A replay slot's label block (selection record, source projection): never an Explorer request. */
export function historyReplaySlot(value: unknown): value is HistoryReplaySlot {
  return object(value) && value.label === 'history replay' && value.protocol === REPLAY_PROTOCOL && positive(value.replay) && positive(value.of) && (value.replay as number) <= (value.of as number) && (value.of as number) <= 3
    && positive(value.history_row) && caseId(value.development_case_id) && stringList(value.recipe) && share(value.violations as number, value.verified_episodes as number)
    && value.violation_share === `${value.violations}/${value.verified_episodes}` && value.every_fault_fired === value.verified_episodes && counts(value.failed_checks)
    && digest(value.schedule_identity_v2) && text(value.basis) && text(value.episode_id) && value.explorer_request === false && (value.selection_id === undefined || text(value.selection_id))
}
/** The frozen history block of a saved v3 plan. The backend recomputes and checks its hash before any Explorer request. */
export function agentHistory(value: unknown): value is AgentHistory {
  if (!object(value) || value.schema_version !== 'faultlab-agent-history/v2' || !['AVAILABLE', 'NO_PRIOR_HISTORY'].includes(String(value.status)) || !text(value.rule)
    || !object(value.agent_identity) || !digest(value.policy_hash) || !count(value.record_cutoff) || !digest(value.episode_ids_hash) || !digest(value.summary_hash)) return false
  const summary = value.summary
  if (!object(summary) || summary.schema_version !== value.schema_version || summary.status !== value.status || !text(summary.statement) || !text(summary.scope) || !object(summary.agent)
    || !count(summary.verified_episodes) || !count(summary.recipes_total) || !count(summary.recipes_omitted) || !count(summary.excluded_only_recipes) || !counts(summary.excluded)
    || !composition(summary.composition) || !builds(summary.builds) || !Array.isArray(summary.recipes) || !summary.recipes.every(historyRow)) return false
  const rows = summary.recipes as AgentHistoryRow[]
  const made = summary.composition as HistoryComposition, verified = summary.verified_episodes as number
  // NO_PRIOR_HISTORY says so plainly: no verified episode and no recipe row. The composition and builds account for every verified episode.
  return (summary.status === 'AVAILABLE') === verified > 0 && rows.reduce((total, row) => total + row.verified_episodes, 0) <= verified
    && (summary.recipes_total as number) === rows.length + (summary.recipes_omitted as number)
    && made.baseline_study_episodes + made.learn_discovery_episodes === verified && (summary.builds as HistoryBuild[]).reduce((total, build) => total + build.verified_episodes, 0) === verified
}
/** A declared discovery block, with the same coherence rules the backend enforces. In a saved plan a v3 block must carry its frozen history. */
export function discoveryDeclaration(value: unknown, saved = false): value is DiscoveryDeclaration {
  if (!object(value) || !DISCOVERY_PROTOCOLS.includes(String(value.protocol)) || !text(value.schedule_identity) || !text(value.dispatch_rule)
    || !['slots', 'explorer_requests_max', 'actor_episodes_max'].every(key => positive(value[key])) || ![0, 1].includes(value.replans_per_slot as number)) return false
  if (HISTORY_PROTOCOLS.includes(String(value.protocol)) ? !(saved ? agentHistory(value.history) : value.history === null) : value.history !== undefined) return false
  if (value.protocol === REPLAY_PROTOCOL ? !(saved ? historyReplay(value.replay, value.history) : value.replay === null) : value.replay !== undefined) return false
  const v2 = preChecked(value.protocol), slots = value.slots as number
  if (value.explorer_requests_max !== slots * (v2 ? 2 : 1) || value.actor_episodes_max !== slots || value.replans_per_slot !== (v2 ? 1 : 0)) return false
  // At most one transport retry per Explorer request; older plans declare none (absent or null).
  if (!(value.explorer_transport_retries_max === undefined || value.explorer_transport_retries_max === null || value.explorer_transport_retries_max === value.explorer_requests_max)) return false
  if (!v2) return value.pre_check === null
  const check = value.pre_check
  if (!object(check) || !text(check.labeller) || !object(check.caller_model)) return false
  const caller = check.caller_model
  return caller.agent === 'reference' && text(caller.caller_id) && positive(caller.max_business_calls) && positive(caller.adapter_attempts)
    && typeof caller.client_timeout_seconds === 'number' && caller.wait_action === false && stringList(caller.facts) && text(caller.validated_against)
}
const same = (value: unknown, expected: string[]) => Array.isArray(value) && value.length === expected.length && value.every((item, index) => item === expected[index])
/** The declared transport retry rule v1, exactly as the backend freezes it. */
export function transportRetry(value: unknown, actorCalls: number): value is TransportRetryDeclarationV1 {
  return object(value) && value.protocol === 'faultlab-transport-retry/v1' && value.retries_per_request === 1
    && same(value.roles, ['actor', 'explorer', 'mechanic']) && same(value.retryable, ['CONNECTION_ERROR', 'REQUEST_TIMEOUT', 'HTTP_503'])
    && value.service_unavailable_delay_seconds === 1 && value.actor_retries_per_episode_max === actorCalls && text(value.rule)
}
/** Rule v2 (lab-role backoff), exactly as the backend freezes it into a Learn plan. */
export function transportRetryV2(value: unknown, actorCalls: number): value is TransportRetryDeclarationV2 {
  return object(value) && value.protocol === TRANSPORT_RETRY_V2 && same(value.retryable, ['CONNECTION_ERROR', 'REQUEST_TIMEOUT', 'HTTP_503'])
    && same(value.agent_roles, ['actor']) && value.agent_retries_per_request === 1 && value.service_unavailable_delay_seconds === 1
    && value.actor_retries_per_episode_max === actorCalls && same(value.lab_roles, ['explorer', 'mechanic']) && value.lab_retries_per_request === 3
    && Array.isArray(value.lab_backoff_seconds) && value.lab_backoff_seconds.length === 3 && [5, 20, 60].every((delay, index) => (value.lab_backoff_seconds as unknown[])[index] === delay)
    && value.lab_retries_per_campaign_max === 12 && value.stop_during_wait === 'STOPPED' && text(value.rule)
}
/** The declared automatic evidence retry rule, exactly as the backend freezes it into a Learn plan. */
export function evidenceRetry(value: unknown): value is EvidenceRetryDeclaration {
  if (!object(value)) return false
  const limit = value.protocol === 'faultlab-evidence-retry/v3' ? value.automatic_retries_per_campaign === 24
    : value.protocol === 'faultlab-evidence-retry/v2' ? value.automatic_retries_per_campaign === 6
    : value.protocol === 'faultlab-evidence-retry/v1' && !('automatic_retries_per_campaign' in value)
  return limit && value.trigger === 'WAITING_EVIDENCE' && value.automatic_retries_per_wait === 3
    && Array.isArray(value.delays_seconds) && value.delays_seconds.length === 3 && [30, 120, 300].every((delay, index) => (value.delays_seconds as unknown[])[index] === delay)
    && value.path === 'retry-evidence' && value.telemetry_only === true && value.repeats_model_requests === false && value.repeats_business_actions === false
    && value.charged_model_calls === 0 && value.after_last_retry === 'NEEDS_OPERATOR' && text(value.rule)
}
function discoveryOptions(value: unknown): boolean {
  if (!Array.isArray(value) || !value.length) return false
  const ids = new Set<string>()
  for (const option of value) {
    if (!object(option) || !DISCOVERY_PROTOCOLS.includes(String(option.protocol_id)) || ids.has(String(option.protocol_id)) || typeof option.default !== 'boolean'
      || !text(option.label) || !text(option.description) || !Array.isArray(option.supported_agents) || !option.supported_agents.every(isAgentKind)
      || !(option.unsupported_reason === undefined || text(option.unsupported_reason)) || !discoveryDeclaration(option.declaration) || option.declaration.protocol !== option.protocol_id) return false
    if (preChecked(option.protocol_id) && (option.default || option.supported_agents.some(isNativeAgent))) return false
    if (HISTORY_PROTOCOLS.includes(String(option.protocol_id)) && option.default) return false
    ids.add(String(option.protocol_id))
  }
  return value.filter(option => option.default).length === 1
}
function validateCaps(value: unknown) {
  validateContract('CampaignBudget', value)
  if (!object(value) || !['model_calls', 'tokens', 'dollars', 'discovery_selections', 'candidates', 'input_tokens_per_call', 'output_tokens_per_call'].every(key => typeof value[key] === 'number')) return malformed('run limits')
}
function validateEpisodeBudget(value: unknown) {
  validateContract('EpisodeBudget', value)
  if (!object(value) || !['http_attempts', 'actor_calls', 'wait_cycles', 'ticks', 'policy_steps', 'wall_seconds'].every(key => typeof value[key] === 'number')) return malformed('episode limits')
}
export function validateRunOptions(value: unknown): RunOptions {
  if (!object(value) || value.schema_version !== 'faultlab-run-options/v1' || !digest(value.setup_hash) || value.provider_calls !== 0
    || !object(value.data_store) || !digest(value.data_store.identity) || !text(value.data_store.path) || typeof value.data_store.read_only !== 'boolean'
    || !object(value.task) || value.task.task_definition_id !== TASK_DEFINITION || !text(value.task.label) || !text(value.task.description) || !text(value.task.task_text_default)
    || !object(value.models) || !['actor', 'explorer', 'mechanic'].every(role => typeof (value.models as Record<string, unknown>)[role] === 'string')
    || !object(value.offline) || value.offline.agent !== 'reference' || !digest(value.offline.configuration_hash) || value.offline.registration_required !== false) return malformed('run options')
  validateCaps(value.caps)
  validateEpisodeBudget(value.episode_budget)
  if (!Array.isArray(value.profiles) || value.profiles.length !== 2 || new Set(value.profiles.map(p => object(p) && p.profile_id)).size !== 2) return malformed('run profiles')
  for (const profile of value.profiles) {
    if (!object(profile) || !text(profile.label) || !(profile.profile_id === 'offline-v1' && profile.source_mode === 'offline_fixture' && profile.arm === 'B1' && profile.registration_required === false || profile.profile_id === 'live-v1' && profile.source_mode === 'live' && profile.arm === 'B0' && profile.registration_required === true)) return malformed('run profile')
  }
  if (!object(value.development) || !digest(value.development.manifest_hash) || !Array.isArray(value.development.cases) || value.development.cases.length !== 6) return malformed('development cases')
  const caseIds = new Set<string>()
  for (const item of value.development.cases) {
    if (!object(item) || !text(item.case_id) || !/^dev-[1-6]$/.test(item.case_id) || caseIds.has(item.case_id) || !text(item.label) || !text(item.description) || !text(item.fixture_id) || !positive(item.expected_version)) return malformed('development case')
    validateContract('FaultSpec', item.fault_spec); caseIds.add(item.case_id)
  }
  if (!object(value.learn) || !digest(value.learn.manifest_hash) || !searchSpace(value.learn.search_space) || !positive(value.learn.selection_limit) || !comparison(value.compare)) return malformed('run search space')
  if (value.learn.discovery_protocols !== undefined && !discoveryOptions(value.learn.discovery_protocols)) return malformed('discovery protocols')
  if (value.learn.transport_retry !== undefined && !(object(value.episode_budget) && transportRetryV2(value.learn.transport_retry, value.episode_budget.actor_calls as number))) return malformed('Learn transport retry rule')
  if (value.learn.mechanic_context !== undefined && !mechanicContextDeclaration(value.learn.mechanic_context)) return malformed('Learn Mechanic request-size rule')
  if (value.learn.challenge_selection !== undefined && !challengeSelectionDeclaration(value.learn.challenge_selection)) return malformed('Learn challenge-pick rule')
  if (value.learn.mechanic_evidence !== undefined && !mechanicEvidenceDeclaration(value.learn.mechanic_evidence)) return malformed('Learn native citation-status rule')
  if (value.learn.mechanic_diagnosis !== undefined && !mechanicDiagnosisDeclaration(value.learn.mechanic_diagnosis)) return malformed('Learn diagnosis repair-and-record rule')
  if (value.learn.diagnosis_guide !== undefined && !diagnosisGuideDeclaration(value.learn.diagnosis_guide)) return malformed('Learn diagnosis guide')
  if (value.learn.explorer_selection !== undefined && !explorerSelectionDeclaration(value.learn.explorer_selection)) return malformed('Learn history fireability rule')
  // The reference Actor and native adapter v1 are always offered; native adapter v2 is offered by current backends.
  if (!Array.isArray(value.agents) || ![2, 3].includes(value.agents.length) || new Set(value.agents.map(a => object(a) && a.agent)).size !== value.agents.length
    || !['reference', 'smolagents'].every(kind => (value.agents as unknown[]).some(a => object(a) && a.agent === kind))) return malformed('reviewed agents')
  for (const agent of value.agents) {
    if (!object(agent) || !isAgentKind(agent.agent) || !text(agent.label) || !['READY', 'UNAVAILABLE'].includes(String(agent.status)) || !text(agent.reason_code) || !text(agent.message)
      || !(agent.configuration_hash === null || digest(agent.configuration_hash)) || !nullableText(agent.proposed_registration_id) || !nullableText(agent.registration_id) || !nullableText(agent.accepted_policy_version)
      || typeof agent.registered !== 'boolean' || typeof agent.compare_available !== 'boolean' || typeof agent.model !== 'string' || !['VERIFIED', 'UNAVAILABLE'].includes(String(agent.source_conformance)) || agent.provider_access !== 'not_checked' || agent.behavior_verified !== false || !stringList(agent.limitations)
      || agent.registered !== (agent.registration_id !== null) || (agent.compare_available && agent.accepted_policy_version === null)
      || (agent.status === 'READY' && (!digest(agent.configuration_hash) || !text(agent.proposed_registration_id) || agent.source_conformance !== 'VERIFIED'))
      || (agent.status === 'UNAVAILABLE' && (agent.configuration_hash !== null || agent.proposed_registration_id !== null || agent.registered || agent.compare_available))) return malformed('reviewed agent')
  }
  return value as RunOptions
}
export function validateCampaignPlan(value: unknown, campaignId: string): CampaignPlan {
  if (!object(value) || value.campaign_id !== campaignId) return malformed('campaign plan identity')
  if (value.status === 'LEGACY' && value.plan === null) return value as CampaignPlan
  const plan = value.plan
  if (value.status !== 'PLANNED' || !object(plan) || plan.schema_version !== 'faultlab-run-plan/v1' || plan.campaign_id !== campaignId || plan.task_definition_id !== TASK_DEFINITION
    || !['setup_hash', 'configuration_hash', 'initial_policy_hash', 'plan_hash'].every(key => digest(plan[key])) || !['task_text', 'order_id', 'agent_registration_id', 'initial_policy_version'].every(key => text(plan[key]))
    || !['baseline', 'learn', 'compare'].includes(String(plan.mode)) || !isAgentKind(plan.agent) || !object(plan.selection)) return malformed('campaign plan')
  if (!(plan.config_profile_id === 'live-v1' && plan.source_mode === 'live' || plan.config_profile_id === 'offline-v1' && plan.source_mode === 'offline_fixture' && plan.agent === 'reference' && plan.mode === 'baseline')) return malformed('campaign plan execution profile')
  validateCaps(plan.caps)
  validateEpisodeBudget(plan.episode_budget)
  const selection = plan.selection
  if (plan.mode === 'baseline') {
    if (selection.kind !== 'development_case' || !text(selection.case_id) || !/^dev-[1-6]$/.test(selection.case_id) || !text(selection.fixture_id) || !positive(selection.expected_version) || !digest(selection.scenario_hash) || !digest(selection.manifest_hash)) return malformed('campaign plan case')
    validateContract('FaultSpec', selection.fault_spec)
  } else if (plan.mode === 'learn') {
    if (selection.kind !== 'development_search' || !digest(selection.manifest_hash) || !searchSpace(selection.search_space)) return malformed('campaign plan search space')
  } else if (selection.kind !== 'protected_comparison' || !comparison(selection)) return malformed('campaign plan comparison')
  // Rule v1 in any plan (every plan saved before rule v2, and every baseline or compare plan); rule v2 only in a Learn plan.
  const actorCalls = (plan.episode_budget as Required<EpisodeBudget>).actor_calls
  if (!(plan.transport_retry === undefined || plan.transport_retry === null || transportRetry(plan.transport_retry, actorCalls)
    || (plan.mode === 'learn' && transportRetryV2(plan.transport_retry, actorCalls)))) return malformed('campaign plan transport retry rule')
  // Only a Learn plan waits for evidence, so only a Learn plan may declare automatic evidence retries.
  if (!(plan.evidence_retry === undefined || plan.evidence_retry === null || (plan.mode === 'learn' && evidenceRetry(plan.evidence_retry)))) return malformed('campaign plan evidence retry rule')
  // The two loop-limit rules: only a Learn plan declares them, exactly as frozen; older plans have neither.
  if (!(plan.mechanic_context === undefined || plan.mechanic_context === null || (plan.mode === 'learn' && mechanicContextDeclaration(plan.mechanic_context)))) return malformed('campaign plan Mechanic request-size rule')
  if (!(plan.challenge_selection === undefined || plan.challenge_selection === null || (plan.mode === 'learn' && challengeSelectionDeclaration(plan.challenge_selection)))) return malformed('campaign plan challenge-pick rule')
  // Native citation status: only a Learn plan of native adapter v2 declares it, exactly as frozen.
  if (!(plan.mechanic_evidence === undefined || plan.mechanic_evidence === null || (plan.mode === 'learn' && plan.agent === 'smolagents-v2' && mechanicEvidenceDeclaration(plan.mechanic_evidence)))) return malformed('campaign plan native citation-status rule')
  // The diagnosis rules: only a Learn plan declares them (any agent), exactly as frozen; older plans have neither.
  if (!(plan.mechanic_diagnosis === undefined || plan.mechanic_diagnosis === null || (plan.mode === 'learn' && mechanicDiagnosisDeclaration(plan.mechanic_diagnosis)))) return malformed('campaign plan diagnosis repair-and-record rule')
  if (!(plan.diagnosis_guide === undefined || plan.diagnosis_guide === null || (plan.mode === 'learn' && diagnosisGuideDeclaration(plan.diagnosis_guide)))) return malformed('campaign plan diagnosis guide')
  if (plan.discovery !== undefined && plan.discovery !== null) {
    // Only Learn declares a discovery protocol; the pre-check (v2, v3 with pre-check) models only the reference Actor.
    if (plan.mode !== 'learn' || !discoveryDeclaration(plan.discovery, true) || (preChecked(plan.discovery.protocol) && plan.agent !== 'reference')
      || (plan.discovery.history && plan.discovery.history.policy_hash !== plan.initial_policy_hash)) return malformed('campaign plan discovery protocol')
  }
  // History fireability: only a Learn plan with discovery v3 · agent history or v4 declares it, and its table was frozen from that
  // plan's own frozen history (same summary, episode set and cutoff). The backend recomputes both before Start.
  if (!(plan.explorer_selection === undefined || plan.explorer_selection === null)) {
    const discovery = plan.discovery as DiscoveryDeclaration | null | undefined, history = discovery?.history
    const declared = plan.explorer_selection
    if (plan.mode !== 'learn' || !discovery || !(FIREABILITY_PROTOCOLS as readonly string[]).includes(discovery.protocol) || !history
      || !explorerSelectionDeclaration(declared, true) || !('table' in declared) || declared.table.history_summary_hash !== history.summary_hash
      || declared.table.history_episode_ids_hash !== history.episode_ids_hash || declared.table.record_cutoff !== history.record_cutoff
      || declared.table.verified_episodes !== history.summary.verified_episodes) return malformed('campaign plan history fireability rule')
  }
  return value as CampaignPlan
}
export function validateHistoryCheck(value: unknown, campaignId: string): HistoryCheck {
  if (!object(value) || value.campaign_id !== campaignId || !['CURRENT', 'CHANGED', 'NOT_CHECKED', 'NOT_APPLICABLE'].includes(String(value.status)) || !text(value.message)
    || !(value.record_cutoff === null || count(value.record_cutoff)) || !(value.summary_hash === null || digest(value.summary_hash))) return malformed('agent history check')
  return value as HistoryCheck
}
export const runApi = {
  options: () => request('/run-options', validateRunOptions),
  plan: (campaignId: string) => request(`/campaigns/${encodeURIComponent(campaignId)}/plan`, value => validateCampaignPlan(value, campaignId)),
  historyCheck: (campaignId: string) => request(`/campaigns/${encodeURIComponent(campaignId)}/plan/history-check`, value => validateHistoryCheck(value, campaignId)),
  register: (storeIdentity: string, agent: AgentKind) => request('/agent-registrations', value => validateContract<AgentRegistration>('AgentRegistration', value), { expected_store_identity: storeIdentity, agent }),
  create: (input: PlannedCampaignRequest) => request('/planned-campaigns', value => validateContract<Campaign>('Campaign', value), input),
}
