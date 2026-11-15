import { object, request } from './api'

// Saved study records (GET /api/studies, backend app/studies.py over faultlab.research.archive). Read-only: these
// endpoints read published record files and never start a run or call a provider.

export type StudyKind = 'unseen_comparison' | 'unseen_study' | 'repair_study' | 'development_check'
export type StudyDecision = { arm: string | null; decision: string; model: string | null; presentation: string | null }
export type DeclarationDigest = { sha256: string; verified: boolean | null }
export type StudySummary = {
  id: string; kind: StudyKind; title: string; date: string | null; started_at: string | null; claim: string
  question: string | null; decisions: StudyDecision[]; dollars: number | null; declaration: DeclarationDigest | null; problems: string[]
}
export type StudyIndex = { schema: 'faultlab-study-index/v1'; root: string; studies: StudySummary[] }
export type Declaration = DeclarationDigest & {
  schema: string | null; name: string | null; declared_at: string | null; purpose: string | null; question: string | null
  claim_scope: string | null; decision_rule: string | null; readouts: string[]; stop_rules: string[]; expected_cost: string | null
}
export type Calls = { mean: number | null; max: number | null; at_cap: number; histogram: Record<string, number> }
export type RuleReadouts = {
  trials: number; scoreable: number; slips: number; acted: number; blocked_proposals: number; trials_with_block: number
  side_effect_trials: number; no_report_after_block: number; advice_turns: number; trials_with_advice: number
  correct_refusals: number; tasks: Record<string, number>; legacy: Record<string, number>; model_calls: Calls
  rule_silent: { trials: number; no_report: number; tasks: Record<string, number> }
  last_call_advice: { trials: number; side_effect_trials: number; blocked: number } | null
}
export type BaselineReadouts = {
  trials: number; scoreable: number; slips: number; correct_refusals: number; no_report: number
  tasks: Record<string, number>; legacy: Record<string, number>; model_calls: Calls
}
export type CaseReadouts = {
  passed: boolean | null; acting: number | null; clean: number | null; side_effect_trials: number; trials_with_block: number
  trials_with_advice: number; rule_silent: number; slips: number; B0_slips: number
}
export type StudyArm = {
  name: string; record: string; study_name: string | null; decision: string; reason: string | null; model: string | null
  presentation: string | null; policy_digest: string | null; created_at: string | null; ended_at: string | null
  design: { pairs: number | null; other_pairs: number | null; gap_min: number | null; rejected_cases: number; other_cases: number; caps: Record<string, unknown> | null }
  failed_cases: string[]; no_report: { L: number; B0: number }
  rejected: { L: RuleReadouts; B0: BaselineReadouts; per_case: Record<string, CaseReadouts> }
  other: { L: RuleReadouts; B0: BaselineReadouts }
  measured: Record<string, number | null> | null
}
export type PrimaryComparison = Record<string, Record<string, unknown>>
export type RepairRule = { hook?: string; when?: string; operation?: string; steps?: Record<string, unknown>[] }
export type RepairDetail = {
  decision: string; reason: string | null; model: string | null; mechanic_model: string | null; notes: string[]
  created_at: string | null; ended_at: string | null; design: Record<string, unknown>
  gap: Record<string, unknown> | null; gate_opened: boolean | null
  proposals: { slot: number | null; valid: boolean | null; ended: string | null; turns: number | null; attempts: number | null; version: string | null; rules: RepairRule[] }[]
  candidates: Record<string, unknown>[]
  validation: { slot: number | null; passed: boolean | null; cases: Record<string, { passed: boolean | null; inert: boolean | null; acting: number | null; clean: number | null; B0: Record<string, unknown> | null; L: Record<string, unknown> | null }> }[]
  measured: Record<string, number | null> | null
}
export type DevelopmentDetail = { decision: string; model: string | null; arms: Record<string, Record<string, number | null>>; primary: Record<string, Record<string, unknown>> }
export type StudyDetail = {
  schema: 'faultlab-study/v1'; id: string; kind: StudyKind; title: string; date: string | null; started_at: string | null; claim: string
  declaration: Declaration | null; arms: StudyArm[]; comparison: { order: string[]; primary: PrimaryComparison; note: string | null } | null
  repair: RepairDetail | null; development: DevelopmentDetail | null; files: { name: string; bytes: number }[]; dollars: number | null; problems: string[]
}

