import { useEffect, useRef } from 'react'
import type { ReactNode } from 'react'
import { useResource } from '../useResource'
import { getStudies, getStudy, money, shortModel, studyFileUrl, studyHref, studyKinds } from '../studies'
import type { BaselineReadouts, Declaration, DevelopmentDetail, PrimaryComparison, RepairDetail, RuleReadouts, StudyArm, StudyDetail, StudyIndex, StudyKind, StudySummary } from '../studies'
import { Badge, Empty, Field, Hash, Panel, ResourceNote } from './common'
import { ThemeToggle } from './ThemeToggle'

const KIND_ORDER: StudyKind[] = ['unseen_comparison', 'unseen_study', 'development_check', 'repair_study']
const presentationLabel = (value: string | null) => value === 'requirement' ? 'advice as the report gate’s requirement'
  : value === 'expectation' ? 'advice as an expectation' : 'presentation not recorded'
const dash = '—'

export function StudiesScreen({ selectedId }: { selectedId: string | null }) {
  const index = useResource('studies', getStudies, null)
  const studies = index.data?.studies ?? []
  const id = selectedId ?? studies[0]?.id ?? null
  const detail = useResource(id ? `study:${id}` : null, () => getStudy(id!), null)
  // Choosing another study from the list brings its detail into view (the list stays put beside it).
  const shown = useRef(id)
  useEffect(() => { if (shown.current !== id && shown.current !== null) document.getElementById('study-detail')?.scrollIntoView?.({ block: 'start' }); shown.current = id }, [id])
  return <main className="workspace studies-page">
    <a className="skip-link" href="#study-detail" onClick={event => { event.preventDefault(); document.getElementById('study-detail')?.focus() }}>Skip to the selected study</a>
    <header className="masthead"><a className="brand" href="#/"><span className="monogram" aria-hidden="true">F<span>∕</span>L</span><span>FaultLab<small>BY GATEKEEPER</small></span></a>
      <div className="header-right"><span className="environment">SAVED STUDY RECORDS</span><nav className="header-actions" aria-label="Pages"><a className="nav-link" href="#/">Campaigns</a><a className="nav-link" aria-current="page" href={studyHref()}>Study results</a><ThemeToggle /></nav></div></header>
    <section className="intro"><div><p className="eyebrow">What the lab has shown so far</p><h1>Study results<br /><em>as declared, as measured.</em></h1>
      <p className="description">Every finished study published with the project: the question fixed before the run, each study’s own decision, and its read-outs. Read-only: this page starts nothing and calls no model provider.</p></div>
      <div className="lab-index"><span className="index-label">THREE DIFFERENT CLAIMS</span><ol><li>Development <span>→</span> qualified on public cases</li><li>Unseen cases <span>→</span> held on new schedules</li><li>Active policy <span>→</span> none claimed</li></ol><p>A correct refusal is a working lab, not a learned repair.</p></div></section>
    <ResourceNote resource={index} />
    {index.data && <StudyTotals index={index.data} onRefresh={index.refresh} />}
    {index.data && !studies.length && <section className="notice"><h2>No saved studies</h2><p>No study folder was found under <code>{index.data.root}</code>. Finished studies publish their declaration and records there; set <code>FAULTLAB_STUDIES_DIR</code> to read another folder.</p></section>}
    {!!studies.length && <div className="studies-layout"><StudyList studies={studies} selectedId={id} />
      <div className="study-detail" id="study-detail" tabIndex={-1}>
        {selectedId && !studies.some(study => study.id === selectedId) && <div role="alert" className="error">No saved study is called <code>{selectedId}</code>. Choose one from the list.</div>}
        <ResourceNote resource={detail} />
        {detail.data && detail.data.id === id && <StudyView study={detail.data} />}
      </div></div>}
    <footer><span>FaultLab / Gatekeeper</span><span>Published records only · no case file, trial store or bundle is opened</span><code>GET /api/studies</code></footer>
  </main>
}

