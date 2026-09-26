#!/usr/bin/env python3
"""Phase 28 landing step F0 (PHASE28_EXPERIMENT.md section 9): check, before and after the copy, that what lands on
the main checkout is exactly what was last reviewed. $0. It hashes files, runs the pinned gate_freeze.py once
(--before; read-only, stdlib only, it never opens .env), reads the Phase 28a run's manifest and read-outs, reads the
28a harness's and the runner's constants with ast (it imports neither), and lists processes. It writes exactly one
file, the gate freeze it takes (--gate-freeze-before; never overwritten), and copies nothing.

--before (from the main checkout's root, with ./.venv/bin/python, before anything is copied):
  0. the arguments: --phase28a-run is a repository-relative run directory artifacts/phase28a-<date>/<name>, and
     --phase28a-readouts (if given) names that run's readouts.json or its date folder's readouts-recheck.json. A
     refusal here comes before the gate freeze is taken, so it writes nothing and a re-run can use the same file
     names (review round 3, R3L-1). A refusal after the freeze leaves the freeze file behind: the protocol's F0 step 3
     says to rename that attempt's two outputs with a -<n> suffix and re-run;
  1. the gate freeze: it runs the pinned gate_freeze.py (5e21c0ec...) itself with <main>/.venv/bin/python, saves the
     output to --gate-freeze-before, and requires it to equal Phase 22's freeze file
     (artifacts/phase22-2026-09-24/gate-freeze-after.json, 8994e962...) byte for byte, so nobody changed backend/app
     meanwhile. (Review round 2, WB-3: round 1 hashed a file the operator supplied, and a copy of Phase 22's own
     file passed over a drifted tree.)
  2. the three files the landing overwrites are still their base versions on the main checkout, and the four new
     files do not exist there yet;
  3. the six code and test files in --from equal REVIEWED, and the protocol's declared text (every byte above its
     '## Review log' heading) equals REVIEWED_PROTOCOL_BODY. The Review log below it may grow: a round that closes
     with only a log entry needs no new pin (review round 2, WB-2 and LN-2). The protocol as a whole is bound later,
     by P at F9 and in review.json;
  4. the prep scripts beside this one equal REVIEWED_PREP (review round 2, WB-4 and LN-3), and this script's own
     sha256 is printed, to be compared with the reviewed-build record's (build_protocol_sha256, the whole protocol in
     --from, is printed too, and is compared with the record's by hand: review round 3, R3L-3);
  5. Phase 28a ended on GO: its run manifest is final and its read-outs say GO. The read-outs are the run's own
     readouts.json; only when the run wrote none may --phase28a-readouts name the declared recomputation
     artifacts/phase28a-<date>/readouts-recheck.json (review round 2, WB-5; the runner applies the same rule);
  6. the Phase 28a file format copied here and in the runner in --from equals the 28a harness's on the main
     checkout (review round 2, LN-5);
  7. Phase 30 has ended (docs/part2/PHASE30_RESULTS.md exists) and no paid run is live (slot2_probe's process rule,
     imported, never edited).
--after (after the copy; run the copy in artifacts/phase28-<date>/prep/, which is the one F4 uses):
  every landed file equals the file in --from byte for byte (the protocol included, Review log and all), the six
  equal REVIEWED and the protocol's declared text equals REVIEWED_PROTOCOL_BODY; the pre-change copies under
  --pre-change-dir are the three base files at their repository paths; checks 0, 4, 5 and 6 again. It checks its
  siblings only against values it carries itself, so the protocol's F0 step 6 also compares its printed
  script_sha256 with the record's and checks the landed prep folder against the preserve's PREP_SHA256SUMS
  (review round 3, R3-2).
REVIEWED, REVIEWED_PROTOCOL_BODY and REVIEWED_PREP change only as part of a review round's fixes, and are reviewed
with them (the one rule of PHASE28_EXPERIMENT.md section 9). Exit 0 = every check passed.

Usage (from the main checkout's root, with the venv interpreter; <build> is the preserve's build/, the worktree
only as a fallback):
  ./.venv/bin/python <prep>/landing_check_p28.py --before --from <build> \\
      --phase28a-run artifacts/phase28a-<date>/<name> --gate-freeze-before artifacts/phase28-<date>/gate-freeze-before.json
  ./.venv/bin/python artifacts/phase28-<date>/prep/landing_check_p28.py --after --from <the same build> \\
      --phase28a-run artifacts/phase28a-<date>/<name> --pre-change-dir artifacts/phase28-<date>/pre-change
  (add --phase28a-readouts artifacts/phase28a-<date>/readouts-recheck.json only if the 28a run wrote no readouts.json)
"""
import argparse
import ast
import hashlib
import json
import pathlib
import subprocess
import sys

