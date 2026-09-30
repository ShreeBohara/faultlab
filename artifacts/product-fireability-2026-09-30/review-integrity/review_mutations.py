"""Integrity review: independent negative-control mutations ($0, offline).

Every mutation is applied to a SCRATCH COPY of the working tree (/Users/shree/FaultLab_Scratch/review-integrity-fireability/
mut-tree; backend, contracts, scripts and audit/development|freeze|portability|search-comparison.json only; no .env, no
promotion or final-audit manifest), never to the Desktop working tree. For each mutation the named tests run under the
network guard; the mutation is CAUGHT when pytest fails. The original file is restored and its sha256 re-checked after
each mutation. Run:  /Users/shree/Desktop/Coreweave_AGI_Hackthon/faultlab/.venv/bin/python -B review_mutations.py
"""
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

M = Path('/Users/shree/FaultLab_Scratch/review-integrity-fireability/mut-tree')
PY = '/Users/shree/Desktop/Coreweave_AGI_Hackthon/faultlab/.venv/bin/python'
RUNNER = M / 'run_guarded.py'
RUNNER.write_text('''import sys
sys.path.insert(0, %r)
import guard
import pytest
code = pytest.main(['-q', '-x', '-p', 'no:cacheprovider', '-W', 'ignore::DeprecationWarning', *sys.argv[1:]])
print('[mut] refused outbound', len(guard.REFUSED), file=sys.stderr)
sys.exit(code)
''' % str(M))

FIRE_TESTS = ['tests/lab/test_history_fireability.py']
HIST_TESTS = ['tests/lab/test_history_fireability.py', 'tests/lab/test_agent_history.py']
RETRY_TESTS = ['tests/lab/test_evidence_retry_v3.py', 'tests/lab/test_evidence_wait.py']

