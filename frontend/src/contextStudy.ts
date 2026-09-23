import { object, request } from './api'
import { validateContract } from './generated/validate'
import type { TrialResult, Usage } from './generated/contracts'

export type ContextTrial = { case_id: string; actor_context_protocol: string; trial: TrialResult }
export type ContextCaseCounts = Record<string, number>
export type ContextAssessment = {
  decision: string; reason: string
  by_case?: Record<string, Record<string, ContextCaseCounts | boolean | string>>
  incomplete_case_ids?: string[]; comparable_case_ids?: string[]; primary_case_ids?: string[]
  primary_completions?: Record<string, number>; primary_denominator?: number
  violations?: Record<string, number>; regressed_case_ids?: string[]
}
export type ContextStudy = {
  schema_version: 'faultlab-context-study/v1'; study_id: string; campaign_id: string
  status: 'QUEUED' | 'RUNNING' | 'COMPLETED' | 'INCOMPLETE' | 'INTERRUPTED'; stage: string
  decision: 'PENDING' | 'NO_CHANGE' | 'INCOMPLETE' | 'OBSERVED_IMPROVEMENT' | 'REGRESSION'; reason: string
  ordinary_policy_accepted: false; configuration_hash: string; policy_hash: string
  policy_version: string; model: string; arms: string[]
  protocol_by_arm: Record<string, string>
  trial_rows: ContextTrial[]; assessment?: ContextAssessment | null
  action_profile_totals?: Record<string, Record<string, ContextCaseCounts>>
  evidence: Record<string, string>; charged_model_calls: number; usage: Usage
}
const text = (v: unknown): v is string => typeof v === 'string' && v.length > 0
const hash = (v: unknown): v is string => typeof v === 'string' && /^[a-f0-9]{64}$/.test(v)
const malformed = (): never => { throw new Error('Malformed context study or campaign identity. The last verified data is retained.') }

function validateAssessment(value: unknown) {
  if (value === undefined || value === null) return
  if (!object(value) || !text(value.decision) || typeof value.reason !== 'string'
    || (value.by_case !== undefined && !object(value.by_case))) return malformed()
  for (const key of ['incomplete_case_ids', 'comparable_case_ids', 'primary_case_ids', 'regressed_case_ids'] as const) {
    const list = value[key]
    if (list !== undefined && (!Array.isArray(list) || !list.every(item => text(item)))) return malformed()
  }
}

