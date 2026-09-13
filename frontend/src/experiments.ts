import { object, request } from './api'
import { validateContract, validateList } from './generated/validate'
import type { Counterexample, FaultSpec, ReductionResult, DiagnosticResult, InterventionExperiment, ChallengeResult } from './generated/contracts'
export type ExperimentRecord = { counterexample: Counterexample; source_recipe: FaultSpec | null; retained_recipe: FaultSpec | null; reduction: ReductionResult | null; diagnostics: DiagnosticResult[]; interventions: InterventionExperiment[]; challenges: ChallengeResult[] }
export type EvidenceReference = { episode_id: string; source: string; root_call_id: string | null; child_call_ids: string[]; source_project: string | null; root_call_url?: string | null; trace_url?: string | null }
// The experiments endpoint returns stored ingestion progress, not full WeaveIngestion records.
export type EvidenceIngestion = { episode_id: string; state: 'PENDING' | 'FETCHING' | 'INGESTED' | 'RETRYABLE_ERROR' | 'REJECTED'; status: 'weave_pending' | 'weave_verified' | 'weave_error'; execution_epoch: number; error_code: string | null }
export type Experiments = { counterexamples: ExperimentRecord[]; evidence: EvidenceReference[]; ingestions: EvidenceIngestion[]; portability_ids: string[] }
function validateIngestions(value: unknown): EvidenceIngestion[] {
  if (!Array.isArray(value)) throw new Error('Malformed ingestion progress response.')
  return value.map(v => {
    if (!object(v) || typeof v.episode_id !== 'string' || !v.episode_id || !['PENDING', 'FETCHING', 'INGESTED', 'RETRYABLE_ERROR', 'REJECTED'].includes(String(v.state)) || !['weave_pending', 'weave_verified', 'weave_error'].includes(String(v.status)) || !Number.isInteger(v.execution_epoch) || (v.execution_epoch as number) < 0 || !(v.error_code === null || typeof v.error_code === 'string') || Object.keys(v).some(k => !['episode_id', 'state', 'status', 'execution_epoch', 'error_code'].includes(k))) throw new Error('Malformed ingestion progress response.')
    return v as EvidenceIngestion
  })
}
export function validateExperiments(value: unknown): Experiments {
  if (!object(value) || !Array.isArray(value.counterexamples) || !Array.isArray(value.evidence) || !Array.isArray(value.portability_ids) || !value.portability_ids.every(v => typeof v === 'string')) throw new Error('Malformed experiment evidence response.')
  const counterexamples = value.counterexamples.map(v => {
    if (!object(v)) throw new Error('Malformed counterexample projection.')
    return { counterexample: validateContract<Counterexample>('Counterexample', v.counterexample), source_recipe: v.source_recipe === null ? null : validateContract<FaultSpec>('FaultSpec', v.source_recipe), retained_recipe: v.retained_recipe === null ? null : validateContract<FaultSpec>('FaultSpec', v.retained_recipe), reduction: v.reduction === null ? null : validateContract<ReductionResult>('ReductionResult', v.reduction), diagnostics: validateList<DiagnosticResult>('DiagnosticResult', v.diagnostics), interventions: validateList<InterventionExperiment>('InterventionExperiment', v.interventions), challenges: validateList<ChallengeResult>('ChallengeResult', v.challenges) }
  })
  for (const e of value.evidence) if (!object(e) || typeof e.episode_id !== 'string' || !['weave_verified', 'local_only'].includes(String(e.source)) || !(e.root_call_id === null || typeof e.root_call_id === 'string') || !Array.isArray(e.child_call_ids) || !e.child_call_ids.every(c => typeof c === 'string') || !(e.source_project === null || typeof e.source_project === 'string')) throw new Error('Malformed evidence reference.')
  return { counterexamples, evidence: value.evidence as EvidenceReference[], ingestions: validateIngestions(value.ingestions), portability_ids: value.portability_ids as string[] }
}
export const getExperiments = (id: string) => request(`/campaigns/${encodeURIComponent(id)}/experiments`, validateExperiments)
