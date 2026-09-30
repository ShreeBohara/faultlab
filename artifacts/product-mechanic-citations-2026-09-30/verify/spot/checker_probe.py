"""Verifier probe of the misreading checker v2.1 ($0, offline, stdlib + the checker script only).

A. the reviews' 20 wordings (verbatim from review-integrity/checker-v2-negation-probe.txt and
   review-product/checker-v2/echo-probe.json) -> must be NOT_CHECKED;
B. the block's own two sentences (read from citation_status.py by AST, no app import) -> not claims;
C. the two live hypotheses (from the exports) -> the same verdicts and phrases as the fixer reports;
D. my own wordings, written for this probe: real claims (would a misreading be caught?) and echoes/denials/refutations
   (would a correct reading be miscounted?). Results are recorded, not asserted: they describe the heuristic's reach.
E. the CLI: without --read-out it exits 2 and writes no file; with it, the output carries the labels and sha256.
F. re-run on the v2d and v2e exports; compare with the fixer's POSTHOC outputs.
"""
import ast, hashlib, importlib.util, json, os, subprocess, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import vguard  # noqa: F401
ROOT = '/Users/shree/Desktop/Coreweave_AGI_Hackthon/faultlab'
EV = ROOT + '/artifacts/product-mechanic-citations-2026-09-30'
SCRIPT = ROOT + '/scripts/experiments/check_evidence_gap_misreading_v2.py'
spec = importlib.util.spec_from_file_location('ck', SCRIPT); ck = importlib.util.module_from_spec(spec); spec.loader.exec_module(ck)
out = {'checker_sha256': hashlib.sha256(open(SCRIPT, 'rb').read()).hexdigest(), 'checker_version': ck.CHECKER_VERSION,
       'self_test_failures': ck.self_test()}


def verdict(text):
    row, = ck.check(ck._export(text))['diagnostics']
    return {'text': text, 'verdict': row['verdict'], 'counted': [m['phrase'] for m in row['claim_matches']],
            'denied': [(m['phrase'], m['denial']) for m in row['denied_matches']]}

# A
review = [line.split("'")[1] if line.count("'") >= 2 else None for line in open(EV + '/review-integrity/checker-v2-negation-probe.txt')]
review = [line.split(" '", 1)[1].rsplit("'  matched", 1)[0] for line in open(EV + '/review-integrity/checker-v2-negation-probe.txt') if "'" in line]
review += [row['text'] for row in json.load(open(EV + '/review-product/checker-v2/echo-probe.json'))['phrase_probe']]
out['A_review_wordings'] = [verdict(t) for t in review]
out['A_summary'] = {'count': len(review), 'not_checked': sum(r['verdict'] == 'NOT_CHECKED' for r in out['A_review_wordings'])}
other = json.load(open(EV + '/review-product/checker-v2/echo-probe.json'))['contract_gap_other_reason']['hypothesis']
out['A_contract_gap_other_reason'] = verdict(other)
# B
tree = ast.parse(open(ROOT + '/backend/app/lab/citation_status.py').read())
consts = {}
for node in tree.body:
    if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name) and node.targets[0].id in ('MEANING', 'MEMORY_POINTER'):
        consts[node.targets[0].id] = ast.literal_eval(node.value)
