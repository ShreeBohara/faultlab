import { ApiError, object, request, type ConfigStatus } from './api'
import type { EpisodeBudget, FaultSpec, RegressionExecution, TrialResult } from './generated/contracts'
import { validateContract, validateList } from './generated/validate'
import { taskTextProblem } from './taskText'

export const MAX_IMPORT_BYTES = 24 * 1024 * 1024
export type ImportTarget = { agent_registration_id: string; configuration_hash: string; model: string; agent: string }
export type ImportedBundleSummary = {
  import_id: string; bundle_id: string; manifest_hash: string; imported_at: string
  artifact_kind: 'incident_fixture' | 'candidate_comparison' | 'accepted_policy_bundle'
  policy: { version: string; hash: string; decision: string }; runnable: boolean; runnable_reason: string | null
  source: { configuration_hash: string; model: string; agent_registration_id: string | null; agent_registration_malformed?: boolean; source_mode: string | null; source_modes?: string[]; evidence_verification: 'NO_LOCAL_VERIFICATION' }
}
export type ExecutionTask = { task_text: string; order_id: string; origin: 'bundled' | 'default' }
export type ImportLimits = { required_trials: 3; episode_budget: EpisodeBudget; reserved_actor_turns: number; transport_retry_allowance: number; max_model_requests: number }
export type ImportedBundle = ImportedBundleSummary & {
  historical: { trials: TrialResult[]; evidence_available: boolean; label: string; recording: Record<string, unknown> | null }
  recipe: { source: FaultSpec; retained: FaultSpec | null; fixture_id: string; target_invariant: string }
  execution_task: ExecutionTask | null
  limits: ImportLimits
  targets: (ImportTarget & { compatible: boolean; reason: string | null })[]
  data_store: NonNullable<ConfigStatus['data_store']>; provider_calls: 0
}
export type OwnerCharges = { model_calls: number; reserved_model_calls: number; measured_input_tokens: number; measured_output_tokens: number; actual_cost_dollars: number | null; charged_dollar_upper_bound: number | null; request_ceiling: number }
export type ImportedExecution = { import_id: string; request_id: string; owner_campaign_id: string; regression_id: string; target: ImportTarget; execution: RegressionExecution; assertions: Record<string, unknown> | null; error: Record<string, unknown> | null; trial_errors?: Record<string, unknown> | null; owner_charges?: OwnerCharges | null; source_evidence_verified_locally: false }
export type ImportPage<T> = { items: T[]; next_before: number | null; has_more: boolean; skipped?: number }
export type UploadedImport = { bundle: ImportedBundle; status: 'created' | 'existing' | 'unknown' }
export type ImportExecutionRequest = { expected_store_identity: string; expected_manifest_hash: string; expected_target_configuration_hash: string; agent_registration_id: string; request_id: string; execution_profile_id: 'sandbox-v1'; execute_live: true }
export type PendingImportRequest = { import_id: string; request: ImportExecutionRequest }
export type CancelledImportRequest = { cancelled: true; import_id: string; request_id: string }
export type ImportOwner = { imported_owner: false } | { imported_owner: true; import_id: string; request_id: string; execution_id: string; target: ImportTarget; reserved_actor_turns?: number; request_ceiling?: number }
export type ImportProvenance = { imported: false } | { imported: true; import_id: string; source_policy_version: string; source_policy_hash: string; historical_decision: string; local_acceptance: false }
const text = (value: unknown): value is string => typeof value === 'string' && value.trim().length > 0
const digest = (value: unknown): value is string => typeof value === 'string' && /^[a-f0-9]{64}$/.test(value)
const nullableText = (value: unknown) => value === null || text(value)
const count = (value: unknown): value is number => Number.isSafeInteger(value) && (value as number) >= 0
const nullableNumber = (value: unknown) => value === null || typeof value === 'number' && Number.isFinite(value) && value >= 0
const ID = /^[A-Za-z0-9][A-Za-z0-9_.:-]*$/
const invalid = (name: string): never => { throw new Error(`Malformed imported ${name} response. The response could not be verified. Check the saved request before trying again.`) }
const targetValid = (value: unknown): value is ImportTarget => object(value) && text(value.agent_registration_id) && digest(value.configuration_hash) && text(value.model) && text(value.agent)