export function validateContextStudy(value: unknown, campaignId: string, studyId?: string): ContextStudy {
  if (!object(value) || value.schema_version !== 'faultlab-context-study/v1' || value.campaign_id !== campaignId
    || !text(value.study_id) || (studyId !== undefined && value.study_id !== studyId)
    || !['QUEUED', 'RUNNING', 'COMPLETED', 'INCOMPLETE', 'INTERRUPTED'].includes(String(value.status))
    || !['PENDING', 'NO_CHANGE', 'INCOMPLETE', 'OBSERVED_IMPROVEMENT', 'REGRESSION'].includes(String(value.decision))
    || !text(value.stage) || typeof value.reason !== 'string' || value.ordinary_policy_accepted !== false
    || !hash(value.configuration_hash) || !hash(value.policy_hash) || !text(value.policy_version)
    || !text(value.model) || !Array.isArray(value.arms) || !object(value.protocol_by_arm)
    || !Array.isArray(value.trial_rows) || !object(value.evidence)
    || !Number.isInteger(value.charged_model_calls) || (value.charged_model_calls as number) < 0) return malformed()
  const arms = value.arms.map(arm => text(arm) ? arm : malformed()) as string[]
  const protocols = value.protocol_by_arm as Record<string, unknown>
  // Both arms must carry the same unchanged policy. Only the declared per-turn
  // context protocol may differ, and every protocol must be distinct.
  if (arms.length !== 2 || new Set(arms).size !== 2
    || Object.keys(protocols).length !== 2 || !arms.every(arm => text(protocols[arm]))
    || new Set(arms.map(arm => protocols[arm])).size !== 2) return malformed()
  const episodes = new Set<string>()
  const trial_rows: ContextTrial[] = value.trial_rows.map(row => {
    if (!object(row) || !text(row.case_id) || !text(row.actor_context_protocol)) return malformed()
    const trial = validateContract<TrialResult>('TrialResult', row.trial)
    if (episodes.has(trial.episode_id) || trial.policy_hash !== value.policy_hash
      || !arms.includes(trial.arm) || protocols[trial.arm] !== row.actor_context_protocol) return malformed()
    episodes.add(trial.episode_id)
    return { case_id: row.case_id, actor_context_protocol: row.actor_context_protocol, trial }
  })
  for (const [episode, source] of Object.entries(value.evidence)) {
    if (!episodes.has(episode)
      || !['local_only', 'weave_pending', 'weave_verified'].includes(String(source))) return malformed()
  }
  validateAssessment(value.assessment)
  if (value.decision === 'OBSERVED_IMPROVEMENT' || value.decision === 'REGRESSION') {
    const assessment = value.assessment
    if (value.status !== 'COMPLETED' || !object(assessment)
      || assessment.decision !== value.decision) return malformed()
  }
  if (value.decision === 'OBSERVED_IMPROVEMENT') {
    const assessment = value.assessment as ContextAssessment
    const primary = assessment.primary_case_ids ?? []
    const completions = assessment.primary_completions ?? {}
    const changed = arms.find(arm => arm !== 'B0') ?? ''
    // A claimed gain needs a strict pooled advantage, no violation in the
    // changed arm and no case regression. This guard only rejects a projection
    // that contradicts itself; the backend owns the predeclared predicate.
    if (!primary.length || (assessment.regressed_case_ids ?? []).length
      || (assessment.violations?.[changed] ?? 0) > 0
      || !((completions[changed] ?? 0) > (completions.B0 ?? 0))) return malformed()
    for (const { trial } of trial_rows) {
      if (trial.arm !== changed) continue
      if (trial.outcome === 'VIOLATION' || trial.failed_checks?.length) return malformed()
    }
  }
  const usage = validateContract<Usage>('Usage', value.usage)
  return { ...value, arms, trial_rows, usage } as ContextStudy
}

export function validateContextStudies(value: unknown, campaignId: string): ContextStudy[] {
  if (!Array.isArray(value)) return malformed()
  const studies = value.map(item => validateContextStudy(item, campaignId))
  if (new Set(studies.map(item => item.study_id)).size !== studies.length) return malformed()
  return studies
}

export const getContextStudies = (campaignId: string) =>
  request(`/campaigns/${encodeURIComponent(campaignId)}/context-studies`, value => validateContextStudies(value, campaignId))

// Observed counts grouped by case and arm. They are not a substitute for the
// study's predeclared decision rule and they never imply an accepted policy.
export function contextGroups(rows: ContextTrial[]) {
  const groups = new Map<string, { caseId: string; arm: TrialResult['arm']; protocol: string; trials: TrialResult[] }>()
  for (const { case_id, actor_context_protocol, trial } of rows) {
    const key = JSON.stringify([case_id, trial.arm, actor_context_protocol])
    if (!groups.has(key)) groups.set(key, { caseId: case_id, arm: trial.arm, protocol: actor_context_protocol, trials: [] })
    groups.get(key)!.trials.push(trial)
  }
  return [...groups.values()].map(group => ({ ...group,
    attempted: group.trials.length,
    valid: group.trials.filter(t => t.lifecycle === 'COMPLETED' && t.outcome !== null && t.outcome !== 'LAB_ERROR' && (!t.fault_scheduled || t.fault_triggered)).length,
    completed: group.trials.filter(t => t.lifecycle === 'COMPLETED' && t.outcome === 'COMPLETED').length,
    violations: group.trials.filter(t => t.lifecycle === 'COMPLETED' && t.outcome === 'VIOLATION').length,
    unresolved: group.trials.filter(t => t.lifecycle === 'COMPLETED' && t.outcome === 'SAFE_UNRESOLVED').length,
    rejected: group.trials.filter(t => t.lifecycle === 'COMPLETED' && t.outcome === 'CORRECTLY_REJECTED').length,
    scheduled: group.trials.filter(t => t.fault_scheduled).length,
    triggered: group.trials.filter(t => t.fault_scheduled && t.fault_triggered).length,
  }))
}