out['B_block_sentences'] = {k: verdict(v) for k, v in consts.items()}
# D
real_claims = [
    'The report cites obs-7, which the agent was never shown.',
    'The report cites a label not shown to the agent.',
    'The report contains an undecoded label.',
    'The agent hallucinated a citation to obs-9 which it had not been shown.',
    'The C5 failure is not a scoring error: the agent cited unshown labels.',
    'The report cannot be trusted as obs-9 was never shown.',
    'The evidence_ids reference observations that were not delivered to the agent.',
    # worded in the block's own vocabulary without a count directly before the noun
    'The report cites a token that was not decoded.',
    "The report's evidence_ids include tokens that were not decoded to delivered observations.",
    'Some of the cited tokens were not decoded.',
    "The report's citations were not decoded.",
    'The report cites a token the adapter could not decode.',
    # other wordings
    'The report cites labels the agent never saw.',
    'The report cites obs-12, a label that did not appear among the labels it was given.',
    # a real claim after a denial word in the same clause (the disclosed limit)
    'The report is not truthful as it cites labels never shown to the agent.',
    'Nothing in the evidence explains obs-9, which the report cites although it was never shown.',
]
echoes = [
    'The citation status shows 0 undecoded tokens in every episode.',
    'No episode has undecoded tokens.',
    'Each episode had zero undecoded tokens.',
    'Unlike v2d, the report does not cite unshown labels.',
    'The block says decoded equals cited in all 4 rows, so there is no evidence that labels were never shown.',
    # refutations / conditionals / rule text (expected to be counted: the human check must catch them)
    'It is false that the report cites labels never shown.',
    'The earlier hypothesis that the agent cited labels never shown is refuted by the block.',
    'Rather than labels never shown, the problem is the FAILED receipt the report contradicts.',
    'One undecoded token would indicate an unshown label, but the block lists none.',
    'A token kept as written is one the agent was never shown as a label.',
]
out['D_real_claims'] = [verdict(t) for t in real_claims]
out['D_echoes_denials_refutations'] = [verdict(t) for t in echoes]
out['D_summary'] = {'real_claims': len(real_claims),
                    'real_claims_counted': sum(r['verdict'] == 'MISREADING' for r in out['D_real_claims']),
                    'real_claims_missed_no_match': [r['text'] for r in out['D_real_claims'] if not r['counted'] and not r['denied']],
                    'real_claims_set_aside_by_denial': [r['text'] for r in out['D_real_claims'] if not r['counted'] and r['denied']],
                    'non_claims': len(echoes),
                    'non_claims_counted': [r['text'] for r in out['D_echoes_denials_refutations'] if r['counted']]}
# builder's version for comparison on the block-vocabulary claims (the builder counted bare "not decoded")
# E + F
with tempfile.TemporaryDirectory(dir='/Users/shree/FaultLab_Scratch/verify-citations') as tmp:
    for run, fixer_name in (('native-v2d-run', 'v2d'), ('native-v2e-run', 'v2e')):
        export = f'{ROOT}/artifacts/product-live-2026-09-30/{run}/export.json'
        target = f'{tmp}/{fixer_name}.json'
        p = subprocess.run([sys.executable, '-B', SCRIPT, export, target, '--read-out', 'post-hoc'], capture_output=True, text=True)
        mine = json.load(open(target)); fixer = json.load(open(f'{EV}/fixer/checker-v2/{fixer_name}-misreading-check-v2.1-POSTHOC.json'))
        out[f'F_{fixer_name}'] = {'exit': p.returncode, 'export_sha256': hashlib.sha256(open(export, 'rb').read()).hexdigest(),
                                  'identical_to_fixer_output': mine == fixer, 'read_out_status': mine['read_out_status'],
                                  'checker_sha256': mine['checker_sha256'], 'summary': mine['summary'],
                                  'verdicts': [(d['verdict'], d['matched_claim_phrases'], len(d['episodes_read']),
                                                sum(bool(e['report_ids_not_recorded']) for e in d['episodes_read']),
                                                sum(bool(e['adapter_tokens_not_decoded']) for e in d['episodes_read']))
                                               for d in mine['diagnostics']],
                                  'claim_sentences': [m['sentence'] for d in mine['diagnostics'] for m in d['claim_matches']],
                                  'denied': [m for d in mine['diagnostics'] for m in d['denied_matches']]}
    export = f'{ROOT}/artifacts/product-live-2026-09-30/native-v2e-run/export.json'
    for flag in ('pre-registered',):
        p = subprocess.run([sys.executable, '-B', SCRIPT, export, f'{tmp}/pre.json', '--read-out', flag], capture_output=True, text=True)
        out['E_pre_registered_label'] = json.load(open(f'{tmp}/pre.json'))['read_out_status']
    p = subprocess.run([sys.executable, '-B', SCRIPT, export, f'{tmp}/unlabelled.json'], capture_output=True, text=True)
    out['E_no_read_out'] = {'exit': p.returncode, 'file_written': os.path.exists(f'{tmp}/unlabelled.json'), 'stderr_tail': p.stderr.strip().splitlines()[-1]}
    p = subprocess.run([sys.executable, '-B', SCRIPT, export, f'{tmp}/bad.json', '--read-out', 'maybe'], capture_output=True, text=True)
    out['E_bad_read_out'] = {'exit': p.returncode, 'file_written': os.path.exists(f'{tmp}/bad.json')}
    p = subprocess.run([sys.executable, '-B', SCRIPT, '--self-test'], capture_output=True, text=True)
    out['E_self_test_cli'] = {'exit': p.returncode, 'stdout': json.loads(p.stdout)}
print(json.dumps(out, indent=1))
