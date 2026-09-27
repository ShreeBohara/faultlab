import { object, request } from './api'
import { validateContract } from './generated/validate'
import type { TrialResult, Usage } from './generated/contracts'

export type CompletionTrial = { stage: string; case_id: string; trial: TrialResult }
export type CompletionAssessment = { decision: string; reason: string; by_case?: Record<string, unknown> }
export type CompletionCandidate = { proposal_ref: string; policy_version?: string; policy_hash?: string; decision: string; reason?: string; source_assessment?: CompletionAssessment | null }
export type CompletionStudy = {
  schema_version: 'faultlab-completion-study/v1'; study_id: string; campaign_id: string
  status: 'QUEUED' | 'RUNNING' | 'COMPLETED' | 'INCOMPLETE' | 'INTERRUPTED'; stage: string
  decision: 'PENDING' | 'NO_CHANGE' | 'INCOMPLETE' | 'OBSERVED_IMPROVEMENT'; reason: string
  ordinary_policy_accepted: false; configuration_hash: string; incumbent_hash: string; model: string
  selected_candidate_version?: string; selected_candidate_hash?: string
  replay_of?: string | null; replay_policy_hash?: string | null
  trial_rows: CompletionTrial[]; candidates: CompletionCandidate[]
  validation_assessment?: CompletionAssessment | null
  evidence: Record<string, string>; charged_model_calls: number; usage: Usage
}
const text = (v: unknown): v is string => typeof v === 'string' && v.length > 0
const hash = (v: unknown): v is string => typeof v === 'string' && /^[a-f0-9]{64}$/.test(v)
const malformed = (): never => { throw new Error('Malformed completion study or campaign identity. The last verified data is retained.') }
function validateAssessment(value: unknown) {
  if (value !== undefined && value !== null && (!object(value) || !text(value.decision)
    || typeof value.reason !== 'string' || (value.by_case !== undefined && !object(value.by_case)))) return malformed()
}

