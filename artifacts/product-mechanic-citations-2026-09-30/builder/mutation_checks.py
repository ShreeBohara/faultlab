"""Negative-control mutations ($0, offline): each one undoes or breaks one part of the native citation-status build; the
new tests must fail on it. Every file is restored and its sha256 checked after each mutation.

Run from faultlab/backend:  ../.venv/bin/python -B ../artifacts/product-mechanic-citations-2026-09-30/builder/mutation_checks.py
"""
import hashlib
import subprocess
import sys
from pathlib import Path

BACKEND = Path.cwd()
PY = str(BACKEND.parent / '.venv/bin/python')
TESTS = ['tests/lab/test_citation_status.py']
CHECKER_TESTS = ['tests/experiments/test_check_evidence_gap_misreading_v2.py']

MUTATIONS = [
    ('M1 decoded counts every cited token (ignores the label map)', 'app/lab/citation_status.py',
     "if isinstance(token, str) and token in shown and evidence_of.get(token) == evidence_id)", "if True)", TESTS),
    ('M2 undecoded tokens dropped', 'app/lab/citation_status.py',
     "'undecoded': list(undecoded)}", "'undecoded': []}", TESTS),
    ('M3 no memory pointer in Mechanic requests', 'app/lab/citation_status.py',
     "request['runtime_contract'] = _with_pointer(context.get('runtime_contract'))", "pass", TESTS),
    ('M4 private events read too', 'app/lab/citation_status.py',
     "page = store.events(episode_id, after=after, limit=200)", "page = store.events(episode_id, after=after, limit=200, include_private=True)", TESTS),
    ('M5 episodes sorted instead of first-listing order', 'app/lab/citation_status.py',
     "    return seen\n\n\ndef submitted_report", "    return sorted(seen)\n\n\ndef submitted_report", TESTS),
    ('M6 challenge wrapper also changes non-challenge requests', 'app/lab/citation_status.py',
     "        if challenge:\n            context = attach(self.store, context, request_kind='explorer_challenge')",
     "        context = attach(self.store, context, request_kind='explorer_challenge')", TESTS),
    ('M7 every new Learn plan declares it (not only native v2)', 'app/lab/run_plans.py',
     "        if agent in CITATION_STATUS_AGENTS:\n            plan['mechanic_evidence']", "        if True:\n            plan['mechanic_evidence']", TESTS),
    ('M8 other agents or modes may declare it', 'app/lab/run_plans.py',
     "    if plan.get('mechanic_evidence') is not None and (campaign.mode != 'learn' or plan['agent'] not in CITATION_STATUS_AGENTS):",
     "    if False:", TESTS),
    ('M9 Start accepts another rule text', 'app/lab/run_plans.py',
     "    if plan.get('mechanic_evidence') is not None and plan['mechanic_evidence'] != mechanic_evidence_declaration():",
     "    if False:", TESTS),
    ('M10 an absent rule is saved as null (older plans change bytes)', 'app/lab/run_plans.py',
     "        for key in ('mechanic_context', 'challenge_selection', 'mechanic_evidence'):",
     "        for key in ('mechanic_context', 'challenge_selection'):", TESTS),
    ('M11 learning loop: no block in candidate requests', 'app/lab/learning.py',
     "                        proposal_context=citation_status.attach(store,proposal_context,request_kind='mechanic_proposal')",
     "                        pass", TESTS),
    ('M12 learning loop: block added after the size rule counts the diagnosis request', 'app/lab/learning.py',
     "            diagnosis_mechanic=mechanic if context_rule is None else loop_limits.BoundedMechanic(mechanic,store,campaign_id=id,counterexample=counter)\n            if citation_rule is not None: diagnosis_mechanic=citation_status.CitationStatusMechanic(diagnosis_mechanic,store)",
     "            diagnosis_mechanic=mechanic if citation_rule is None else citation_status.CitationStatusMechanic(mechanic,store)\n            if context_rule is not None: diagnosis_mechanic=loop_limits.BoundedMechanic(diagnosis_mechanic,store,campaign_id=id,counterexample=counter)",
     TESTS),
    ('M13 learning loop: challenge Explorer requests unwrapped', 'app/lab/learning.py',
     "        challenge_explorer=explorer if citation_rule is None else citation_status.CitationStatusExplorer(explorer,store)",
     "        challenge_explorer=explorer", TESTS),
    ('M14 learning loop: the rule applied to every plan', 'app/lab/learning.py',
     "        citation_rule=citation_status.campaign_rule(store,campaign)", "        citation_rule=citation_status.declaration()", TESTS),
    ('M15 learning loop: candidate block added after the size rule', 'app/lab/learning.py',
     "                    if citation_rule is not None:\n                        # Added before the size rule counts the request; that rule compacts only the evidence tables.\n                        proposal_context=citation_status.attach(store,proposal_context,request_kind='mechanic_proposal')\n                    compaction_ref=None\n                    if context_rule is not None:\n                        size={'source_context_id':source_context,'candidate_index':candidate_count-1}\n                        try:\n                            proposal_context,compaction_ref=loop_limits.fit_request(store,mechanic,proposal_context,request_kind='mechanic_proposal',campaign_id=id,counterexample=counter,extra=size)\n                        except loop_limits.MechanicContextUnfit:\n                            candidate_count-=1  # Never sent: it does not use one of the campaign's candidate requests.\n                            break  # Recorded; this source's candidate search ends and discovery continues.\n",
     "                    compaction_ref=None\n                    if context_rule is not None:\n                        size={'source_context_id':source_context,'candidate_index':candidate_count-1}\n                        try:\n                            proposal_context,compaction_ref=loop_limits.fit_request(store,mechanic,proposal_context,request_kind='mechanic_proposal',campaign_id=id,counterexample=counter,extra=size)\n                        except loop_limits.MechanicContextUnfit:\n                            candidate_count-=1  # Never sent: it does not use one of the campaign's candidate requests.\n                            break  # Recorded; this source's candidate search ends and discovery continues.\n                    if citation_rule is not None:\n                        proposal_context=citation_status.attach(store,proposal_context,request_kind='mechanic_proposal')\n",
     TESTS),
    ('M16 checker v2: "never shown" removed from the phrase list', '../scripts/experiments/check_evidence_gap_misreading_v2.py',
     "CLAIM_V2_ADDED = (r'never\\s+(?:been\\s+)?shown|", "CLAIM_V2_ADDED = (r'", CHECKER_TESTS),
    ('M17 checker v2: a count of none read as a claim', '../scripts/experiments/check_evidence_gap_misreading_v2.py',
     "(?<!\\b0\\s)(?<!\\bno\\s)(?<!zero\\s)(?<!without\\s)undecoded", "undecoded", CHECKER_TESTS),
]


