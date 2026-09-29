import { object, request } from './api'
import type { AgentRegistration, Campaign, CampaignBudget, EpisodeBudget, FaultSpec } from './generated/contracts'
import { validateContract } from './generated/validate'

export const TASK_DEFINITION = 'orders.upgrade_then_confirm/v1' as const
export type AgentKind = 'reference' | 'smolagents'
export type RunMode = 'baseline' | 'learn' | 'compare'
export type RunProfile = 'offline-v1' | 'live-v1'
export type RunCaps = Required<CampaignBudget>
export type SearchSpace = { maximum_primitives: number; kinds: string[]; occurrence: number[]; f1_milliseconds: number[]; f2_ticks: number[]; f3_versions: number[]; f4_count: number[]; preflight_required: boolean }
export type DevelopmentCase = { case_id: string; label: string; description: string; fixture_id: string; expected_version: number; fault_spec: FaultSpec }
export type DiscoveryProtocolId = 'faultlab-discovery/v1' | 'faultlab-discovery/v2-reachability'
export type CallerModel = { caller_id: string; agent: 'reference'; max_business_calls: number; adapter_attempts: number; client_timeout_seconds: number; wait_action: boolean; ticks_per_http_attempt: number; http_attempts: number; ticks: number; polling: string; unknown_status_checks?: number; resends_failed_writes?: boolean; validated_against: string; facts: string[] }
/** explorer_transport_retries_max: one charged retry per Explorer request that got no answer; not a request itself. Absent or null in plans saved before it existed (none declared). */
export type DiscoveryDeclaration = { protocol: DiscoveryProtocolId; schedule_identity: string; slots: number; explorer_requests_max: number; explorer_transport_retries_max?: number | null; actor_episodes_max: number; replans_per_slot: number; dispatch_rule: string; pre_check: null | { labeller: string; caller_model: CallerModel } }
/** The shared model-request retry rule frozen into a plan (backend app/agents/transport_retry.py). */
export type TransportRetryDeclaration = { protocol: 'faultlab-transport-retry/v1'; retries_per_request: 1; roles: ['actor', 'explorer', 'mechanic']; retryable: ['CONNECTION_ERROR', 'REQUEST_TIMEOUT', 'HTTP_503']; service_unavailable_delay_seconds: 1; actor_retries_per_episode_max: number; rule: string }
export type DiscoveryOption = { protocol_id: DiscoveryProtocolId; default: boolean; label: string; description: string; supported_agents: AgentKind[]; unsupported_reason?: string; declaration: DiscoveryDeclaration }
export type RunAgent = { agent: AgentKind; label: string; status: 'READY' | 'UNAVAILABLE'; reason_code: string; message: string; configuration_hash: string | null; proposed_registration_id: string | null; registered: boolean; registration_id: string | null; model: string; source_conformance: 'VERIFIED' | 'UNAVAILABLE'; provider_access: 'not_checked'; behavior_verified: false; compare_available: boolean; accepted_policy_version: string | null; limitations: string[] }
export type RunOptions = {
  schema_version: 'faultlab-run-options/v1'; setup_hash: string; data_store: { identity: string; path: string; read_only: boolean }
  task: { task_definition_id: typeof TASK_DEFINITION; label: string; description: string; task_text_default: string }
  profiles: { profile_id: RunProfile; label: string; source_mode: 'offline_fixture' | 'live'; arm: 'B1' | 'B0'; registration_required: boolean }[]
  development: { manifest_hash: string; cases: DevelopmentCase[] }
  learn: { manifest_hash: string; search_space: SearchSpace; selection_limit: number; discovery_protocols?: DiscoveryOption[] }
  compare: { partition: 'promotion'; manifest_hash: string; case_count: number; trials_per_case: number }
  agents: RunAgent[]; offline: { agent: 'reference'; configuration_hash: string; registration_required: false }
  caps: RunCaps; episode_budget: Required<EpisodeBudget>; models: { actor: string; explorer: string; mechanic: string }; provider_calls: 0
}
export type PlanSelection =
  | { kind: 'development_case'; case_id: string; fixture_id: string; expected_version: number; fault_spec: FaultSpec; scenario_hash: string; manifest_hash: string }
  | { kind: 'development_search'; manifest_hash: string; search_space: SearchSpace }
  | { kind: 'protected_comparison'; partition: 'promotion'; manifest_hash: string; case_count: number; trials_per_case: number }