export function validateCompletionStudy(value: unknown, campaignId: string, studyId?: string): CompletionStudy {
  if (!object(value) || value.schema_version !== 'faultlab-completion-study/v1' || value.campaign_id !== campaignId
    || !text(value.study_id) || (studyId !== undefined && value.study_id !== studyId)
    || !['QUEUED', 'RUNNING', 'COMPLETED', 'INCOMPLETE', 'INTERRUPTED'].includes(String(value.status))
    || !['PENDING', 'NO_CHANGE', 'INCOMPLETE', 'OBSERVED_IMPROVEMENT'].includes(String(value.decision))
    || !text(value.stage) || typeof value.reason !== 'string' || value.ordinary_policy_accepted !== false
    || !hash(value.configuration_hash) || !hash(value.incumbent_hash) || !text(value.model)
    || !Array.isArray(value.trial_rows) || !Array.isArray(value.candidates) || !object(value.evidence)
    || !Number.isInteger(value.charged_model_calls) || (value.charged_model_calls as number) < 0) return malformed()
  const candidates: CompletionCandidate[] = value.candidates.map(item => {
    if (!object(item) || !text(item.proposal_ref) || !text(item.decision)
      || (item.policy_version !== undefined && !text(item.policy_version))
      || (item.policy_hash !== undefined && !hash(item.policy_hash))
      || (item.reason !== undefined && typeof item.reason !== 'string')) return malformed()
    validateAssessment(item.source_assessment)
    return item as CompletionCandidate
  })
  // A replay study proposes nothing, so its candidate-arm trials carry the replayed
  // policy's hash and its candidates list is empty. Ordinary studies are unaffected.
  const replayHash = text(value.replay_policy_hash) ? String(value.replay_policy_hash) : undefined
  if ((value.replay_of !== undefined && value.replay_of !== null && !text(value.replay_of))
    || (value.replay_policy_hash !== undefined && value.replay_policy_hash !== null && !hash(value.replay_policy_hash))
    || (replayHash !== undefined) !== (text(value.replay_of) as boolean)) return malformed()
  const candidateHashes = new Set([
    ...candidates.flatMap(item => item.policy_hash ? [item.policy_hash] : []),
    ...(replayHash ? [replayHash] : []),
  ])
  if (replayHash && (candidates.length > 0 || replayHash === value.incumbent_hash)) return malformed()
  const episodes = new Set<string>()
  const trial_rows: CompletionTrial[] = value.trial_rows.map(row => {
    if (!object(row) || !text(row.stage) || !text(row.case_id)) return malformed()
    const trial = validateContract<TrialResult>('TrialResult', row.trial)
    if (episodes.has(trial.episode_id) || (trial.arm === 'B0' ? trial.policy_hash !== value.incumbent_hash
      : trial.arm !== 'L' || !candidateHashes.has(trial.policy_hash))) return malformed()
    episodes.add(trial.episode_id)
    return { stage: row.stage, case_id: row.case_id, trial }
  })
  for (const [episode, source] of Object.entries(value.evidence)) {
    if (!episodes.has(episode) || !['local_only', 'weave_verified'].includes(String(source))) return malformed()
  }
  validateAssessment(value.validation_assessment)
  if ((value.selected_candidate_version !== undefined && !text(value.selected_candidate_version))
    || (value.selected_candidate_hash !== undefined && !hash(value.selected_candidate_hash))) return malformed()
  if (value.decision === 'OBSERVED_IMPROVEMENT') {
    const selected = candidates.filter(candidate => candidate.policy_version === value.selected_candidate_version
      && candidate.policy_hash === value.selected_candidate_hash)
    const validation = trial_rows.filter(row => row.stage === 'validation').map(row => row.trial)
    // A replay identifies its policy by replay_of/replay_policy_hash; an ordinary study
    // must still name exactly one selected candidate.
    const identified = replayHash ? text(value.replay_of) && replayHash !== value.incumbent_hash
      : text(value.selected_candidate_version) && hash(value.selected_candidate_hash)
        && value.selected_candidate_hash !== value.incumbent_hash && selected.length === 1
    const validatedPolicyHash = replayHash ?? value.selected_candidate_hash
    if (value.status !== 'COMPLETED' || !object(value.validation_assessment)
      || value.validation_assessment.decision !== 'OBSERVED_IMPROVEMENT' || !identified
      || !validation.some(trial => trial.arm === 'B0') || !validation.some(trial => trial.arm === 'L')) return malformed()
    for (const trial of validation) {
      if (trial.lifecycle !== 'COMPLETED' || trial.outcome === null || trial.outcome === 'LAB_ERROR'
        || (trial.fault_scheduled && !trial.fault_triggered) || value.evidence[trial.episode_id] !== 'weave_verified'
        || (trial.arm === 'L' && (trial.policy_hash !== validatedPolicyHash || trial.outcome === 'VIOLATION' || trial.failed_checks?.length))) return malformed()
    }
    // The backend owns the fixed per-case improvement predicate. This guard
    // only prevents a contradictory or unfinished projection claiming a gain.
  }
  const usage = validateContract<Usage>('Usage', value.usage)
  return { ...value, candidates, trial_rows, usage } as CompletionStudy
}

export function validateCompletionStudies(value: unknown, campaignId: string): CompletionStudy[] {
  if (!Array.isArray(value)) return malformed()
  const studies = value.map(item => validateCompletionStudy(item, campaignId))
  if (new Set(studies.map(item => item.study_id)).size !== studies.length) return malformed()
  return studies
}
export const getCompletionStudies = (campaignId: string) => request(`/campaigns/${encodeURIComponent(campaignId)}/completion-studies`, value => validateCompletionStudies(value, campaignId))

// Observed counts are grouped by stage, case and exact policy. They are not a
// substitute for the backend's predeclared completion or promotion predicates.
export function completionGroups(rows: CompletionTrial[]) {
  const groups = new Map<string, { stage: string; caseId: string; arm: TrialResult['arm']; policyHash: string; trials: TrialResult[] }>()
  for (const { stage, case_id, trial } of rows) {
    const key = JSON.stringify([stage, case_id, trial.arm, trial.policy_hash])
    if (!groups.has(key)) groups.set(key, { stage, caseId: case_id, arm: trial.arm, policyHash: trial.policy_hash, trials: [] })
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