def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    caught = 0
    for name, rel, old, new, tests in MUTATIONS:
        path = (BACKEND / rel).resolve()
        original = path.read_bytes(); before = sha(path)
        text = original.decode()
        if text.count(old) != 1:
            print(f'{name}: MUTATION TEXT NOT FOUND EXACTLY ONCE ({text.count(old)})'); sys.exit(2)
        path.write_text(text.replace(old, new))
        try:
            result = subprocess.run([PY, '-B', '-m', 'pytest', '-q', '-x', '-p', 'no:cacheprovider', *tests], cwd=BACKEND,
                                    capture_output=True, text=True, timeout=900)
        finally:
            path.write_bytes(original)
        restored = sha(path) == before
        failed = result.returncode != 0
        caught += failed
        last = [line for line in result.stdout.splitlines() if line.strip()][-1:] or ['']
        first_failure = next((line for line in result.stdout.splitlines() if line.startswith('FAILED')), '')
        print(f'{"CAUGHT " if failed else "MISSED "} {name} | restored={restored} | {last[0]} | {first_failure}')
        if not restored: sys.exit(3)
    print(f'caught {caught}/{len(MUTATIONS)}')
    return 0 if caught == len(MUTATIONS) else 1


if __name__ == '__main__':
    sys.exit(main())
