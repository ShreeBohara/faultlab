"""Follow-up stage negative controls ($0, offline), in a scratch copy outside the Desktop that is deleted at the end.

Run from faultlab/:  .venv/bin/python -B artifacts/product-diagnosis-rules-2026-09-30/followup/mutation_checks.py

Scratch tree: /Users/shree/FaultLab_Scratch/followup-diagnosis-rules/mutations/ (backend, contracts, the two probe
scripts, the artifact files the tests read, the frontend's sources, tests and config; node_modules and audit/ are
symlinks, so nothing protected is copied). A second scratch file, .../grown/lab.sqlite3, is a copy of the saved
native-v2b store plus synthetic records standing in for a later live run (grow_store.py). The saved store itself is only
ever read with mode=ro&immutable=1.

1. The unmutated copy passes: the three diagnosis-rules test files, the eight saved-store tests (none skipped) and the
   frontend diagnosis-rules test.
2. Snapshot controls (part B):
   S1 the unpinned saved-store tests (626bae4's test_history_fireability.py) fail on today's store (the known 2 failures);
   S2 the pinned saved-store tests pass on the grown store (records added after the snapshot change nothing);
   S3 the unpinned versions fail on the grown store (626bae4's fireability and v2d-rebuild tests, and the diagnosis-rules
      T1 test as it was before this stage);
   S4 the pinned fireability tests fail when their cutoff is moved to the store's end today (8583), so the snapshot, not
      a loosened assertion, is what makes them pass.
3. Mutations of the product: part A (the restored checks_note) and part B (what the saved-store tests verify); each must
   make at least one of the tests it targets fail. Every mutated file is restored before the next one.
Backend runs use pytest's own network block (conftest) and PYTHONDONTWRITEBYTECODE; the frontend run uses vitest.
"""
import os
import re
import shutil
import subprocess
from pathlib import Path

FAULTLAB = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
BASE = Path('/Users/shree/FaultLab_Scratch/followup-diagnosis-rules')
SCRATCH = BASE / 'mutations'
GROWN = BASE / 'grown' / 'lab.sqlite3'
SAVED = '/Users/shree/FaultLab_Runs/2026-09-30/native-v2b/lab.sqlite3'
PYTHON = FAULTLAB / '.venv/bin/python'
COPY = ['backend', 'contracts', 'scripts/experiments/diagnosis_probe.py', 'scripts/experiments/check_evidence_gap_misreading_v2.py',
        'artifacts/product-diagnosis-rules-2026-09-30/probe-inputs', 'artifacts/analysis-diagnosis-2026-09-30/inv-a',
        'artifacts/analysis-diagnosis-2026-09-30/design-minimal', 'artifacts/analysis-diagnosis-2026-09-30/designer-integrity',
        *[f'artifacts/product-live-2026-09-30/native-v2{r}-run/export.json' for r in 'defg'],
        'frontend/src', 'frontend/tests', 'frontend/index.html', 'frontend/local-ports.ts', 'frontend/package.json',
        'frontend/tsconfig.json', 'frontend/vite.config.ts']
PART_A = ['tests/lab/test_diagnosis_rules.py', 'tests/lab/test_diagnosis_rules_loop.py', 'tests/experiments/test_diagnosis_probe.py']
FIRE = 'tests/lab/test_history_fireability.py::'
FIRE_TESTS = [FIRE + 'test_a_new_v4_plan_on_the_saved_store_refuses_the_lone_status_read_target',
              FIRE + 'test_the_saved_stores_status_read_picks_are_refused_and_its_other_picks_are_allowed',
              FIRE + 'test_through_the_real_loop_on_the_saved_store_a_status_pick_is_refused_and_replanned']
T1 = 'tests/lab/test_diagnosis_rules.py::test_T1_every_saved_native_v2b_plan_rereads_with_its_plan_hash_and_no_new_keys'
V2D_TESTS = ['tests/lab/test_loop_limits_mechanic_context.py::test_the_refused_v2d_request_rebuilds_exactly_and_fits_after_compaction_with_its_omission_statement',
             'tests/lab/test_citation_status.py::test_v2ds_refused_candidate_request_with_the_block_still_fits_after_compaction_and_keeps_every_row']
