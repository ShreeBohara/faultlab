// @vitest-environment jsdom
import { cleanup, render, screen, within } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import { PolicyStatusPanel } from '../src/components/PolicyStatusPanel'
import { validatePolicyStatus } from '../src/policyStatus'
import type { CampaignPolicyStatus } from '../src/policyStatus'
import { campaign, hash } from './fixtures'

afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals() })

function savedStatus(): CampaignPolicyStatus {
  return { schema_version: 'faultlab-policy-status/v1', campaign_id: campaign.campaign_id,
    active_policy: { version: 'policy-v0', hash }, studies: [{ study_id: 'study-qualified', source_campaign_id: campaign.campaign_id,
      policy_hash: 'b'.repeat(64), policy_version: 'policy-qualified',
      development: { status: 'QUALIFIED', reason: 'Met the declared development qualification rule.' },
      unseen_checks: [{ check_id: 'heldout-check', campaign_id: 'campaign-heldout', source_study_id: 'study-qualified',
        policy_hash: 'b'.repeat(64), status: 'COMPLETED', decision: 'HARM', predicate: 'faultlab-heldout-no-harm/v2' }] }] }
}
function respond(value: unknown) {
  vi.stubGlobal('fetch', vi.fn(async () => ({ ok: true, json: async () => value })))
}

it('separates development qualification, a failed unseen check and the unchanged baseline', async () => {
  respond(savedStatus())
  render(<PolicyStatusPanel campaignId={campaign.campaign_id} />)
  const development = await screen.findByRole('region', { name: 'Development qualified' })
  expect(within(development).getByText('Qualified on development cases')).toBeTruthy()
  const unseen = screen.getByRole('region', { name: 'Unseen-case result' })
  expect(within(unseen).getByText('Harm detected')).toBeTruthy()
  expect(within(unseen).getByText(/does not by itself prove/)).toBeTruthy()
  const active = screen.getByRole('region', { name: 'Active policy' })
  expect(within(active).getByText('Baseline remains active')).toBeTruthy()
  expect(within(active).getByText('policy-v0')).toBeTruthy()
  expect(screen.queryByRole('button')).toBeNull()
  expect(vi.mocked(fetch).mock.calls).toHaveLength(1)
  expect(vi.mocked(fetch).mock.calls[0][0]).toBe(`/api/campaigns/${campaign.campaign_id}/policy-status`)
  expect(vi.mocked(fetch).mock.calls[0][1]?.method).toBe('GET')
})

it('shows a replay as a replay rather than a new qualification or unseen-case pass', async () => {
  const saved = savedStatus(); saved.studies[0].development.status = 'REPLAY_ONLY'; saved.studies[0].unseen_checks = []
  respond(saved)
  render(<PolicyStatusPanel campaignId={campaign.campaign_id} />)
  await screen.findByText('Replay only')
  expect(screen.queryByText('Qualified on development cases')).toBeNull()
  expect(screen.getByText('Not run')).toBeTruthy()
  expect(screen.getByText(/does not generate or qualify a new repair/)).toBeTruthy()
})

it('keeps a positive study that missed the stronger qualification rule as not qualified', async () => {
  const saved = savedStatus(); saved.studies[0].development = { status: 'NOT_QUALIFIED', reason: 'Observed improvement did not meet the fresh-case gain requirement.' }
  saved.studies[0].unseen_checks = []; respond(saved)
  render(<PolicyStatusPanel campaignId={campaign.campaign_id} />)
  await screen.findByText('Not qualified')
  expect(screen.queryByText('Qualified on development cases')).toBeNull()
  expect(screen.getByText(saved.studies[0].development.reason)).toBeTruthy()
})

it.each([
  ['INCOMPLETE', 'INCOMPLETE', 'Incomplete'],
  ['RUNNING', 'PENDING', 'Still running'],
  ['COMPLETED', 'NO_HARM', 'No harm observed'],
] as const)('labels %s / %s without claiming activation', async (status, decision, label) => {
  const saved = savedStatus(); Object.assign(saved.studies[0].unseen_checks[0], { status, decision }); respond(saved)
  render(<PolicyStatusPanel campaignId={campaign.campaign_id} />)
  await screen.findByText(label)
  expect(screen.getByText('Baseline remains active')).toBeTruthy()
  expect(screen.queryByText('Harm detected')).toBeNull()
})

it('does not borrow unseen checks from another source study with the same policy hash', () => {
  const saved = savedStatus(); saved.studies[0].unseen_checks[0].source_study_id = 'other-study'
  expect(() => validatePolicyStatus(saved, campaign.campaign_id)).toThrow(/Malformed/)
})

