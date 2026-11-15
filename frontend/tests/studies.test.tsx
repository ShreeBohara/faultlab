// @vitest-environment jsdom
import { act, cleanup, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { App } from '../src/App'
import { StudiesScreen } from '../src/components/StudiesScreen'
import { studiesRoute, studyFileUrl, studyHref, validateStudy, validateStudyIndex } from '../src/studies'
import { fixtureResponse } from './fixtures'
import indexFixture from './fixtures/studies/index.json'
import comparison4 from './fixtures/studies/unseen-comparison-4-2026-11-15.json'
import repairV3 from './fixtures/studies/repair-study-v3-2026-11-14.json'
import dev1 from './fixtures/studies/advice-presentation-dev-1-2026-11-15.json'
import run1 from './fixtures/studies/unseen-study-1-2026-11-08.json'

const C4 = 'unseen-comparison-4-2026-11-15'
const details: Record<string, unknown> = { [C4]: comparison4, 'repair-study-v3-2026-11-14': repairV3, 'advice-presentation-dev-1-2026-11-15': dev1, 'unseen-study-1-2026-11-08': run1 }
const copy = <T,>(value: T): T => JSON.parse(JSON.stringify(value))

function studiesFetch(overrides: Record<string, unknown> = {}) {
  return vi.fn(async (url: string) => {
    const path = url.replace(/^\/api/, '')
    if (path in overrides) return { ok: true, json: async () => overrides[path] }
    if (path === '/studies') return { ok: true, json: async () => indexFixture }
    const id = decodeURIComponent(path.replace(/^\/studies\//, ''))
    if (path.startsWith('/studies/') && id in details) return { ok: true, json: async () => details[id] }
    if (path.startsWith('/studies/')) return { ok: false, status: 404, json: async () => ({ error: { code: 'STUDY_NOT_FOUND', message: 'No published study has that name.' } }) }
    return { ok: true, json: async () => fixtureResponse(url) }
  })
}

beforeEach(() => { window.location.hash = '' })
afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals() })

it('accepts the real study list and every detail shape, and refuses malformed ones', () => {
  const index = validateStudyIndex(copy(indexFixture))
  expect(index.studies.length).toBeGreaterThanOrEqual(16)
  expect(index.studies[0].id).toBe(C4)
  for (const [id, detail] of Object.entries(details)) expect(validateStudy(copy(detail), id).id).toBe(id)
  const bad = [
    { ...copy(indexFixture), schema: 'faultlab-study-index/v2' },
    { ...copy(indexFixture), studies: [...copy(indexFixture).studies, copy(indexFixture).studies[0]] },
    { ...copy(indexFixture), studies: [{ ...copy(indexFixture).studies[0], id: '../escape' }] },
    { ...copy(indexFixture), studies: [{ ...copy(indexFixture).studies[0], declaration: { sha256: 'short', verified: true } }] },
  ]
  for (const value of bad) expect(() => validateStudyIndex(value)).toThrow(/Malformed saved study list/)
  expect(() => validateStudy(copy(comparison4), 'unseen-comparison-3-2026-11-15')).toThrow(/Malformed saved study/)
  const negative = copy(comparison4); negative.arms[0].rejected.L.slips = -1
  expect(() => validateStudy(negative, C4)).toThrow(/read-outs/)
  const noComparison = copy(comparison4) as Record<string, unknown>; noComparison.comparison = null
  expect(() => validateStudy(noComparison, C4)).toThrow(/Malformed saved study/)
  const repairWithArms = copy(repairV3) as Record<string, unknown>; repairWithArms.arms = copy(comparison4).arms
  expect(() => validateStudy(repairWithArms, 'repair-study-v3-2026-11-14')).toThrow(/Malformed saved study/)
})

it('routes only #/studies hashes to the study pages and never decodes an unsafe name', () => {
  expect(studiesRoute('#/studies')).toEqual({ id: null })
  expect(studiesRoute('#/studies/')).toEqual({ id: null })
  expect(studiesRoute(`#/studies/${C4}`)).toEqual({ id: C4 })
  expect(studiesRoute('#/studies/..%2F..%2Fetc')).toEqual({ id: null })
  expect(studiesRoute('#/studies/%E0%A4%A')).toEqual({ id: null })
  expect(studiesRoute('#evidence-workspace')).toBeNull()
  expect(studiesRoute('')).toBeNull()
  expect(studyHref(C4)).toBe(`#/studies/${C4}`)
  expect(studyFileUrl(C4, 'Q/unseen-study.json')).toBe(`/api/studies/${C4}/files/Q/unseen-study.json`)
})

it('lists the saved studies by kind and opens the newest with its declared question, decisions and read-outs', async () => {
  const fetch = studiesFetch(); vi.stubGlobal('fetch', fetch)
  render(<StudiesScreen selectedId={null} />)
  const list = await screen.findByRole('navigation', { name: 'Saved studies' })
  expect(within(list).getByRole('heading', { name: /Unseen-case comparisons 4/ })).toBeTruthy()
  expect(within(list).getByRole('heading', { name: /Repair studies \(development\) 7/ })).toBeTruthy()
  expect(within(list).getByRole('link', { name: /Unseen comparison 4/ }).getAttribute('aria-current')).toBe('true')
  const detail = await screen.findByRole('article', { name: 'Unseen comparison 4' })
  expect(within(detail).getByText(/Not an active policy/)).toBeTruthy()
  expect(within(detail).getByText(/With Sonnet 5.5 as the Actor/)).toBeTruthy()
  expect(within(detail).getByText('Declaration verified')).toBeTruthy()
  expect(within(detail).getByRole('heading', { name: /Q · advice as the report gate’s requirement/ })).toBeTruthy()
  expect(within(detail).getAllByText('Transferred')).toHaveLength(1)
  expect(within(detail).getAllByText('Not transferred')).toHaveLength(1)
  expect(within(detail).getByText(/failed cases: unseen-r2/)).toBeTruthy()
  expect(within(detail).queryByText(/^Failed cases:/)).toBeNull()                     // the reason already names them
  expect(within(detail).getByText(/Trials with a blocked report:/).closest('li')!.textContent).toBe('Trials with a blocked report: E 0 of 36 · Q 0 of 36 · two-sided Fisher exact p = 1')
  const table = within(detail).getByRole('table', { name: /36 trials in each column/ })
  const slips = within(table).getByRole('row', { name: /Slip: a wrong notification label/ })
  expect(within(slips).getAllByRole('cell').map(cell => cell.textContent)).toEqual(['11', '0', '8', '0'])
  const noReport = within(table).getByRole('row', { name: /^No report/ })
  expect(within(noReport).getAllByRole('cell').map(cell => cell.textContent)).toEqual(['4', '1', '3', '0'])
  const caseTable = within(detail).getByRole('table', { name: /^E · The unseen-case gate/ })
  expect(within(caseTable).getByRole('row', { name: /unseen-r2/ }).textContent).toContain('Failed')
  const link = within(detail).getByRole('link', { name: /Q\/unseen-study.json/ })
  expect(link.getAttribute('href')).toBe(`/api/studies/${C4}/files/Q/unseen-study.json`)
  expect(fetch.mock.calls.map(call => call[0])).toEqual(expect.arrayContaining(['/api/studies', `/api/studies/${C4}`]))
  expect(fetch.mock.calls.every(call => !call[1] || (call[1] as RequestInit).method === 'GET')).toBe(true)
})

it('shows a repair study as development qualification with its proposal and validation', async () => {
  vi.stubGlobal('fetch', studiesFetch())
  render(<StudiesScreen selectedId="repair-study-v3-2026-11-14" />)
  const detail = await screen.findByRole('article', { name: 'Repair study v3' })
  expect(within(detail).getByText(/Development qualification on the public cases/)).toBeTruthy()
  expect(within(detail).getByText('Repaired')).toBeTruthy()
  expect(within(detail).getByRole('heading', { name: /Slot 1 · rejection-notification-not-required/ })).toBeTruthy()
  expect(within(detail).getAllByText('before_final_report').length).toBeGreaterThan(0)
  expect(within(detail).getByRole('row', { name: /dev-1/ }).textContent).toContain('Inert')
})

it('shows a development check and an older record whose gate kept fewer counts', async () => {
  vi.stubGlobal('fetch', studiesFetch())
  const { unmount } = render(<StudiesScreen selectedId="advice-presentation-dev-1-2026-11-15" />)
  const dev = await screen.findByRole('article', { name: 'Advice presentation dev 1' })
  expect(within(dev).getByText('Proceed')).toBeTruthy()
  expect(within(dev).getByText(/Trials with a blocked report:/).closest('li')!.textContent).toMatch(/E 7 of 12 · Q 0 of 12/)
  unmount()
  render(<StudiesScreen selectedId="unseen-study-1-2026-11-08" />)
  const run = await screen.findByRole('article', { name: 'Unseen study 1' })
  expect(within(run).getByRole('row', { name: /unseen-r1/ }).textContent).toContain('— / —')
  expect(within(run).getByText(/presentation not recorded/)).toBeTruthy()
})

it('names an unknown study instead of guessing one', async () => {
  vi.stubGlobal('fetch', studiesFetch())
  render(<StudiesScreen selectedId="unseen-comparison-9-2026-12-01" />)
  await waitFor(() => expect(screen.getAllByRole('alert').some(alert => /No saved study is called unseen-comparison-9-2026-12-01/.test(alert.textContent ?? ''))).toBe(true))
  expect(screen.queryByRole('article')).toBeNull()
})

it('flags a declaration that no longer matches its digest, and an empty folder', async () => {
  const changed = copy(comparison4); changed.declaration.verified = false
  changed.problems = ['the declaration does not match its published sha256']
  vi.stubGlobal('fetch', studiesFetch({ [`/studies/${C4}`]: changed }))
  const { unmount } = render(<StudiesScreen selectedId={C4} />)
  expect(await screen.findByText('Declaration changed')).toBeTruthy()
  expect(screen.getByText(/Check this record: the declaration does not match/)).toBeTruthy()
  unmount()
  vi.stubGlobal('fetch', studiesFetch({ '/studies': { schema: 'faultlab-study-index/v1', root: '/tmp/none', studies: [] } }))
  render(<StudiesScreen selectedId={null} />)
  expect(await screen.findByRole('heading', { name: 'No saved studies' })).toBeTruthy()
})

it('switches between the campaign screen and the study pages by the address hash', async () => {
  vi.stubGlobal('fetch', studiesFetch())
  window.location.hash = '#/studies'
  render(<App />)
  expect(await screen.findByRole('heading', { name: /Study results/ })).toBeTruthy()
  expect(document.title).toBe('Study results · FaultLab')
  act(() => { window.location.hash = '#/'; window.dispatchEvent(new HashChangeEvent('hashchange')) })
  await waitFor(() => expect(screen.getByRole('heading', { name: /Find the fault/ })).toBeTruthy())
  expect(screen.getByRole('link', { name: 'Study results' }).getAttribute('href')).toBe('#/studies')
  act(() => { window.location.hash = `#/studies/${C4}`; window.dispatchEvent(new HashChangeEvent('hashchange')) })
  expect(await screen.findByRole('article', { name: 'Unseen comparison 4' })).toBeTruthy()
})