OTHER_SAVED = ['tests/lab/test_citation_status.py::test_the_v2e_and_v2d_diagnosis_requests_rebuild_exactly_and_all_8_diagnosed_episodes_decoded_every_citation',
               'tests/lab/test_citation_status.py::test_a_new_native_v2_plan_on_a_copy_of_the_v2e_store_gets_the_block_with_zero_undecoded_for_every_diagnosed_episode']
SAVED_TESTS = FIRE_TESTS + [T1] + V2D_TESTS + OTHER_SAVED
STORE_FILES = ['backend/tests/lab/test_history_fireability.py', 'backend/tests/lab/test_diagnosis_rules.py',
               'backend/tests/lab/test_loop_limits_mechanic_context.py', 'backend/tests/lab/citation_status_saved.py']

# The diagnosis-rules T1 test exactly as it was before this stage (verified round), and as pinned now.
T1_UNPINNED = """        plans = store.list_records('campaign_plans')
        assert plans
"""
T1_PINNED = """        plans = [raw for _, raw in store.records_upto('campaign_plans', SAVED_PLANS_CUTOFF)]
        assert {raw['campaign_id'] for raw in plans} == SAVED_PLAN_CAMPAIGNS and len(plans) == 6
"""
GUIDE = 'backend/app/lab/diagnosis_guide.py'
C6 = "C6 is the check of the report\\'s citations: where C6 passed, that report\\'s citations met it."
# (part, label, file, text now, mutated text, tests the mutation targets ('A' = PART_A + frontend, 'B' = SAVED_TESTS))
MUTATIONS = [
    ('A', 'the C6 sentence is back in checks_note (the draft\'s full note)', GUIDE,
     "'check\\'s public meaning. Explain each failed check from its own meaning.')",
     "'check\\'s public meaning. " + C6 + " Explain each failed check from its own meaning.')", 'backend'),
    ('A', 'the block leaves out checks_note (the declaration still has it)', GUIDE,
     "'checks': dict(rule['checks']), 'checks_note': rule['checks_note'], 'contract_note'", "'checks': dict(rule['checks']), 'contract_note'", 'backend'),
    ('A', 'the plan validator no longer binds the checks_note text', GUIDE,
     "FIXED_TEXT = {'meaning': MEANING, 'kinds': KINDS, 'checks_note': CHECKS_NOTE, ", "FIXED_TEXT = {'meaning': MEANING, 'kinds': KINDS, ", 'backend'),
    ('A', 'the note\'s second sentence is shortened', GUIDE,
     "Explain each failed check from its own meaning.')", "Explain each failed check.')", 'backend'),
    ('A', 'the dashboard validator no longer checks checks_note', 'frontend/src/loopLimits.ts',
     "&& text(value.checks_note)\n    && text(value.contract_note)", "\n    && text(value.contract_note)", 'frontend'),
    ('B', 'fireability needs 5 verified episodes instead of 3 before refusing a target', 'backend/app/lab/fireability.py',
     'MIN_VERIFIED_EPISODES = 3\n', 'MIN_VERIFIED_EPISODES = 5\n', 'backend'),
    ('B', 'fireability refuses no fired share (bar 0 instead of 1/2)', 'backend/app/lab/fireability.py',
     'MIN_FIRED_SHARE = Fraction(1, 2)\n', 'MIN_FIRED_SHARE = Fraction(0, 1)\n', 'backend'),
    ('B', 'the agent history ignores its record cutoff (reads every episode now in the store)', 'backend/app/lab/agent_history.py',
     "candidates = store.records_upto('episodes', cutoff, where=", "candidates = store.records_upto('episodes', store.max_record_rowid(), where=", 'backend'),
    ('B', 'history replay needs 4 verified episodes instead of 2', 'backend/app/lab/history_replay.py',
     'MIN_VERIFIED_EPISODES = 2\n', 'MIN_VERIFIED_EPISODES = 4\n', 'backend'),
    ('B', 'older plans gain a null mechanic_diagnosis key when re-read', 'backend/app/lab/run_plans.py',
     "'explorer_selection', 'mechanic_diagnosis',\n", "'explorer_selection',\n", 'backend'),
    ('B', 'the Mechanic request-size rule compacts to 1,000 tokens more', 'backend/app/lab/loop_limits.py',
     'COMPACTION_TARGET_TOKENS = MODEL_INPUT_TOKEN_LIMIT - FORMAT_REPAIR_RESERVE_TOKENS\n',
     'COMPACTION_TARGET_TOKENS = MODEL_INPUT_TOKEN_LIMIT - FORMAT_REPAIR_RESERVE_TOKENS + 1000\n', 'backend'),
]


