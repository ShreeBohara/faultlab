"""Negative-control mutations ($0, offline): each one undoes or breaks one part of this build; the new tests must fail on it.
Every file is restored and its sha256 checked after each mutation.

Run from faultlab/backend:  ../.venv/bin/python -B ../artifacts/product-fireability-2026-09-30/builder/mutation_checks.py
"""
import hashlib
import subprocess
import sys
from pathlib import Path

BACKEND = Path.cwd()
FRONTEND = BACKEND.parent / 'frontend'
PY = str(BACKEND.parent / '.venv/bin/python')
FIRE = ['tests/lab/test_history_fireability.py']
RETRY = ['tests/lab/test_evidence_retry_v3.py']
FRONT = ['tests/history-fireability.test.tsx']

MUTATIONS = [
    # --- the table reads only the frozen history's own episodes (candidate independence)
    ('M1 the table (and history) also count candidate-policy episodes', 'app/lab/agent_history.py',
     "                or episode.get('arm') == 'B1' or episode.get('policy_hash') != policy_hash):",
     "                or episode.get('arm') == 'B1'):", FIRE),
    ('M2 the table also counts challenge, source-validation and reproduction episodes', 'app/lab/agent_history.py',
     "    candidates = store.records_upto('episodes', cutoff, where={'split': 'development', 'experiment_purpose': 'discovery'})\n    for _, episode in candidates:\n        # The SQL filter is repeated here: nothing outside the development discovery scope is ever read further.\n        if (episode.get('split') != 'development' or episode.get('experiment_purpose') != 'discovery'",
     "    candidates = store.records_upto('episodes', cutoff, where={'split': 'development'})\n    for _, episode in candidates:\n        # The SQL filter is repeated here: nothing outside the development discovery scope is ever read further.\n        if (episode.get('split') != 'development'", FIRE),
    ('M3 the table counts history replay episodes', 'app/lab/agent_history.py',
     "        if episode.get('episode_id') in replayed:\n            continue  # a discovery v4 history replay",
     "        if False:\n            continue  # a discovery v4 history replay", FIRE),
    ('M4 an episode counts as fired when ANY fault on the target fired', 'app/lab/fireability.py',
     "counts[key] = (verified + 1, all_fired + all(fired))", "counts[key] = (verified + 1, all_fired + any(fired))", FIRE),
    # --- the threshold
    ('M5 a share of exactly 1/2 is refused too', 'app/lab/fireability.py',
     "return REFUSED if Fraction(fired, verified) < MIN_FIRED_SHARE else ALLOWED", "return REFUSED if Fraction(fired, verified) <= MIN_FIRED_SHARE else ALLOWED", FIRE),
    ('M6 two verified episodes are enough to refuse', 'app/lab/fireability.py',
     "MIN_VERIFIED_EPISODES = 3", "MIN_VERIFIED_EPISODES = 2", FIRE),
    # --- the Explorer and the loop
    ('M7 challenge picks are never checked', '../backend/app/agents/explorer.py',
     "        if fire is not None and challenge:\n", "        if False:\n", FIRE),
    ('M8 discovery picks are never refused', '../backend/app/agents/explorer.py',
     "            elif fire is not None and selected is not None:\n", "            elif False:\n", FIRE),
    ('M9 a refused discovery pick gets no re-plan', 'app/lab/fireability.py',
     "    if output is None and refused and not stop() and session.admit_discovery_request():",
     "    if False:", FIRE),
    ('M10 a discovery re-plan is free (not one of the declared requests)', 'app/lab/fireability.py',
     "    if output is None and refused and not stop() and session.admit_discovery_request():",
     "    if output is None and refused and not stop():", FIRE),
    ('M11 a refused challenge pick gets no re-plan', 'app/lab/fireability.py',
     "            state.pending = item if decision['slot_request'] == 1 else None", "            state.pending = None", FIRE),
    ('M12 the request does not carry the table', 'app/lab/fireability.py',
     "             'rows': [dict(row) for row in session.table['rows']],", "             'rows': [],", FIRE),
    ('M13 a slot left without a request is not recorded', 'app/lab/fireability.py',
     "        record_unrequested_slot(store, session, slot_context)\n        return None, None", "        return None, None", FIRE),
    # --- plans
    ('M14 new v3-history / v4 plans do not freeze the rule', 'app/lab/run_plans.py',
     "        if discovery['protocol'] in FIREABILITY_PROTOCOLS:\n            from app.lab import fireability",
     "        if False:\n            from app.lab import fireability", FIRE),
    ('M15 Start accepts another rule text', 'app/lab/run_plans.py',
     "    if selection_rule is not None and {key: value for key, value in selection_rule.items()",
     "    if False and {key: value for key, value in selection_rule.items()", FIRE),
    ('M16 the table is not re-verified before Start or the first request', 'app/lab/run_plans.py',
     "    if plan.get('explorer_selection') is not None:\n        # History fireability: the table is recomputed",
     "    if False:\n        # History fireability: the table is recomputed", FIRE),
    ('M17 a table frozen from another history is accepted', 'app/lab/run_plans.py',
     "        if (table['history_summary_hash'] != frozen['summary_hash']", "        if False and (table['history_summary_hash'] != frozen['summary_hash']", FIRE),
    ('M22 the saved-plan model accepts a row status that does not follow its counts', 'app/lab/run_plans.py',
     "                or self.status != fireability_row_status(self.verified_episodes, self.fired_episodes)):",
     "                or False):", FIRE),
    ('M18 an absent block is saved as null (older plans change bytes)', 'app/lab/run_plans.py',
     "        for key in ('mechanic_context', 'challenge_selection', 'mechanic_evidence', 'explorer_selection'):",
     "        for key in ('mechanic_context', 'challenge_selection', 'mechanic_evidence'):", FIRE),
    # --- evidence retry v3
    ('M19 rule v3 keeps the cap of 6', 'app/lab/evidence_wait.py',
     "AUTOMATIC_RETRIES_PER_CAMPAIGN = 24", "AUTOMATIC_RETRIES_PER_CAMPAIGN = 6", RETRY),
    ('M20 Start refuses a saved v2 plan', 'app/lab/run_plans.py',
     "plan['evidence_retry'] not in (evidence_retry_declaration(), evidence_retry_declaration_v2()):",
     "plan['evidence_retry'] != evidence_retry_declaration():", RETRY),
    ('M21 new plans still freeze rule v2', 'app/lab/evidence_wait.py',
     "    return _declaration(EVIDENCE_RETRY_PROTOCOL, AUTOMATIC_RETRIES_PER_CAMPAIGN, RULE)",
     "    return _declaration(EVIDENCE_RETRY_PROTOCOL_V2, AUTOMATIC_RETRIES_PER_CAMPAIGN_V2, RULE_V2)", RETRY),
    # --- the dashboard
    ('F1 dashboard: a table frozen from another history is accepted', '../frontend/src/runPlans.ts',
     "|| !explorerSelectionDeclaration(declared, true) || !('table' in declared) || declared.table.history_summary_hash !== history.summary_hash",
     "|| !explorerSelectionDeclaration(declared, true) || !('table' in declared)", FRONT),
    ('F2 dashboard: a row status that does not follow its counts is accepted', '../frontend/src/historyFireability.ts',
     "  return fired <= verified && value.fired_share === `${fired}/${verified}` && value.status === rowStatus(verified, fired)",
     "  return fired <= verified && value.fired_share === `${fired}/${verified}`", FRONT),
    ('F3 dashboard: evidence retry v3 with a cap of 6 is accepted', '../frontend/src/runPlans.ts',
     "value.protocol === 'faultlab-evidence-retry/v3' ? value.automatic_retries_per_campaign === 24",
     "value.protocol === 'faultlab-evidence-retry/v3' ? [6, 24].includes(value.automatic_retries_per_campaign as number)", FRONT),
    ('F4 dashboard: a refusal by the rule is accepted without its check', '../frontend/src/searchAttempts.ts',
     "(v2 ? V2_STATUSES : fire ? FIREABILITY_STATUSES : V1_STATUSES)", "(v2 ? V2_STATUSES : FIREABILITY_STATUSES)", FRONT),
]


