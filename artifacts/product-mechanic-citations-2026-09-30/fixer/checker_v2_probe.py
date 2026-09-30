"""Fixer probe ($0, offline, under the guard): the fixed checker v2 on (1) the integrity review's 10 probe sentences
(review-integrity/checker-v2-negation-probe.txt), (2) the sentences a native v2 Mechanic request now carries: the block's
meaning sentence, the memory pointer and each sentence of the unchanged v2 memory text. Imports the checker unchanged.
Run from faultlab/backend:  ../.venv/bin/python -B ../artifacts/product-mechanic-citations-2026-09-30/fixer/checker_v2_probe.py
"""
import importlib.util, json, re, sys
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import guard  # noqa: E402,F401
spec = importlib.util.spec_from_file_location('c2', '../scripts/experiments/check_evidence_gap_misreading_v2.py')
c2 = importlib.util.module_from_spec(spec); spec.loader.exec_module(c2)
from app.lab.citation_status import MEANING, MEMORY_POINTER  # noqa: E402
from app.lab.diagnosis import V2_MEMORY  # noqa: E402
integrity = [re.match(r"^(?:CLAIM|none)\s+'(.*)'\s+matched=", line).group(1) for line in
             (HERE.parent / 'review-integrity/checker-v2-negation-probe.txt').read_text().splitlines() if line.strip()]
def row(text):
    counted, denied = c2.claim_matches(text)
    return {'text': text, 'counted': [m['phrase'] for m in counted], 'denied': [(m['phrase'], m['denial']) for m in denied]}
request_texts = [('meaning', MEANING), ('memory_pointer', MEMORY_POINTER)] + [
    (f'v2_memory_sentence_{i + 1}', s) for i, s in enumerate(re.split(r'(?<=[.!?])\s+', V2_MEMORY))]
out = {'checker_version': c2.CHECKER_VERSION,
       'integrity_probe': [row(t) for t in integrity],
       'integrity_probe_counted': sum(1 for t in integrity if c2.claim_matches(t)[0]),
       'request_texts': [{'name': n, **row(t)} for n, t in request_texts],
       'note': 'A counted match in a v2 memory sentence is the known limit: a Mechanic repeating that unchanged rule text '
               'would count, and only the human check of claim_matches sentences catches it.'}
print(json.dumps(out, indent=1))
