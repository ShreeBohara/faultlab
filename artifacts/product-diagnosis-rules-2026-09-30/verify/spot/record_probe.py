"""Verifier spot-check ($0, offline): review finding MEDIUM-1 / F3 (intervention_ran means a fresh trial ran; early_end;
the statement names the early end) with the REAL Mechanic (scripted provider), the REAL RecordingDiagnosisMechanic, the
REAL Diagnostician and the REAL referee run_interventions. The runners and every assertion are the verifier's own; only the
FaultSpec / evidence fixtures are imported from the product's test module (they are data).

Seven endings, each run with the rule OFF and ON: the rule must not change the diagnostic kind, the proposed kind, the
intervention results/pairs/limitations or the trial count (gate invariance), and the ON record must say what happened.
Extra endings beyond the fixer's five: INVALID_CALLBACK_RESULT, INVALID_OR_UNTRIGGERED_TRIAL, and a Stop in the middle of
the first pair (one trial, zero complete pairs).
Verifier correction after the first run: run_interventions does not break inside a pair after an invalid trial (it sets the
reason and still runs the pair's other arm), so the untriggered ending runs 2 trials and 1 complete pair; the first run of
this script expected 1 and 0, which was the verifier's own error (record-probe-first-run.json keeps that run). Also: the consistency refusals (no attempt state; fresh trials without an
experiment) and the INVALID_OUTPUT / VALID_NO_REQUEST statements.
Run from faultlab/backend with ../.venv/bin/python -B; temp stores live under /Users/shree/FaultLab_Scratch.
"""
import asyncio, json, os, shutil, sys
from pathlib import Path
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import vguard  # noqa: E402,F401
BACKEND = Path('/Users/shree/Desktop/Coreweave_AGI_Hackthon/faultlab/backend')
sys.path.insert(0, str(BACKEND)); sys.path.insert(0, str(BACKEND / 'tests' / 'lab')); sys.path.insert(0, str(BACKEND / 'tests'))
os.chdir(BACKEND)
TMP = Path('/Users/shree/FaultLab_Scratch/verify-diagnosis-rules/spot-tmp')

from app.agents.mechanic import Mechanic  # noqa: E402
from app.contracts.models import TrialResult, Usage, canonical_json, content_hash  # noqa: E402
from app.lab import diagnosis_protocol  # noqa: E402
from app.lab.diagnosis import Diagnostician  # noqa: E402
from app.lab.storage import LabStore  # noqa: E402
from app.providers.runtime import RuntimeGeneration  # noqa: E402
import app.lab.diagnosis as diagnosis_module  # noqa: E402
from test_diagnosis_rules import RECIPE, POLICY, EVIDENCE, CAMPAIGN  # noqa: E402  (fixture data only)

MODEL = 'deepseek-ai/DeepSeek-V4-Pro-0813'
RESULTS = []


def check(name, ok, detail=''):
    RESULTS.append((name, bool(ok), detail))


class Provider:
    def __init__(self, outputs): self.outputs = list(outputs)
    def role_model(self, role): return MODEL
    async def complete(self, messages, **kwargs):
        out = self.outputs.pop(0)
        return RuntimeGeneration(out(messages) if callable(out) else out, MODEL, input_tokens=10, output_tokens=5)


class Ledger:
    def __init__(self): self.reservations = {}
    def consume_call(self, **k): pass
    def reconcile(self, g): pass
    def reserve(self, name, calls, tokens=None): self.reservations[name] = calls
    def release(self, name): self.reservations.pop(name, None)


def reply(kind, *, requested=True, length=None):
    def out(messages):
        ctx = json.loads(messages[1]['content'])
        hyp = 'Verifier fixture: removing the delay removes the violation.' if length is None else 'v' * length
        return canonical_json({'proposed_kind': kind, 'hypothesis': hyp, 'evidence_ids': ctx['evidence_ids'][:1],
                               'requested_intervention_id': ctx['intervention_ids'][0] if requested else None})
    return out


def trial(spec, index, n, *, violation, triggered=True):
    return TrialResult(episode_id=f'v-ep-{n}', world_id=f'v-w-{n}', scenario_hash=content_hash(spec), policy_hash=POLICY.policy_hash,
                       arm='B0', trial_index=index, lifecycle='COMPLETED', outcome='VIOLATION' if violation else 'COMPLETED',
                       failed_checks=['C3'] if violation else [], fault_scheduled=bool(spec.primitives),
                       fault_triggered=triggered and bool(spec.primitives), usage=Usage(actor_calls=1, http_attempts=1))


