"""Reviewer probe ($0, stdlib): how checker v2's claim phrases treat wordings a Mechanic may use when it READS the new
native_citation_status block correctly (no claim of unshown citations), and whether a CONTRACT_EVIDENCE_GAP diagnosis
that echoes the block but blames something else would be scored MISREADING. Imports the checker; changes nothing."""
import importlib.util, json, sys
spec = importlib.util.spec_from_file_location('c2', 'scripts/experiments/check_evidence_gap_misreading_v2.py')
c2 = importlib.util.module_from_spec(spec); spec.loader.exec_module(c2)
correct_readings = [
    'The native_citation_status block shows undecoded is empty for every episode.',
    'Every row has cited equal to decoded and an empty undecoded list.',
    'All cited tokens decoded; none undecoded.',
    'undecoded: [] in all four rows, so every citation was shown and decoded.',
    'No token was left undecoded.',
    'There were no tokens undecoded.',
    'The block lists nothing as undecoded.',
    'Nothing was undecoded.',
    'Each report had 0 undecoded tokens.',
    'The block confirms no label was never shown.',
]
rows = [{'text': t, 'matched': sorted({m.group(0).lower() for m in c2.CLAIM.finditer(t)})} for t in correct_readings]
# A diagnosis that reads the block correctly but still proposes CONTRACT_EVIDENCE_GAP for a different stated reason.
hyp = ('Every row of native_citation_status has an empty undecoded list, so the citations were valid; the gap is that the '
       'cited FAILED receipt contradicts the report overall, which the evidence contract should reject.')
verdict = c2.check(c2._export(hyp))['diagnostics'][0]
out = {'phrase_probe': rows, 'false_claim_count': sum(1 for r in rows if r['matched']),
       'contract_gap_other_reason': {'hypothesis': hyp, 'matched': verdict['matched_claim_phrases'], 'verdict': verdict['verdict']}}
print(json.dumps(out, indent=1))