PHASE22_FREEZE = 'artifacts/phase22-2026-09-24/gate-freeze-after.json'
PHASE22_FREEZE_SHA256 = '8994e96273be43a8abc0f10fd41a131d9c0700b9a9916b70ddbef2afd74a3bf1'
GATE_FREEZE_SCRIPT = 'scripts/experiments/gate_freeze.py'
GATE_FREEZE_SCRIPT_SHA256 = '5e21c0ecb64ee12cbe9fb4b0972efa8f6d84b08011faddd23f526ff3b79e1190'
VENV_PYTHON = '.venv/bin/python'
GATE_FREEZE_TIMEOUT = 900
# The main checkout before landing: the Phase 22 tree (configuration 2cf63e93...).
BASE = {
    'backend/app/lab/completion_study.py': 'c3fc22345359157612631c2b88c1ab8d641b274ad5aaf1527ae77dbe7107988a',
    'backend/app/lab/api.py': '9c3ac4534a1f40da9c2c07e22e7a0026d0b57ca1a4f4667baf5dadc2240a2a63',
    'backend/tests/experiments/test_run_gap_probe.py': '336b485f8cebf24c2afba44ee9979f9cc5513e78441ced76d73477a9e8afd564',
}
PROTOCOL = 'docs/part2/PHASE28_EXPERIMENT.md'
RUNNER = 'scripts/experiments/run_upgrade_loop.py'
NEW_FILES = ('backend/tests/lab/test_completion_manifests.py', RUNNER,
             'backend/tests/experiments/test_run_upgrade_loop.py', PROTOCOL)
