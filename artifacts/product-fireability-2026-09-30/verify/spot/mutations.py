"""Verifier negative controls (fireability round), run ONLY in the scratch tree
/Users/shree/FaultLab_Scratch/verify-fireability/tree (backup 432e54b plus the 33 changed/added working files, with a
private copy of frontend/node_modules). Each mutation undoes one claimed fix, or one piece of the rule, and the listed tests
must fail. Every mutated file is restored and its sha256 checked. The working tree is never touched. $0, offline (vguard
for pytest; the frontend runs vitest in the scratch copy, which makes no network call).

These mutations are the verifier's own, written from the fixer's claims, not copied from fixer/mutation_checks.py.
"""
import hashlib, os, subprocess, sys, time
TREE = '/Users/shree/FaultLab_Scratch/verify-fireability/tree'
R = '/Users/shree/Desktop/Coreweave_AGI_Hackthon/faultlab'
V = R + '/artifacts/product-fireability-2026-09-30/verify'
PY = R + '/.venv/bin/python'
FB = 'backend/app/lab/fireability.py'
BACK_TESTS = ['tests/lab/test_history_fireability.py', 'tests/lab/test_history_fireability_review_fixes.py',
              'tests/lab/test_evidence_retry_v3.py', 'tests/lab/test_evidence_wait.py', 'tests/lab/test_discovery_v3_flow.py']
FRONT_TESTS = ['tests/history-fireability.test.tsx', 'tests/history-fireability-fixes.test.tsx', 'tests/evidence-wait.test.tsx']

B = 'backend'; F = 'frontend'
MUTATIONS = [
    # ---- MEDIUM-1 / F1: the "every fault" rule
    ('M1 MEDIUM-1: the builder\'s "any fault" decision restored', B, FB, 1,
     "    if len(refused) < len(decision['targets']):", "    if not refused:"),
    ('M2 MEDIUM-1: declaration without pick_refused_when (the builder\'s shape)', B, FB, 1,
     "            'pick_refused_when': PICK_REFUSED_WHEN, 'min_verified_episodes'", "            'min_verified_episodes'"),
    ('M3 MEDIUM-1: saved-plan model accepts any pick_refused_when string', B, 'backend/app/lab/run_plans.py', 1,
     "    pick_refused_when: Literal['every_fault_on_a_refused_target']", "    pick_refused_when: str"),
    # ---- F2: the request note
    ('M4 F2: the Explorer note is dropped from every request under the rule', B, FB, 1,
     "    block = {'rule': RULE, 'meaning': MEANING, 'note': EXPLORER_NOTE, ", "    block = {'rule': RULE, 'meaning': MEANING, "),
    # ---- F3: poll cost
    ('M5 F3: campaign_decisions parses every selection again', B, FB, 1,
     "    for selection in store.get_records('selections', ids):", "    for selection in store.list_records('selections'):"),
    ('M6 F3: the experiments poll validates the plan of every campaign without a counterexample', B, 'backend/app/lab/api.py', 1,
     "        if not counters and 'explorer_selection' in (c().store.get_record('campaign_plans',id) or {}):",
     "        if not counters:"),
    # ---- LOW-2 test gaps
    ('M7 LOW-2 (R4): the table no longer checks the ids hash against the frozen history', B, FB, 1,
     "    if content_hash(sorted(ids)) != history['episode_ids_hash'] or len(ids) != history['summary']['verified_episodes']:",
     "    if False:"),
    ('M8 LOW-2 (R15): one challenge state for the whole Session (never reset)', B, FB, 1,
     "        if self.challenge is None or self.challenge.key != key or context.get('proposal_index') == 0:",
     "        if self.challenge is None:"),
    ('M9 LOW-2 (R16): a fault with no recorded execution counts as fired', B, FB, 1,
     "            targets.setdefault(key, []).append(execution.get('triggered') is True)",
     "            targets.setdefault(key, []).append(execution.get('triggered', True) is True)"),
    # ---- the rule's own mechanics (not claimed as fixer fixes; coverage of the shipped rule)
    ('M10 rule: a refused re-plan gets another re-plan', B, FB, 1,
     "            state.pending = item if decision['slot_request'] == 1 else None", "            state.pending = item"),
    ('M11 rule: challenge picks are never checked (discovery only)', B, 'backend/app/agents/explorer.py', 1,
     "        fire=self.fireability if (challenge or (discovery and v2 is None and history is not None)) else None",
     "        fire=self.fireability if (discovery and v2 is None and history is not None) else None"),
    ('M12 rule: v4 plans no longer freeze the rule (v3-history only)', B, 'backend/app/lab/run_plans.py', 1,
     "        if discovery['protocol'] in FIREABILITY_PROTOCOLS:", "        if discovery['protocol'] == 'faultlab-discovery/v3-history':"),
    ('M13 rule: threshold 1/3 instead of 1/2 (coverage probe)', B, FB, 1,
     "MIN_FIRED_SHARE = Fraction(1, 2)", "MIN_FIRED_SHARE = Fraction(1, 3)"),
    # ---- evidence retry v3
    ('M14 evidence retry: new plans declare v2 again', B, 'backend/app/lab/run_plans.py', 1,
     "        plan['evidence_retry'] = evidence_retry_declaration()", "        plan['evidence_retry'] = evidence_retry_declaration_v2()"),
    ('M15 evidence retry: a v2 plan gets the v3 cap (cap read from the constant, not the plan)', B, 'backend/app/lab/evidence_wait.py', 2,
     "cap = self.rule.get('automatic_retries_per_campaign')", "cap = AUTOMATIC_RETRIES_PER_CAMPAIGN"),
    # ---- frontend (F1, F2, F4, MEDIUM-1 on the dashboard)
    ('FM1 MEDIUM-1: the dashboard accepts a refusal with a target that is not REFUSED', F, 'frontend/src/historyFireability.ts', 1,
     "return refusedRows > 0 && refusedRows === targets.length && ", "return refusedRows > 0 && "),
    ('FM2 MEDIUM-1: the dashboard rejects an allowed pick beside a REFUSED target', F, 'frontend/src/historyFireability.ts', 1,
     "return targets.length > 0 && refusedRows < targets.length && (refusedRows === 0 || text(value.reason))",
     "return targets.length > 0 && refusedRows === 0"),
    ('FM3 MEDIUM-1: the dashboard accepts any pick_refused_when', F, 'frontend/src/historyFireability.ts', 1,
     "    && value.pick_refused_when === 'every_fault_on_a_refused_target'\n", "\n"),
    ('FM4 F4: re-plan refusals lose the "Re-plan." prefix', F, 'frontend/src/historyFireability.ts', 1,
     "return decision.slot_request === 2 ? `Re-plan. ${reason}` : reason", "return reason"),
    ('FM5 F2: the budget says "no re-plans" even under the rule', F, 'frontend/src/components/DiscoveryProtocol.tsx', 1,
     ": fireability ? `one re-plan per pick refused by history fireability, inside the same ${declaration.explorer_requests_max} Explorer requests` : 'no re-plans'",
     ": 'no re-plans'"),
    ('FM6 F1: the challenge panel no longer names the targets refused on their own', F, 'frontend/src/components/LoopLimits.tsx', 1,
     "    {!!summary.refused_targets.length && <p className=\"muted\">Refused on their own", "    {false && <p className=\"muted\">Refused on their own"),
    ('FM7 F4: the plan no longer names the evidence retry rule beside the cap', F, 'frontend/src/components/CampaignPlan.tsx', 1,
     "per campaign`} under rule ${plan.evidence_retry.protocol} (after", "per campaign`} (after"),
    ('FM8 F4: the REFUSED table row is no longer highlighted', F, 'frontend/src/components/LoopLimits.tsx', 1,
     "className={row.status === 'REFUSED' ? 'fireability-refused' : ''}", "className=''"),
]