class VRunner:
    """The verifier's own fresh-trial runner. ending picks how the first experiment ends."""
    def __init__(self, ending): self.ending, self.calls = ending, 0
    async def run(self, campaign, spec, policy, *, purpose, trial_index, fixture_id, ledger, reservation, stop):
        n = self.calls; self.calls += 1
        control = content_hash(spec) == content_hash(RECIPE)
        if self.ending == 'callback_error': raise TimeoutError('verifier: trial could not start')
        if self.ending == 'invalid_result': return None
        if self.ending == 'untriggered' and n == 0:
            return trial(spec, trial_index, n, violation=True, triggered=False)
        return trial(spec, trial_index, n, violation=control)


def reproduction():
    return [TrialResult(episode_id=f'v-r{i}', world_id=f'v-rw{i}', scenario_hash=content_hash(RECIPE), policy_hash=POLICY.policy_hash, arm='B0',
                        trial_index=i, lifecycle='COMPLETED', outcome='VIOLATION', failed_checks=['C3'], fault_scheduled=True,
                        fault_triggered=True, usage=Usage(actor_calls=1, http_attempts=1)) for i in range(3)]


async def one(label, ending, answers, flag):
    original = diagnosis_module.run_interventions
    import functools
    if ending == 'preflight':
        diagnosis_module.run_interventions = functools.partial(original, validate=lambda recipe: False)
    runner = VRunner(ending)
    stop = {'stop_first': (lambda: True), 'stop_mid_pair': (lambda: runner.calls >= 1)}.get(ending, lambda: False)
    store = LabStore(TMP / f'{label}-{"on" if flag else "off"}.db')
    mech = Mechanic(Provider(answers), store, Ledger()); chain = mech
    if flag:
        mech.diagnosis_protocol = diagnosis_protocol.declaration()
        chain = diagnosis_protocol.RecordingDiagnosisMechanic(mech, mech)
    counter = SimpleNamespace(counterexample_id='v-counter', target_invariant='C3', attempted_count=3, valid_count=3, target_violation_count=3)
    try:
        diag, run = await Diagnostician(store, runner, Ledger(), chain).run(CAMPAIGN, counter, RECIPE, POLICY, reproduction(), evidence=EVIDENCE, stop=stop)
    finally:
        diagnosis_module.run_interventions = original
    rec = diagnosis_protocol.record(store, CAMPAIGN, counter, diag, run, chain) if flag else None
    stored = store.get_record('diagnosis_requests', diag.diagnostic_id) if flag else None
    store.close()
    return diag, run, rec, stored


def summary(diag, run):
    return {'kind': diag.kind, 'proposed_kind': diag.proposed_kind, 'trials': len(run.trials),
            'experiments': [(e.result, len(e.trial_pairs), list(e.limitations)) for e in run.experiments]}