MUTATIONS = [
    # --- candidate independence: what the table may read
    ('R1 table/history read candidate-policy discovery episodes (policy filter removed)', 'app/lab/agent_history.py',
     "                or episode.get('arm') == 'B1' or episode.get('policy_hash') != policy_hash):",
     "                or episode.get('arm') == 'B1'):", HIST_TESTS),
    ('R2 table/history read every purpose (challenge, source validation, reproduction, reduction...)', 'app/lab/agent_history.py',
     "        if (episode.get('split') != 'development' or episode.get('experiment_purpose') != 'discovery'\n                or episode.get('arm') == 'B1'",
     "        if (episode.get('split') != 'development'\n                or episode.get('arm') == 'B1'", HIST_TESTS),
    ('R2b same, SQL filter also widened', 'app/lab/agent_history.py',
     "    candidates = store.records_upto('episodes', cutoff, where={'split': 'development', 'experiment_purpose': 'discovery'})\n    for _, episode in candidates:\n        # The SQL filter is repeated here: nothing outside the development discovery scope is ever read further.\n        if (episode.get('split') != 'development' or episode.get('experiment_purpose') != 'discovery'\n",
     "    candidates = store.records_upto('episodes', cutoff, where={'split': 'development'})\n    for _, episode in candidates:\n        # The SQL filter is repeated here: nothing outside the development discovery scope is ever read further.\n        if (episode.get('split') != 'development'\n", HIST_TESTS),
    ('R3 table only (not history) counts unverified / lab-error episodes, binding check removed', 'app/lab/fireability.py',
     "    used = agent_history.used_episodes(store, identity=history['agent_identity'], policy_hash=history['policy_hash'],\n                                       cutoff=history['record_cutoff'])\n    ids = [episode['episode_id'] for episode, _ in used]\n    if content_hash(sorted(ids)) != history['episode_ids_hash'] or len(ids) != history['summary']['verified_episodes']:",
     "    known, replayed = agent_history._public_recipes(store, history['record_cutoff'])\n    used = [(e, entry[0]) for e, _, entry, reason in agent_history._in_scope(store, identity=history['agent_identity'], policy_hash=history['policy_hash'], cutoff=history['record_cutoff'], known=known, replayed=replayed, cache={}) if entry is not None]\n    ids = [episode['episode_id'] for episode, _ in used]\n    if False:", FIRE_TESTS),
    ('R4 binding check alone removed (defence in depth)', 'app/lab/fireability.py',
     "    if content_hash(sorted(ids)) != history['episode_ids_hash'] or len(ids) != history['summary']['verified_episodes']:",
     "    if False:", FIRE_TESTS),
    ('R5 history replay slots counted', 'app/lab/agent_history.py',
     "        if episode.get('episode_id') in replayed:\n            continue",
     "        if False:\n            continue", HIST_TESTS),
    ('R6 B1 control counted', 'app/lab/agent_history.py',
     "                or episode.get('arm') == 'B1' or episode.get('policy_hash') != policy_hash):",
     "                or episode.get('policy_hash') != policy_hash):", HIST_TESTS),
    ('R7 other agents counted (identity check removed)', 'app/lab/agent_history.py',
     "        if source is None or identity is None or _episode_identity(store, episode, cache) != identity:",
     "        if source is None or identity is None:", HIST_TESTS),
    # --- the rule itself
    ('R8 challenge picks not checked (rule silently off in the challenge)', 'app/agents/explorer.py',
     "        fire=self.fireability if (challenge or (discovery and v2 is None and history is not None)) else None",
     "        fire=self.fireability if (discovery and v2 is None and history is not None) else None", FIRE_TESTS),
    ('R9 learning loop never sets the rule on its Explorer', 'app/lab/learning.py',
     "            explorer.fireability=fire\n", "            pass\n", FIRE_TESTS),
    ('R10 threshold: a share of exactly 1/2 refused', 'app/lab/fireability.py',
     "    return REFUSED if Fraction(fired, verified) < MIN_FIRED_SHARE else ALLOWED",
     "    return REFUSED if Fraction(fired, verified) <= MIN_FIRED_SHARE else ALLOWED", FIRE_TESTS),
    ('R11 threshold: 2 verified episodes enough to refuse', 'app/lab/fireability.py',
     "    if verified < MIN_VERIFIED_EPISODES:", "    if verified < 2:", FIRE_TESTS),
    ('R12 Start/first-request re-verification ignores the table', 'app/lab/fireability.py',
     "    if block['table'] != table or block['table_hash'] != content_hash(table):",
     "    if False:", FIRE_TESTS),
    ('R13 discovery re-plan not charged against the declared requests', 'app/lab/fireability.py',
     "    if output is None and refused and not stop() and session.admit_discovery_request():",
     "    if output is None and refused and not stop():", FIRE_TESTS),
    ('R14 a refused re-plan gets another re-plan (discovery)', 'app/lab/fireability.py',
     "        ref, output = await explorer.select({**slot_context, 'slot_request': 2, 'replan_of': ref,\n                                             'slot_feedback': slot_feedback(record)},\n                                            fallback=fallback, discovery_history=discovery_history)\n    return ref, output",
     "        ref, output = await explorer.select({**slot_context, 'slot_request': 2, 'replan_of': ref,\n                                             'slot_feedback': slot_feedback(record)},\n                                            fallback=fallback, discovery_history=discovery_history)\n        if output is None and session.admit_discovery_request():\n            ref, output = await explorer.select({**slot_context, 'slot_request': 2, 'replan_of': ref, 'slot_feedback': slot_feedback(store.get_record('selections', ref))}, fallback=fallback, discovery_history=discovery_history)\n    return ref, output", FIRE_TESTS),
    ('R15 challenge state never reset between challenges (one candidate\'s refusals shown in the next challenge)', 'app/lab/fireability.py',
     "        if self.challenge is None or self.challenge.key != key or context.get('proposal_index') == 0:",
     "        if self.challenge is None:", FIRE_TESTS),
    ('R16 a missing fault execution counts as fired', 'app/lab/fireability.py',
     "            targets.setdefault(key, []).append(execution.get('triggered') is True)",
     "            targets.setdefault(key, []).append(execution.get('triggered') is not False)", FIRE_TESTS),
    ('R17 a two-fault pick is refused only when EVERY target is refused', 'app/lab/fireability.py',
     "    refused = [item['table_row'] for item in decision['targets'] if item['status'] == REFUSED]\n    if not refused:",
     "    refused = [item['table_row'] for item in decision['targets'] if item['status'] == REFUSED]\n    if len(refused) < len(decision['targets']):", FIRE_TESTS),
    # --- evidence retry v3
    ('E1 v2 plans get the v3 cap of 24', 'app/lab/evidence_wait.py',
     "AUTOMATIC_RETRIES_PER_CAMPAIGN_V2 = 6", "AUTOMATIC_RETRIES_PER_CAMPAIGN_V2 = 24", RETRY_TESTS),
    ('E2 new plans keep the v2 cap of 6', 'app/lab/evidence_wait.py',
     "AUTOMATIC_RETRIES_PER_CAMPAIGN = 24", "AUTOMATIC_RETRIES_PER_CAMPAIGN = 6", RETRY_TESTS),
    ('E3 the per-wait limit raised to 4', 'app/lab/evidence_wait.py',
     "AUTOMATIC_RETRIES_PER_WAIT = 3", "AUTOMATIC_RETRIES_PER_WAIT = 4", RETRY_TESTS),
]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(tests):
    started = time.time()
    proc = subprocess.run([PY, '-B', str(RUNNER), *tests], cwd=M / 'backend', capture_output=True, text=True,
                          env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1', 'PYTHON_DOTENV_DISABLED': '1'})
    tail = (proc.stdout.strip().splitlines() or [''])[-1]
    refused = [line for line in proc.stderr.splitlines() if line.startswith('[mut] refused outbound')]
    return proc.returncode, tail, refused[-1] if refused else 'guard line missing', round(time.time() - started)


results = []
only = sys.argv[1:]
baseline_tests = sorted({t for *_, tests in MUTATIONS for t in tests})
code, tail, guard_line, secs = run(baseline_tests)
results.append({'mutation': 'BASELINE (no mutation)', 'exit': code, 'tail': tail, 'guard': guard_line, 'seconds': secs})
print(json.dumps(results[-1]), flush=True)
assert code == 0, 'baseline must pass'
for name, rel, old, new, tests in MUTATIONS:
    if only and not any(name.startswith(o) for o in only):
        continue
    path = M / 'backend' / rel
    original = path.read_text(); before = sha(path)
    if original.count(old) != 1:
        results.append({'mutation': name, 'error': f'anchor found {original.count(old)} times'}); print(json.dumps(results[-1]), flush=True); continue
    path.write_text(original.replace(old, new))
    try:
        code, tail, guard_line, secs = run(tests)
    finally:
        path.write_text(original)
    restored = sha(path) == before
    results.append({'mutation': name, 'file': rel, 'caught': code != 0, 'exit': code, 'tail': tail, 'guard': guard_line,
                    'seconds': secs, 'restored_sha256_identical': restored})
    print(json.dumps(results[-1]), flush=True)
print(json.dumps({'caught': sum(1 for r in results if r.get('caught')), 'mutations': sum(1 for r in results if 'caught' in r),
                  'survived': [r['mutation'] for r in results if r.get('caught') is False],
                  'anchor_errors': [r['mutation'] for r in results if 'error' in r],
                  'all_restored': all(r.get('restored_sha256_identical', True) for r in results)}))