def backend(tests):
    env = {**os.environ, 'PYTHONDONTWRITEBYTECODE': '1', 'PYTHON_DOTENV_DISABLED': '1', 'COLUMNS': '1000'}  # wide, so pytest keeps each failure's message
    result = subprocess.run([str(PYTHON), '-B', '-m', 'pytest', '-p', 'no:cacheprovider', '-q', '-rA', *tests],
                            cwd=SCRATCH / 'backend', capture_output=True, text=True, env=env)
    lines = [line.strip() for line in (result.stdout + result.stderr).splitlines() if line.strip()]
    outcomes = {}
    for line in lines:
        match = re.match(r'^(PASSED|FAILED|SKIPPED|ERROR) (\S+)(?: - (.*))?$', line)
        if match:
            outcomes[match.group(2)] = (match.group(1), (match.group(3) or '')[:150])
    summary = next((line for line in reversed(lines) if re.search(r'\d+ (passed|failed|error)', line)), lines[-1] if lines else '')
    return result.returncode, outcomes, summary


def frontend():
    result = subprocess.run(['npx', 'vitest', 'run', 'tests/diagnosis-rules.test.tsx'], cwd=SCRATCH / 'frontend', capture_output=True, text=True)
    lines = [line.strip() for line in (result.stdout + result.stderr).splitlines() if line.strip()]
    failed = next((line for line in lines if line.startswith('FAIL ') or line.startswith('×') or line.startswith('✗')), None)
    return result.returncode, failed, next((line for line in lines if line.startswith('Tests ')), lines[-1] if lines else '')


def short(outcomes):
    return '; '.join(f"{node.split('::')[-1][:60]}={state}" + (f' ({why})' if state == 'FAILED' and why else '')
                     for node, (state, why) in outcomes.items())


def edit(relative, old, new):
    path = SCRATCH / relative
    text = path.read_text()
    assert text.count(old) >= 1, (relative, old[:60])
    path.write_text(text.replace(old, new))
    return text


def git_show(relative):
    return subprocess.run(['git', 'show', f'626bae4:{relative}'], cwd=FAULTLAB, capture_output=True, text=True, check=True,
                          env={**os.environ, 'GIT_OPTIONAL_LOCKS': '0'}).stdout


def point_at(store):
    saved = {relative: (SCRATCH / relative).read_text() for relative in STORE_FILES}
    for relative in STORE_FILES:
        edit(relative, SAVED, str(store))
    return saved


def restore(saved):
    for relative, text in saved.items():
        (SCRATCH / relative).write_text(text)