REVIEW_LOG_HEADING = b'## Review log'
# The build after the review round-3 fixes (2026-09-26 UTC). Whole-file sha256 of the six code and test files.
REVIEWED_ROUND = 'after review round 3'
REVIEWED = {
    'backend/app/lab/completion_study.py': '03e3d8bed4cbcc117ffdbb9f552f254cd33234d177e6b58254aba3f398a1b9c4',
    'backend/app/lab/api.py': '32a1b0873dd83baf7c57ec4f610d400b87179fe6adb1a88d4d901145da813283',
    'backend/tests/lab/test_completion_manifests.py': 'fb352a62314bc520d2dafe92533a0674be1aca62a591432243fea82ec9e8f359',
    'backend/tests/experiments/test_run_gap_probe.py': '03dd92e21c3e0908a068971eaf101a442cf5daf5dbf27bef674161e806b6f2a0',
    RUNNER: '9432419e2b7585d447924be5a603851290aecbb6adfac5385419385176da63a7',
    'backend/tests/experiments/test_run_upgrade_loop.py': '1de4f5214e6048758920e2ecc2773235b9a17afb2c5c055705f92d32d4c0a73b',
}
# sha256 of every byte of the protocol above its first line that starts with '## Review log'.
REVIEWED_PROTOCOL_BODY = '672195d6155b6ab0ba0f2beb4d9e3a2b324950de7b01e7ee2bbac74ef0ee84ea'
# The prep scripts that travel with this one (the same folder), as reviewed.
REVIEWED_PREP = {
    'freeze_compare_p28.py': '1e53a42d7abce4145e8379e47279a48b92b570836a81b310589fa6f23bc5cd05',
    'new_function_hashes.py': '9dc8d889cfa908bb19d90ef81c993a2f18ffb855057a2bd18f9d638100e2ff5f',
    'manifest_hash.py': '5b3199e56884643ff6c31385891cb3eed3d50fb673c3242b35f793961c1ba3b1',
    'draft_manifest_r1.py': 'a49506ea9d5f5c67076539bbbb3053aece80d3c3669492ea27d7366264187604',
    'design_numbers_r1.py': '7a1c413e4e03afeb914e0da36b8370328d398d9c734b0dc66964faa0a9b88f6c',
}
PHASE30_RESULTS = 'docs/part2/PHASE30_RESULTS.md'
# The Phase 28a run, as run_upgrade_loop.phase28a_problem reads it (upgrade_mechanic_probe.py writes it).
HARNESS_28A = 'scripts/experiments/upgrade_mechanic_probe.py'
PHASE28A_PREFIX = 'phase28a-'
PHASE28A_CLAIM_DIR = 'phase28a-live-claims'
PHASE28A_MANIFEST = 'upgrade-mechanic-probe-manifest.json'
PHASE28A_READOUTS = 'readouts.json'
PHASE28A_READOUT_SCHEMA = 'faultlab-upgrade-mechanic-probe-readouts/v1'
PHASE28A_FINAL_STATUSES = ('COMPLETED', 'STOPPED', 'ABORTED')
PHASE28A_RECHECK = 'readouts-recheck.json'
PHASE28A_MISMATCH_KEY = 'label'
# The 28a harness's names for the copied constants, and the runner's.
HARNESS_NAMES = {'PHASE_PREFIX': 'PHASE28A_PREFIX', 'CLAIM_DIR': 'PHASE28A_CLAIM_DIR', 'MANIFEST_NAME': 'PHASE28A_MANIFEST',
                 'READOUT_SCHEMA': 'PHASE28A_READOUT_SCHEMA', 'FINAL_STATUSES': 'PHASE28A_FINAL_STATUSES'}
RUNNER_NAMES = ('PHASE28A_PREFIX', 'PHASE28A_CLAIM_DIR', 'PHASE28A_MANIFEST', 'PHASE28A_READOUTS',
                'PHASE28A_READOUT_SCHEMA', 'PHASE28A_FINAL_STATUSES', 'PHASE28A_RECHECK', 'PHASE28A_MISMATCH_KEY')


def sha256(path):
    try:
        return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()
    except OSError:
        return None


def protocol_body(data):
    """Every byte above the first line that starts with '## Review log', or None when there is no such line."""
    offset = 0
    for line in data.splitlines(keepends=True):
        if line.startswith(REVIEW_LOG_HEADING):
            return data[:offset]
        offset += len(line)
    return None


def protocol_problems(path, where):
    try:
        body = protocol_body(pathlib.Path(path).read_bytes())
    except OSError:
        return [f'{PROTOCOL} is missing {where}'], None
    if body is None:
        return [f'{PROTOCOL} {where} has no "## Review log" heading'], None
    value = hashlib.sha256(body).hexdigest()
    if value != REVIEWED_PROTOCOL_BODY:
        return [f'{PROTOCOL} {where}: the declared text above "## Review log" is not the last-reviewed version '
                f'({REVIEWED_ROUND})'], value
    return [], value


def literal(node):
    """A string or a tuple of strings written literally; anything else is None (nothing is evaluated)."""
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.Tuple) and all(isinstance(e, ast.Constant) for e in node.elts):
        return tuple(e.value for e in node.elts)
    return None


def module_constants(path, names):
    found = {}
    for node in ast.parse(pathlib.Path(path).read_text(encoding='utf-8')).body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id in names:
                    found[target.id] = literal(node.value)
    return found