async def main():
    if TMP.exists(): shutil.rmtree(TMP)
    TMP.mkdir(parents=True)
    cases = [  # ending, trials, pairs, early_end, phrase
        ('preflight', 0, 0, 'PREFLIGHT_REJECTED', 'preflight rejected its recipes before any trial'),
        ('stop_first', 0, 0, 'STOPPED', 'a Stop request stopped it'),
        ('callback_error', 0, 0, 'CALLBACK_ERROR:TimeoutError', 'a trial could not run'),
        ('invalid_result', 0, 0, 'INVALID_CALLBACK_RESULT', 'a trial returned an invalid result'),
        ('untriggered', 2, 1, 'INVALID_OR_UNTRIGGERED_TRIAL', 'a trial was invalid or its fault did not fire'),
        ('stop_mid_pair', 1, 0, 'STOPPED', 'a Stop request stopped it'),
        ('full', 6, 3, None, None),
    ]
    table = []
    for ending, trials, pairs, early, phrase in cases:
        off = await one(ending, ending, [reply('POLICY_GAP')], False)
        on = await one(ending, ending, [reply('POLICY_GAP')], True)
        rec = on[2]
        check(f'{ending}: rule changes no kind/result/trials', summary(*off[:2]) == summary(*on[:2]), json.dumps([summary(*off[:2]), summary(*on[:2])]))
        check(f'{ending}: stored record equals returned record', canonical_json(on[3]) == canonical_json(rec))
        check(f'{ending}: fresh trials {trials}', rec['fresh_intervention_trials'] == trials == len(on[1].trials), str(rec['fresh_intervention_trials']))
        check(f'{ending}: intervention_ran is {trials > 0}', rec['intervention_ran'] is (trials > 0))
        check(f'{ending}: experiment recorded', rec['intervention_experiment_recorded'] is True)
        row, = rec['interventions']
        check(f'{ending}: pairs {pairs}, early_end {early}', row['trial_pairs'] == pairs and row['early_end'] == early, json.dumps(row))
        st = rec['statement']
        if early:
            check(f'{ending}: statement names the early end', early in st and phrase in st and f'after {pairs} of 3 trial pairs' in st, st)
            check(f'{ending}: statement says whether a fresh trial ran',
                  ('no fresh trial ran' in st) if trials == 0 else (f'{trials} fresh intervention trial(s) ran' in st), st)
            check(f'{ending}: verdict INCONCLUSIVE', rec['verdict'] == 'INCONCLUSIVE' and row['result'] == 'INCONCLUSIVE')
        else:
            check('full: SUPPORTED, POLICY_GAP, no early end in statement',
                  row['result'] == 'SUPPORTED' and rec['verdict'] == 'POLICY_GAP' and 'ended early' not in st and '6 fresh intervention trial(s) ran' in st, st)
        table.append({'ending': ending, 'intervention_ran': rec['intervention_ran'], 'experiment_recorded': rec['intervention_experiment_recorded'],
                      'fresh_trials': rec['fresh_intervention_trials'], 'row': row, 'verdict': rec['verdict'], 'statement': st})
    # INVALID_OUTPUT (two 614-character answers) and VALID_NO_REQUEST.
    off = await one('invalid', 'full', [reply('CONTRACT_EVIDENCE_GAP', length=614)] * 2, False)
    on = await one('invalid', 'full', [reply('CONTRACT_EVIDENCE_GAP', length=614)] * 2, True)
    rec = on[2]
    check('invalid: rule changes no kind/result', summary(*off[:2]) == summary(*on[:2]))
    check('invalid: INVALID_OUTPUT, code_default, 2 attempts, nothing ran',
          rec['proposal_status'] == 'INVALID_OUTPUT' and rec['recorded_proposed_kind_source'] == 'code_default' and len(rec['attempts']) == 2
          and rec['intervention_ran'] is False and rec['intervention_experiment_recorded'] is False and rec['recorded_proposed_kind'] == 'INCONCLUSIVE', json.dumps(rec['attempts']))
    check('invalid: repair errors state 600 and 614', all(e.get('max_characters') == 600 and e.get('your_characters') == 614
                                                         for a in rec['attempts'] for e in a['validation_errors'] if e['type'] == 'string_too_long')
          and all(any(e['type'] == 'string_too_long' for e in a['validation_errors']) for a in rec['attempts']))
    check('invalid: statement', '614 of at most 600 characters' in rec['statement'] and 'code default' in rec['statement'], rec['statement'])
    table.append({'ending': 'invalid_output', 'record': {k: rec[k] for k in ('proposal_status', 'recorded_proposed_kind', 'recorded_proposed_kind_source',
                                                                          'intervention_ran', 'intervention_experiment_recorded', 'statement')}})
    on = await one('decline', 'full', [reply('CONTRACT_EVIDENCE_GAP', requested=False)], True)
    rec = on[2]
    check('decline: VALID_NO_REQUEST, model, nothing ran', rec['proposal_status'] == 'VALID_NO_REQUEST' and rec['recorded_proposed_kind_source'] == 'model'
          and rec['intervention_ran'] is False and rec['intervention_experiment_recorded'] is False and 'requested no intervention' in rec['statement'], rec['statement'])
    # Consistency refusals: no attempt state; fresh trials with no experiment.
    diag = SimpleNamespace(diagnostic_id='v-diag', proposed_kind='POLICY_GAP', kind='INCONCLUSIVE')
    counter = SimpleNamespace(counterexample_id='v-counter', target_invariant='C3')
    for label, wrapper, run in (
            ('no attempt state', SimpleNamespace(last=None), SimpleNamespace(trials=[], experiments=[])),
            ('trials without experiment', SimpleNamespace(last={'attempts': {'output_refs': ['o1'], 'validation_errors': [[]], 'request_id': 'r', 'first_turn_hash': 'h'},
                                                                'ref': 'o1', 'raws': ['{}'], 'proposal': SimpleNamespace(requested_intervention_id='i', proposed_kind='POLICY_GAP'),
                                                                'options': []}), SimpleNamespace(trials=[object()], experiments=[]))):
        try:
            diagnosis_protocol.build_record(CAMPAIGN, counter, diag, run, wrapper); check(f'refusal: {label}', False, 'no error raised')
        except RuntimeError as error:
            check(f'refusal: {label}', 'v-diag' in str(error) and 'v-counter' in str(error), str(error))
    shutil.rmtree(TMP)
    return table


table = asyncio.run(main())
out = {'passed': sum(ok for _, ok, _ in RESULTS), 'failed': [r for r in RESULTS if not r[1]], 'checks': [[n, ok] for n, ok, _ in RESULTS], 'table': table}
print(json.dumps(out, indent=1))
print(f'[record_probe] {out["passed"]} of {len(RESULTS)} checks passed', file=sys.stderr)