export const studyKinds: Record<StudyKind, string> = {
  unseen_comparison: 'Unseen-case comparisons', unseen_study: 'Unseen-case studies',
  repair_study: 'Repair studies (development)', development_check: 'Development checks',
}
export const STUDY_ID = /^[a-z0-9][a-z0-9._-]{0,127}$/
const HASH = /^[a-f0-9]{64}$/
const malformed = (what: string): never => { throw new Error(`Malformed saved ${what}. The last verified data is retained.`) }
const text = (v: unknown): v is string => typeof v === 'string'
const optionalText = (v: unknown) => v === null || typeof v === 'string'
const count = (v: unknown): v is number => Number.isInteger(v) && (v as number) >= 0
const optionalCount = (v: unknown) => v === null || count(v)
const number = (v: unknown) => typeof v === 'number' && Number.isFinite(v)
const optionalNumber = (v: unknown) => v === null || number(v)
const strings = (v: unknown): v is string[] => Array.isArray(v) && v.every(text)
const counts = (v: unknown) => object(v) && Object.values(v).every(count)
const kind = (v: unknown): v is StudyKind => typeof v === 'string' && v in studyKinds

function checkDigest(v: unknown, what: string) {
  if (v !== null && (!object(v) || !text(v.sha256) || !HASH.test(v.sha256) || !(v.verified === null || typeof v.verified === 'boolean'))) malformed(what)
}

export function validateStudyIndex(value: unknown): StudyIndex {
  if (!object(value) || value.schema !== 'faultlab-study-index/v1' || !text(value.root) || !Array.isArray(value.studies)) return malformed('study list')
  const ids = new Set<string>()
  for (const study of value.studies) {
    if (!object(study) || !text(study.id) || !STUDY_ID.test(study.id) || ids.has(study.id) || !kind(study.kind) || !text(study.title)
      || !optionalText(study.date) || !optionalText(study.started_at) || !text(study.claim) || !optionalText(study.question)
      || !Array.isArray(study.decisions) || !optionalNumber(study.dollars) || !strings(study.problems)) return malformed('study list')
    for (const d of study.decisions) {
      if (!object(d) || !optionalText(d.arm) || !text(d.decision) || !optionalText(d.model) || !optionalText(d.presentation)) return malformed('study list')
    }
    checkDigest(study.declaration, 'study list')
    ids.add(study.id)
  }
  return value as StudyIndex
}

function checkCalls(v: unknown) {
  return object(v) && optionalNumber(v.mean) && optionalNumber(v.max) && count(v.at_cap) && counts(v.histogram)
}
function checkRule(v: unknown) {
  if (!object(v) || !['trials', 'scoreable', 'slips', 'acted', 'blocked_proposals', 'trials_with_block', 'side_effect_trials', 'no_report_after_block',
    'advice_turns', 'trials_with_advice', 'correct_refusals'].every(key => count(v[key])) || !counts(v.tasks) || !counts(v.legacy) || !checkCalls(v.model_calls)
    || !object(v.rule_silent) || !count(v.rule_silent.trials) || !count(v.rule_silent.no_report)) malformed('study read-outs')
  const last = (v as Record<string, unknown>).last_call_advice
  if (last !== null && (!object(last) || !count(last.trials) || !count(last.side_effect_trials) || !count(last.blocked))) malformed('study read-outs')
}
function checkBaseline(v: unknown) {
  if (!object(v) || !['trials', 'scoreable', 'slips', 'correct_refusals', 'no_report'].every(key => count(v[key])) || !counts(v.tasks)
    || !counts(v.legacy) || !checkCalls(v.model_calls)) malformed('study read-outs')
}
function checkArm(arm: unknown) {
  if (!object(arm) || !text(arm.name) || !text(arm.record) || !text(arm.decision) || !optionalText(arm.reason) || !optionalText(arm.model)
    || !optionalText(arm.presentation) || !optionalText(arm.policy_digest) || !strings(arm.failed_cases) || !object(arm.design)
    || !object(arm.no_report) || !count(arm.no_report.L) || !count(arm.no_report.B0) || !object(arm.rejected) || !object(arm.other)
    || !object(arm.rejected.per_case) || !(arm.measured === null || object(arm.measured))) malformed('study record')
  const a = arm as { rejected: Record<string, unknown> & { per_case: Record<string, unknown> }; other: Record<string, unknown> }
  checkRule(a.rejected.L); checkBaseline(a.rejected.B0); checkRule(a.other.L); checkBaseline(a.other.B0)
  for (const c of Object.values(a.rejected.per_case)) {
    if (!object(c) || !(c.passed === null || typeof c.passed === 'boolean') || !optionalCount(c.acting) || !optionalCount(c.clean)
      || !['side_effect_trials', 'trials_with_block', 'trials_with_advice', 'rule_silent', 'slips', 'B0_slips'].every(key => count(c[key]))) malformed('study record')
  }
}