export function validateImportSummary(value: unknown): ImportedBundleSummary {
  if (!object(value) || !['import_id', 'bundle_id', 'imported_at'].every(key => text(value[key])) || !digest(value.manifest_hash)
    || !['incident_fixture', 'candidate_comparison', 'accepted_policy_bundle'].includes(String(value.artifact_kind))
    || !object(value.policy) || !text(value.policy.version) || !digest(value.policy.hash) || !text(value.policy.decision)
    || typeof value.runnable !== 'boolean' || !nullableText(value.runnable_reason)
    || !object(value.source) || !digest(value.source.configuration_hash) || typeof value.source.model !== 'string'
    || !nullableText(value.source.agent_registration_id) || !nullableText(value.source.source_mode) || value.source.evidence_verification !== 'NO_LOCAL_VERIFICATION'
    || !(value.source.source_modes === undefined || Array.isArray(value.source.source_modes) && value.source.source_modes.every(text))) return invalid('bundle summary')
  return value as ImportedBundleSummary
}
export function validateImport(value: unknown, expectedId?: string): ImportedBundle {
  const summary = validateImportSummary(value)
  if (expectedId && summary.import_id !== expectedId) return invalid('bundle identity')
  if (!object(value) || !object(value.historical) || typeof value.historical.evidence_available !== 'boolean' || !text(value.historical.label)
    || !(value.historical.recording === null || object(value.historical.recording))
    || !object(value.recipe) || !text(value.recipe.fixture_id) || !/^C[1-8]$/.test(String(value.recipe.target_invariant))
    || !object(value.limits) || value.limits.required_trials !== 3 || value.provider_calls !== 0
    || !['reserved_actor_turns', 'transport_retry_allowance', 'max_model_requests'].every(key => count((value.limits as Record<string, unknown>)[key]))
    || value.limits.max_model_requests !== (value.limits.reserved_actor_turns as number) + (value.limits.transport_retry_allowance as number)
    || !(value.execution_task === null || validTask(value.execution_task)) || value.runnable === true && value.execution_task === null
    || !object(value.data_store) || !text(value.data_store.identity) || !text(value.data_store.path) || typeof value.data_store.read_only !== 'boolean'
    || !Array.isArray(value.targets) || value.targets.some(target => !targetValid(target) || typeof (target as Record<string, unknown>).compatible !== 'boolean' || !nullableText((target as Record<string, unknown>).reason))) return invalid('bundle review')
  validateList<TrialResult>('TrialResult', value.historical.trials)
  validateContract('FaultSpec', value.recipe.source)
  if (value.recipe.retained !== null) validateContract('FaultSpec', value.recipe.retained)
  validateContract('EpisodeBudget', value.limits.episode_budget)
  if (new Set(value.targets.map(target => (target as ImportTarget).agent_registration_id)).size !== value.targets.length) return invalid('target identities')
  return value as ImportedBundle
}
function validTask(value: unknown): value is ExecutionTask {
  // The backend's rule, counted in the same unit (code points) with the same visibility test.
  return object(value) && taskTextProblem(value.task_text) === null
    && typeof value.order_id === 'string' && value.order_id.length <= 128 && ID.test(value.order_id) && ['bundled', 'default'].includes(String(value.origin))
}
function validCharges(value: unknown): value is OwnerCharges {
  return object(value) && ['model_calls', 'reserved_model_calls', 'measured_input_tokens', 'measured_output_tokens', 'request_ceiling'].every(key => count(value[key]))
    && nullableNumber(value.actual_cost_dollars) && nullableNumber(value.charged_dollar_upper_bound)
}
export function validateImportExecution(value: unknown, expectedImport: string, expectedRequest?: string): ImportedExecution {
  if (!object(value) || value.import_id !== expectedImport || !text(value.request_id) || (expectedRequest && value.request_id !== expectedRequest)
    || !(value.owner_charges === undefined || value.owner_charges === null || validCharges(value.owner_charges))
    || !text(value.owner_campaign_id) || !text(value.regression_id) || !targetValid(value.target)
    || !(value.assertions === null || object(value.assertions)) || !(value.error === null || object(value.error)) || !(value.trial_errors === undefined || value.trial_errors === null || object(value.trial_errors)) || value.source_evidence_verified_locally !== false) return invalid('execution identity')
  const execution = validateContract<RegressionExecution>('RegressionExecution', value.execution)
  if (execution.registration_id !== value.target.agent_registration_id || execution.configuration_hash !== value.target.configuration_hash || execution.mode !== 'FRESH_SANDBOX') return invalid('execution target')
  return value as ImportedExecution
}
export function matchingImportExecution(value: ImportedExecution, bundle: ImportedBundle): ImportedExecution {
  if (value.import_id !== bundle.import_id || value.execution.bundle_id !== bundle.bundle_id || value.execution.manifest_hash !== bundle.manifest_hash || value.execution.policy_hash !== bundle.policy.hash) return invalid('execution bundle identity')
  return value
}
export function validateImportPage<T>(value: unknown, decode: (item: unknown) => T, identity: (item: T) => string, before?: number): ImportPage<T> {
  if (!object(value) || !Array.isArray(value.items) || typeof value.has_more !== 'boolean' || !(value.next_before === null || Number.isSafeInteger(value.next_before) && (value.next_before as number) > 0)) return invalid('history')
  const items = value.items.map(decode)
  if (new Set(items.map(identity)).size !== items.length || value.has_more !== (value.next_before !== null) || value.has_more && (!items.length || before !== undefined && (value.next_before as number) >= before)) return invalid('history cursor')
  return { items, next_before: value.next_before as number | null, has_more: value.has_more }
}
/** Saved-import list: one malformed summary is skipped and counted, never allowed to hide the others. */
export function validateImportListPage(value: unknown, before?: number): ImportPage<ImportedBundleSummary> {
  if (!object(value) || !Array.isArray(value.items) || typeof value.has_more !== 'boolean' || !(value.next_before === null || Number.isSafeInteger(value.next_before) && (value.next_before as number) > 0)) return invalid('history')
  const items: ImportedBundleSummary[] = []; let skipped = 0
  for (const item of value.items) { try { items.push(validateImportSummary(item)) } catch { skipped += 1 } }
  if (new Set(items.map(item => item.import_id)).size !== items.length || value.has_more !== (value.next_before !== null) || value.has_more && (!value.items.length || before !== undefined && (value.next_before as number) >= before)) return invalid('history cursor')
  return { items, next_before: value.next_before as number | null, has_more: value.has_more, skipped }
}
export function validateImportProvenance(value: unknown): ImportProvenance {
  if (!object(value)) return invalid('policy provenance')
  if (value.imported === false) return { imported: false }
  if (value.imported !== true || !text(value.import_id) || !text(value.source_policy_version) || !digest(value.source_policy_hash) || !text(value.historical_decision) || value.local_acceptance !== false) return invalid('policy provenance')
  return value as ImportProvenance
}
export function validateImportOwner(value: unknown): ImportOwner {
  if (!object(value)) return invalid('accounting owner')
  if (value.imported_owner === false) return { imported_owner: false }
  if (value.imported_owner !== true || !text(value.import_id) || !text(value.request_id) || !text(value.execution_id) || !targetValid(value.target)
    || !(value.reserved_actor_turns === undefined || count(value.reserved_actor_turns)) || !(value.request_ceiling === undefined || count(value.request_ceiling))) return invalid('accounting owner')
  return value as ImportOwner
}
export function validateImportLookup(value: unknown, importId: string, requestId: string): ImportedExecution | CancelledImportRequest {
  if (object(value) && value.cancelled === true) {
    if (value.import_id !== importId || value.request_id !== requestId) return invalid('cancelled request identity')
    return value as CancelledImportRequest
  }
  return validateImportExecution(value, importId, requestId)
}
export function validateImportCancellation(value: unknown, importId: string, requestId: string): CancelledImportRequest | { cancelled: false; execution: ImportedExecution } {
  if (object(value) && value.cancelled === false) return { cancelled: false, execution: validateImportExecution(value.execution, importId, requestId) }
  const result = validateImportLookup(value, importId, requestId)
  if ('cancelled' in result) return result
  return invalid('request cancellation')
}
export function validatePendingImportRequest(value: unknown): PendingImportRequest {
  if (!object(value) || !text(value.import_id) || !object(value.request)) return invalid('pending request')
  const body = value.request
  if (!text(body.expected_store_identity) || !digest(body.expected_manifest_hash) || !digest(body.expected_target_configuration_hash) || !text(body.agent_registration_id) || !text(body.request_id) || body.execution_profile_id !== 'sandbox-v1' || body.execute_live !== true) return invalid('pending request')
  return value as PendingImportRequest
}
export function importFileError(file: File): string | null {
  if (/\.json$/i.test(file.name)) return 'Campaign recordings are JSON evidence archives. Import a regression bundle ZIP exported from Portable regression.'
  if (!/\.zip$/i.test(file.name)) return 'Choose an exported regression bundle ZIP.'
  if (!file.size) return 'The selected ZIP is empty.'
  if (file.size > MAX_IMPORT_BYTES) return 'Regression bundle ZIPs must be 24 MiB or smaller.'
  return null
}
async function upload(file: File, storeIdentity: string): Promise<UploadedImport> {
  const error = importFileError(file)
  if (error) throw new Error(error)
  const controller = new AbortController(); const timer = window.setTimeout(() => controller.abort(), 30000)
  try {
    const response = await fetch('/api/bundle-imports', { method: 'POST', headers: { 'Content-Type': 'application/zip', 'X-FaultLab-Store-Identity': storeIdentity }, body: file, signal: controller.signal })
    const value: unknown = await response.json().catch(() => null)
    if (!response.ok) throw new ApiError(response.status, object(value) && object(value.error) && typeof value.error.message === 'string' ? value.error.message : `The backend returned HTTP ${response.status}.`)
    const status = object(value) && (value.import_status === 'created' || value.import_status === 'existing') ? value.import_status : 'unknown'
    return { bundle: validateImport(value), status }
  } catch (reason) {
    if (reason instanceof Error && reason.name === 'AbortError') throw new Error('The import response timed out. Refresh imported bundles before trying the same ZIP again; importing never starts execution.')
    throw reason
  } finally { window.clearTimeout(timer) }
}
const segment = encodeURIComponent
const query = (before?: number) => `?limit=20${before === undefined ? '' : `&before=${before}`}`
export const importApi = {
  upload,
  list: (before?: number) => request(`/bundle-imports${query(before)}`, value => validateImportListPage(value, before)),
  detail: (id: string) => request(`/bundle-imports/${segment(id)}`, value => validateImport(value, id)),
  executions: (id: string, before?: number) => request(`/bundle-imports/${segment(id)}/executions${query(before)}`, value => validateImportPage(value, item => validateImportExecution(item, id), item => item.execution.execution_id, before)),
  execute: (id: string, body: ImportExecutionRequest) => request(`/bundle-imports/${segment(id)}/execute`, value => validateImportExecution(value, id, body.request_id), body),
  lookup: (id: string, requestId: string) => request(`/bundle-imports/${segment(id)}/requests/${segment(requestId)}`, value => validateImportLookup(value, id, requestId)),
  cancel: (id: string, body: ImportExecutionRequest) => request(`/bundle-imports/${segment(id)}/requests/${segment(body.request_id)}/cancel`, value => validateImportCancellation(value, id, body.request_id), body),
  provenance: (policyId: string) => request(`/policies/${segment(policyId)}/import-provenance`, validateImportProvenance),
  owner: (campaignId: string) => request(`/campaigns/${segment(campaignId)}/import-owner`, validateImportOwner),
}
