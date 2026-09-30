"""Verifier spot-check ($0, offline, no provider): the probe harness scripts/experiments/diagnosis_probe.py after the fixer.

  A. Refusals through main(--execute-live) with a SENTINEL provider factory (it records any call; it must never be
     called): no declaration, wrong sha256, empty approver, clock drift not checked, wrong temperature, empty
     repeats_reading, altered pre-registered outcomes, $9 cap, used output folder.
  B. A scripted "live" run through main() with a scripted provider (no network): 140 calls charged on the probe's own
     ledger, answers.jsonl carries model_id (no served_model), manifest carries the project-ledger note,
     review-blinded.csv has no arm / checker / hint column, scoring reports repeats (14 of 14 keys one distinct answer).
  C. A second scripted run whose provider returns another model id on its third answer: STOPPED, MODEL_ID_DIFFERS.
  D. P1 counting (MEDIUM-2) and P4 'worse' on the verifier's own synthetic rows, calling the harness's scoring functions.
Output folders and declarations live under /Users/shree/FaultLab_Scratch/verify-diagnosis-rules/probe-scripted (deleted
at the end; the summary is printed). Run from faultlab/ with .venv/bin/python -B.
"""
import asyncio, contextlib, csv, hashlib, importlib.util, io, json, os, shutil, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import vguard  # noqa: E402,F401

ROOT = Path(os.environ.get('PROBE_ROOT', '/Users/shree/Desktop/Coreweave_AGI_Hackthon/faultlab'))  # PROBE_ROOT: the verifier's scratch tree for negative controls
SCR = Path('/Users/shree/FaultLab_Scratch/verify-diagnosis-rules/probe-scripted')
spec = importlib.util.spec_from_file_location('diagnosis_probe_under_verification', ROOT / 'scripts/experiments/diagnosis_probe.py')
probe = importlib.util.module_from_spec(spec); spec.loader.exec_module(probe)
_real_main = probe.main
PRINTED = io.StringIO()
def _quiet_main(*a, **k):
    with contextlib.redirect_stdout(PRINTED), contextlib.redirect_stderr(PRINTED):
        return _real_main(*a, **k)
probe.main = _quiet_main
from app.providers.runtime import RuntimeGeneration  # noqa: E402
from app.contracts.models import canonical_json  # noqa: E402

RESULTS = []
def check(name, ok, detail=''): RESULTS.append((name, bool(ok), str(detail)[:400]))

SENTINEL_CALLS = []
def sentinel():
    SENTINEL_CALLS.append(1); raise AssertionError('verifier sentinel: a provider was built')


def write_decl(path, value):
    data = json.dumps(value, indent=1, sort_keys=True).encode()
    path.write_bytes(data)
    return hashlib.sha256(data).hexdigest()


class Scripted:
    """Answers every request with one fixed answer per request key (so repeats are identical), built from the request."""
    def __init__(self, other_model_at=None): self.calls = 0; self.other_model_at = other_model_at; self.closed = False
    async def complete(self, messages, *, role, max_output_tokens, timeout_seconds):
        assert role == 'mechanic' and max_output_tokens == 2000 and timeout_seconds == 20
        self.calls += 1
        ctx = json.loads(messages[1]['content'])
        repair = len(messages) == 4
        hyp = ('Shortened: removing the delay removes the premature confirmation.' if repair else
               ('The agent cited evidence ids it was not shown, so the citations are wrong.' if 'diagnosis_guide' not in ctx
                else 'The agent confirmed the upgrade although the delivered receipt said FAILED (C3).'))
        raw = canonical_json({'proposed_kind': 'POLICY_GAP', 'hypothesis': hyp, 'evidence_ids': ctx['evidence_ids'][:1],
                              'requested_intervention_id': ctx['intervention_ids'][0]})
        model = probe.MODEL if self.calls != self.other_model_at else 'some-other-model'
        return RuntimeGeneration(raw, model, input_tokens=1000, output_tokens=50)
    async def close(self): self.closed = True