def copied_constant_problems(root, runner_path):
    """LN-5: the 28a file format copied here and in the runner equals the 28a harness's (read with ast)."""
    ours = {name: globals()[name] for name in RUNNER_NAMES}
    problems, seen = [], {}
    try:
        harness = module_constants(root / HARNESS_28A, set(HARNESS_NAMES))
        seen['harness'] = {HARNESS_NAMES[k]: v for k, v in harness.items()}
        for name, mine in HARNESS_NAMES.items():
            if harness.get(name) != ours[mine]:
                problems.append(f'the 28a harness {name} is {harness.get(name)!r}; this check copied {ours[mine]!r}')
        text = (root / HARNESS_28A).read_text(encoding='utf-8')
        if f"out / '{PHASE28A_READOUTS}'" not in text or f"'{PHASE28A_MISMATCH_KEY}': NOT_THE_RUNS_HARNESS" not in text:
            problems.append(f'the 28a harness no longer writes {PHASE28A_READOUTS} or labels a mismatched recomputation '
                            f'under {PHASE28A_MISMATCH_KEY!r}')
    except (OSError, SyntaxError) as error:
        problems.append(f'the 28a harness {HARNESS_28A} cannot be read ({type(error).__name__})')
    try:
        runner = module_constants(runner_path, set(RUNNER_NAMES))
        seen['runner'] = runner
        if runner != ours:
            problems.append(f'the runner copies the 28a file format differently: {runner} != {ours}')
    except (OSError, SyntaxError) as error:
        problems.append(f'the runner {runner_path} cannot be read ({type(error).__name__})')
    return problems, seen


def phase28a_arguments(run_dir, readouts_arg):
    """(problems, own, recheck, named) from the two 28a arguments alone, with no file read: the run directory's
    shape and which read-outs file is named. main() applies it before the gate freeze is taken (review round 3,
    R3L-1), so a refusal here writes nothing."""
    parts = pathlib.PurePosixPath(run_dir or '').parts
    if (len(parts) != 3 or parts[0] != 'artifacts' or not parts[1].startswith(PHASE28A_PREFIX)
            or parts[1] == PHASE28A_CLAIM_DIR or parts[2] in ('.', '..')):
        return [('--phase28a-run is not a run directory artifacts/phase28a-<date>/<name> (pass it repository-relative, '
                 'as the protocol writes it)')], None, None, None
    own = f'{run_dir}/{PHASE28A_READOUTS}'
    recheck = f'artifacts/{parts[1]}/{PHASE28A_RECHECK}'
    named = readouts_arg or own
    if named not in (own, recheck):
        return [f'--phase28a-readouts names neither {own} nor {recheck}'], own, recheck, named
    return [], own, recheck, named


