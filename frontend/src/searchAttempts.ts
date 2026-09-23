import { object, request } from './api'
import { validateContract } from './generated/validate'
import type { ExplorerOutput, Usage } from './generated/contracts'

export type SearchAttempt = {
  selection_ref: string; campaign_id: string; selection_index: number; configuration_hash: string; policy_hash: string
  search_decision: { status: 'SELECTED' | 'SKIPPED_DUPLICATE' | 'INVALID_OUTPUT'; schedule_hash: string | null; reason: string | null; prior_selection_refs: string[]; prior_episode_refs: string[] }
  selected_output: ExplorerOutput | null; output: ExplorerOutput | null; raw_response: string; usage: Usage; provenance: string; error: string | null
}
const nonempty = (value: unknown): value is string => typeof value === 'string' && value.length > 0
const hash = (value: unknown): value is string => typeof value === 'string' && /^[a-f0-9]{64}$/.test(value)
const references = (value: unknown): value is string[] => Array.isArray(value) && value.every(nonempty)
const malformed = (): never => { throw new Error('Malformed search attempts or campaign identity. The last verified data is retained.') }

export function validateSearchAttempts(value: unknown, campaignId: string): SearchAttempt[] {
  if (!Array.isArray(value)) return malformed()
  const refs = new Set<string>()
  return value.map(row => {
    if (!object(row) || row.campaign_id !== campaignId || !nonempty(row.selection_ref) || refs.has(row.selection_ref)
      || !Number.isInteger(row.selection_index) || (row.selection_index as number) < 0
      || !hash(row.configuration_hash) || !hash(row.policy_hash) || !object(row.search_decision)
      || typeof row.raw_response !== 'string' || !nonempty(row.provenance) || !(row.error === null || typeof row.error === 'string')) return malformed()
    const decision = row.search_decision
    if (!['SELECTED', 'SKIPPED_DUPLICATE', 'INVALID_OUTPUT'].includes(String(decision.status))
      || !(decision.schedule_hash === null || hash(decision.schedule_hash))
      || !(decision.reason === null || typeof decision.reason === 'string')
      || !references(decision.prior_selection_refs) || !references(decision.prior_episode_refs)) return malformed()
    const selected_output = row.selected_output === null ? null : validateContract<ExplorerOutput>('ExplorerOutput', row.selected_output)
    const output = row.output === null ? null : validateContract<ExplorerOutput>('ExplorerOutput', row.output)
    if ((decision.status === 'SELECTED') !== !!selected_output || (decision.status !== 'INVALID_OUTPUT' && !decision.schedule_hash)) return malformed()
    refs.add(row.selection_ref)
    return { ...row, selected_output, output, usage: validateContract<Usage>('Usage', row.usage) } as SearchAttempt
  })
}
export const getSearchAttempts = (campaignId: string) => request(`/campaigns/${encodeURIComponent(campaignId)}/search-attempts`, value => validateSearchAttempts(value, campaignId))
