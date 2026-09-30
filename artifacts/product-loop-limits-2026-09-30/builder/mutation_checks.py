"""Negative controls ($0, offline): each mutation breaks one part of the two loop-limit rules; the named tests must fail.

Each mutation edits one source file in place, runs the named tests, and restores the file byte-for-byte (sha256 checked
before and after). Run from faultlab/:  python3 -B artifacts/product-loop-limits-2026-09-30/builder/mutation_checks.py
"""
import hashlib
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PY = str(ROOT / '.venv/bin/python')
MC = 'tests/lab/test_loop_limits_mechanic_context.py'
CR = 'tests/lab/test_loop_limits_challenge_reach.py'
PL = 'tests/lab/test_loop_limits_plans.py'
FRONT = 'tests/loop-limits.test.tsx'

MUTATIONS = [
    ('a request over the limit is never compacted', 'backend/app/lab/loop_limits.py',
     '    if full <= MODEL_INPUT_TOKEN_LIMIT: return context, None', '    if True: return context, None', 'backend', [MC]),
    ('the source and failing episodes are omitted like clean ones', 'backend/app/lab/loop_limits.py',
     "        if episode_id in protected or _row_failed(summary, row, facts):", "        if False:", 'backend', [MC]),
    ('the format-repair reserve is ignored (target = the limit)', 'backend/app/lab/loop_limits.py',
     '        if size <= COMPACTION_TARGET_TOKENS:', '        if size <= MODEL_INPUT_TOKEN_LIMIT:', 'backend', [MC]),
    ('an outcome that differs inside a recipe is grouped away', 'backend/app/lab/loop_limits.py',
     "        group = canonical_json({'scenario_hash': facts['scenario_hash'], **outcome}) if facts else canonical_json({'episode_id': episode_id})",
     "        group = canonical_json({'scenario_hash': facts['scenario_hash'], 'arm': facts['arm']}) if facts else canonical_json({'episode_id': episode_id})", 'backend', [MC]),
    ('the omission statement is left out of the request', 'backend/app/lab/loop_limits.py',
     "        request = {**compacted, 'context_compaction': {", "        request = {**compacted, 'context_compaction_hidden': {", 'backend', [MC]),
    ('an unsent request still uses a candidate request', 'backend/app/lab/learning.py',
     "                            candidate_count-=1  # Never sent", "                            pass  # Never sent", 'backend', [MC]),
    ('a refused format-repair turn ends the campaign in ERROR', 'backend/app/lab/learning.py',
     "                        if context_rule is None: raise  # A plan saved before", "                        raise  # A plan saved before", 'backend', [MC]),
    ('the diagnosis request is sent unfitted', 'backend/app/lab/learning.py',
     "            diagnosis_mechanic=mechanic if context_rule is None else loop_limits.BoundedMechanic(mechanic,store,campaign_id=id,counterexample=counter)",
     "            diagnosis_mechanic=mechanic", 'backend', [MC]),
    ('the challenge rule is never handed to the Explorer', 'backend/app/lab/learning.py',
     "        explorer.challenge_reach=loop_limits.challenge_selection_rule(store,campaign)", "        explorer.challenge_reach=None", 'backend', [CR]),
    ('the Explorer never checks challenge picks', 'backend/app/agents/explorer.py',
     "        reach_rule=self.challenge_reach if challenge else None", "        reach_rule=None", 'backend', [CR]),
    ("the candidate policy's reads count as agent calls", 'backend/app/lab/loop_limits.py',
     "    unreached = [t for t in decision['targets'] if t not in reach['agent']]",
     "    unreached = [t for t in decision['targets'] if t not in reach['agent'] + reach['policy_only']]", 'backend', [CR]),
    ('a refused pick gets no re-plan', 'backend/app/lab/loop_limits.py',
     "        session.pending = item if decision['slot_request'] == 1 else None", "        session.pending = None", 'backend', [CR]),
    ('a refused re-plan gets another re-plan', 'backend/app/lab/loop_limits.py',
     "        session.pending = item if decision['slot_request'] == 1 else None", "        session.pending = item", 'backend', [CR]),
    ('a pick is refused without evidence', 'backend/app/lab/loop_limits.py',
     "    if not reach['episode_ids']:", "    if False:", 'backend', [CR]),
    ('new Learn plans do not freeze the Mechanic rule', 'backend/app/lab/run_plans.py',
     "        plan['mechanic_context'] = mechanic_context_declaration()\n", "", 'backend', [PL]),
    ('Start accepts a declared rule that differs from the installed one', 'backend/app/lab/run_plans.py',
     "    if plan.get('mechanic_context') is not None and plan['mechanic_context'] != mechanic_context_declaration():",
     "    if False:", 'backend', [PL]),
    ('an older plan gains null keys when read back', 'backend/app/lab/run_plans.py',
     "        for key in ('mechanic_context', 'challenge_selection'):\n            if data.get(key) is None:\n                data.pop(key, None)",
     "        for key in ():\n            pass", 'backend', [PL]),
    ('the experiments API shows the lists for every campaign', 'backend/app/lab/api.py',
     "        if plan is not None and plan.get('challenge_selection') is not None:", "        if True:", 'backend', [PL]),
    ('the dashboard accepts a Mechanic rule with a different target', 'frontend/src/loopLimits.ts',
     "value.compaction_target_tokens === 28000", "typeof value.compaction_target_tokens === 'number'", 'frontend', [FRONT]),
    ('the dashboard accepts a refusal without a reason', 'frontend/src/loopLimits.ts',
     "value.unreached.length > 0 && text(value.reason)", "value.unreached.length > 0", 'frontend', [FRONT]),
    ('the saved plan hides the challenge-pick rule', 'frontend/src/components/LoopLimits.tsx',
     '<Field name="Challenge picks">{challengeSelectionText(challengeSelection)}</Field>', '', 'frontend', [FRONT]),
]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(kind, tests):
    if kind == 'backend':
        return subprocess.run([PY, '-m', 'pytest', '-q', '-x', '-p', 'no:cacheprovider', *tests], cwd=ROOT / 'backend', capture_output=True, text=True)
    return subprocess.run(['npx', 'vitest', 'run', *tests], cwd=ROOT / 'frontend', capture_output=True, text=True)


def main():
    caught = 0
    for name, rel, old, new, kind, tests in MUTATIONS:
        path = ROOT / rel; original = path.read_bytes(); before = sha(path)
        text = original.decode()
        if text.count(old) != 1:
            print(f'SETUP ERROR  {name}: pattern found {text.count(old)} times in {rel}'); sys.exit(2)
        try:
            path.write_text(text.replace(old, new))
            result = run(kind, tests)
        finally:
            path.write_bytes(original)
        assert sha(path) == before, f'{rel} was not restored'
        failed = result.returncode != 0
        caught += failed
        tail = [line for line in (result.stdout + result.stderr).splitlines() if line.strip()][-1:] or ['']
        print(f'{"CAUGHT " if failed else "MISSED "} {name} ({rel}) :: {tail[0][:150]}')
    # The unmutated tests pass.
    clean = [run('backend', [MC, CR, PL]), run('frontend', [FRONT])]
    print(f'unmutated: backend exit {clean[0].returncode}, frontend exit {clean[1].returncode}')
    print(f'{caught}/{len(MUTATIONS)} mutations caught; every file restored (sha256 checked)')
    sys.exit(0 if caught == len(MUTATIONS) and not any(r.returncode for r in clean) else 1)


if __name__ == '__main__':
    main()