function StudyTotals({ index, onRefresh }: { index: StudyIndex; onRefresh?: () => void }) {
  const byKind = (kind: StudyKind) => index.studies.filter(study => study.kind === kind).length
  const spent = index.studies.reduce((sum, study) => sum + (study.dollars ?? 0), 0)
  return <div className="campaign-bar study-totals"><span><strong>{index.studies.length}</strong> saved studies · {KIND_ORDER.map(kind => `${byKind(kind)} ${studyKinds[kind].toLowerCase()}`).join(' · ')}</span>
    <span>{money(spent)} of API money measured in the records · <code>{index.root}</code>{onRefresh && <button className="text-button" onClick={onRefresh}>Reload list</button>}</span></div>
}

function StudyList({ studies, selectedId }: { studies: StudySummary[]; selectedId: string | null }) {
  return <nav className="panel study-list" aria-label="Saved studies">{KIND_ORDER.map(kind => {
    const group = studies.filter(study => study.kind === kind)
    return group.length ? <div key={kind} className="study-group"><h2>{studyKinds[kind]} <span className="muted">{group.length}</span></h2><ul>{group.map(study =>
      <li key={study.id}><a href={studyHref(study.id)} aria-current={study.id === selectedId ? 'true' : undefined} className={study.id === selectedId ? 'selected' : ''}>
        <span className="study-list-title">{study.title}</span><span className="study-list-meta">{study.date ?? 'undated'} · {[...new Set(study.decisions.map(d => shortModel(d.model)))].join(', ')}</span>
        <span className="study-list-decisions">{study.decisions.map((d, i) => <span key={`${d.arm}:${i}`}>{d.arm && <span className="arm-name">{d.arm}</span>}<Badge value={d.decision} /></span>)}{study.problems.length > 0 && <Badge value="UNVERIFIED" />}</span>
      </a></li>)}</ul></div> : null
  })}</nav>
}

function StudyView({ study }: { study: StudyDetail }) {
  return <article className="study-view" aria-label={study.title}>
    <Panel title={study.title} aside={<span className="muted">{study.date ?? 'undated'} · {studyKinds[study.kind]}</span>}>
      <p className="notice claim-notice">{study.claim}</p>
      {study.problems.map(problem => <div key={problem} role="alert" className="error">Check this record: {problem}.</div>)}
      {study.declaration?.question && <><h3>Declared question</h3><p className="study-question">{study.declaration.question}</p></>}
      {!study.declaration?.question && study.declaration?.purpose && <><h3>Declared purpose</h3><p className="study-question">{study.declaration.purpose}</p></>}
      {study.declaration?.claim_scope && <p className="muted"><strong>Scope:</strong> {study.declaration.claim_scope}</p>}
      <dl className="facts compact"><Field name="Declaration">{study.declaration ? <><Badge value={study.declaration.verified === true ? 'DECLARATION_VERIFIED' : study.declaration.verified === false ? 'DECLARATION_CHANGED' : 'UNVERIFIED'} /> <Hash value={study.declaration.sha256} /></> : 'none published'}</Field>
        <Field name="API money in these records">{money(study.dollars)}{study.dollars !== null && <span className="muted"> · a launcher’s preflight is in the spend ledger, not here</span>}</Field></dl>
    </Panel>
    {study.arms.length > 0 && <UnseenView study={study} />}
    {study.repair && <RepairView repair={study.repair} />}
    {study.development && <DevelopmentView development={study.development} />}
    {study.declaration && <DeclarationView declaration={study.declaration} />}
    <Panel title="Saved records"><p className="muted">The published record files, as saved. Case files, trial stores and bundles of unseen draws stay sealed and are never served.</p>
      <ul className="file-list">{study.files.map(file => <li key={file.name}><a href={studyFileUrl(study.id, file.name)} target="_blank" rel="noreferrer">{file.name} ↗</a> <span className="muted">{(file.bytes / 1024).toFixed(1)} KB</span></li>)}</ul></Panel>
  </article>
}