def main():
    if SCR.exists(): shutil.rmtree(SCR)
    SCR.mkdir(parents=True)
    plan, messages = probe.build_plan()
    check('plan: 140 calls, $6.9776 max, cap $8', plan['counts']['total_calls'] == 140 and plan['charge']['max_charge_dollars'] == 6.9776
          and plan['charge']['hard_spend_cap_dollars'] == 8.0, plan['charge'])
    check('plan: temperature 0 frozen from the saved plan', probe.frozen_temperature(plan) == 0)
    check('plan: guide not offered in the plan record', plan['diagnosis_guide']['offered'] is False)
    out = SCR / 'out'
    template = probe.declaration_template(plan, str(out.resolve()))
    check('template: carries exactly PRE_REGISTERED_OUTCOMES incl. repeats and decision rule',
          template['pre_registered_outcomes'] == probe.PRE_REGISTERED_OUTCOMES and set(template['pre_registered_outcomes']) == {'P1', 'P2', 'P3', 'P4', 'repeats', 'decision_rule'})
    check('template: P4 defines worse; P1 counts person-only GUIDE rows',
          "'worse'" in probe.PRE_REGISTERED_OUTCOMES['P4'] and 'without a checker match' in probe.PRE_REGISTERED_OUTCOMES['P1'])
    check('template: preconditions include clock_drift_checked, all False', template['preconditions'] == {k: False for k in probe.PRECONDITIONS}
          and 'clock_drift_checked' in probe.PRECONDITIONS)
    good = {**template, 'approved_by': 'verifier (scripted, not an approval)', 'sampling': {'temperature': 0, 'repeats_reading': 'cell is the unit'},
            'preconditions': {k: True for k in probe.PRECONDITIONS}}
    variants = {
        'no declaration': None,
        'wrong sha256': 'WRONGSHA',
        'empty approver': {**good, 'approved_by': ' '},
        'clock drift not checked': {**good, 'preconditions': {**good['preconditions'], 'clock_drift_checked': False}},
        'clock drift missing': {**good, 'preconditions': {k: True for k in probe.PRECONDITIONS if k != 'clock_drift_checked'}},
        'temperature 0.7': {**good, 'sampling': {'temperature': 0.7, 'repeats_reading': 'x'}},
        'temperature False (a bool, not a number)': {**good, 'sampling': {'temperature': False, 'repeats_reading': 'x'}},
        'empty repeats_reading': {**good, 'sampling': {'temperature': 0, 'repeats_reading': '  '}},
        'altered P4 text': {**good, 'pre_registered_outcomes': {**good['pre_registered_outcomes'], 'P4': 'pass if 5 of 10'}},
        'outcomes missing decision rule': {**good, 'pre_registered_outcomes': {k: v for k, v in good['pre_registered_outcomes'].items() if k != 'decision_rule'}},
        '$9 cap': {**good, 'spend_cap_dollars': 9.0},
        'other plan hash': {**good, 'plan_hash': '0' * 64},
        'other out folder': {**good, 'output_folder': str((SCR / 'elsewhere').resolve())},
    }
    for label, value in variants.items():
        argv = ['--execute-live', '--out', str(out)]
        if value == 'WRONGSHA':
            write_decl(SCR / 'decl.json', good); argv += ['--declaration', str(SCR / 'decl.json'), '--declaration-sha256', '0' * 64]
        elif value is not None:
            digest = write_decl(SCR / 'decl.json', value); argv += ['--declaration', str(SCR / 'decl.json'), '--declaration-sha256', digest]
        rc = probe.main(argv, provider_factory=sentinel)
        check(f'refused: {label}', rc == 2 and not SENTINEL_CALLS and not out.exists(), f'rc={rc} sentinel={len(SENTINEL_CALLS)}')
    # A used output folder is refused too.
    out.mkdir(); (out / 'leftover.txt').write_text('x')
    digest = write_decl(SCR / 'decl.json', good)
    rc = probe.main(['--execute-live', '--out', str(out), '--declaration', str(SCR / 'decl.json'), '--declaration-sha256', digest], provider_factory=sentinel)
    check('refused: used output folder', rc == 2 and not SENTINEL_CALLS, f'rc={rc}')
    shutil.rmtree(out)
    # B. the scripted run.
    provider = Scripted()
    rc = probe.main(['--execute-live', '--out', str(out), '--declaration', str(SCR / 'decl.json'), '--declaration-sha256', digest],
                    provider_factory=lambda: provider)
    manifest = json.loads((out / 'manifest.json').read_text())
    check('scripted: completed, 140 calls sent, provider closed', rc == 0 and manifest['status'] == 'COMPLETED' and provider.calls == 140 and provider.closed, manifest.get('status'))
    check('scripted: ledger charged 140 calls, $6.9776', manifest['ledger']['charged_calls'] == 140 and manifest['ledger']['charged_dollar_upper_bound'] == 6.9776, manifest['ledger'])
    check('scripted: manifest project-ledger note', 'carried total' in manifest['project_ledger_note'] and 'probe-ledger.sqlite3' in manifest['project_ledger_note'], manifest['project_ledger_note'])
    rows = [json.loads(l) for l in (out / 'answers.jsonl').read_text().splitlines()]
    check('scripted: answers.jsonl has model_id, no served_model', len(rows) == 140 and all(r['model_id'] == probe.MODEL and 'served_model' not in r for r in rows))
    with open(out / 'review-blinded.csv', newline='') as handle:
        reader = csv.reader(handle); header = next(reader); body = list(reader)
    check('scripted: review file columns exactly REVIEW_COLUMNS, no arm/checker/hint column', tuple(header) == probe.REVIEW_COLUMNS
          and not any(x in c for c in header for x in ('arm', 'auto', 'hint', 'checker', 'claim')), header)
    check('scripted: review file has the 100 delivered first-turn rows', len(body) == 100)
    scoring = json.loads((out / 'scoring.json').read_text())
    rep = scoring['repeats']
    check('scripted: repeats 14 of 14 keys one distinct answer, temperature 0', rep['keys_with_one_distinct_answer'] == 14 and rep['request_keys'] == 14 and rep['temperature'] == 0, rep['keys_with_one_distinct_answer'])
    check('scripted: P1 pending a person, P4 PASS (all valid, short)', scoring['P1']['status'] == 'PENDING_HUMAN_CONFIRMATION' and scoring['P4']['status'] == 'PASS', (scoring['P1']['status'], scoring['P4']['status']))
    # Verifier correction after the first run: SQLite's -wal / -shm side files of the probe ledger also stay under --out
    # (the first run expected only the eight named files; that expectation was the verifier's, not a harness defect).
    names = sorted(p.name for p in out.iterdir())
    check('scripted: only the named files (plus the ledger\'s SQLite side files) under --out', set(names) - {'probe-ledger.sqlite3-wal', 'probe-ledger.sqlite3-shm'}
          == {'answers.jsonl', 'manifest.json', 'plan.json', 'probe-ledger.sqlite3', 'requests.json', 'review-blinded.csv', 'review-key.json', 'scoring.json'},
          {n: (out / n).stat().st_size for n in names})
    # C. MODEL_ID_DIFFERS.
    out2 = SCR / 'out2'
    digest2 = write_decl(SCR / 'decl2.json', {**good, 'output_folder': str(out2.resolve())})
    provider2 = Scripted(other_model_at=3)
    rc = probe.main(['--execute-live', '--out', str(out2), '--declaration', str(SCR / 'decl2.json'), '--declaration-sha256', digest2], provider_factory=lambda: provider2)
    m2 = json.loads((out2 / 'manifest.json').read_text())
    check('model id differs: STOPPED after 3 answers', rc == 1 and m2['status'] == 'STOPPED' and m2['stop_reason'] == 'MODEL_ID_DIFFERS' and m2['delivered_answers'] == 3, (rc, m2['status'], m2['stop_reason'], m2['delivered_answers']))
    # D. P1 and P4 on synthetic rows.
    def rows_for(arm, specs):
        out_rows = []; n = 0
        for count, auto, human in specs:
            for _ in range(count):
                request = probe.DEV5[n % 4]; n += 1
                out_rows.append({'request': request, 'arm': arm, 'delivered': True, 'auto_claim_matches': ['x'] if auto else [],
                                 'human': {'human_blames_citations_labels_or_evidence_ids': human} if human else {}, 'hypothesis': f'{arm}-{n}'})
        return out_rows
    control_ok = rows_for('CONTROL', [(25, True, 'Y'), (15, False, 'N')])
    cases = {
        'GUIDE 2 confirmed + 3 person-only = 5 -> FAIL': (control_ok, rows_for('GUIDE', [(2, True, 'Y'), (3, False, 'Y'), (35, False, 'N')]), 'FAIL'),
        'GUIDE 2 confirmed + 2 person-only = 4 -> PASS': (control_ok, rows_for('GUIDE', [(2, True, 'Y'), (2, False, 'Y'), (36, False, 'N')]), 'PASS'),
        'GUIDE 10 checker matches the person denies -> PASS': (control_ok, rows_for('GUIDE', [(10, True, 'N'), (30, False, 'N')]), 'PASS'),
        'CONTROL 19 confirmed -> UNINFORMATIVE': (rows_for('CONTROL', [(19, True, 'Y'), (21, False, 'N')]), rows_for('GUIDE', [(40, False, 'N')]), 'UNINFORMATIVE'),
        'CONTROL person-only Y does not lift the premise -> UNINFORMATIVE': (rows_for('CONTROL', [(15, True, 'Y'), (10, False, 'Y'), (15, False, 'N')]), rows_for('GUIDE', [(40, False, 'N')]), 'UNINFORMATIVE'),
        'one GUIDE row not reviewed -> PENDING': (control_ok, rows_for('GUIDE', [(1, False, None), (39, False, 'N')]), 'PENDING_HUMAN_CONFIRMATION'),
    }
    for label, (c, g, expected) in cases.items():
        got = probe._p1(c + g)['status']
        check(f'P1: {label}', got == expected, got)
    def rep_rows(name, arm, ok, n=10):
        return [{'request': name, 'arm': arm, 'delivered': True, 'valid': i < ok, 'hypothesis_characters': 100, 'raw': f'{name}{arm}{i}'} for i in range(n)]
    worse = probe._p4(rep_rows('v2f-dev5', 'REPAIR_RULE1', 9) + rep_rows('v2g-dev5', 'REPAIR_RULE1', 9) + rep_rows('v2f-dev5', 'REPAIR_TODAY', 10) + rep_rows('v2g-dev5', 'REPAIR_TODAY', 10))
    check('P4: 18 vs 20 -> PASS but worse in total', worse['status'] == 'PASS' and worse['rule1_worse_than_today_in_total'] is True, worse['status'])
    same = probe._p4(rep_rows('v2f-dev5', 'REPAIR_RULE1', 10) + rep_rows('v2g-dev5', 'REPAIR_RULE1', 10) + rep_rows('v2f-dev5', 'REPAIR_TODAY', 10) + rep_rows('v2g-dev5', 'REPAIR_TODAY', 10))
    check('P4: 20 vs 20 -> PASS, not worse', same['status'] == 'PASS' and same['rule1_worse_than_today_in_total'] is False)
    # Added after the verifier's negative controls showed no repo test pins the 9-of-10 bar.
    eight = probe._p4(rep_rows('v2f-dev5', 'REPAIR_RULE1', 8) + rep_rows('v2g-dev5', 'REPAIR_RULE1', 10) + rep_rows('v2f-dev5', 'REPAIR_TODAY', 5) + rep_rows('v2g-dev5', 'REPAIR_TODAY', 5))
    check('P4: 8 of 10 on one setup -> FAIL (bar is 9 of 10 on EACH setup), not worse than today (18 vs 10)', eight['status'] == 'FAIL' and eight['rule1_worse_than_today_in_total'] is False, eight['status'])
    shutil.rmtree(SCR)
    check('scratch folder deleted', not SCR.exists())


main()
summary = {'passed': sum(ok for _, ok, _ in RESULTS), 'total': len(RESULTS), 'failed': [r for r in RESULTS if not r[1]],
           'checks': [[n, ok, d] for n, ok, d in RESULTS], 'sentinel_provider_builds': len(SENTINEL_CALLS)}
summary['harness_printed_tail'] = PRINTED.getvalue()[-3000:]
print(json.dumps(summary, indent=1))
print(f'[probe_harness_probe] {summary["passed"]} of {summary["total"]} checks passed; sentinel provider builds {len(SENTINEL_CALLS)}', file=sys.stderr)
