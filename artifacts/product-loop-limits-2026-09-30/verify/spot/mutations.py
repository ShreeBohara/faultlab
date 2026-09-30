"""Verifier negative controls ($0, offline), run ONLY in the scratch tree /Users/shree/FaultLab_Scratch/verify-loop-limits/tree.

Each mutation undoes one fixer change (or weakens one guarantee); the named tests must fail (CAUGHT). Every file is
restored byte-for-byte and its sha256 checked after each mutation. Tests run with the verifier guard (no network, no
protected file) and the promotion-manifest stand-in (vstub). The verifier probes (spot/test_verifier_probes.py) are
copied in as tests/lab/test_verifier_probes.py for the run and removed afterwards.
"""
import hashlib, os, re, shutil, subprocess, sys

TREE = '/Users/shree/FaultLab_Scratch/verify-loop-limits/tree'
V = '/Users/shree/Desktop/Coreweave_AGI_Hackthon/faultlab/artifacts/product-loop-limits-2026-09-30/verify'
PY = '/Users/shree/Desktop/Coreweave_AGI_Hackthon/faultlab/.venv/bin/python'
MC = 'tests/lab/test_loop_limits_mechanic_context.py::'
CR = 'tests/lab/test_loop_limits_challenge_reach.py::'
PL = 'tests/lab/test_loop_limits_plans.py::'
PR = 'tests/lab/test_verifier_probes.py::'
NEW_PLAN = ("        plan['mechanic_context'] = mechanic_context_declaration()\n",
            "        plan['mechanic_context'] = mechanic_context_declaration()\n"
            "        from app.lab.loop_limits import challenge_selection_declaration as _csd; plan['challenge_selection'] = _csd()\n")
MUTATIONS = [
    # (name, file, [(old, new), ...], tests)
    ('I-HIGH-1a: new Learn plans freeze the challenge rule again AND creation/Start accept it (the builder state)',
     'app/lab/run_plans.py', [NEW_PLAN, ('        return CHALLENGE_SELECTION_WITHDRAWN\n', '        return None\n')],
     [CR + 'test_under_a_new_learn_plan_a_pick_refusal_cannot_turn_a_counterexample_into_a_pass',
      PL + 'test_run_options_and_every_new_learn_plan_declare_the_mechanic_rule_only_and_baseline_plans_neither']),
    ('I-HIGH-1b: new Learn plans freeze the challenge rule (withdrawal check still on)', 'app/lab/run_plans.py', [NEW_PLAN],
     [CR + 'test_under_a_new_learn_plan_a_pick_refusal_cannot_turn_a_counterexample_into_a_pass',
      PL + 'test_run_options_and_every_new_learn_plan_declare_the_mechanic_rule_only_and_baseline_plans_neither']),
    ('I-HIGH-1c: withdrawn_rule_problem never refuses', 'app/lab/run_plans.py',
     [('        return CHALLENGE_SELECTION_WITHDRAWN\n', '        return None\n')],
     [PL + 'test_a_plan_declaring_the_withdrawn_challenge_rule_cannot_be_created_or_started']),
    ('I-HIGH-1d: run options offer the challenge rule again', 'app/lab/run_plans.py',
     [("                  'mechanic_context': mechanic_context_declaration()},",
       "                  'mechanic_context': mechanic_context_declaration(), 'challenge_selection': __import__('app.lab.loop_limits', fromlist=['x']).challenge_selection_declaration()},")],
     [PL + 'test_run_options_and_every_new_learn_plan_declare_the_mechanic_rule_only_and_baseline_plans_neither']),
    ('I-LOW-1: a VIOLATION outcome without failed checks is compactable', 'app/lab/loop_limits.py',
     [(" or facts.get('outcome') == 'VIOLATION')))", ")))")], [MC + 'test_an_episode_whose_trial_outcome_is_violation_is_always_kept']),
    ('I-LOW-2a: stage-2 group ignores policy', 'app/lab/loop_limits.py',
     [("'policy_hash': facts['policy_hash'], 'purpose': facts['purpose'],", "'purpose': facts['purpose'],")],
     [MC + 'test_stage_two_never_lets_one_policy_or_purpose_stand_for_another']),
    ('I-LOW-2b: purpose never read', 'app/lab/loop_limits.py',
     [("    facts['purpose'] = (store.get_record('episodes', episode_id) or {}).get('experiment_purpose')", "    facts['purpose'] = None")],
     [MC + 'test_stage_two_never_lets_one_policy_or_purpose_stand_for_another']),
    ('I-LOW-2c (coverage probe): stage-1 identity ignores trial facts (policy/purpose/outcome)', 'app/lab/loop_limits.py',
     [("'check_row': row['check_row'], 'facts': facts})", "'check_row': row['check_row']})")],
     [MC + 'test_stages_run_in_order_keep_the_source_and_every_failure_and_name_every_omitted_episode',
      MC + 'test_an_outcome_that_differs_inside_a_recipe_keeps_its_own_full_example',
      MC + 'test_stage_two_never_lets_one_policy_or_purpose_stand_for_another',
      MC + 'test_the_refused_v2d_request_rebuilds_exactly_and_fits_after_compaction_with_its_omission_statement']),
    ('I-LOW-3a: NO_CHANGE reason never names an ended search', 'app/lab/loop_limits.py',
     [('    if not ended: return None\n', '    return None\n')], [MC + 'test_a_search_cut_short_by_the_size_rule_is_named_in_the_campaigns_final_reason']),
    ('I-LOW-3b: first-turn lookup ignores the record-row cutoff', 'app/lab/loop_limits.py',
     [('            (int(cutoff), campaign_id, PROMPT_OF[request_kind])).fetchone()', '            (0, campaign_id, PROMPT_OF[request_kind])).fetchone()')],
     [MC + 'test_a_first_turn_the_mechanic_itself_refuses_is_recorded_as_never_sent', PR + 'test_B_a_later_first_turn_refusal_is_before_send_despite_an_earlier_saved_answer']),
    ('I-LOW-3c: a first-turn refusal still uses a candidate request', 'app/lab/learning.py',
     [('                        if first is None:\n                            candidate_count-=1', '                        if first is None:\n                            pass')],
     [MC + 'test_a_first_turn_the_mechanic_itself_refuses_is_recorded_as_never_sent']),
    ('I-LOW-3d: every refusal recorded as FORMAT_REPAIR', 'app/lab/loop_limits.py',
     [('    if first is None:\n        reason = FIRST_TURN_REFUSED_REASON', '    if False:\n        reason = FIRST_TURN_REFUSED_REASON'),
      ("                  first_turn_output_ref=first[0], reason=reason)", "                  first_turn_output_ref=first[0] if first else None, reason=reason)")],
     [MC + 'test_a_first_turn_the_mechanic_itself_refuses_is_recorded_as_never_sent']),
    ('P-LOW-1: stage-2 field named represented_by again', 'app/lab/loop_limits.py',
     [("'group_example': groups[group]}", "'represented_by': groups[group]}")],
     [MC + 'test_stage_two_names_a_group_example_and_says_the_omitted_rows_can_differ_from_it']),
    ('P-LOW-1b: stage-2 texts no longer say rows can differ', 'app/lab/loop_limits.py',
     [("                         'the others are listed by episode_id, and their own rows can differ from that example',",
       "                         'the others are listed by episode_id',")],
     [MC + 'test_stage_two_names_a_group_example_and_says_the_omitted_rows_can_differ_from_it']),
    ('P-LOW-3: a refused format-repair turn leaves no candidate record', 'app/lab/learning.py',
     [("                        store.put_record('campaign_proposals',first_ref,", "                        (lambda *a,**k: None)('campaign_proposals',first_ref,")],
     [MC + 'test_a_refused_format_repair_turn_leaves_a_rejected_proposal_in_the_candidate_history']),
    ('Rule 1 core: an unfit candidate request raises (ERROR) instead of ending the search', 'app/lab/learning.py',
     [('                        except loop_limits.MechanicContextUnfit:\n                            candidate_count-=1',
       '                        except loop_limits.MechanicContextUnfit:\n                            raise\n                            candidate_count-=1')],
     [MC + 'test_a_candidate_request_that_cannot_fit_ends_that_search_without_error_and_is_never_sent']),
    ('Display: challenge_reach list shown for every campaign with a plan', 'app/lab/api.py',
     [("        if plan is not None and plan.get('challenge_selection') is not None:", "        if plan is not None:")],
     [PL + 'test_the_dashboard_projection_and_the_recording_show_both_rules_only_where_declared']),
]