def main():
    if BASE.exists():
        shutil.rmtree(BASE)
    for relative in COPY:
        source, target = FAULTLAB / relative, SCRATCH / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        (shutil.copytree(source, target, ignore=shutil.ignore_patterns('__pycache__', '.pytest_cache')) if source.is_dir()
         else shutil.copyfile(source, target))
    (SCRATCH / 'audit').symlink_to(FAULTLAB / 'audit')
    (SCRATCH / 'frontend/node_modules').symlink_to(FAULTLAB / 'frontend/node_modules')
    grown = subprocess.run([str(PYTHON), '-B', str(HERE / 'run_guarded.py'), str(HERE / 'grow_store.py'), str(GROWN)],
                           cwd=FAULTLAB / 'backend', capture_output=True, text=True, env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'})
    print('GROWN STORE (grow_store.py):', grown.stdout.strip().replace('\n', ' '), grown.stderr.strip().splitlines()[-1], flush=True)
    assert grown.returncode == 0
    caught = total = 0
    try:
        code, outcomes, summary = backend(PART_A + SAVED_TESTS)
        states = {node: state for node, (state, _) in outcomes.items() if node in SAVED_TESTS}
        print(f'UNMUTATED backend: exit {code}: {summary}; saved-store tests: {states}', flush=True)
        assert code == 0 and all(states.get(node) == 'PASSED' for node in SAVED_TESTS), 'the unmutated copy must pass, none skipped'
        code, failed, summary = frontend()
        print(f'UNMUTATED frontend: exit {code}: {summary}', flush=True)
        assert code == 0

        # S1: the unpinned fireability tests (626bae4) on today's store.
        fire = 'backend/tests/lab/test_history_fireability.py'
        pinned_fire = (SCRATCH / fire).read_text(); (SCRATCH / fire).write_text(git_show(fire))
        code, outcomes, summary = backend(FIRE_TESTS)
        (SCRATCH / fire).write_text(pinned_fire)
        print(f'S1 unpinned (626bae4) fireability tests, today\'s store: exit {code}: {summary}\n    {short(outcomes)}', flush=True)

        # S2: the pinned tests on the grown store.
        saved = point_at(GROWN)
        try:
            code, outcomes, summary = backend(SAVED_TESTS)
            print(f'S2 pinned saved-store tests, grown store: exit {code}: {summary}\n    {short(outcomes)}', flush=True)
            assert code == 0 and all(outcomes.get(node, ('?',))[0] == 'PASSED' for node in SAVED_TESTS)
            # S3: the unpinned versions on the grown store.
            loop = 'backend/tests/lab/test_loop_limits_mechanic_context.py'
            pinned_loop = (SCRATCH / loop).read_text()
            (SCRATCH / fire).write_text(git_show(fire).replace(SAVED, str(GROWN)))
            (SCRATCH / loop).write_text(git_show(loop).replace(SAVED, str(GROWN)))
            before_t1 = edit('backend/tests/lab/test_diagnosis_rules.py', T1_PINNED, T1_UNPINNED)
            try:
                code, outcomes, summary = backend(FIRE_TESTS + [T1] + V2D_TESTS)
            finally:
                (SCRATCH / fire).write_text(pinned_fire.replace(SAVED, str(GROWN)))
                (SCRATCH / loop).write_text(pinned_loop)
                (SCRATCH / 'backend/tests/lab/test_diagnosis_rules.py').write_text(before_t1)
            print(f'S3 unpinned versions, grown store: exit {code}: {summary}\n    {short(outcomes)}', flush=True)
        finally:
            restore(saved)

        # S4: the pinned fireability tests with the cutoff moved to the store's end today.
        before = edit(fire, 'SNAPSHOT_CUTOFF = 6748\n', 'SNAPSHOT_CUTOFF = 8583\n')
        code, outcomes, summary = backend(FIRE_TESTS)
        (SCRATCH / fire).write_text(before)
        print(f'S4 pinned fireability tests with the cutoff at the store\'s end (8583): exit {code}: {summary}\n    {short(outcomes)}', flush=True)

        # Mutations of the product.
        for part, label, relative, now, mutated, stage in MUTATIONS:
            total += 1
            original = edit(relative, now, mutated)
            try:
                if stage == 'frontend':
                    code, failed, summary = frontend(); detail = failed or ''
                else:
                    code, outcomes, summary = backend(PART_A if part == 'A' else SAVED_TESTS)
                    detail = short({n: o for n, o in outcomes.items() if o[0] != 'PASSED'})
            finally:
                (SCRATCH / relative).write_text(original)
            caught += code != 0
            print(f"{'CAUGHT' if code != 0 else 'MISSED'} [{part}] {label}: {summary}\n    {detail[:1200]}", flush=True)
        code, outcomes, summary = backend(PART_A + SAVED_TESTS)
        print(f'RESTORED copy: exit {code}: {summary}', flush=True)
    finally:
        shutil.rmtree(BASE)
        print(f'scratch deleted: {not BASE.exists()}')
    print(f'{caught} of {total} product mutations caught')


if __name__ == '__main__':
    main()