export type RunPlan = { schema_version: 'faultlab-run-plan/v1'; campaign_id: string; setup_hash: string; task_definition_id: typeof TASK_DEFINITION; mode: RunMode; config_profile_id: RunProfile; task_text: string; order_id: string; configuration_hash: string; agent_registration_id: string; agent: AgentKind; source_mode: 'live' | 'offline_fixture'; caps: RunCaps; episode_budget: Required<EpisodeBudget>; initial_policy_version: string; initial_policy_hash: string; selection: PlanSelection; discovery?: DiscoveryDeclaration | null; transport_retry?: TransportRetryDeclaration | null; plan_hash: string }
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
const DISCOVERY_PROTOCOLS = ['faultlab-discovery/v1', 'faultlab-discovery/v2-reachability']
/** A declared discovery block, with the same coherence rules the backend enforces. */
export function discoveryDeclaration(value: unknown): value is DiscoveryDeclaration {
  if (!object(value) || !DISCOVERY_PROTOCOLS.includes(String(value.protocol)) || !text(value.schedule_identity) || !text(value.dispatch_rule)
    || !['slots', 'explorer_requests_max', 'actor_episodes_max'].every(key => positive(value[key])) || ![0, 1].includes(value.replans_per_slot as number)) return false
  const v2 = value.protocol === 'faultlab-discovery/v2-reachability', slots = value.slots as number
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
/** The declared transport retry rule, exactly as the backend freezes it. */
export function transportRetry(value: unknown, actorCalls: number): value is TransportRetryDeclaration {
  return object(value) && value.protocol === 'faultlab-transport-retry/v1' && value.retries_per_request === 1
    && same(value.roles, ['actor', 'explorer', 'mechanic']) && same(value.retryable, ['CONNECTION_ERROR', 'REQUEST_TIMEOUT', 'HTTP_503'])
    && value.service_unavailable_delay_seconds === 1 && value.actor_retries_per_episode_max === actorCalls && text(value.rule)
}
function discoveryOptions(value: unknown): boolean {
  if (!Array.isArray(value) || !value.length) return false
  const ids = new Set<string>()
  for (const option of value) {
    if (!object(option) || !DISCOVERY_PROTOCOLS.includes(String(option.protocol_id)) || ids.has(String(option.protocol_id)) || typeof option.default !== 'boolean'
      || !text(option.label) || !text(option.description) || !Array.isArray(option.supported_agents) || !option.supported_agents.every(agent => ['reference', 'smolagents'].includes(String(agent)))
      || !(option.unsupported_reason === undefined || text(option.unsupported_reason)) || !discoveryDeclaration(option.declaration) || option.declaration.protocol !== option.protocol_id) return false
    if (option.protocol_id === 'faultlab-discovery/v2-reachability' && (option.default || option.supported_agents.includes('smolagents'))) return false
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
  if (!Array.isArray(value.agents) || value.agents.length !== 2 || new Set(value.agents.map(a => object(a) && a.agent)).size !== 2) return malformed('reviewed agents')
  for (const agent of value.agents) {
    if (!object(agent) || !['reference', 'smolagents'].includes(String(agent.agent)) || !text(agent.label) || !['READY', 'UNAVAILABLE'].includes(String(agent.status)) || !text(agent.reason_code) || !text(agent.message)
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
    || !['baseline', 'learn', 'compare'].includes(String(plan.mode)) || !['reference', 'smolagents'].includes(String(plan.agent)) || !object(plan.selection)) return malformed('campaign plan')
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
  if (!(plan.transport_retry === undefined || plan.transport_retry === null || transportRetry(plan.transport_retry, (plan.episode_budget as Required<EpisodeBudget>).actor_calls))) return malformed('campaign plan transport retry rule')
  if (plan.discovery !== undefined && plan.discovery !== null) {
    // Only Learn declares a discovery protocol; v2 pre-checks only the reference Actor.
    if (plan.mode !== 'learn' || !discoveryDeclaration(plan.discovery) || (plan.discovery.protocol === 'faultlab-discovery/v2-reachability' && plan.agent !== 'reference')) return malformed('campaign plan discovery protocol')
  }
  return value as CampaignPlan
}
export const runApi = {
  options: () => request('/run-options', validateRunOptions),
  plan: (campaignId: string) => request(`/campaigns/${encodeURIComponent(campaignId)}/plan`, value => validateCampaignPlan(value, campaignId)),
  register: (storeIdentity: string, agent: AgentKind) => request('/agent-registrations', value => validateContract<AgentRegistration>('AgentRegistration', value), { expected_store_identity: storeIdentity, agent }),
  create: (input: PlannedCampaignRequest) => request('/planned-campaigns', value => validateContract<Campaign>('Campaign', value), input),
}