def sha(path):
    return hashlib.sha256(open(path, 'rb').read()).hexdigest()


def run(tests):
    env = dict(os.environ, PYTHONPATH=f'{V}:{V}/spot')
    return subprocess.run([PY, '-B', '-m', 'pytest', '-p', 'vguard', '-p', 'vstub', '-p', 'no:cacheprovider', '-q', *tests],
                          cwd=TREE + '/backend', env=env, capture_output=True, text=True)


def tail(result):
    lines = [l for l in (result.stdout + result.stderr).splitlines() if l.strip()]
    keep = [l for l in lines if re.search(r'passed|failed|error|refused', l)]
    return ' | '.join(keep[-3:])


def main():
    shutil.copy(f'{V}/spot/test_verifier_probes.py', f'{TREE}/backend/tests/lab/test_verifier_probes.py')
    caught = missed = 0
    try:
        all_tests = sorted({t for m in MUTATIONS for t in m[3]})
        base = run(all_tests)
        print(f'UNMUTATED  {"PASS" if base.returncode == 0 else "FAIL"} :: {tail(base)}', flush=True)
        if base.returncode != 0:
            print(base.stdout[-3000:]); sys.exit(2)
        for name, rel, edits, tests in MUTATIONS:
            path = f'{TREE}/backend/{rel}'; before = sha(path); original = open(path).read(); text = original
            for old, new in edits:
                if text.count(old) != 1:
                    print(f'SETUP ERROR {name}: pattern found {text.count(old)} times'); sys.exit(2)
                text = text.replace(old, new)
            open(path, 'w').write(text)
            try:
                result = run(tests)
            finally:
                open(path, 'w').write(original)
                assert sha(path) == before, f'restore failed for {rel}'
            failed = result.returncode != 0
            caught += failed; missed += not failed
            print(f'{"CAUGHT" if failed else "MISSED"}  {name} :: {tail(result)}', flush=True)
    finally:
        os.remove(f'{TREE}/backend/tests/lab/test_verifier_probes.py')
    print(f'TOTAL caught {caught} missed {missed}; every mutated file restored (sha256 checked)')


main()