function UnseenView({ study }: { study: StudyDetail }) {
  const arms = study.arms
  return <>
    <Panel title={arms.length > 1 ? 'Each study’s own decision' : 'Decision'}>
      <div className="arm-grid">{arms.map(arm => <article key={arm.name} className="study-arm">
        <div className="split-heading"><h3>{arms.length > 1 ? `${arm.name} · ` : ''}{presentationLabel(arm.presentation)}</h3><Badge value={arm.decision} /></div>
        <p className="muted">{shortModel(arm.model)} · {arm.design.rejected_cases} rejected-upgrade cases × {arm.design.pairs ?? dash} pairs{arm.design.other_cases ? ` · ${arm.design.other_cases} other cases × ${arm.design.other_pairs ?? arm.design.pairs ?? dash}` : ''}</p>
        {arm.reason && <p>{arm.reason}</p>}
        {arm.failed_cases.length > 0 && !arm.failed_cases.every(c => arm.reason?.includes(c)) && <p className="muted">Failed cases: {arm.failed_cases.map(c => <code key={c}>{c}</code>)}</p>}
      </article>)}</div>
      {study.comparison && <PrimaryView primary={study.comparison.primary} order={study.comparison.order} note={study.comparison.note} />}
    </Panel>
    <ReadoutTable arms={arms} />
    {arms.map(arm => <CaseTable key={arm.name} arm={arm} single={arms.length === 1} />)}
  </>
}

function PrimaryView({ primary, order, note }: { primary: PrimaryComparison; order: string[]; note: string | null }) {
  const names: Record<string, string> = { side_effect_trials: 'Side-effect trials', trials_with_block: 'Trials with a blocked report' }
  return <div className="primary-comparison"><h3>Declared comparison between the studies</h3><ul>{Object.entries(primary).map(([key, value]) =>
    <li key={key}><strong>{names[key] ?? key.replaceAll('_', ' ')}:</strong> {order.filter(name => Array.isArray(value[name])).map(name => { const [n, of] = value[name] as number[]; return `${name} ${n} of ${of}` }).join(' · ')}{typeof value.fisher_two_sided_p === 'number' && <> · two-sided Fisher exact p = {value.fisher_two_sided_p}</>}</li>)}</ul>
    <p className="muted">{note ?? 'p-values describe; each study’s own decision is its claim.'}</p></div>
}

type Side = 'B0' | 'L'
const sides: Side[] = ['B0', 'L']
function ReadoutTable({ arms }: { arms: StudyArm[] }) {
  const ruleOnly = (pick: (r: RuleReadouts) => string) => (side: Side, arm: StudyArm) => side === 'B0' ? dash : pick(arm.rejected.L)
  const rows: [string, (side: Side, arm: StudyArm) => ReactNode][] = [
    ['Slip: a wrong notification label after the rejection', (side, arm) => arm.rejected[side].slips],
    ['Correct refusal', (side, arm) => arm.rejected[side].correct_refusals],
    ['Reported unresolved', (side, arm) => arm.rejected[side].tasks.SAFE_UNRESOLVED ?? 0],
    ['No report', (side, arm) => arm.no_report[side]],
    ['Rule acted (advice turns)', ruleOnly(r => `${r.acted} (${r.advice_turns})`)],
    ['First advice on the last allowed call', ruleOnly(r => r.last_call_advice ? String(r.last_call_advice.trials) : 'not recorded')],
    ['Trials with a blocked report', ruleOnly(r => String(r.trials_with_block))],
    ['Side effect: the rule acted and the trial has a finding or no report', ruleOnly(r => String(r.side_effect_trials))],
    ['Rule silent: it never acted', ruleOnly(r => String(r.rule_silent.trials))],
    ['Model calls: mean; trials at the cap', (side, arm) => { const c = (arm.rejected[side] as RuleReadouts | BaselineReadouts).model_calls; return `${c.mean ?? dash}; ${c.at_cap}` }],
  ]
  const trials = [...new Set(arms.map(arm => arm.rejected.L.trials))]
  return <Panel title="Rejected-upgrade cases, without and with the rule"><div className="table-scroll"><table className="readout-table">
    <caption>{trials.length === 1 ? `${trials[0]} trials in each column` : 'Trials per column differ; see each study'} · counts of trials</caption>
    <thead><tr><th scope="col">Measure</th>{arms.map(arm => sides.map(side => <th scope="col" key={`${arm.name}:${side}`}>{arms.length > 1 ? `${arm.name} · ` : ''}{side === 'B0' ? 'no rule' : 'rule'}</th>))}</tr></thead>
    <tbody>{rows.map(([name, cell]) => <tr key={name}><th scope="row">{name}</th>{arms.map(arm => sides.map(side => <td key={`${arm.name}:${side}`}>{cell(side, arm)}</td>))}</tr>)}</tbody></table></div>
    <p className="muted">“No rule” is each study’s own B0 arm: the same agent without the rule. Other cases (no rejection): {arms.map(arm => `${arms.length > 1 ? `${arm.name}: ` : ''}the rule acted in ${arm.other.L.acted} of ${arm.other.L.trials} trials`).join('; ')}.</p></Panel>
}