def sha(path):
    return hashlib.sha256(open(path, 'rb').read()).hexdigest()


def run_backend():
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1', PYTHONPATH=f'{V}:{V}/spot')
    p = subprocess.run([PY, '-B', '-m', 'pytest', '-p', 'vguard', '-p', 'vstub', '-p', 'no:cacheprovider', '-q', '-x', *BACK_TESTS],
                       cwd=TREE + '/backend', capture_output=True, text=True, env=env)
    tail = [l for l in p.stdout.splitlines() if ' passed' in l or ' failed' in l or ' error' in l]
    return p.returncode, (tail[-1] if tail else (p.stdout + p.stderr)[-300:])


def run_frontend():
    p = subprocess.run(['node', 'node_modules/vitest/vitest.mjs', 'run', '--reporter=dot', *FRONT_TESTS],
                       cwd=TREE + '/frontend', capture_output=True, text=True, env=dict(os.environ, CI='1'))
    out = p.stdout + p.stderr
    tail = [l.strip() for l in out.splitlines() if 'Tests ' in l or 'Test Files' in l]
    return p.returncode, (' | '.join(tail[-2:]) if tail else out[-300:])


RUN = {B: run_backend, F: run_frontend}
if __name__ == '__main__':
    only = sys.argv[1] if len(sys.argv) > 1 else None
    for side in (B, F):
        if only and side != only: continue
        t = time.time(); code, summary = RUN[side]()
        print(f'UNMUTATED {side}: exit {code} | {summary} ({time.time() - t:.0f}s)', flush=True)
        assert code == 0, f'unmutated {side} run must pass'
    caught = total = 0
    for name, side, rel, count, old, new in MUTATIONS:
        if only and side != only: continue
        path = f'{TREE}/{rel}'
        before = sha(path)
        text = open(path).read()
        assert text.count(old) == count, f'{name}: anchor found {text.count(old)} times, expected {count}'
        open(path, 'w').write(text.replace(old, new))
        try:
            code, summary = RUN[side]()
        finally:
            open(path, 'w').write(text)
        restored = sha(path) == before
        total += 1; caught += code != 0
        print(f"{'CAUGHT    ' if code != 0 else 'NOT CAUGHT'} {name} | exit {code} | {summary} | restored={restored}", flush=True)
        assert restored
    for side in (B, F):
        if only and side != only: continue
        code, summary = RUN[side]()
        print(f'UNMUTATED AGAIN {side}: exit {code} | {summary}', flush=True)
    print(f'{caught} of {total} caught')