it('allows the exact source study linked from an unseen-check campaign, not arbitrary other campaigns', () => {
  const saved = savedStatus(); saved.campaign_id = 'campaign-heldout'
  expect(validatePolicyStatus(saved, saved.campaign_id).studies[0].source_campaign_id).toBe(campaign.campaign_id)
  saved.studies[0].unseen_checks[0].campaign_id = 'unrelated-campaign'
  expect(() => validatePolicyStatus(saved, saved.campaign_id)).toThrow(/Malformed/)
})

it.each([
  ['wrong schema', (s: any) => { s.schema_version = 'unknown' }],
  ['wrong campaign', (s: any) => { s.campaign_id = 'another-campaign' }],
  ['wrong check policy', (s: any) => { s.studies[0].unseen_checks[0].policy_hash = 'c'.repeat(64) }],
  ['missing check identity', (s: any) => { delete s.studies[0].unseen_checks[0].check_id }],
  ['unknown check decision', (s: any) => { s.studies[0].unseen_checks[0].decision = 'PASSED' }],
  ['unknown development decision', (s: any) => { s.studies[0].development.status = 'ACCEPTED' }],
  ['unfamiliar predicate', (s: any) => { s.studies[0].unseen_checks[0].predicate = 'new-unreviewed-rule' }],
  ['unverified positive check', (s: any) => { Object.assign(s.studies[0].unseen_checks[0], { decision: 'NO_HARM', status: 'RUNNING' }) }],
  ['missing qualified policy', (s: any) => { s.studies[0].policy_hash = null }],
  ['malformed active hash', (s: any) => { s.active_policy.hash = 'bad-hash' }],
  ['duplicate study', (s: any) => { s.studies.push(s.studies[0]) }],
  ['duplicate check', (s: any) => { s.studies[0].unseen_checks.push(s.studies[0].unseen_checks[0]) }],
] as const)('rejects %s rather than displaying a passed result', (_, mutate) => {
  const saved = savedStatus(); mutate(saved)
  expect(() => validatePolicyStatus(saved, campaign.campaign_id)).toThrow(/Malformed/)
})

it('projects only public status fields and drops private evidence or arbitrary additions', () => {
  const saved = savedStatus()
  const withPrivate = { ...saved, private_cases: ['never expose'], studies: [{ ...saved.studies[0], raw_evidence: 'never expose', unseen_checks: [{ ...saved.studies[0].unseen_checks[0], recipe: 'never expose', episode_ids: ['secret-episode'] }] }] }
  const parsed = validatePolicyStatus(withPrivate, campaign.campaign_id)
  expect(parsed).toEqual(saved)
  expect(JSON.stringify(parsed)).not.toContain('never expose')
})

it('shows loading without fabricating a pass, and hides old status when switching campaigns', async () => {
  let release!: (value: unknown) => void
  const pending = new Promise(resolve => { release = resolve })
  vi.stubGlobal('fetch', vi.fn(async (url: string) => ({ ok: true, json: async () => url.includes('next-campaign') ? pending : savedStatus() })))
  const view = render(<PolicyStatusPanel campaignId={campaign.campaign_id} />)
  await screen.findByText('Harm detected')
  view.rerender(<PolicyStatusPanel campaignId="next-campaign" />)
  expect(screen.queryByText('Harm detected')).toBeNull()
  expect(screen.queryByText('Qualified on development cases')).toBeNull()
  expect(screen.getByText('Loading stored evidence…')).toBeTruthy()
  release({ ...savedStatus(), campaign_id: 'wrong-campaign' })
  await screen.findByRole('alert')
  expect(screen.getByText(/Status unavailable/)).toBeTruthy()
  expect(screen.queryByText('Baseline remains active')).toBeNull()
})

it('distinguishes no recorded studies and an unknown active policy from successful qualification', async () => {
  respond({ ...savedStatus(), studies: [], active_policy: { version: null, hash: null } })
  render(<PolicyStatusPanel campaignId={campaign.campaign_id} />)
  await screen.findByText('Not recorded')
  expect(screen.getByText('Not available')).toBeTruthy()
  expect(screen.getByText('Not run')).toBeTruthy()
  expect(screen.queryByText('Qualified on development cases')).toBeNull()
})

it('keeps multiple studies separate and reads the actual active pointer', async () => {
  const saved = savedStatus(); saved.active_policy = { version: 'policy-active', hash: 'c'.repeat(64) }
  saved.studies.push({ study_id: 'study-second', source_campaign_id: campaign.campaign_id, policy_hash: null, policy_version: null,
    development: { status: 'INCOMPLETE', reason: 'The study did not finish.' }, unseen_checks: [] }); respond(saved)
  render(<PolicyStatusPanel campaignId={campaign.campaign_id} />)
  await screen.findByText('Harm detected')
  expect(screen.getAllByRole('region', { name: 'Development qualified' })).toHaveLength(2)
  expect(screen.getByText('Incomplete')).toBeTruthy()
  expect(screen.getAllByText('policy-active')).toHaveLength(2)
  expect(screen.queryByText('Baseline remains active')).toBeNull()
})
