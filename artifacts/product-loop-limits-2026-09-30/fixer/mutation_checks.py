"""Fixer negative controls ($0, offline): each mutation undoes one review fix; the named tests must fail.

Each mutation edits one source file in place, runs only the named tests (node ids, no -x), and restores the file
byte-for-byte (sha256 checked before and after). A mutation counts as CAUGHT only if at least one named test fails.
Run from faultlab/:  python3 -B artifacts/product-loop-limits-2026-09-30/fixer/mutation_checks.py
"""
import hashlib
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PY = str(ROOT / '.venv/bin/python')
MC = 'tests/lab/test_loop_limits_mechanic_context.py::'
CR = 'tests/lab/test_loop_limits_challenge_reach.py::'
PL = 'tests/lab/test_loop_limits_plans.py::'
FRONT = 'tests/loop-limits.test.tsx'

MUTATIONS = [
    # HIGH-1 (integrity and product): the candidate-reach rule is withdrawn from new plans and cannot start.
    ('HIGH-1: new Learn plans freeze the challenge-pick rule again (and Start would accept it)', 'backend/app/lab/run_plans.py',
     "        plan['mechanic_context'] = mechanic_context_declaration()\n",
     "        plan['mechanic_context'] = mechanic_context_declaration()\n"
     "        from app.lab.loop_limits import challenge_selection_declaration\n"
     "        plan['challenge_selection'] = challenge_selection_declaration()\n", 'backend',
     [CR + 'test_under_a_new_learn_plan_a_pick_refusal_cannot_turn_a_counterexample_into_a_pass',
      PL + 'test_run_options_and_every_new_learn_plan_declare_the_mechanic_rule_only_and_baseline_plans_neither']),
    ('HIGH-1: Start accepts a plan that declares the withdrawn rule', 'backend/app/lab/run_plans.py',
     "        return CHALLENGE_SELECTION_WITHDRAWN\n", "        return None\n", 'backend',
     [PL + 'test_a_plan_declaring_the_withdrawn_challenge_rule_cannot_be_created_or_started']),
    ('HIGH-1: run options offer the withdrawn rule again', 'backend/app/lab/run_plans.py',
     "                  'mechanic_context': mechanic_context_declaration()},",
     "                  'mechanic_context': mechanic_context_declaration(), 'challenge_selection': __import__('app.lab.loop_limits', fromlist=['x']).challenge_selection_declaration()},",
     'backend', [PL + 'test_run_options_and_every_new_learn_plan_declare_the_mechanic_rule_only_and_baseline_plans_neither']),
    # Integrity LOW-1
    ('I-LOW-1: a VIOLATION outcome without failed checks may be omitted', 'backend/app/lab/loop_limits.py',
     "facts.get('failed_checks') or facts.get('outcome') == 'VIOLATION'", "facts.get('failed_checks')", 'backend',
     [MC + 'test_an_episode_whose_trial_outcome_is_violation_is_always_kept']),
    # Integrity LOW-2
    ('I-LOW-2: the stage-2 group ignores policy and purpose', 'backend/app/lab/loop_limits.py',
     "'policy_hash': facts['policy_hash'], 'purpose': facts['purpose'],", "", 'backend',
     [MC + 'test_stage_two_never_lets_one_policy_or_purpose_stand_for_another']),
    # Product LOW-1
    ('P-LOW-1: the legend no longer says omitted rows can differ from the example', 'backend/app/lab/loop_limits.py',
     "'; rows can differ from their group_example (same recipe, arm, policy, purpose and '", "'; see group_example (same recipe, arm, policy, purpose and '",
     'backend', [MC + 'test_stage_two_names_a_group_example_and_says_the_omitted_rows_can_differ_from_it']),
    ('P-LOW-1: the stage-2 field is called represented_by again', 'backend/app/lab/loop_limits.py',
     "'omitted_as': STAGE_ONE_PER_GROUP, 'group_example': groups[group]}", "'omitted_as': STAGE_ONE_PER_GROUP, 'represented_by': groups[group]}",
     'backend', [MC + 'test_stage_two_names_a_group_example_and_says_the_omitted_rows_can_differ_from_it',
                 MC + 'test_an_outcome_that_differs_inside_a_recipe_keeps_its_own_full_example']),
    # Integrity LOW-3
    ('I-LOW-3: NO_CHANGE does not name a search the size rule ended', 'backend/app/lab/learning.py',
     "        ended=loop_limits.search_ended_note(store,id) if context_rule is not None else None",
     "        ended=None", 'backend', [MC + 'test_a_search_cut_short_by_the_size_rule_is_named_in_the_campaigns_final_reason']),
    ('I-LOW-3: every refused turn is recorded as FORMAT_REPAIR ("first turn was sent")', 'backend/app/lab/loop_limits.py',
     "    first = first_turn_output(store, campaign_id, request_kind, cutoff)\n",
     "    first = first_turn_output(store, campaign_id, request_kind, cutoff) or ('unknown', {'raw': ''})\n", 'backend',
     [MC + 'test_a_first_turn_the_mechanic_itself_refuses_is_recorded_as_never_sent']),
    ('I-LOW-3: a first turn that was never sent still uses a candidate request', 'backend/app/lab/learning.py',
     "                        if first is None:\n                            candidate_count-=1",
     "                        if first is None:\n                            candidate_count-=0", 'backend',
     [MC + 'test_a_first_turn_the_mechanic_itself_refuses_is_recorded_as_never_sent']),
    # Product LOW-3
    ('P-LOW-3: a refused format-repair turn leaves no proposal record', 'backend/app/lab/learning.py',
     "                        store.put_record('campaign_proposals',first_ref,",
     "                        (lambda *args,**kwargs: None)('campaign_proposals',first_ref,", 'backend',
     [MC + 'test_a_refused_format_repair_turn_leaves_a_rejected_proposal_in_the_candidate_history']),
    # Product LOW-2 (dashboard)
    ('P-LOW-2: a refused format-repair turn is shown as "not sent"', 'frontend/src/loopLimits.ts',
     "  if (row.stage === 'FORMAT_REPAIR') return", "  if (row.stage === 'NEVER') return", 'frontend', [FRONT]),
    ('P-LOW-2: an unsent request shows an "in full" line', 'frontend/src/components/LoopLimits.tsx',
     "{row.outcome === 'COMPACTED' && !!row.blocks?.length &&", "{!!row.blocks?.length &&", 'frontend', [FRONT]),
    ('P-LOW-2: a refusal says "refused" twice', 'frontend/src/loopLimits.ts',
     "return `${request}: ${row.reason ?? 'Refused before any pair ran.'}`", "return `${request}: refused, no pair ran. ${row.reason ?? ''}`.trim()",
     'frontend', [FRONT]),
    ('P-LOW-2: the pick badge is lower case', 'frontend/src/loopLimits.ts',
     "SELECTED: 'Selected',", "SELECTED: 'selected',", 'frontend', [FRONT]),
    # Rule 2 withdrawal on the dashboard
    ('HIGH-1 (dashboard): the setup form claims two rules when one is offered', 'frontend/src/components/LoopLimits.tsx',
     "{count === 1 ? 'Every new Learn plan also freezes this rule:' :", "{count === 0 ? 'Every new Learn plan also freezes this rule:' :",
     'frontend', [FRONT]),
    ('HIGH-1 (dashboard): an undeclared challenge rule is described as "saved before" it', 'frontend/src/loopLimits.ts',
     "  if (!rule) return 'Not declared: every valid challenge pick runs its pairs, as before.'",
     "  if (!rule) return 'Not declared: this plan was saved before the challenge-pick rule. Every valid challenge pick runs its pairs, as before.'",
     'frontend', [FRONT]),
]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(kind, tests):
    if kind == 'backend':
        return subprocess.run([PY, '-m', 'pytest', '-q', '-p', 'no:cacheprovider', '-rf', *tests], cwd=ROOT / 'backend', capture_output=True, text=True)
    return subprocess.run(['npx', 'vitest', 'run', *tests], cwd=ROOT / 'frontend', capture_output=True, text=True)


def summary(result):
    text = re.sub(r'\x1b\[[0-9;]*m', '', result.stdout + result.stderr)
    failed = sorted(set(re.findall(r'FAILED (\S+)', text)))
    tally = [line.strip() for line in text.splitlines() if re.search(r'(\d+ (failed|passed))|Tests\s+\d', line)]
    return (tally[-1] if tally else '') + (' :: ' + ', '.join(f.split('::')[-1] for f in failed) if failed else '')


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
        print(f'{"CAUGHT " if failed else "MISSED "} {name} ({rel}) :: {summary(result)[:300]}', flush=True)
    backend_tests = sorted({t for _, _, _, _, kind, tests in MUTATIONS if kind == 'backend' for t in tests})
    clean = [run('backend', backend_tests), run('frontend', [FRONT])]
    print(f'unmutated: backend exit {clean[0].returncode} ({summary(clean[0])}), frontend exit {clean[1].returncode} ({summary(clean[1])})')
    print(f'{caught}/{len(MUTATIONS)} mutations caught; every file restored (sha256 checked)')
    sys.exit(0 if caught == len(MUTATIONS) and not any(r.returncode for r in clean) else 1)


if __name__ == '__main__':
    main()