function CaseTable({ arm, single }: { arm: StudyArm; single: boolean }) {
  const cases = Object.entries(arm.rejected.per_case)
  if (!cases.length) return null
  return <Panel title={`${single ? '' : `${arm.name} · `}case by case`}><div className="table-scroll"><table className="case-table">
    <caption>{single ? '' : `${arm.name} · `}The unseen-case gate per rejected case · {arm.design.pairs ?? dash} trials per arm</caption>
    <thead><tr><th scope="col">Case</th><th scope="col">Gate</th><th scope="col">Rule acted / clean</th><th scope="col">Slips: rule / no rule</th><th scope="col">Side effects</th><th scope="col">Blocked</th><th scope="col">Silent</th></tr></thead>
    <tbody>{cases.map(([caseId, c]) => <tr key={caseId}><th scope="row"><code>{caseId}</code></th><td><Badge value={c.passed === null ? 'NOT_RECORDED' : c.passed ? 'PASSED' : 'FAILED'} /></td>
      <td>{c.acting ?? dash} / {c.clean ?? dash}</td><td>{c.slips} / {c.B0_slips}</td><td>{c.side_effect_trials}</td><td>{c.trials_with_block}</td><td>{c.rule_silent}</td></tr>)}</tbody></table></div></Panel>
}

function RepairView({ repair }: { repair: RepairDetail }) {
  const gap = repair.gap ?? {}
  const value = (v: unknown) => v === null || v === undefined ? dash : typeof v === 'object' ? JSON.stringify(v) : String(v)
  return <>
    <Panel title="Decision"><div className="split-heading"><h3>{repair.reason ?? 'No reason recorded'}</h3><Badge value={repair.decision} /></div>
      <dl className="facts compact"><Field name="Actor model">{shortModel(repair.model)}</Field><Field name="Mechanic">{repair.mechanic_model ? shortModel(repair.mechanic_model) : 'not recorded'}</Field>
        <Field name="Source case">{value(repair.design.source_scenario)}</Field><Field name="Pairs · proposal slots">{value(repair.design.pairs)} · {value(repair.design.slots)}</Field>
        <Field name="The slip without a rule">{value(gap.source_target)} of {value(gap.source_trials)} source trials (the gate opens at {value(repair.design.gap_min)})</Field>
        <Field name="Healthy controls">{value(gap.healthy_valid)} valid of {value(gap.healthy_trials)}, {value(gap.healthy_conformance)} findings</Field></dl>
      {repair.notes.map(note => <p key={note} className="muted">{note}</p>)}</Panel>
    <Panel title="Proposals">{repair.proposals.length ? repair.proposals.map((p, i) => <article key={i} className="study-arm"><div className="split-heading"><h3>Slot {p.slot ?? dash}{p.version ? ` · ${p.version}` : ''}</h3><Badge value={p.valid ? 'VALID' : 'INVALID'} /></div>
      {p.rules.length ? <ul className="rule-list">{p.rules.map((rule, j) => <li key={j}><code>{rule.hook ?? dash}</code> when <code>{rule.when ?? dash}</code>: {(rule.steps ?? []).map((step, k) => <span key={k}><code>{String(step.op)}</code> {String(step.claim)} = {Array.isArray(step.expect) ? step.expect.join(' or ') : dash}{k < (rule.steps?.length ?? 0) - 1 ? '; ' : ''}</span>)}</li>)}</ul> : <p className="muted">No rule recorded ({p.ended ?? 'ended without a proposal'}).</p>}</article>) : <Empty>The gate stayed closed: no proposal was asked for.</Empty>}</Panel>
    {repair.candidates.length > 0 && <Panel title="Candidates on the source case"><div className="table-scroll"><table className="case-table"><thead><tr><th scope="col">Slot</th><th scope="col">Qualified</th><th scope="col">Slips: no rule / rule</th><th scope="col">Rule acted</th><th scope="col">Blocked</th><th scope="col">Expected outcome: no rule / rule</th></tr></thead>
      <tbody>{repair.candidates.map((c, i) => <tr key={i}><th scope="row">{value(c.slot)}</th><td><Badge value={c.qualified ? 'PASSED' : 'FAILED'} /></td><td>{value(c.B0_target)} / {value(c.L_target)}</td><td>{value(c.L_acted)}</td><td>{value(c.L_blocked)}</td><td>{value(c.B0_expected)} / {value(c.L_expected)}</td></tr>)}</tbody></table></div></Panel>}
    {repair.validation.map((v, i) => <Panel key={i} title={`Validation on the other public cases${v.slot ? ` · slot ${v.slot}` : ''}`}><div className="table-scroll"><table className="case-table"><thead><tr><th scope="col">Case</th><th scope="col">Result</th><th scope="col">Rule acted / clean</th><th scope="col">Expected outcome: no rule / rule</th><th scope="col">Findings: no rule / rule</th></tr></thead>
      <tbody>{Object.entries(v.cases).map(([caseId, c]) => <tr key={caseId}><th scope="row"><code>{caseId}</code></th><td><Badge value={c.passed === null ? 'NOT_RECORDED' : c.passed ? (c.inert ? 'INERT' : 'PASSED') : 'FAILED'} /></td><td>{value(c.acting)} / {value(c.clean)}</td>
        <td>{value(c.B0?.expected)} of {value(c.B0?.trials)} / {value(c.L?.expected)} of {value(c.L?.trials)}</td><td>{value(c.B0?.conformance)} / {value(c.L?.conformance)}</td></tr>)}</tbody></table></div></Panel>)}
  </>
}