def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()


def run_tests(tests):
    if tests is FRONT:
        return subprocess.run(['npx', 'vitest', 'run', *tests], cwd=FRONTEND, capture_output=True, text=True, timeout=900)
    return subprocess.run([PY, '-B', '-m', 'pytest', '-q', '-x', '-p', 'no:cacheprovider', *tests], cwd=BACKEND,
                          capture_output=True, text=True, timeout=900)


def main():
    caught = 0; restored_all = True
    for name, rel, old, new, tests in MUTATIONS:
        path = (BACKEND / rel).resolve()
        original = path.read_bytes(); before = sha(path)
        text = original.decode()
        if text.count(old) != 1:
            print(f'{name}: MUTATION TEXT NOT FOUND EXACTLY ONCE ({text.count(old)})'); sys.exit(2)
        path.write_text(text.replace(old, new))
        try:
            result = run_tests(tests)
        finally:
            path.write_bytes(original)
        restored = sha(path) == before; restored_all &= restored
        failed = result.returncode != 0
        caught += failed
        lines = (result.stdout + result.stderr).strip().splitlines()
        summary = next((line for line in reversed(lines) if ' failed' in line or ' passed' in line or 'Tests' in line), lines[-1] if lines else '')
        first = next((line for line in lines if line.startswith('FAILED') or line.strip().startswith('×') or 'FAIL ' in line), '')
        print(f"{'CAUGHT ' if failed else 'MISSED '} {name} | restored={restored} | {summary.strip()} | {first.strip()[:160]}", flush=True)
    print(f'caught {caught}/{len(MUTATIONS)}')
    print('all files restored (sha256 identical)' if restored_all else 'A FILE WAS NOT RESTORED')
    sys.exit(0 if caught == len(MUTATIONS) and restored_all else 1)


if __name__ == '__main__':
    main()