export function validateStudy(value: unknown, id: string): StudyDetail {
  if (!object(value) || value.schema !== 'faultlab-study/v1' || value.id !== id || !kind(value.kind) || !text(value.title) || !text(value.claim)
    || !optionalText(value.date) || !Array.isArray(value.arms) || !Array.isArray(value.files) || !strings(value.problems) || !optionalNumber(value.dollars)) return malformed('study')
  const declaration = value.declaration
  if (declaration !== null) {
    checkDigest(declaration, 'declaration')
    const d = declaration as Record<string, unknown>
    if (!['schema', 'name', 'declared_at', 'purpose', 'question', 'claim_scope', 'decision_rule', 'expected_cost'].every(key => optionalText(d[key]))
      || !strings(d.readouts) || !strings(d.stop_rules)) return malformed('declaration')
  }
  value.arms.forEach(checkArm)
  if (['unseen_comparison', 'unseen_study'].includes(value.kind as string) !== (value.arms.length > 0)) return malformed('study')
  const comparison = value.comparison
  if (comparison !== null && (!object(comparison) || !strings(comparison.order) || !object(comparison.primary) || !optionalText(comparison.note))) return malformed('comparison')
  if ((value.kind === 'unseen_comparison') !== (comparison !== null)) return malformed('study')
  const repair = value.repair
  if ((value.kind === 'repair_study') !== (repair !== null)) return malformed('study')
  if (repair !== null && (!object(repair) || !text(repair.decision) || !optionalText(repair.reason) || !Array.isArray(repair.proposals)
    || !Array.isArray(repair.candidates) || !Array.isArray(repair.validation) || !strings(repair.notes) || !object(repair.design))) return malformed('repair study')
  const development = value.development
  if ((value.kind === 'development_check') !== (development !== null)) return malformed('study')
  if (development !== null && (!object(development) || !text(development.decision) || !object(development.arms) || !object(development.primary))) return malformed('development check')
  for (const file of value.files) if (!object(file) || !text(file.name) || !count(file.bytes)) return malformed('study')
  return value as StudyDetail
}

export const getStudies = () => request('/studies', validateStudyIndex)
export const getStudy = (id: string) => request(`/studies/${encodeURIComponent(id)}`, value => validateStudy(value, id))
export const studyFileUrl = (id: string, name: string) => `/api/studies/${encodeURIComponent(id)}/files/${name.split('/').map(encodeURIComponent).join('/')}`

/** `#/studies` and `#/studies/<id>` open the study pages; any other hash is the campaign screen. */
export function studiesRoute(hash: string): { id: string | null } | null {
  const match = /^#\/studies(?:\/([^/?#]*))?\/?$/.exec(hash)
  if (!match) return null
  if (!match[1]) return { id: null }
  let id: string
  try { id = decodeURIComponent(match[1]) } catch { return { id: null } }
  return { id: STUDY_ID.test(id) ? id : null }
}
export const studyHref = (id?: string | null) => id ? `#/studies/${encodeURIComponent(id)}` : '#/studies'

/** A model reference without its provider prefix, for compact labels. */
export const shortModel = (model: string | null) => model ? model.slice(model.indexOf(':') + 1) : 'model not recorded'
export const money = (value: number | null) => value === null ? 'not recorded' : `$${value.toFixed(value < 1 ? 4 : 2)}`