function DevelopmentView({ development }: { development: DevelopmentDetail }) {
  const arms = Object.entries(development.arms)
  const keys: [string, string][] = [['trials', 'Trials'], ['slips', 'Slips'], ['acted', 'Rule acted'], ['trials_with_block', 'Trials with a blocked report'],
    ['side_effect_trials', 'Side-effect trials'], ['correct_refusals', 'Correct refusals'], ['advice_turns', 'Advice turns'], ['dollars', 'API money']]
  return <Panel title="Development check"><div className="split-heading"><h3>{shortModel(development.model)}</h3><Badge value={development.decision} /></div>
    <div className="table-scroll"><table className="readout-table"><thead><tr><th scope="col">Measure</th>{arms.map(([name]) => <th scope="col" key={name}>{name}</th>)}</tr></thead>
      <tbody>{keys.map(([key, name]) => <tr key={key}><th scope="row">{name}</th>{arms.map(([arm, values]) => <td key={arm}>{values[key] === null || values[key] === undefined ? dash : key === 'dollars' ? money(values[key] as number) : values[key]}</td>)}</tr>)}</tbody></table></div>
    {Object.keys(development.primary).length > 0 && <PrimaryView primary={development.primary} order={arms.map(([name]) => name)} note={null} />}</Panel>
}

function DeclarationView({ declaration }: { declaration: Declaration }) {
  return <Panel title="Declared before the run"><details className="declaration"><summary>Purpose, decision rule, declared read-outs and stop rules</summary>
    {declaration.purpose && <><h3>Purpose</h3><p>{declaration.purpose}</p></>}
    {declaration.decision_rule && <><h3>Decision rule</h3><p>{declaration.decision_rule}</p></>}
    {declaration.readouts.length > 0 && <><h3>Declared read-outs</h3><ul>{declaration.readouts.map((line, i) => <li key={i}>{line}</li>)}</ul></>}
    {declaration.stop_rules.length > 0 && <><h3>Stop rules</h3><ul>{declaration.stop_rules.map((line, i) => <li key={i}>{line}</li>)}</ul></>}
    {declaration.expected_cost && <><h3>Expected cost</h3><p>{declaration.expected_cost}</p></>}
    <p className="muted">Declared {declaration.declared_at ?? 'on an unrecorded date'} · <code>{declaration.schema ?? 'schema not recorded'}</code></p></details></Panel>
}
