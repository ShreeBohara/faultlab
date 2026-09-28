import development from '../../audit/development.json' with { type: 'json' }
import type { Campaign } from '../src/generated/contracts'
import type { RunOptions, RunPlan } from '../src/runPlans'

const hash = 'a'.repeat(64)
export const runOptions: RunOptions = {
  schema_version: 'faultlab-run-options/v1', setup_hash: hash, data_store: { identity: 'b'.repeat(64), path: '/local/fixture-store/lab.sqlite3', read_only: false },
  task: { task_definition_id: 'orders.upgrade_then_confirm/v1', label: 'Express upgrade, then confirmation', description: 'Upgrade one authorized synthetic order, then record one truthful confirmation. The tools and fixed scorer cover this task only.', task_text_default: 'Upgrade this order to express shipping, then send its confirmation.' },
  profiles: [{ profile_id: 'offline-v1', label: 'Offline reference smoke', source_mode: 'offline_fixture', arm: 'B1', registration_required: false }, { profile_id: 'live-v1', label: 'Live · configured model', source_mode: 'live', arm: 'B0', registration_required: true }],
  development: { manifest_hash: development.manifest_hash, cases: development.cases.map(item => ({ case_id: item.case_id, label: item.name.replaceAll('_', ' '), description: `Public development fixture: ${item.name.replaceAll('_', ' ')}.`, fixture_id: item.fixture_id, expected_version: item.expected_version, fault_spec: item.fault_spec as RunOptions['development']['cases'][number]['fault_spec'] })) },
  learn: { manifest_hash: development.manifest_hash, search_space: development.development_grammar, selection_limit: 8 },
  compare: { partition: 'promotion', manifest_hash: 'c'.repeat(64), case_count: 6, trials_per_case: 3 },
  agents: (['reference', 'smolagents'] as const).map(agent => ({ agent, label: agent === 'reference' ? 'FaultLab reference actor' : 'smolagents ToolCallingAgent 1.26.0', status: 'READY', reason_code: 'READY', message: 'Reviewed source and adapter match this runtime.', configuration_hash: hash, proposed_registration_id: `${agent}-fixture`, registered: false, registration_id: null, model: 'fixture-model', source_conformance: 'VERIFIED', provider_access: 'not_checked', behavior_verified: false, compare_available: false, accepted_policy_version: null, limitations: ['Provider access and behavior were not tested by this source check.'] })),
  offline: { agent: 'reference', configuration_hash: hash, registration_required: false },
  caps: { model_calls: 6000, tokens: 204000000, dollars: 200, discovery_selections: 8, candidates: 4, input_tokens_per_call: 32000, output_tokens_per_call: 2000 },
  episode_budget: { http_attempts: 18, actor_calls: 8, wait_cycles: 4, ticks: 20, policy_steps: 32, wall_seconds: 90 },
  models: { actor: 'fixture-model', explorer: 'fixture-explorer', mechanic: 'fixture-mechanic' }, provider_calls: 0,
}
export function planned(campaign: Campaign, patch: Partial<RunPlan> = {}): RunPlan {
  const item = runOptions.development.cases[0]
  return { schema_version: 'faultlab-run-plan/v1', campaign_id: campaign.campaign_id, setup_hash: hash, task_definition_id: runOptions.task.task_definition_id, mode: 'baseline', config_profile_id: 'offline-v1', task_text: campaign.task_text, order_id: campaign.order_id, configuration_hash: campaign.configuration_hash, agent_registration_id: 'reference-offline-fixture', agent: 'reference', source_mode: 'offline_fixture', caps: runOptions.caps, episode_budget: runOptions.episode_budget, initial_policy_version: 'policy-v0', initial_policy_hash: hash, selection: { kind: 'development_case', case_id: item.case_id, fixture_id: item.fixture_id, expected_version: item.expected_version, fault_spec: item.fault_spec, scenario_hash: hash, manifest_hash: development.manifest_hash }, plan_hash: hash, ...patch }
}