def phase28a(root, run_dir, readouts_arg):
    """(problems, the read-outs file used, its sha256) for the named Phase 28a run; the runner's rule."""
    found, own, recheck, named = phase28a_arguments(run_dir, readouts_arg)
    if found:
        return found, named, None
    try:
        manifest = json.loads((root / run_dir / PHASE28A_MANIFEST).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return [f'Phase 28a: {run_dir} has no readable run manifest (has 28a run?)'], named, None
    problems = []
    if not (isinstance(manifest, dict) and manifest.get('status') in PHASE28A_FINAL_STATUSES and manifest.get('ended_at')):
        problems.append('Phase 28a: the run has not ended (its run manifest is not final)')
    if named == recheck and (root / own).exists():
        problems.append(f'Phase 28a: the run wrote its own {PHASE28A_READOUTS}; the landing uses it, not a recomputation')
    try:
        raw = (root / named).read_bytes()
        readouts = json.loads(raw)
    except (OSError, ValueError):
        return problems + [f'Phase 28a: the read-outs {named} are missing or not JSON'], named, None
    if isinstance(readouts, dict) and PHASE28A_MISMATCH_KEY in readouts:
        problems.append(f"Phase 28a: {named} is a recomputation labelled {readouts.get(PHASE28A_MISMATCH_KEY)!r}")
    elif not (isinstance(readouts, dict) and readouts.get('schema_version') == PHASE28A_READOUT_SCHEMA
              and readouts.get('decision') == 'GO'):
        decision = readouts.get('decision') if isinstance(readouts, dict) else None
        problems.append(f'Phase 28a: the read-outs do not say GO (decision {decision!r})')
    return problems, named, hashlib.sha256(raw).hexdigest()


def take_gate_freeze(root, out_path):
    """WB-3: run the pinned gate_freeze.py with the venv, save its output (never over an existing file) and compare it
    with Phase 22's freeze byte for byte. Returns (problems, record)."""
    record = {'script': GATE_FREEZE_SCRIPT, 'script_sha256': sha256(root / GATE_FREEZE_SCRIPT),
              'python': str(root / VENV_PYTHON), 'output': str(out_path)}
    if record['script_sha256'] != GATE_FREEZE_SCRIPT_SHA256:
        return [f'{GATE_FREEZE_SCRIPT} is not the pinned script ({GATE_FREEZE_SCRIPT_SHA256[:8]}...)'], record
    if out_path.exists():
        return [f'{out_path} exists; the gate freeze taken here is never written over an earlier one (name a new '
                'file, e.g. gate-freeze-before-2.json)'], record
    try:
        result = subprocess.run([str(root / VENV_PYTHON), str(root / GATE_FREEZE_SCRIPT)], cwd=root,
                                capture_output=True, timeout=GATE_FREEZE_TIMEOUT, check=False)
    except (OSError, subprocess.SubprocessError) as error:
        return [f'gate_freeze.py could not run ({type(error).__name__})'], record
    record['exit_status'] = result.returncode
    try:
        with open(out_path, 'xb') as handle:
            handle.write(result.stdout)
    except OSError as error:
        return [f'the gate freeze could not be saved to {out_path} ({type(error).__name__}); create the folder first '
                '(mkdir -p artifacts/phase28-<date>)'], record
    record['output_sha256'] = hashlib.sha256(result.stdout).hexdigest()
    problems = []
    if result.returncode != 0:
        problems.append(f'gate_freeze.py exited {result.returncode}')
    try:
        phase22 = (root / PHASE22_FREEZE).read_bytes()
    except OSError:
        return problems + [f'{PHASE22_FREEZE} cannot be read'], record
    if hashlib.sha256(phase22).hexdigest() != PHASE22_FREEZE_SHA256:
        problems.append(f'{PHASE22_FREEZE} is not the Phase 22 freeze (8994e962...)')
    if result.stdout != phase22:
        problems.append('the gate freeze of the main checkout now is not the Phase 22 freeze byte for byte: backend/app '
                        'or another fingerprinted file changed after Phase 22')
        try:
            now, then = json.loads(result.stdout), json.loads(phase22)
            record['differs'] = sorted(f'{section}:{key}' for section in ('functions', 'files', 'fingerprints')
                                       for key in set(now.get(section) or {}) | set(then.get(section) or {})
                                       if (now.get(section) or {}).get(key) != (then.get(section) or {}).get(key))
        except ValueError:
            record['differs'] = 'not JSON'
    return problems, record


def prep_problems(here):
    found = {name: sha256(here / name) for name in REVIEWED_PREP}
    return [f'the prep script {name} beside this check is not the reviewed version ({REVIEWED_ROUND})'
            for name, value in REVIEWED_PREP.items() if found[name] != value], found


def paid_runs(root):
    try:
        sys.path.insert(0, str(root / 'scripts/experiments'))
        import slot2_probe  # noqa: E402  the reviewed Phase 25 harness; only its paid-run process rule is used
        return slot2_probe.live_experiment_processes()
    except Exception as error:  # noqa: BLE001  fail closed
        return [f'the paid-run process rule could not run ({type(error).__name__}), so no live run can be ruled out']


def main(argv=None):
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--before', action='store_true')
    mode.add_argument('--after', action='store_true')
    parser.add_argument('--main', default='.', help='the main checkout root (default: the current directory)')
    parser.add_argument('--from', dest='source', required=True,
                        help='the build the files are copied from: the preserve\'s build/ folder (the worktree only as a fallback)')
    parser.add_argument('--phase28a-run', required=True, help='artifacts/phase28a-<date>/<name>')
    parser.add_argument('--phase28a-readouts',
                        help='only if the 28a run wrote no readouts.json: artifacts/phase28a-<date>/readouts-recheck.json')
    parser.add_argument('--gate-freeze-before', help='--before: where to save the gate freeze this check takes (new file)')
    parser.add_argument('--pre-change-dir', help='--after: the folder holding the three pre-change copies at their paths')
    args = parser.parse_args(argv)
    root = pathlib.Path(args.main).resolve()
    source = pathlib.Path(args.source).resolve()
    here = pathlib.Path(__file__).resolve().parent
    checks, problems = {'script_sha256': sha256(__file__)}, []
    if args.before and not args.gate_freeze_before:
        parser.error('--before needs --gate-freeze-before')
    if args.after and not args.pre_change_dir:
        parser.error('--after needs --pre-change-dir')
    early = phase28a_arguments(args.phase28a_run, args.phase28a_readouts)[0]
    if early:
        # Review round 3 (R3L-1): refused on the arguments alone, before the gate freeze is taken, so nothing is
        # written and a re-run can use the same file names.
        checks['arguments'] = ('refused before any other check: no gate freeze was taken and nothing was written; '
                               're-run with the same file names')
        return report(args, root, source, checks, early)
    if args.before:
        found, checks['gate_freeze_before'] = take_gate_freeze(root, root / args.gate_freeze_before)
        problems += found
        for path, value in BASE.items():
            now = checks.setdefault('main_before', {})[path] = sha256(root / path)
            if now != value:
                problems.append(f'{path} on the main checkout is not its base version ({value[:8]}...)')
        for path in NEW_FILES:
            present = checks.setdefault('main_new_files_present', {})[path] = (root / path).exists()
            if present:
                problems.append(f'{path} already exists on the main checkout')
        for path, value in REVIEWED.items():
            now = checks.setdefault('build', {})[path] = sha256(source / path)
            if now != value:
                problems.append(f'{path} in the build is not the last-reviewed version ({REVIEWED_ROUND})')
        found, checks['build_protocol_body'] = protocol_problems(source / PROTOCOL, 'in the build')
        problems += found
        checks['build_protocol_sha256'] = sha256(source / PROTOCOL)
        runner_path = source / RUNNER
        results = (root / PHASE30_RESULTS).exists()
        checks['phase30_results_written'] = results
        if not results:
            problems.append(f'Phase 30 has not ended: {PHASE30_RESULTS} does not exist')
        live = paid_runs(root)
        checks['paid_runs_live'] = live
        if live:
            problems.append(f'a paid run is live: {live[0]}')
    else:
        for path in (*REVIEWED, PROTOCOL):
            landed, built = sha256(root / path), sha256(source / path)
            checks.setdefault('main_after', {})[path] = landed
            if landed is None or landed != built:
                problems.append(f'{path} on the main checkout is not the file in the build')
            elif path in REVIEWED and landed != REVIEWED[path]:
                problems.append(f'{path} on the main checkout is not the last-reviewed version ({REVIEWED_ROUND})')
        found, checks['main_protocol_body'] = protocol_problems(root / PROTOCOL, 'on the main checkout')
        problems += found
        for path, value in BASE.items():
            copy = checks.setdefault('pre_change_copies', {})[path] = sha256(root / args.pre_change_dir / path)
            if copy != value:
                problems.append(f'the pre-change copy of {path} is missing or is not the base file ({value[:8]}...)')
        runner_path = root / RUNNER
    found, checks['prep'] = prep_problems(here)
    problems += found
    found, checks['phase28a_format'] = copied_constant_problems(root, runner_path)
    problems += found
    found, named, readouts_sha = phase28a(root, args.phase28a_run, args.phase28a_readouts)
    problems += found
    checks['phase28a'] = {'run_dir': args.phase28a_run, 'readouts_path': named, 'readouts_sha256': readouts_sha}
    return report(args, root, source, checks, problems)


def report(args, root, source, checks, problems):
    print(json.dumps({'mode': 'before' if args.before else 'after', 'main': str(root), 'from': str(source),
                      'reviewed': REVIEWED_ROUND, 'checks': checks, 'problems': problems, 'ok': not problems},
                     indent=1, sort_keys=True))
    return 0 if not problems else 1


if __name__ == '__main__':
    sys.exit(main())
