"""Phase 25: a non-scoring replay probe of the Mechanic's slot-2 duplicates.

A completion study asks the Mechanic twice (completion_study.PROPOSAL_SLOTS = 2). Slot 2 repeats
slot 1's policy in most studies, so the study gets one real draw, not two (pitfall 70). This probe
re-sends the stored v4-era slot-2 Mechanic requests and asks two things:

1. Why does slot 2 reproduce slot 1? From the code and the store ($0, recorded in the plan's
   `investigation`): the slot-2 request is NOT slot 1's request again. completion_study._execute
   builds it with `candidate_history: deepcopy(record['candidates'])`, which carries slot 1's policy
   twice (`content`, canonical, and `raw_outputs`, the verbatim text the model wrote), and it adds
   slot 1's six source episodes to `development_evidence` and `observed_outcomes`. Slot 2's output
   then repeats slot 1's rules text byte for byte in most studies while its explanation is new. That
   coincides with the prior candidate being in the input, but it does not show copying: when slot 1
   lands on the same policy in two different studies (no prior candidate at all), its rules text is
   byte-identical in 5 of 6 such pairs (plan['investigation']['slot1_layout_identity']). The layout is
   the model's own style. Copying is a hypothesis; arms H and N test it.
2. Does ONE declared change to the slot-2 input produce distinct proposals whose retry step fires
   and that carry no declared harmful side rule, without breaking validity?

How a request is rebuilt and verified. A Mechanic request is exactly
  [{system: prompts/completion.md}, {user: canonical_json({**context, 'output_schema': schema})}]
(Mechanic._generate), where `context` is the stored `completion_proposal_inputs` record. No Mechanic
request hash is stored anywhere (mechanic_outputs keeps raw, model, attempt, request_id and usage;
only the Actor's events carry request hashes), so a prompt is used only if every check in
verify_slot() holds: the immutable input record; its candidate_history equal to the study record's
earlier candidates; its observed_outcomes recomputed by the runtime's own trial_outcomes from the
study's stored trial rows; its development_evidence recomputed by the runtime's own
summarize_evidence from the stored evidence bundles; its runtime_contract equal to the code's; its
fixed fields; the historical attempt-0 output record; the study configuration's source and contract
hashes, dependency lock and per-role model settings equal to the pinned configuration's; the stored
payload bytes equal to canonical_json of the context; and the provider's own prompt-token count for
that request equal to the vendored DeepSeek-V4 tokenizer's count of the rebuilt bytes plus the
declared two-message framing (FRAMING_TOKENS). A prompt that fails is counted, reported and never
sent.

Arms (slot-2 prompts):
  C  the exact verified request, re-sent (temperature 0, the frozen Mechanic settings). 3 draws.
  T  the same bytes at temperature T_TEMPERATURE (the program's declared 0.7). The only change is the
     temperature keyword, applied by this script's client wrapper after RuntimeProvider built the
     frozen request. 3 draws.
  H  temperature 0; the prior candidate appears once: its verbatim `raw_outputs` text is withheld
     from candidate_history. Its canonical `content`, explanation, decision and source assessment
     stay. Built here; nothing in backend/app changes. 3 draws.
  N  reference, temperature 0: the same slot-2 context with an empty candidate_history (no prior
     candidate in view; the slot-2 evidence, including slot 1's source episodes, stays). How often
     the evidence alone leads back to slot 1's policy. 1 draw, descriptive only.

Every response is classified by a static auditor: parses under the Mechanic's schema and the
policy repository's rules (valid); byte-identical to slot 1; the same policy as slot 1 (the study's
DUPLICATE rule); distinct; contains the step (notifications retry_original_request at
after_notification_response, the Phase 9 predicate); the step can fire after a transient failure
(an abstract run of the policy interpreter on the source case, pitfall 77); side rules (premature
defer, pitfall 78; a rule that stops the first confirmation). A draw is WORKING only if it is
distinct, its step fires and it has no harmful side rule. The yield condition sums, over the prompts
whose slot-1 policy's step does not already fire, X's WORKING share of its draws minus C's, so each
prompt adds between -1 and +1 and within-prompt spread cannot move it (review round 2).

A run that stops before its end, by a stop the operator does not choose (the spend guard, five errored
requests in a row, a crash), still has a declared read-out if round 1 (r0001-r0104) is complete: each
arm's decision then falls back to round 1 alone, labelled. After an operator stop (any SIGINT or
SIGTERM, whoever sent it: the handler cannot tell the operator from the OS or a tool that launched the
run; or a process that died with no final manifest) an incomplete decision stays INCOMPLETE. Saved
response lines carry no classification while the run is live, and --readouts refuses until the run's
manifest is final. After the main pass, each request that errored with nothing delivered is re-sent once
(blind, charged; pitfall 49).

Nothing here creates a campaign, study, trial, world, policy or store row. The store is opened
read-only; results are never shown to any model and never enter a study.

Dry by default. `--execute-live`, a matching `--confirm-entity`, the reviewed plan hash and the
harness and protocol hashes are all required before any provider call. The protocol's status block
must no longer say it is not yet reviewed, it must carry the bare line "Reviewed for launch:
harness <sha256> plan <hash>", and the review record must repeat the pins. A live run refuses
beside any other paid run, takes an atomic claim, and the $15 cap is a phase cap.

Usage:
  python scripts/experiments/slot2_probe.py
  python scripts/experiments/slot2_probe.py --write-plan artifacts/phase25-<date>/dry-plan
  python scripts/experiments/slot2_probe.py --readouts artifacts/phase25-<date>/live
  python scripts/experiments/slot2_probe.py --finalize-abandoned artifacts/phase25-live-claims/claim-NN.json
  python scripts/experiments/slot2_probe.py --execute-live --confirm-entity ENTITY \\
      --out artifacts/phase25-<date>/live --expect-plan-hash H \\
      --expect-harness-sha256 S --expect-protocol-sha256 P
"""
from __future__ import annotations

import argparse
import asyncio
from collections import Counter, defaultdict
from copy import deepcopy
from datetime import datetime, timezone
from fractions import Fraction
import hashlib
import json
import math
import os
import pathlib
import random
import re
import shlex
import signal
import sqlite3
import subprocess
import sys
import traceback
from types import SimpleNamespace
import urllib.error
import urllib.request

# Even dry inspection should not create Python cache files in the workspace.
sys.dont_write_bytecode = True
ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'backend'))

from pydantic import TypeAdapter, ValidationError  # noqa: E402

from app.agents.actor import RETRYABLE_TRANSPORT_CODES  # noqa: E402
from app.agents.mechanic import PROMPTS  # noqa: E402
from app.agents.progress import ACTOR_CONTEXT_PROTOCOL_V4  # noqa: E402
from app.contracts.models import (CandidatePolicy, EvidenceBundle, MechanicCandidate,  # noqa: E402
                                  MechanicNoChange, MechanicOutput, TrialResult, canonical_json, content_hash)
from app.lab.completion_study import SCHEMA as COMPLETION_SCHEMA  # noqa: E402
from app.lab.diagnosis import (COMPACT_EVIDENCE_V2, runtime_contract, summarize_evidence,  # noqa: E402
                               trial_outcomes)
from app.providers.runtime import MODEL_REQUEST_SETTINGS, RuntimeProviderError, response_format_for  # noqa: E402
from app.providers.wandb_inference import model_request_options  # noqa: E402

SCHEMA = 'faultlab-slot2-probe/v1'
READOUT_SCHEMA = 'faultlab-slot2-probe-readouts/v1'
MANIFEST_NAME = 'slot2-probe-manifest.json'
FINAL_STATUSES = ('COMPLETED', 'STOPPED', 'ABORTED')
# A live run writes its manifest at exactly artifacts/phase25-<date>/<name>/ (check_output), and only
# that depth is read: a copy saved deeper as evidence is never a live-gate input.
LIVE_MANIFEST_GLOB = f'phase25-*/*/{MANIFEST_NAME}'
CLAIM_DIR = 'phase25-live-claims'
CLAIM_NAME = re.compile(r'claim-(\d+)\.json')
# A run whose process died while RUNNING may have one request and its blind retry admitted and
# charged but not yet recorded; --finalize-abandoned charges them.
ABANDONED_IN_FLIGHT_ATTEMPTS = 2
STORE = ROOT / 'artifacts/lab.sqlite3'
# The last completion study of Phase 23 was created at 05:42:09Z and the run ended at 05:48:55Z;
# Phase 24 (05:51-06:01Z) created none. Defence in depth against any later study in this store.
STORE_CUTOFF = '2026-09-24T05:50:00Z'

# The two v4-era full-loop configurations. Their studies are the census this probe replays.
DECLARED_CONFIGURATIONS = {
    'c4169ee49deb7fb27ac44205d6e74b4f89912d1b43bf945636745b1872110418': 'phase17',
    '2cf63e93480e71afe5de9f459ac21aaebb418f242cfdb1ff18e803f11ce9a5ba': 'phase23',
}
# The runs' own manifests name their studies; the population must equal their studies with two
# proposals. Pinned: both runs are closed and their manifests final.
PHASE_MANIFESTS = {
    'phase17': ('artifacts/phase17-2026-09-23/full-loop-manifest.json',
                'f90605404d00a3c43107ef0165b15bb0acad87207e873c8ad2d7421480f63830'),
    'phase23': ('artifacts/phase23-2026-09-24/full-loop-manifest.json',
                'aac41711ea8df103ed1c5bdb6df7a75275d019f60c716a9a0aaf102b7b31b6f5'),
}
EXPECTED_MECHANIC_MODEL = 'deepseek-ai/DeepSeek-V4-Pro-0813'
EXPECTED_PROJECT = 'shreetbohara-quinstreet/Faultlab'
DECLARED_SETTINGS = 'artifacts/phase16-2026-09-22/settings-phase17.json'
DECLARED_SETTINGS_SHA256 = '1e2002d383cbccb3c0479f411f9d9ab7fd13af97f3d923a27281a454060c941d'
# The Phase 17 settings on the Phase 22 code (PHASE22_RESULTS.md). Recomputed from the settings file
# alone; backend/app must not change for it to hold.
DECLARED_CONFIGURATION_HASH = '2cf63e93480e71afe5de9f459ac21aaebb418f242cfdb1ff18e803f11ce9a5ba'
# The Phase 22 code freeze. Only its recorded fingerprints and the file hashes this probe depends on
# are compared; gate_freeze.py itself is not run (it hashes files this phase must not read).
DECLARED_FREEZE = 'artifacts/phase22-2026-09-24/gate-freeze-after.json'
DECLARED_FREEZE_SHA256 = '8994e96273be43a8abc0f10fd41a131d9c0700b9a9916b70ddbef2afd74a3bf1'
FREEZE_FILES = ('backend/app/agents/prompts/completion.md', 'backend/app/agents/mechanic.py',
                'backend/app/lab/diagnosis.py', 'backend/app/lab/completion_study.py', 'backend/app/lab/policies.py')
FREEZE_FINGERPRINTS = ('source_hash', 'runtime_hash', 'contract_hash', 'algorithm_hash', 'interpreter_hash')
# The reviewed protocol declares this harness's sha256 and the plan hash; the operator types the
# protocol's own sha256 and the review record repeats it. The script never pins the protocol.
PROTOCOL = ROOT / 'docs/part2/PHASE25_EXPERIMENT.md'
REVIEW_RECORD = 'artifacts/phase25-2026-09-24/review.json'
REVIEW_PENDING_MARKER = 'NOT yet reviewed'
REVIEWED_LINE = 'Reviewed for launch: harness {harness} plan {plan}'

MECHANIC_MAX_OUTPUT_TOKENS = 2000    # Mechanic._generate
MECHANIC_TIMEOUT_SECONDS = 20.0      # Mechanic._generate
PER_REQUEST_DOLLAR_BOUND = 0.04984   # 32,000 in x $1.31/M + 2,000 out x $3.96/M (frozen mechanic pricing)
HARD_SPEND_CAP = 15.0
CONSECUTIVE_ERROR_ABORT = 5
# After a request that ends in error, wait before the next one; the fifth errored request in a row
# stops the run. Waiting is not resampling: an errored request delivered nothing (pitfall 49).
BACKOFF_SECONDS = (30, 120, 300, 300)
BLIND_RETRY_WAIT_SECONDS = 10
# The provider's prompt tokens for a two-message V4-Pro request exceed the vendored tokenizer's
# content count (roles and contents) by exactly this many chat-template tokens on every one of the 52
# stored v4-era completion requests (both slots); plan['investigation'] recomputes it.
FRAMING_TOKENS = 24
BASELINE_VERSION = 'policy-v0'
PURPOSE = 'completion_study'

SLOT2_ARMS = ('C', 'T', 'H')          # 3 draws per prompt each; the decisions use these
REFERENCE_ARMS = ('N',)               # 1 draw per prompt; descriptive only
ALL_ARMS = SLOT2_ARMS + REFERENCE_ARMS
T_TEMPERATURE = 0.7   # EXPERIMENT_PROGRAM_PHASES_20-27.md, Phase 26c: "T=0 vs T=0.7"
ARM_TEMPERATURE = {'C': 0, 'T': T_TEMPERATURE, 'H': 0, 'N': 0}
H_WITHHELD_KEYS = ('raw_outputs',)
H_RULE = ('candidate_history entries keep content, explanation, decision, policy_hash, policy_version, '
          'proposal_ref and source_assessment; raw_outputs (the verbatim text the Mechanic wrote) is removed')
N_RULE = ('the verified slot-2 context with candidate_history = [] (no prior candidate in view); '
          'development_evidence and observed_outcomes, which carry slot 1\'s source episodes, stay')
SLOT2_REPEATS = 3
N_REPEATS = 1
ARM_REPEATS = {'C': SLOT2_REPEATS, 'T': SLOT2_REPEATS, 'H': SLOT2_REPEATS, 'N': N_REPEATS}
SAMPLE_SEED = 'faultlab-phase25-2026-09-24'
RECEIVED = ('ok', 'empty_response')
REQUEST_KEYS = ('model', 'messages', 'max_tokens', 'response_format', 'temperature', 'stream', 'extra_body')
# After the main pass, a request whose every attempt failed with one of these codes and that delivered no
# generation is re-sent once (blind, charged; pitfall 49). Local refusals are never re-sent.
RESEND_CODES = ('CONNECTION_ERROR', 'REQUEST_TIMEOUT', 'HTTP_ERROR', 'PROVIDER_ERROR')

# Declared read-out thresholds (see PHASE25_EXPERIMENT.md).
COMPLETE_MIN = Fraction(95, 100)
DISTINCT_MIN = Fraction(7, 10)
DISTINCT_GAIN_MIN = Fraction(3, 10)
SIGN_ALPHA = 0.05
# Condition 5 (review round 2): a per-draw yield contrast that within-prompt spread cannot move. Over the
# prompts whose slot-1 policy's step does not already fire, each prompt adds X's WORKING share of its planned
# draws (a missing X draw is not WORKING) minus C's WORKING-or-missing share of its planned draws, so each
# prompt adds between -1 and +1 and the expectation is 0 at equal per-draw WORKING rates, however the draws
# cluster within a prompt. (Round 1 counted prompts with at least one WORKING draw; that count rewards the
# arm whose draws vary more within a prompt at equal per-draw rates, which is breadth, not yield. It is kept
# as a descriptive figure.) With 3 planned draws per prompt in every arm, a gain of g is 3g more WORKING
# draws in X than WORKING-or-missing draws in C. The minimum is chosen by slot2_protocol_numbers.py so that
# P(RECOMMEND) <= 0.05 when X is more distinct but no more working than C (the yield null). Review round 3: a
# temperature-0 arm may repeat its own output for the same input, and then each prompt's share is 0 or 1 and
# the gain is a whole number, so 8/3 acted as a count of 3 prompts (above 0.05 under that null). The grid now
# runs that repeat model too, and chooses 10/3.
WORKING_SHARE_GAIN_MIN = Fraction(10, 3)
WORKING_SHARE_GAIN_MIN_ROUND1 = Fraction(4)   # the round-1 fallback (1 draw per prompt per arm)
INVALID_MARGIN = Fraction(1, 10)
# Of X's distinct draws whose step fires, at most half may carry a declared harmful side rule. Not diluted by
# distinct draws that do not fire (which cannot qualify at the source). The store's rate is 3 of 9 distinct
# v4-era firing policies; a contrast of harmful draws per planned draw was tried in round 1 and dropped
# because it refused the arms that fire most (see the Review log).
HARMFUL_FIRING_SHARE_MAX = Fraction(1, 2)
MECHANISM_GAIN_MIN = Fraction(3, 10)
MECHANISM_DISTINCT_GAIN_MIN = Fraction(3, 10)
MECHANISM_NONCANDIDATE_MARGIN = Fraction(1, 10)

# The policy interpreter's per-episode bounds (EpisodeBudget, runtime_contract).
POLICY_STEP_CAP = 32
WAIT_CYCLE_CAP = 4


class PlanningError(ValueError):
    pass


def sha256_file(path):
    return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()


def sha256_text(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest() if isinstance(text, str) else None


def rank(*parts):
    return hashlib.sha256(':'.join((SAMPLE_SEED,) + tuple(str(p) for p in parts)).encode()).hexdigest()


def before_cutoff(created_at, cutoff=STORE_CUTOFF):
    if not created_at:
        return False
    parse = lambda value: datetime.fromisoformat(value.replace('Z', '+00:00'))  # noqa: E731
    return parse(created_at) < parse(cutoff)


# ---------------------------------------------------------------- read-only store access

def connect(store):
    path = pathlib.Path(store).resolve()
    if not path.exists():
        raise PlanningError(f'No store at {path}')
    return sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)


def load_record_text(connection, kind, record_id):
    """The stored payload text, exactly as put_record wrote it, and the immutable flag."""
    row = connection.execute('select payload, immutable from records where kind=? and id=?',
                             (kind, record_id)).fetchone()
    return (row[0], bool(row[1])) if row else (None, False)


def load_record(connection, kind, record_id):
    text, immutable = load_record_text(connection, kind, record_id)
    return (json.loads(text), immutable) if text is not None else (None, False)


def output_attempts(connection, proposal_ref):
    """Every mechanic_outputs record of the request that produced this proposal, in attempt order."""
    record, _ = load_record(connection, 'mechanic_outputs', proposal_ref)
    if not record:
        return []
    rows = connection.execute("select payload from records where kind='mechanic_outputs' and "
                              "json_extract(payload,'$.request_id')=?", (record.get('request_id'),)).fetchall()
    return sorted((json.loads(p) for (p,) in rows), key=lambda r: r.get('attempt', 0))


def in_scope(study, cutoff=STORE_CUTOFF):
    """A study of a declared configuration created before the cutoff. Only these can enter the plan, so
    only these are counted in it: a later study, or one of another configuration, cannot move the plan
    hash."""
    return study.get('configuration_hash') in DECLARED_CONFIGURATIONS and before_cutoff(study.get('created_at'), cutoff)


def load_population(connection, cutoff=STORE_CUTOFF):
    """The census: every v4-era full-loop completion study (Phases 17 and 23) that asked for slot 2.
    Returns (studies, exclusions among in-scope studies)."""
    studies, excluded = [], Counter()
    for (payload,) in connection.execute("select payload from records where kind='completion_studies'"):
        study = json.loads(payload)
        if not in_scope(study, cutoff):
            continue
        if study.get('replay_of') is not None:
            excluded['replay'] += 1
        elif (study.get('actor_context_protocol') != ACTOR_CONTEXT_PROTOCOL_V4
              or study.get('evidence_protocol') != COMPACT_EVIDENCE_V2):
            excluded['not_v4_era'] += 1
        elif len(study.get('candidates') or []) < 2:
            excluded['no_slot2_proposal'] += 1
        else:
            studies.append(study)
    studies.sort(key=lambda s: (s['created_at'], s['study_id']))
    return studies, dict(sorted(excluded.items()))


def store_outside_scope(connection, cutoff=STORE_CUTOFF):
    """Store-wide counts of completion studies outside the plan's scope (reported in the dry summary only,
    never in the hashed plan)."""
    counts = Counter()
    for (payload,) in connection.execute("select payload from records where kind='completion_studies'"):
        study = json.loads(payload)
        if study.get('configuration_hash') not in DECLARED_CONFIGURATIONS:
            counts['other_configuration'] += 1
        elif not before_cutoff(study.get('created_at'), cutoff):
            counts['declared_configuration_at_or_after_cutoff'] += 1
    return dict(sorted(counts.items()))


def manifest_studies(root=None):
    """Study ids with two proposals in the pinned Phase 17 and 23 run manifests."""
    root = pathlib.Path(root or ROOT)
    found = {}
    for phase, (path, digest) in PHASE_MANIFESTS.items():
        if sha256_file(root / path) != digest:
            raise PlanningError(f'The {phase} run manifest is not the pinned one ({path})')
        for attempt in json.loads((root / path).read_text())['attempts']:
            if len(attempt.get('candidates') or []) == 2:
                found[attempt['study_id']] = phase
    return found


# ---------------------------------------------------------------- the request, rebuilt

def output_schema():
    return TypeAdapter(MechanicOutput).json_schema()


def system_prompt():
    return (PROMPTS / 'completion.md').read_text()


def mechanic_messages(context):
    """Mechanic._generate's request, exactly: the completion prompt and the canonical context."""
    return [{'role': 'system', 'content': system_prompt()},
            {'role': 'user', 'content': canonical_json({**context, 'output_schema': output_schema()})}]


def request_body(messages, temperature, model=EXPECTED_MECHANIC_MODEL):
    """The keyword arguments RuntimeProvider.complete passes to chat.completions.create, minus the
    transport timeout, with the arm's temperature."""
    return {'model': model, 'messages': messages, 'max_tokens': MECHANIC_MAX_OUTPUT_TOKENS,
            'response_format': response_format_for(role='mechanic'), 'temperature': temperature,
            'stream': False, **model_request_options(model)}


def request_digest(kwargs):
    return content_hash({key: kwargs[key] for key in REQUEST_KEYS if key in kwargs})


def local_prompt_tokens(messages):
    from app.contracts.tokens import deepseek_v4_encoding
    tokenizer = deepseek_v4_encoding()
    count = lambda text: len(tokenizer.encode(text, add_special_tokens=False).ids)  # noqa: E731
    return sum(count(m['role']) + count(m['content']) for m in messages)


def withhold_raw_text(context):
    """Arm H: the prior candidate appears once, without the verbatim text the Mechanic wrote."""
    changed = deepcopy(context)
    for entry in changed.get('candidate_history') or []:
        for key in H_WITHHELD_KEYS:
            entry.pop(key, None)
    return changed


def without_prior_candidate(context):
    """Reference arm N: the slot-2 context with no prior candidate in view (candidate_history = [])."""
    changed = deepcopy(context)
    changed['candidate_history'] = []
    return changed


def arm_context(context, arm):
    if arm == 'H':
        return withhold_raw_text(context)
    if arm == 'N':
        return without_prior_candidate(context)
    return context


def used_trial_rows(study, slot):
    """The rows completion_study._execute summarised for this slot: the controls, then the source
    rows of every earlier candidate that ran (feedback_rows)."""
    earlier = {f'candidate-{index}' for index in range(1, slot)}
    rows = study.get('trial_rows') or []
    return [r for r in rows if r['stage'] == 'controls'] + [r for r in rows if r['stage'] in earlier]


def parse_policy(raw):
    try:
        return TypeAdapter(MechanicOutput).validate_json(raw)
    except (ValidationError, ValueError, TypeError):
        return None


def verify_slot(connection, study, slot, pins, *, framing=FRAMING_TOKENS):
    """Rebuild one stored slot request and run every declared check. Returns (context, checks,
    facts); the prompt is verified only if every check is True."""
    checks, facts = {}, {}
    key = f"{study['study_id']}-{slot}"
    stored, immutable = load_record_text(connection, 'completion_proposal_inputs', key)
    context = json.loads(stored) if stored is not None else None
    checks['input_record_immutable'] = context is not None and immutable
    if context is None:
        return None, checks, facts
    # put_record stores canonical_json(payload): the context the rebuild serialises is byte for byte the
    # stored one, not merely an equal value.
    checks['stored_payload_canonical'] = canonical_json(context) == stored
    manifest_cases = {case['case_id']: case for case in study['manifest']['cases']}
    expected_keys = {'campaign_id', 'study_id', 'objective', 'parent_version', 'source_fault_spec',
                     'control_fault_spec', 'runtime_contract', 'development_evidence', 'observed_outcomes',
                     'candidate_history'}
    checks['context_keys'] = set(context) == expected_keys
    checks['fixed_fields'] = (context.get('campaign_id') == study['campaign_id']
                              and context.get('study_id') == study['study_id']
                              and context.get('objective') == COMPLETION_SCHEMA
                              and context.get('parent_version') == BASELINE_VERSION
                              and context.get('source_fault_spec') == manifest_cases['notification-2']['fault_spec']
                              and context.get('control_fault_spec') == manifest_cases['healthy']['fault_spec'])
    checks['candidate_history'] = (canonical_json(context.get('candidate_history'))
                                   == canonical_json(study['candidates'][:slot - 1]))
    rows = used_trial_rows(study, slot)
    try:
        trials = [TrialResult.model_validate_json(canonical_json(r['trial'])) for r in rows]
    except ValidationError:
        trials = None
    checks['observed_outcomes'] = trials is not None and (
        canonical_json(context.get('observed_outcomes')) == canonical_json(trial_outcomes(trials)))
    bundles = []
    for trial in trials or []:
        bundle, _ = load_record(connection, 'evidence', trial.episode_id)
        try:
            bundles.append(EvidenceBundle.model_validate_json(canonical_json(bundle)) if bundle else None)
        except ValidationError:
            bundles.append(None)
    if trials and all(bundles):
        evidence = summarize_evidence(bundles, outcomes={t.episode_id: t.outcome for t in trials})
        checks['development_evidence'] = canonical_json(context.get('development_evidence')) == canonical_json(evidence)
    else:
        checks['development_evidence'] = False
    checks['runtime_contract'] = canonical_json(context.get('runtime_contract')) == canonical_json(runtime_contract())
    configuration, _ = load_record(connection, 'configurations', study['configuration_hash'])
    checks['configuration_source_and_contract'] = bool(configuration) and (
        configuration.get('source_hash') == pins['source_hash']
        and configuration.get('contract_hash') == pins['contract_hash']
        and configuration.get('dependency_lock_hash') == pins['dependency_lock_hash']
        and canonical_json(configuration.get('model_settings_by_role')) == canonical_json(pins['model_settings_by_role'])
        and configuration.get('models', {}).get('mechanic') == EXPECTED_MECHANIC_MODEL)
    candidate = study['candidates'][slot - 1]
    attempts = output_attempts(connection, candidate.get('proposal_ref'))
    first = attempts[0] if attempts else {}
    checks['historical_output'] = (bool(attempts) and first.get('attempt') == 0
                                   and first.get('prompt') == 'completion.md'
                                   and first.get('model_id') == EXPECTED_MECHANIC_MODEL
                                   and first.get('campaign_id') == study['campaign_id']
                                   and [a.get('raw') for a in attempts] == candidate.get('raw_outputs'))
    messages = mechanic_messages(context)
    reported = (first.get('usage') or {}).get('input_tokens')
    local = local_prompt_tokens(messages)
    facts.update(reported_prompt_tokens=reported, local_content_tokens=local,
                 framing=None if reported is None else reported - local, attempts=len(attempts),
                 user_bytes=len(messages[1]['content'].encode('utf-8')))
    checks['provider_token_fingerprint'] = reported is not None and reported == local + framing
    facts['historical_raw'] = first.get('raw')
    facts['historical_final_raw'] = attempts[-1].get('raw') if attempts else None
    if slot == 2:
        prior = study['candidates'][0]
        parsed = parse_policy((prior.get('raw_outputs') or [None])[-1] or '')
        checks['slot1_reference'] = (isinstance(parsed, MechanicCandidate)
                                     and content_hash(parsed.candidate) == prior.get('policy_hash'))
    return context, checks, facts


# ---------------------------------------------------------------- the static auditor

def condition(name, state, flag):
    """app.lab.policy_state.PolicyState.condition on an abstract state (a test pins it to the source)."""
    if name == 'always':
        return True
    if name == 'receipt_missing':
        return flag
    service = state['notifications'] if name.startswith('notification') else state['orders']
    receipt = service['receipt']
    status = receipt if receipt else service['status']
    if name.endswith('receipt_missing'):
        return receipt != 'SUCCEEDED'
    if name in ('current_operation_pending', 'notification_operation_pending'):
        return receipt is None and status == 'PENDING'
    if name.endswith('outcome_uncertain'):
        return service['attempted'] and receipt is None and status in ('PENDING', 'UNKNOWN', None)
    if name.endswith('terminal_failure'):
        return receipt == 'FAILED'
    if name.endswith('succeeded'):
        return receipt == 'SUCCEEDED'
    raise ValueError(f'Unknown policy condition {name}')


def run_hook(rules, hook, state, reads, budget):
    """app.lab.policy_interpreter.PolicyInterpreter.invoke on an abstract state. `reads` is the status a
    status read delivers per service. Returns (state, events, closed, blocked, exhausted)."""
    state = deepcopy(state)
    flag, requirements, events, closed = False, set(), [], False
    for rule in rules:
        if rule['hook'] != hook or not condition(rule['when'], state, flag):
            continue
        for step in rule['steps']:
            budget['steps'] += 1
            if budget['steps'] > POLICY_STEP_CAP:
                return state, events + [('exhausted', 'policy_steps')], closed, False, True
            if not condition(step.get('only_if', 'always'), state, flag):
                events.append(('skipped', step['op']))
                continue
            op = step['op']
            if op in ('read_current_operation', 'read_notification_operation'):
                service = 'orders' if op == 'read_current_operation' else 'notifications'
                if state[service]['receipt'] is None:
                    state[service]['status'] = reads[service]
                events.append(('read', service))
            elif op == 'read_order':
                events.append(('read_order', None))
            elif op == 'wait_ticks':
                budget['waits'] += 1
                if budget['waits'] > WAIT_CYCLE_CAP:
                    return state, events + [('exhausted', 'wait_cycles')], closed, False, True
                events.append(('wait', step.get('ticks')))
            elif op == 'retry_original_request':
                service = state[step['service']]
                unmet = service['receipt'] == 'FAILED' or not service['attempted']
                events.append(('retry_unmet' if unmet else 'retry', step['service']))
            elif op == 'require_receipt':
                requirements.add(step['service'])
                flag = state[step['service']]['receipt'] != 'SUCCEEDED'
                events.append(('require', step['service']))
            elif op == 'report_terminal_failure':
                met = state[step['service']]['receipt'] == 'FAILED'
                events.append(('close' if met else 'unmet', op))
                closed = met
            elif op == 'defer_unresolved':
                events.append(('close', op))
                closed = True
            if closed:
                break
        if closed:
            break
    blocked = hook == 'before_confirmation' and any(state[s]['receipt'] != 'SUCCEEDED' for s in requirements)
    return state, events, closed, blocked, False


def _service(attempted=False, receipt=None, status=None):
    return {'attempted': attempted, 'receipt': receipt, 'status': status}


def contains_step(rules):
    """The Phase 9 predicate (run_full_loop.contains_step): op AND service AND hook."""
    return any(rule.get('hook') == 'after_notification_response' and any(
        step.get('op') == 'retry_original_request' and step.get('service') == 'notifications'
        for step in rule.get('steps') or []) for rule in rules)


def audit_policy(content):
    """Static read of one candidate policy (a dict with rules). Declared scenarios:

    source path (notification-2): the Actor's upgrade delivered a matching SUCCEEDED receipt
      (after_upgrade_response), it proposes its first send (before_confirmation), and the send
      failed transiently (after_notification_response): notifications attempted, no receipt, status
      UNKNOWN; a notifications status read delivers UNKNOWN (never PENDING: the write was never
      accepted, pitfall 77). The step FIRES if a notifications retry executes there and nothing
      earlier closed business, blocked the send or exhausted a bound.
    delayed decision: after_upgrade_response while the upgrade is attempted, unreceipted and PENDING,
      and a status read still delivers PENDING. premature_defer: defer_unresolved executes with no
      wait_ticks executed before it in that hook (Phase 17 attempt 4, pitfall 78).
    """
    rules = content.get('rules') or []
    budget = {'steps': 0, 'waits': 0}
    reads = {'orders': 'SUCCEEDED', 'notifications': 'UNKNOWN'}
    state = {'orders': _service(True, 'SUCCEEDED', 'SUCCEEDED'), 'notifications': _service()}
    state, _, closed_a, _, exhausted_a = run_hook(rules, 'after_upgrade_response', state, reads, budget)
    state, _, closed_b, blocked_b, exhausted_b = run_hook(rules, 'before_confirmation', state, reads, budget)
    stops_first_send = bool(closed_a or closed_b or blocked_b or exhausted_a or exhausted_b)
    state['notifications'] = _service(True, None, 'UNKNOWN')
    _, events_c, _, _, _ = run_hook(rules, 'after_notification_response', state, reads, budget)
    retry = ('retry', 'notifications') in events_c
    delayed = {'orders': _service(True, None, 'PENDING'), 'notifications': _service()}
    _, events_d, _, _, _ = run_hook(rules, 'after_upgrade_response', delayed,
                                    {'orders': 'PENDING', 'notifications': 'UNKNOWN'}, {'steps': 0, 'waits': 0})
    premature, waited = False, False
    for kind, detail in events_d:
        waited = waited or kind == 'wait'
        premature = premature or (kind == 'close' and detail == 'defer_unresolved' and not waited)
    present = contains_step(rules)
    return {'rules': len(rules), 'steps': sum(len(r.get('steps') or []) for r in rules),
            'hooks': sorted({r['hook'] for r in rules}),
            'step_present': present, 'step_fires': bool(present and retry and not stops_first_send),
            'dead_step': bool(present and not (retry and not stops_first_send)),
            'stops_first_confirmation': stops_first_send, 'premature_defer': premature,
            'harmful': bool(premature or stops_first_send),
            'orders_retry': any(s.get('op') == 'retry_original_request' and s.get('service') == 'orders'
                                for r in rules for s in r.get('steps') or [])}


def rules_text(raw):
    """Forensic, descriptive only: the raw text from the first "rules" key to the last "explanation"
    key. A byte-identical span shows the text was reproduced with the same layout."""
    if not isinstance(raw, str):
        return None
    start, end = raw.find('"rules"'), raw.rfind('"explanation"')
    return raw[start:end] if 0 <= start < end else None


def explanation_of(raw):
    try:
        value = json.loads(raw)
    except (ValueError, TypeError):
        return None
    return value.get('explanation') if isinstance(value, dict) and isinstance(value.get('explanation'), str) else None


def classify_response(raw, reference):
    """One returned Mechanic output, judged as completion_study would (validate_json, NO_CHANGE,
    policies.proposal's parent and CandidatePolicy checks, the DUPLICATE hash rule), plus the audit."""
    result = {'class': None, 'policy_hash': None, 'byte_identical_to_slot1': False,
              'rules_text_identical_to_slot1': False, 'duplicate_of_slot1': False, 'distinct': False,
              'distinct_firing': False, 'working': False, 'audit': None}
    if not isinstance(raw, str) or not raw.strip():
        result['class'] = 'INVALID'
        return result
    result['byte_identical_to_slot1'] = sha256_text(raw) == reference.get('slot1_raw_sha256')
    text = rules_text(raw)
    result['rules_text_identical_to_slot1'] = text is not None and sha256_text(text) == reference.get('slot1_rules_text_sha256')
    parsed = parse_policy(raw)
    if parsed is None:
        result['class'] = 'INVALID'
        return result
    if isinstance(parsed, MechanicNoChange):
        result['class'] = 'NO_CHANGE'
        return result
    if parsed.candidate.parent_version != BASELINE_VERSION:
        result['class'] = 'STALE_PARENT'
        return result
    try:
        CandidatePolicy.model_validate_json(parsed.candidate.model_dump_json())
    except ValidationError:
        result['class'] = 'INVALID'
        return result
    content = parsed.candidate.model_dump(mode='json')
    result.update({'class': 'CANDIDATE', 'policy_hash': content_hash(parsed.candidate), 'audit': audit_policy(content)})
    result['duplicate_of_slot1'] = result['policy_hash'] == reference.get('slot1_policy_hash')
    result['distinct'] = not result['duplicate_of_slot1']
    # WORKING: a distinct policy whose retry step fires after a transient failure and that carries no
    # declared harmful side rule (a premature defer loses terminal rejection in validation, pitfall 78).
    result['distinct_firing'] = result['distinct'] and result['audit']['step_fires']
    result['working'] = result['distinct_firing'] and not result['audit']['harmful']
    explanation = parsed.explanation
    result['explanation_claims_different'] = 'materially different' in explanation.lower()
    result['explanation_mentions_retry'] = 'retry' in explanation.lower()
    return result


# ---------------------------------------------------------------- $0 investigation (recorded in the plan)

def historical_mechanism(rows):
    """What the stored slot-2 attempts did, against slot 1 (development data, $0)."""
    per_study, totals = [], Counter()
    slot1_hashes = Counter()
    for row in rows:
        c1, c2 = row['contexts'][1], row['contexts'][2]
        reference = row['reference']
        first = classify_response(row['facts'][2]['historical_raw'], reference)
        differing = sorted(k for k in set(c1) | set(c2) if canonical_json(c1.get(k)) != canonical_json(c2.get(k)))
        prior = (c2.get('candidate_history') or [{}])[0]
        raw_in_input = bool(prior.get('raw_outputs')) and all(
            json.dumps(raw, ensure_ascii=False)[1:-1] in row['user_messages'][2] for raw in prior['raw_outputs'])
        audit = first.get('audit') or {}
        entry = {'study_id': row['study']['study_id'], 'phase': row['phase'],
                 'slot2_input_differs_in': differing,
                 'user_bytes': [row['facts'][1]['user_bytes'], row['facts'][2]['user_bytes']],
                 'slot1_raw_text_in_slot2_input': raw_in_input,
                 'slot2_attempt0_class': first['class'],
                 'slot2_attempts': row['facts'][2]['attempts'],
                 'byte_identical_to_slot1': first['byte_identical_to_slot1'],
                 'rules_text_identical_to_slot1': first['rules_text_identical_to_slot1'],
                 'policy_duplicate_of_slot1': first['duplicate_of_slot1'],
                 'explanation_claims_different': bool(first.get('explanation_claims_different')),
                 'explanation_mentions_retry_without_the_step': bool(
                     first.get('explanation_mentions_retry') and not audit.get('step_present')),
                 'distinct_firing': first['distinct_firing'],
                 'distinct_working': first['working'],
                 'slot1_step_fires': reference['slot1_step_fires'],
                 'slot1_harmful': reference['slot1_harmful']}
        per_study.append(entry)
        slot1_hashes[reference['slot1_policy_hash']] += 1
        for key in ('slot1_raw_text_in_slot2_input', 'byte_identical_to_slot1', 'rules_text_identical_to_slot1',
                    'policy_duplicate_of_slot1', 'distinct_firing', 'distinct_working', 'slot1_step_fires',
                    'slot1_harmful'):
            totals[key] += bool(entry[key])
        if entry['policy_duplicate_of_slot1']:
            totals['duplicates_whose_explanation_claims_different'] += entry['explanation_claims_different']
            totals['duplicates_whose_explanation_mentions_retry_without_the_step'] += \
                entry['explanation_mentions_retry_without_the_step']
        totals['slot2_input_differs'] += bool(differing)
        totals[f"attempt0_{first['class']}"] += 1
        totals['distinct'] += first['distinct']
    coincident = sum(math.comb(n, 2) for n in slot1_hashes.values())
    return {'studies': len(rows), 'totals': dict(sorted(totals.items())),
            'slot1_distinct_policies': len(slot1_hashes),
            'slot1_cross_study_coincident_pairs': coincident,
            'slot1_cross_study_pairs': math.comb(len(rows), 2),
            'framing_tokens_observed': sorted({row['facts'][s]['framing'] for row in rows for s in (1, 2)},
                                              key=lambda v: (v is None, v)),
            'per_study': per_study}


def slot1_layout_identity(connection, studies, census_ids):
    """Does an identical rules layout show copying? Slot 1 never sees a prior candidate, so two studies
    whose slot-1 first attempts are the same policy re-derived it independently, from different inputs.
    Counts such cross-study pairs and how many share the rules text byte for byte (development data, $0)."""
    by_policy = defaultdict(list)
    for study in studies:
        candidates = study.get('candidates') or []
        if not candidates:
            continue
        attempts = output_attempts(connection, candidates[0].get('proposal_ref'))
        raw = attempts[0].get('raw') if attempts else None
        parsed = parse_policy(raw or '')
        if not isinstance(parsed, MechanicCandidate):
            continue
        by_policy[content_hash(parsed.candidate)].append(
            (study['study_id'], sha256_text(rules_text(raw)), sha256_text(raw)))
    out = Counter()
    for entries in by_policy.values():
        for index, first in enumerate(entries):
            for second in entries[index + 1:]:
                both = first[0] in census_ids and second[0] in census_ids
                for prefix in ('', 'census_') if both else ('',):
                    out[f'{prefix}same_policy_pairs'] += 1
                    out[f'{prefix}rules_text_identical'] += first[1] is not None and first[1] == second[1]
                    out[f'{prefix}raw_identical'] += first[2] == second[2]
    return {'rule': ('v4-era studies of the two runs (the census and the studies that never reached slot 2), '
                     'slot-1 first attempts, grouped by policy hash; census_ pairs have both studies in the census'),
            'studies': len(studies), **{key: out[key] for key in sorted(out)}}


def step_fired_dynamically(events):
    """run_full_loop_fixed_n.step_fired: the policy itself dispatched send_confirmation."""
    return any(e.get('type') == 'tool_dispatched' and (e.get('payload') or {}).get('caller') == 'policy'
               and (e.get('payload') or {}).get('tool') == 'send_confirmation' for e in events)


def auditor_validation(connection, studies):
    """The auditor against what stored v4-era candidates actually did (development data, $0).

    fires: static step_fires against a policy-dispatched send_confirmation in the candidate's own
    source L trials whose fault triggered. premature_defer: against the candidate's validation result
    on terminal-upgrade-rejection (L correctly rejected fewer than B0), where validation ran."""
    fires, defers, policies = Counter(), [], {}
    for study in studies:
        assessment = study.get('validation_assessment') or {}
        for index, candidate in enumerate(study.get('candidates') or [], 1):
            content = candidate.get('content')
            if not content:
                continue
            audit = audit_policy(content)
            policies.setdefault(candidate['policy_hash'], audit)
            rows = [r for r in study.get('trial_rows') or []
                    if r['stage'] == f'candidate-{index}' and r['trial']['arm'] == 'L' and r['trial'].get('fault_triggered')]
            if rows:
                fired = []
                for row in rows:
                    events = [json.loads(p) for (p,) in connection.execute(
                        'select payload from events where episode_id=? order by seq', (row['trial']['episode_id'],))]
                    fired.append(step_fired_dynamically(events))
                dynamic = 'all' if all(fired) else ('none' if not any(fired) else 'some')
                fires[(audit['step_fires'], dynamic)] += 1
            if study.get('selected_candidate_hash') == candidate['policy_hash'] and assessment.get('by_case'):
                rejection = assessment['by_case'].get('terminal-upgrade-rejection') or {}
                regressed = (rejection.get('L') or {}).get('correctly_rejected', 0) < \
                            (rejection.get('B0') or {}).get('correctly_rejected', 0)
                defers.append({'policy_hash': candidate['policy_hash'], 'premature_defer': audit['premature_defer'],
                               'validation_decision': assessment.get('decision'),
                               'terminal_rejection_regressed': regressed})
    agree = sum(n for (static, dynamic), n in fires.items() if (static and dynamic == 'all') or (not static and dynamic == 'none'))
    return {'candidates_with_triggered_source_trials': sum(fires.values()),
            'static_fires_vs_dynamic': {f'static_{"fires" if s else "silent"}/dynamic_{d}': n
                                        for (s, d), n in sorted(fires.items())},
            'agreement': agree,
            'premature_defer_vs_terminal_rejection': defers,
            'distinct_policies': len(policies),
            'distinct_policies_harmful': sum(a['harmful'] for a in policies.values()),
            'distinct_policies_with_step': sum(a['step_present'] for a in policies.values()),
            'distinct_policies_with_dead_step': sum(a['dead_step'] for a in policies.values())}


# ---------------------------------------------------------------- settings, pins, plan

def settings_from_file(settings_path, *, env_path):
    """Apply the non-empty values of the reviewed non-secret settings file, as the Phase 17 launch and
    runners do. env_path=os.devnull (dry) never reads the root .env; None (live) lets the runtime's own
    loader read credentials from it."""
    from app.config import Settings
    overrides = {k: str(v) for k, v in json.loads(pathlib.Path(settings_path).read_text()).items() if v != ''}
    saved = {k: os.environ.get(k) for k in overrides}
    try:
        os.environ.update(overrides)
        return Settings.from_env(env_path=env_path)
    finally:
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def configuration_pins(settings):
    from app.contracts.models import CampaignBudget
    from app.lab.configuration import frozen_configuration
    caps = CampaignBudget(model_calls=settings.faultlab_model_call_cap, tokens=settings.faultlab_token_cap,
                          dollars=float(settings.faultlab_dollar_cap))
    frozen = frozen_configuration(settings, caps, 'live-v1')
    return {'configuration_hash': content_hash(frozen), 'mechanic_model': frozen['models']['mechanic'],
            'mechanic_model_settings': frozen['model_settings_by_role']['mechanic'],
            'model_settings_by_role': frozen['model_settings_by_role'],
            'dependency_lock_hash': frozen['dependency_lock_hash'],
            'per_request_dollar_bound': frozen['pricing']['mechanic']['per_call_dollar_upper_bound'],
            **{name: frozen[name] for name in FREEZE_FINGERPRINTS}}


def check_pins(pins):
    if pins['configuration_hash'] != DECLARED_CONFIGURATION_HASH:
        raise PlanningError('configuration_hash differs from the declared Phase 22 value; backend/app or settings changed')
    if pins['mechanic_model'] != EXPECTED_MECHANIC_MODEL:
        raise PlanningError('The Mechanic model is not the declared one')
    settings = pins['mechanic_model_settings']
    if (settings.get('temperature') != 0 or MODEL_REQUEST_SETTINGS['temperature'] != 0
            or settings.get('max_output_tokens') != MECHANIC_MAX_OUTPUT_TOKENS
            or settings.get('extra_body') != model_request_options(EXPECTED_MECHANIC_MODEL).get('extra_body')):
        raise PlanningError('The Mechanic request settings are not the frozen ones (temperature 0, 2,000 tokens, no thinking)')
    if pins['per_request_dollar_bound'] != PER_REQUEST_DOLLAR_BOUND:
        raise PlanningError(f'The per-request dollar bound is not the declared ${PER_REQUEST_DOLLAR_BOUND}')


def check_freeze(pins, root=None):
    """The Phase 22 freeze still describes this tree for everything this probe depends on."""
    root = pathlib.Path(root or ROOT)
    path = root / DECLARED_FREEZE
    if sha256_file(path) != DECLARED_FREEZE_SHA256:
        raise PlanningError('The Phase 22 freeze file is not the declared one')
    freeze = json.loads(path.read_text())
    moved = [name for name in FREEZE_FINGERPRINTS if freeze['fingerprints'].get(name) != pins[name]]
    moved += [name for name in FREEZE_FILES if freeze['files'].get(name) != sha256_file(root / name)]
    if moved:
        raise PlanningError(f'The tree no longer matches the Phase 22 freeze: {", ".join(moved)}')
    return {'freeze_sha256': DECLARED_FREEZE_SHA256, 'fingerprints_checked': list(FREEZE_FINGERPRINTS),
            'files_checked': list(FREEZE_FILES)}


def check_budget(total_requests, spend_cap):
    if not (isinstance(spend_cap, (int, float)) and math.isfinite(spend_cap) and 0 < spend_cap <= HARD_SPEND_CAP):
        raise PlanningError(f'The spend cap must be positive and at most ${HARD_SPEND_CAP:.2f}')
    if SpendGuard.micro(total_requests * PER_REQUEST_DOLLAR_BOUND) > SpendGuard.micro(spend_cap):
        raise PlanningError(f'{total_requests} planned requests exceed the ${spend_cap:.2f} cap at '
                            f'${PER_REQUEST_DOLLAR_BOUND}/request')


def survey(connection, pins, cutoff=STORE_CUTOFF, root=None):
    """Load the census, verify both slots of every study, and build the per-study rows."""
    studies, excluded = load_population(connection, cutoff)
    expected = manifest_studies(root)
    found = {s['study_id']: DECLARED_CONFIGURATIONS[s['configuration_hash']] for s in studies}
    if found != expected:
        raise PlanningError('The store census differs from the Phase 17 and 23 run manifests '
                            f'(store only: {sorted(set(found) - set(expected))}; '
                            f'manifests only: {sorted(set(expected) - set(found))})')
    rows, failures = [], []
    for study in studies:
        row = {'study': study, 'phase': found[study['study_id']], 'contexts': {}, 'checks': {}, 'facts': {},
               'user_messages': {}}
        for slot in (1, 2):
            context, checks, facts = verify_slot(connection, study, slot, pins)
            row['contexts'][slot], row['checks'][slot], row['facts'][slot] = context, checks, facts
            row['user_messages'][slot] = mechanic_messages(context)[1]['content'] if context else None
            if not all(checks.values()):
                failures.append({'study_id': study['study_id'], 'slot': slot,
                                 'failed': sorted(k for k, v in checks.items() if not v)})
        prior = study['candidates'][0]
        slot1_raw = (prior.get('raw_outputs') or [None])[-1]
        slot1_audit = audit_policy(prior['content']) if prior.get('content') else {}
        row['reference'] = {'slot1_policy_hash': prior.get('policy_hash'),
                            'slot1_raw_sha256': sha256_text(slot1_raw),
                            'slot1_rules_text_sha256': sha256_text(rules_text(slot1_raw)),
                            # A prompt whose slot-1 policy already fires cannot show a step the change
                            # produced; condition 5 leaves it out (reported separately).
                            'slot1_step_fires': bool(slot1_audit.get('step_fires')),
                            'slot1_harmful': bool(slot1_audit.get('harmful'))}
        rows.append(row)
    return rows, excluded, failures


def precheck(rows):
    """$0 checks that each arm is exactly the declared change. Real checks, not self-checks: they
    compare the arm's request with the control's."""
    out = Counter()
    for row in rows:
        context = row['contexts'][2]
        if context is None or not all(row['checks'][2].values()):
            continue
        control = request_body(mechanic_messages(context), ARM_TEMPERATURE['C'])
        tempered = request_body(mechanic_messages(context), ARM_TEMPERATURE['T'])
        withheld = withhold_raw_text(context)
        hidden = request_body(mechanic_messages(withheld), ARM_TEMPERATURE['H'])
        out['slot2_prompts'] += 1
        out['T_differs_only_in_temperature'] += ({k: v for k, v in tempered.items() if k != 'temperature'}
                                                 == {k: v for k, v in control.items() if k != 'temperature'}
                                                 and tempered['temperature'] != control['temperature'])
        restored = deepcopy(withheld)
        for entry, original in zip(restored['candidate_history'], context['candidate_history']):
            for key in H_WITHHELD_KEYS:
                if key in original:
                    entry[key] = original[key]
        out['H_differs_only_by_the_withheld_keys'] += (canonical_json(restored) == canonical_json(context)
                                                       and hidden['messages'][0] == control['messages'][0]
                                                       and hidden['messages'][1] != control['messages'][1]
                                                       and {k: v for k, v in hidden.items() if k != 'messages'}
                                                       == {k: v for k, v in control.items() if k != 'messages'})
        out['H_keeps_the_prior_canonical_content'] += all(
            'content' in entry for entry in withheld['candidate_history'])
        slot1_raws = context['candidate_history'][0].get('raw_outputs') or []
        out['H_user_message_holds_no_prior_raw_text'] += not any(
            json.dumps(raw, ensure_ascii=False)[1:-1] in hidden['messages'][1]['content'] for raw in slot1_raws)
        reference = request_body(mechanic_messages(without_prior_candidate(context)), ARM_TEMPERATURE['N'])
        emptied = json.loads(reference['messages'][1]['content'])
        emptied.pop('output_schema')
        emptied['candidate_history'] = context['candidate_history']
        out['N_differs_only_by_an_empty_candidate_history'] += (
            canonical_json(emptied) == canonical_json(context)
            and reference['messages'][0] == control['messages'][0]
            and {k: v for k, v in reference.items() if k != 'messages'} == {k: v for k, v in control.items() if k != 'messages'})
        prior = context['candidate_history'][0]
        out['N_user_message_holds_no_prior_candidate'] += (
            json.loads(reference['messages'][1]['content'])['candidate_history'] == []
            and prior['policy_hash'] not in reference['messages'][1]['content']
            and not any(json.dumps(raw, ensure_ascii=False)[1:-1] in reference['messages'][1]['content']
                        for raw in slot1_raws))
    out = dict(out)
    out['passed'] = all(out.get(key) == out.get('slot2_prompts') for key in (
        'T_differs_only_in_temperature', 'H_differs_only_by_the_withheld_keys', 'H_keeps_the_prior_canonical_content',
        'H_user_message_holds_no_prior_raw_text', 'N_differs_only_by_an_empty_candidate_history',
        'N_user_message_holds_no_prior_candidate')) and out.get('slot2_prompts', 0) > 0
    return out


def build_requests(rows):
    """Planned requests in their fixed order, and the distinct prompts they use (by messages hash).
    Only slot-2 prompts are sent; slot 1 is verified but never re-sent."""
    prompts, units = {}, []
    for row in rows:
        study = row['study']
        context = row['contexts'][2]
        if context is None or not all(row['checks'][2].values()):
            continue
        historical = row['facts'][2]['historical_raw']
        history_class = classify_response(historical, row['reference'])
        parsed = parse_policy(historical or '')
        prompt_id = f"{study['study_id']}:slot2"
        for arm in ALL_ARMS:
            messages = mechanic_messages(arm_context(context, arm))
            messages_hash = content_hash(messages)
            prompts.setdefault(messages_hash, {'messages_hash': messages_hash, 'messages': messages,
                                               'prompt_id': prompt_id,
                                               'arm_context': arm if arm in ('H', 'N') else 'stored'})
            units.append({'population': 'slot2', 'prompt_id': prompt_id,
                          'study_id': study['study_id'], 'phase': row['phase'], 'arm': arm,
                          'temperature': ARM_TEMPERATURE[arm], 'messages_hash': messages_hash,
                          'request_hash': request_digest(request_body(messages, ARM_TEMPERATURE[arm])),
                          # The historical fields describe the stored slot-2 request, which only C re-sends.
                          'reference': {**row['reference'],
                                        'historical_raw_sha256': sha256_text(historical),
                                        'historical_policy_hash': (content_hash(parsed.candidate)
                                                                   if isinstance(parsed, MechanicCandidate) else None),
                                        'historical_class': history_class['class'],
                                        'historical_duplicate_of_slot1': history_class['duplicate_of_slot1'],
                                        'historical_attempts': row['facts'][2]['attempts']}})
    order = lambda u, r: (rank('prompt', u['prompt_id'], r), rank('arm', u['prompt_id'], r, u['arm']))  # noqa: E731
    # Round 1 holds every arm of each prompt back to back (C, T, H and the reference N, in ranked order),
    # so a run that stops after r0104 still has a complete round 1 (the declared fallback read-out). Rounds
    # 2 and 3 repeat C, T and H only.
    rounds = [sorted(({**u, 'repeat': r} for u in units if r < ARM_REPEATS[u['arm']]), key=lambda u: order(u, r))
              for r in range(SLOT2_REPEATS)]
    requests = [u for current in rounds for u in current]
    for index, request in enumerate(requests, 1):
        request['request_id'] = f'r{index:04d}'
    return requests, prompts


def build_plan(*, store=STORE, settings_path=None, spend_cap=HARD_SPEND_CAP, cutoff=STORE_CUTOFF, root=None):
    settings_path = pathlib.Path(settings_path or ROOT / DECLARED_SETTINGS)
    if sha256_file(settings_path) != DECLARED_SETTINGS_SHA256:
        raise PlanningError('The settings file is not the declared Phase 17 settings file')
    pins = configuration_pins(settings_from_file(settings_path, env_path=os.devnull))
    check_pins(pins)
    freeze = check_freeze(pins, root)
    connection = connect(store)
    try:
        rows, excluded, failures = survey(connection, pins, cutoff, root)
        checks = precheck(rows)
        if not checks['passed']:
            raise PlanningError('The $0 arm pre-check failed; nothing may be sent')
        requests, prompts = build_requests(rows)
        verified = [r for r in rows if r['contexts'][1] is not None and r['contexts'][2] is not None
                    and all(r['checks'][1].values()) and all(r['checks'][2].values())]
        v4_studies = [r['study'] for r in rows] + _other_v4_studies(connection, rows, cutoff)
        investigation = {'mechanism': historical_mechanism(verified),
                         'slot1_layout_identity': slot1_layout_identity(
                             connection, v4_studies, {r['study']['study_id'] for r in rows}),
                         'auditor_validation': auditor_validation(connection, v4_studies)}
    finally:
        connection.close()
    counts = Counter((r['population'], r['arm']) for r in requests)
    total = len(requests)
    check_budget(total, spend_cap)
    plan = {
        'schema_version': SCHEMA, 'experiment': 'phase25_mechanic_slot2_replay_probe',
        'scoring': 'NON_SCORING_NEVER_FED_BACK', 'split': 'development', 'purpose': PURPOSE,
        'store_cutoff': cutoff, 'harness_sha256': sha256_file(__file__),
        'source_sha256': {name: sha256_file((pathlib.Path(root or ROOT)) / name) for name in FREEZE_FILES
                          + ('backend/app/contracts/models.py', 'backend/app/providers/runtime.py',
                             'backend/app/lab/policy_state.py', 'backend/app/lab/policy_interpreter.py')},
        'settings_file': DECLARED_SETTINGS, 'settings_sha256': DECLARED_SETTINGS_SHA256, **pins, 'freeze': freeze,
        'provider_call': {'role': 'mechanic', 'max_output_tokens': MECHANIC_MAX_OUTPUT_TOKENS,
                          'timeout_seconds': MECHANIC_TIMEOUT_SECONDS, 'response_format': response_format_for(role='mechanic'),
                          'model_options': model_request_options(EXPECTED_MECHANIC_MODEL),
                          'format_repair': 'none: one request per draw (the study would allow one format repair)',
                          'blind_retry': list(RETRYABLE_TRANSPORT_CODES) + [
                              f'at most once, charged, after {BLIND_RETRY_WAIT_SECONDS} s'],
                          'resend_after_main_pass': (
                              'only if the main pass attempted every planned request: each request whose attempts all '
                              f'failed with {list(RESEND_CODES)} and delivered no generation is re-sent once, in plan '
                              'order, charged, under the same blind retry, waits and stop rule; a delivered generation '
                              'is never re-sent'),
                          'backoff_after_errored_request_seconds': list(BACKOFF_SECONDS),
                          'consecutive_errored_requests_stop': CONSECUTIVE_ERROR_ABORT,
                          'request_digest': f'content_hash of the create() keywords {list(REQUEST_KEYS)}; '
                                            'checked before every send',
                          'served_model': 'recorded from each response, never enforced'},
        'arms': {'C': 'the exact verified slot-2 request, re-sent at temperature 0',
                 'T': f'the same bytes at temperature {T_TEMPERATURE}; only the temperature keyword differs',
                 'H': {'temperature': 0, 'rule': H_RULE, 'withheld_keys': list(H_WITHHELD_KEYS)},
                 'N': {'temperature': 0, 'rule': N_RULE,
                       'role': 'reference, descriptive only: the evidence-alone rate of writing slot 1\'s policy'}},
        'populations': {'rule': ('census: every completion study in the read-only store with configuration '
                                 f'{sorted(DECLARED_CONFIGURATIONS)} (Phases 17 and 23), v4 Actor context, '
                                 'evidence v2, not a replay, created before the cutoff, with two proposals; '
                                 'the set must equal the pinned run manifests\' studies with two proposals'),
                        'studies': [r['study']['study_id'] for r in rows],
                        'by_phase': dict(Counter(r['phase'] for r in rows)),
                        'excluded_in_scope': excluded, 'verification_failures': failures,
                        'slot2_prompts': sum(1 for r in requests if r['arm'] == 'C' and r['repeat'] == 0),
                        'prompts_whose_slot1_policy_fires': sorted(
                            r['prompt_id'] for r in requests
                            if r['arm'] == 'C' and r['repeat'] == 0 and r['reference']['slot1_step_fires']),
                        'repeats': dict(ARM_REPEATS),
                        'order': ('round 1: prompts by sha256 rank, and each prompt\'s C, T, H and N back to back in '
                                  f'ranked order (r0001-r{sum(r["repeat"] == 0 for r in requests):04d}); then rounds 2 '
                                  'and 3 of C, T and H, each ranked afresh')},
        'verification': {'rule': sorted({k for r in rows for s in (1, 2) for k in r['checks'][s]}),
                         'framing_tokens': FRAMING_TOKENS,
                         'slots_checked': sum(len(r['checks']) for r in rows),
                         'slots_verified': sum(all(r['checks'][s].values()) for r in rows for s in (1, 2))},
        'precheck': checks,
        'investigation': investigation,
        'readout_rules': readout_rules(),
        'counts': {'by_population_and_arm': {f'{p}/{a}': n for (p, a), n in sorted(counts.items())},
                   'total_requests': total, 'distinct_prompts': len(prompts)},
        'cost': {'per_request_dollar_bound': PER_REQUEST_DOLLAR_BOUND,
                 'planned_upper_bound': round(total * PER_REQUEST_DOLLAR_BOUND, 6), 'spend_cap': spend_cap,
                 'phase_spend_cap': HARD_SPEND_CAP,
                 'max_attempts_under_cap': SpendGuard.micro(spend_cap) // SpendGuard.micro(PER_REQUEST_DOLLAR_BOUND),
                 'retry_headroom_attempts': SpendGuard.micro(spend_cap) // SpendGuard.micro(PER_REQUEST_DOLLAR_BOUND) - total},
        'max_input_tokens_reported_historically': max(r['facts'][s]['reported_prompt_tokens'] or 0
                                                      for r in rows for s in (1, 2)),
        'requests': requests,
    }
    return plan, prompts


def _other_v4_studies(connection, rows, cutoff):
    """v4-era studies of the same two runs that never reached slot 2 (for the auditor validation only)."""
    seen = {r['study']['study_id'] for r in rows}
    out = []
    for (payload,) in connection.execute("select payload from records where kind='completion_studies'"):
        study = json.loads(payload)
        if (study['study_id'] not in seen and study.get('configuration_hash') in DECLARED_CONFIGURATIONS
                and study.get('replay_of') is None and before_cutoff(study.get('created_at'), cutoff)
                and study.get('actor_context_protocol') == ACTOR_CONTEXT_PROTOCOL_V4):
            out.append(study)
    return sorted(out, key=lambda s: (s['created_at'], s['study_id']))


def readout_rules():
    return {
        'unit': ('a draw is one planned request; slot-2 arms have 3 draws per prompt. Classes: INVALID (fails '
                 'MechanicOutput or CandidatePolicy, or empty), NO_CHANGE, STALE_PARENT, CANDIDATE; a CANDIDATE is '
                 'DUPLICATE when its policy hash equals slot 1\'s, else DISTINCT'),
        'distinct_D': 'DISTINCT draws / planned draws; worst case: a missing X draw is not distinct, a missing C draw is',
        'working': ('WORKING = DISTINCT, the static auditor says the step fires after a transient failure, and no '
                    'declared harmful side rule (premature defer, stops the first confirmation)'),
        'working_share': ('over the prompts whose slot-1 policy\'s step does not fire, the sum of X\'s WORKING share '
                          'of its planned draws (a missing X draw is not WORKING) minus C\'s WORKING-or-missing share '
                          'of its planned draws; each prompt adds between -1 and +1, and at equal per-draw WORKING '
                          'rates the expectation is 0 however the draws cluster within a prompt. The round-1 count '
                          'of prompts with any WORKING draw is descriptive only (breadth, not per-draw yield)'),
        'complete': 'an arm is complete when it received >= 95% of its planned draws (75 of 78; 25 of 26 in round 1)',
        'recommend': ('RECOMMEND_FOR_A_LATER_LOOP for X in {T, H} iff X and C are complete AND D_X >= 0.70 AND '
                      'D_X - D_C >= 0.30 AND one-sided exact sign test over prompts (per-prompt D mean, X > C, ties '
                      f'dropped) p < 0.05 AND working share gain >= {WORKING_SHARE_GAIN_MIN} AND invalid_X - '
                      'invalid_C <= 0.10 (received draws) AND at most half of X\'s distinct firing draws carry a '
                      'declared harmful side rule; otherwise NOT_RECOMMENDED (or INCOMPLETE), listing every failed '
                      'condition'),
        'round1_fallback': ('if an arm\'s decision over all rounds is INCOMPLETE and the run ended by a stop the '
                            f'operator does not choose ({list(FALLBACK_STOP_REASONS)}, or a crash recorded with its '
                            'traceback) with no stop signal, its declared decision is the same rule applied '
                            'to round 1 alone (repeat 0: 26 planned draws per arm, complete at 25), with working '
                            f'share gain >= {WORKING_SHARE_GAIN_MIN_ROUND1}, labelled round 1 only, and the '
                            'all-rounds contrast stays beside it; the mechanism read-out falls back the same way. '
                            'After an operator stop (any SIGINT or SIGTERM, whoever sent it, or a process that died '
                            'with no final manifest) an INCOMPLETE decision stays INCOMPLETE'),
        'mechanism': ('COPYING_OF_THE_PRIOR_TEXT_SHOWN iff C and H complete AND dup_C - dup_H >= 0.30 (received '
                      'draws) AND one-sided exact sign test over prompts (per-prompt duplicate mean, C > H) p < 0.05 '
                      'AND distinct_H - distinct_C >= 0.30 (received) AND (INVALID + STALE_PARENT + NO_CHANGE) share '
                      'of H <= that of C + 0.10 (received); otherwise NOT_SHOWN (or INCOMPLETE), quoted beside N\'s '
                      'rate of writing slot 1\'s policy with no prior candidate in view'),
        'descriptive': ('byte-identical and rules-text-identical to slot 1; step present; dead steps; side-rule flags; '
                        'distinct policy counts; distinct firing draws, harmful or not; working draws on prompts whose '
                        'slot-1 policy fires; blind retries, re-sends and timeouts per arm; temperature-0 determinism '
                        'of C and H; C against the historical slot-2 output; the distinct sign test clustered by '
                        'slot-1 policy; Wilson 95% intervals over draws (clustered by prompt, so they understate the '
                        'uncertainty) and Newcombe intervals for differences'),
        'adoption': ('a recommended arm is for a later loop\'s own declaration only; it is never used in a run that '
                     'compares against earlier phases without one'),
    }


def plan_hash(plan):
    return content_hash(plan)


# ---------------------------------------------------------------- spend guard, output guard, claims

class SpendGuard:
    """Charges every attempt at the conservative bound, in integer micro-dollars."""

    def __init__(self, cap, per_request=PER_REQUEST_DOLLAR_BOUND):
        if not (math.isfinite(cap) and 0 < cap <= HARD_SPEND_CAP):
            raise PlanningError(f'The spend cap must be positive and at most ${HARD_SPEND_CAP:.2f}')
        self.cap, self.per_request, self.attempts = cap, per_request, 0

    @staticmethod
    def micro(dollars):
        return round(dollars * 1_000_000)

    def admit(self):
        if (self.attempts + 1) * self.micro(self.per_request) > self.micro(self.cap):
            return False
        self.attempts += 1
        return True

    @property
    def charged(self):
        return self.attempts * self.micro(self.per_request) / 1_000_000


def _root(root=None):
    """The repository root, read at call time so tests can point every guard at a tmp tree."""
    return pathlib.Path(root if root is not None else ROOT)


def delivered_generations(manifest):
    counted = manifest.get('generations_delivered')
    statuses = manifest.get('statuses') or {}
    if type(counted) is not int or not isinstance(statuses, dict):
        return None
    return max(counted, int(statuses.get('ok', 0)) + int(statuses.get('empty_response', 0)))


def entry_delivered(entry):
    """Whether one saved response line shows that a generation may have arrived."""
    if not isinstance(entry, dict):
        return True
    if entry.get('status') in RECEIVED:
        return True
    for attempt in entry.get('attempts') or []:
        if not isinstance(attempt, dict):
            return True
        if (attempt.get('served') is not None or attempt.get('input_tokens') is not None
                or attempt.get('output_tokens') is not None
                or attempt.get('code') in ('EMPTY_FINAL_RESPONSE', 'INVALID_RESPONSE_SHAPE')):
            return True
    return False


def claimed_output(artifacts, out):
    parts = pathlib.PurePosixPath(out).parts if isinstance(out, str) and out else ()
    if (len(parts) != 3 or parts[0] != 'artifacts' or not parts[1].startswith('phase25-') or parts[1] == CLAIM_DIR
            or any(part in ('', '.', '..') for part in parts)):
        return None
    return pathlib.Path(artifacts).parent / parts[0] / parts[1] / parts[2]


def _final(manifest):
    return manifest.get('status') in FINAL_STATUSES and bool(manifest.get('ended_at'))


def _charge(manifest, path):
    charged = manifest.get('charged_upper_bound')
    if type(charged) not in (int, float) or not math.isfinite(charged) or charged < 0:
        raise PlanningError(f'An earlier live run does not state a readable charged_upper_bound ({path}); '
                            'the phase cap cannot be applied. Investigate before any run')
    return charged


def live_run_records(artifacts):
    """Every earlier Phase 25 live run, checked; refuses unless each one is final and delivered nothing.
    Claims are matched to the manifest in the directory each claim names, never by count."""
    artifacts = pathlib.Path(artifacts)
    manifests = {path.resolve(): path for path in artifacts.glob(LIVE_MANIFEST_GLOB)}
    numbers = []
    for claim in sorted((artifacts / CLAIM_DIR).glob('claim-*.json')):
        match = CLAIM_NAME.fullmatch(claim.name)
        if match:
            numbers.append(int(match.group(1)))
        try:
            record = json.loads(claim.read_text())
        except (OSError, ValueError):
            record = None
        output = claimed_output(artifacts, record.get('out')) if isinstance(record, dict) else None
        if output is None:
            raise PlanningError(f'{claim.name} cannot be read or names no valid output directory; investigate '
                                'before any run')
        manifest = output / MANIFEST_NAME
        if not manifest.is_file():
            raise PlanningError(f'{claim.name} claims a live run with no manifest; it may be starting, or it crashed '
                                'before writing one. If its process is gone, close it at $0 with '
                                f'--finalize-abandoned artifacts/{CLAIM_DIR}/{claim.name}')
        manifests.setdefault(manifest.resolve(), manifest)
    undelivered = []
    for _, path in sorted(manifests.items()):
        try:
            manifest = json.loads(path.read_text())
        except (OSError, ValueError):
            raise PlanningError(f'An earlier live manifest cannot be read ({path}); investigate before any run') from None
        if not isinstance(manifest, dict):
            raise PlanningError(f'An earlier live manifest cannot be read ({path}); investigate before any run')
        if not _final(manifest):
            raise PlanningError(f'An earlier live run is not final ({path}); it may still be running. If its process '
                                'is gone, close its claim at $0 with --finalize-abandoned')
        delivered = delivered_generations(manifest)
        if delivered is None or delivered > 0:
            raise PlanningError(f'A live slot-2 probe run already exists ({path}); a second draw would be '
                                'repeat-until-lucky and needs its own declared phase')
        undelivered.append({'manifest': str(path.relative_to(artifacts.parent)),
                            'charged_upper_bound': _charge(manifest, path)})
    return {'undelivered': undelivered, 'claim_numbers': sorted(numbers)}


def earlier_live_runs(artifacts):
    return live_run_records(artifacts)['undelivered']


def phase_spend_remaining(earlier):
    used = sum(SpendGuard.micro(run['charged_upper_bound']) for run in earlier)
    return (SpendGuard.micro(HARD_SPEND_CAP) - used) / 1_000_000


def effective_spend_cap(requested, earlier):
    if not (isinstance(requested, (int, float)) and math.isfinite(requested) and 0 < requested <= HARD_SPEND_CAP):
        raise PlanningError(f'The spend cap must be positive and at most ${HARD_SPEND_CAP:.2f}')
    remaining = phase_spend_remaining(earlier)
    if remaining <= 0:
        raise PlanningError(f'Earlier runs that delivered nothing already charged the ${HARD_SPEND_CAP:.2f} phase cap')
    return min(requested, remaining)


def check_output(out, *, root=None, live=True):
    """A new directory exactly artifacts/phase25-<date>/<name>, never an existing one; one delivering
    live run only."""
    root = _root(root)
    artifacts = (root / 'artifacts').resolve()
    out = pathlib.Path(out)
    out = (out if out.is_absolute() else root / out).resolve()
    try:
        relative = out.relative_to(artifacts)
    except ValueError:
        raise PlanningError('The output directory must be under artifacts/phase25-<date>/') from None
    if len(relative.parts) != 2 or not relative.parts[0].startswith('phase25-') or relative.parts[0] == CLAIM_DIR:
        raise PlanningError('The output directory must be exactly artifacts/phase25-<date>/<name>')
    if out.exists():
        raise PlanningError(f'{out} exists; a run is never resumed or overwritten - use a new directory')
    if live:
        earlier_live_runs(artifacts)
    return out


def take_claim(out, plan_hash_value, harness, *, root=None, spend_cap=None, expected_earlier=None):
    """Atomically claim the next live run (written in full to a private file, then hard-linked to its
    name, which fails if the name exists). Never deleted."""
    artifacts = (_root(root) / 'artifacts').resolve()
    records = live_run_records(artifacts)
    earlier = records['undelivered']
    if expected_earlier is not None and earlier != expected_earlier:
        raise PlanningError('The earlier live runs changed during the launch checks; nothing was claimed. Re-launch')
    directory = artifacts / CLAIM_DIR
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f'claim-{max(records["claim_numbers"], default=0) + 1:02d}.json'
    temporary = directory / f'.{path.name}.{os.getpid()}.tmp'
    try:
        with temporary.open('w', encoding='utf-8') as handle:
            json.dump({'claim': path.name, 'pid': os.getpid(), 'out': str(out.relative_to(artifacts.parent)),
                       'plan_hash': plan_hash_value, 'harness_sha256': harness, 'spend_cap': spend_cap,
                       'claimed_at': datetime.now(timezone.utc).isoformat(),
                       'earlier_undelivered_runs': earlier}, handle, indent=2)
            handle.write('\n')
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temporary, path)
        except FileExistsError:
            raise PlanningError(f'{path.name} is already taken: another live launch claimed this run first') from None
    finally:
        temporary.unlink(missing_ok=True)
    return path, earlier


def claim_process_alive(pid):
    """False only when the claim's process is gone (or the pid now runs something else)."""
    if type(pid) is not int or pid <= 0:
        return True
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except OSError:
        return True
    try:
        command = subprocess.run(['ps', '-ww', '-o', 'command=', '-p', str(pid)], capture_output=True,
                                 text=True, timeout=10).stdout
    except (OSError, subprocess.SubprocessError):
        return True
    return not command.strip() or 'slot2_probe' in command


def finalize_abandoned(claim, *, root=None, alive=None):
    """Close, at $0, a claimed run whose process died before its manifest became final. Refuses while the
    claim's process may be alive and for a final run. Charges every recorded attempt, plus
    ABANDONED_IN_FLIGHT_ATTEMPTS when the run died while RUNNING. A later run is allowed only if
    nothing was delivered."""
    alive = claim_process_alive if alive is None else alive
    root = _root(root)
    artifacts = (root / 'artifacts').resolve()
    path = pathlib.Path(claim)
    path = (path if path.is_absolute() else root / path).resolve()
    if path.parent != artifacts / CLAIM_DIR or not CLAIM_NAME.fullmatch(path.name):
        raise PlanningError(f'--finalize-abandoned takes a claim file in artifacts/{CLAIM_DIR}/')
    try:
        record = json.loads(path.read_text())
    except (OSError, ValueError):
        raise PlanningError(f'{path.name} cannot be read') from None
    output = claimed_output(artifacts, record.get('out')) if isinstance(record, dict) else None
    if output is None:
        raise PlanningError(f'{path.name} names no valid output directory; investigate by hand')
    pid = record.get('pid')
    if alive(pid):
        raise PlanningError(f'The process that took {path.name} (pid {pid}) may still be running. Stop it with '
                            f'kill -TERM {pid} and let it write its final manifest; nothing was changed')
    manifest_path = output / MANIFEST_NAME
    existing = None
    if manifest_path.exists():
        try:
            existing = json.loads(manifest_path.read_text())
        except (OSError, ValueError):
            existing = None
        if not isinstance(existing, dict):
            raise PlanningError(f'{manifest_path} cannot be read; inspect it and move it aside by hand, then re-run')
        if _final(existing):
            raise PlanningError(f'{manifest_path} is already final; there is nothing to finalize')
    responses = output / 'responses.jsonl'
    results, partial = load_results(responses) if responses.exists() else ([], 0)
    previous_status = existing.get('status') if existing else None
    in_flight = 0 if previous_status in (None, 'STARTING') else ABANDONED_IN_FLIGHT_ATTEMPTS
    recorded_attempts = sum(len(r.get('attempts') or []) if isinstance(r, dict) else 2 for r in results)
    prior_attempts = existing.get('attempts') if existing else 0
    attempts = max(prior_attempts if type(prior_attempts) is int else 0, recorded_attempts) + in_flight
    prior = delivered_generations(existing) if existing else 0
    delivered = sum(entry_delivered(r) for r in results)
    now = datetime.now(timezone.utc).isoformat()
    manifest = dict(existing) if existing else {
        'schema_version': SCHEMA, 'mode': 'live', 'plan_hash': record.get('plan_hash'),
        'harness_sha256': record.get('harness_sha256'), 'claim': str(path.relative_to(artifacts.parent)),
        'pid': pid, 'spend_cap': record.get('spend_cap'), 'started_at': None, 'traceback': None}
    manifest.update({
        'status': 'ABORTED', 'stop_reason': 'abandoned', 'ended_at': now,
        'requests_done': sum(1 for r in results if not (isinstance(r, dict) and r.get('resend'))),
        'resend_lines': sum(1 for r in results if isinstance(r, dict) and r.get('resend')),
        'statuses': dict(sorted(Counter(str(r.get('status')) if isinstance(r, dict) else 'unreadable'
                                        for r in results).items())),
        'generations_delivered': None if prior is None else max(prior, delivered),
        'attempts': attempts,
        'charged_upper_bound': attempts * SpendGuard.micro(PER_REQUEST_DOLLAR_BOUND) / 1_000_000,
        'finalized_abandoned': {
            'at': now, 'claim': str(path.relative_to(artifacts.parent)), 'pid': pid, 'pid_alive': False,
            'previous_status': previous_status, 'responses_lines': len(results),
            'partial_lines_skipped': partial, 'unrecorded_in_flight_attempts_charged': in_flight}})
    output.mkdir(parents=True, exist_ok=True)
    write_json(manifest_path, manifest)
    return manifest_path, manifest


# ---------------------------------------------------------------- one paid run at a time

# In-process or direct-provider runs, by their manifests (exact depths only: nothing under a sealed
# or held-out directory is ever listed). Phases 26-29 are being built beside this one; their
# manifest names are not known here, so any *manifest*.json at run depth must be final.
OTHER_RUN_MANIFESTS = (('phase20', 'phase20-*/*/dev-probe-manifest.json'),
                       ('phase21', 'phase21-*/*/lapse-probe-manifest.json'),
                       ('phase23', 'phase23-*/full-loop-manifest.json'),
                       ('phase26-29', 'phase2[6-9]-*/*manifest*.json'),
                       ('phase26-29', 'phase2[6-9]-*/*/*manifest*.json'))
OTHER_CLAIM_DIRS = ('phase21-live-claims', 'phase26-live-claims', 'phase27-live-claims', 'phase28-live-claims',
                    'phase29-live-claims')
BACKEND_STATUS_URL = 'http://127.0.0.1:8000/api/config/status'
OTHER_RUN_AFTER_CLAIM = 'another_paid_run_after_claim'


def manifest_running(manifest):
    """A manifest counts as final only with an end time and no running status."""
    if not isinstance(manifest, dict) or not manifest.get('ended_at'):
        return True
    return (str(manifest.get('status') or '').upper() in ('STARTING', 'RUNNING')
            or manifest.get('stop_reason') == 'running')


def backend_status(url=BACKEND_STATUS_URL, timeout=3.0):
    """Read-only GET of the lab backend's status. ('down', None) when nothing listens (so no backend-driven
    run can be active); ('idle'|'active', id) from the body; ('unknown', reason) otherwise."""
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            body = json.loads(response.read().decode('utf-8'))
    except urllib.error.URLError as error:
        if isinstance(error.reason, ConnectionRefusedError):
            return 'down', None
        return 'unknown', type(error.reason).__name__
    except ConnectionRefusedError:
        return 'down', None
    except (OSError, ValueError) as error:
        return 'unknown', type(error).__name__
    active = body.get('active_campaign_id') if isinstance(body, dict) else None
    return ('active', active) if active else ('idle', None)


HELDOUT_MANIFEST_NAME = 'heldout-manifest.json'
CLAIMED_RUN = re.compile(r'artifacts/phase2[0-9]-[A-Za-z0-9._-]+/[A-Za-z0-9._-]+')


def claimed_run_directory(root, out):
    """The run directory a sibling phase's claim names, or None. Only exactly artifacts/phase2N-<x>/<name>
    is accepted, never phase22-* (the heldout-2 seal), a claims directory, '.' or '..': a malformed or
    foreign claim is a blocker and nothing it names is read."""
    if not isinstance(out, str) or not CLAIMED_RUN.fullmatch(out):
        return None
    parts = pathlib.PurePosixPath(out).parts
    if (parts[1].startswith('phase22-') or parts[1].endswith('-live-claims')
            or any(part in ('.', '..') for part in parts)):
        return None
    return root / parts[0] / parts[1] / parts[2]


def process_list():
    """(pid, ppid, command) for every process, from `ps` (read-only, local, $0)."""
    output = subprocess.run(['ps', '-axww', '-o', 'pid=,ppid=,command='], capture_output=True, text=True,
                            timeout=10, check=True).stdout
    rows = []
    for line in output.splitlines():
        parts = line.split(None, 2)
        if len(parts) == 3 and parts[0].isdigit() and parts[1].isdigit():
            rows.append((int(parts[0]), int(parts[1]), parts[2]))
    return rows


# Review round 3: widened in the fail-closed direction. Any interpreter whose name starts with "python"
# (python3.13t, python3.12-intel64, macOS's framework "Python"); a script at any path ending in
# experiments/<name>.py (a runner started from scripts/ as experiments/x.py); and any prefix of --execute-live
# from "--e" up, because argparse accepts every unambiguous prefix and several older runners have no other --e*
# option (so --e and --ex launch them live).
PYTHON_EXECUTABLE = re.compile(r'python', re.IGNORECASE)
PAID_RUNNER_SCRIPT = re.compile(r'(?:.*/)?experiments/[A-Za-z0-9_.-]+\.py')
PYTHON_OPTIONS_WITH_A_VALUE = ('-W', '-X', '--check-hash-based-pycs')
LIVE_FLAG = '--execute-live'
LIVE_FLAG_SHORTEST_ABBREVIATION = '--e'


def paid_run_command(command):
    """Whether one process's command line is a paid experiment run, by tokens, not substrings (review round
    2): the first token is a Python executable (its name starts with "python"), the script it runs (its first
    argument after Python's own options; -c, -m and - are not a script run) is <any path>/experiments/<name>.py,
    and a later token is --execute-live or any prefix of it from "--e" up (review round 3). A shell, grep or
    heredoc that merely mentions those words, and a `caffeinate -is python ...` helper, are not a run; the
    Python process a caffeinate helper belongs to is. A command line shlex cannot parse is split on whitespace."""
    try:
        tokens = shlex.split(command)
    except ValueError:
        tokens = command.split()
    if not tokens or not PYTHON_EXECUTABLE.match(pathlib.PurePosixPath(tokens[0]).name):
        return False
    index = 1
    while index < len(tokens) and tokens[index].startswith('-'):
        if tokens[index] in ('-c', '-m', '-'):
            return False
        index += 2 if tokens[index] in PYTHON_OPTIONS_WITH_A_VALUE else 1
    if index >= len(tokens) or not PAID_RUNNER_SCRIPT.fullmatch(tokens[index]):
        return False
    return any(token == LIVE_FLAG or (len(token) >= len(LIVE_FLAG_SHORTEST_ABBREVIATION) and LIVE_FLAG.startswith(token))
               for token in tokens[index + 1:])


def live_experiment_processes(reader=None):
    """Other processes launched as a paid experiment run: a Python process running an experiments/*.py script
    with --execute-live or a prefix of it (paid_run_command). This process, its ancestors (the
    shell that launched it) and its descendants are excluded: `caffeinate -is <python ...>` keeps the original
    pid for Python and forks the caffeinate helper as Python's CHILD, whose command line repeats the launch
    arguments (measured in review round 2). Fail closed: a process list that cannot be read is itself a
    blocker."""
    try:
        rows = (reader or process_list)()
    except Exception as error:  # noqa: BLE001
        return [f'the process list could not be read ({type(error).__name__}), so no other paid run can be ruled out']
    parent, children = {}, defaultdict(list)
    for pid, ppid, _ in rows:
        parent[pid] = ppid
        children[ppid].append(pid)
    own, pid = set(), os.getpid()
    while pid and pid not in own:
        own.add(pid)
        pid = parent.get(pid)
    pending = [os.getpid()]
    while pending:
        for child in children.get(pending.pop(), ()):
            if child not in own:
                own.add(child)
                pending.append(child)
    return [f'pid {pid}: {command[:200]}' for pid, _, command in rows
            if pid not in own and paid_run_command(command)]


def other_paid_runs(*, root=None, ignore=(), status=None, processes=None):
    """Every reason to believe another paid run may be in progress. Empty means none was found."""
    root = _root(root)
    artifacts = (root / 'artifacts').resolve()
    ignored = {(pathlib.Path(p) if pathlib.Path(p).is_absolute() else root / p).resolve() for p in ignore or ()}
    blockers = []
    for phase, pattern in OTHER_RUN_MANIFESTS:
        for path in sorted(artifacts.glob(pattern)):
            if path.resolve() in ignored or path.name == HELDOUT_MANIFEST_NAME:
                continue
            try:
                manifest = json.loads(path.read_text())
            except (OSError, ValueError):
                manifest = None
            if manifest_running(manifest):
                blockers.append(f'{phase} run may be in progress ({path.relative_to(root)})')
    for name in OTHER_CLAIM_DIRS:
        for claim in sorted((artifacts / name).glob('claim-*.json')):
            if claim.resolve() in ignored:
                continue
            try:
                record = json.loads(claim.read_text())
            except (OSError, ValueError):
                record = None
            directory = claimed_run_directory(root, record.get('out')) if isinstance(record, dict) else None
            if directory is None:
                blockers.append(f'{name}/{claim.name} cannot be read or names no valid run directory; nothing it '
                                'names was read')
                continue
            finals = []
            for path in directory.glob('*manifest*.json'):
                if path.name == HELDOUT_MANIFEST_NAME:
                    continue
                try:
                    finals.append(not manifest_running(json.loads(path.read_text())))
                except (OSError, ValueError):
                    finals.append(False)
            if not any(finals):
                blockers.append(f'{name}/{claim.name} names a run with no final manifest')
    blockers.extend(live_experiment_processes() if processes is None else list(processes))
    state, detail = (status or backend_status)()
    if state == 'active':
        blockers.append(f'the lab backend reports an active campaign ({detail})')
    elif state == 'unknown':
        blockers.append(f'the lab backend status could not be read ({detail}); check it by hand')
    return blockers, state


def blocker_advice(blockers):
    """What the operator can do about each kind of blocker. --ignore-manifest clears only a manifest or a claim
    (review round 2: the refusal used to suggest it for a process too)."""
    advice = []
    if any(b.startswith(('pid ', 'the process list')) for b in blockers):
        advice.append('A listed process is a paid experiment run, or the process list could not be read: wait for '
                      'that run to end (stop it only if it is yours); --ignore-manifest cannot clear a process')
    if any(b.startswith('the lab backend') for b in blockers):
        advice.append('Check the lab backend by hand; --ignore-manifest cannot clear it')
    if any(not b.startswith(('pid ', 'the process list', 'the lab backend')) for b in blockers):
        advice.append('If a listed run manifest or claim is known to have crashed, pass its exact path to '
                      '--ignore-manifest')
    return '. '.join(advice)


def check_other_paid_runs(args, *, root=None, status=None):
    blockers, state = other_paid_runs(root=root, ignore=getattr(args, 'ignore_manifest', None) or (), status=status)
    if blockers:
        more = f' (and {len(blockers) - 1} more: {"; ".join(blockers[1:4])})' if len(blockers) > 1 else ''
        raise PlanningError(f'One paid run at a time: {blockers[0]}{more}. {blocker_advice(blockers)}')
    return state


# ---------------------------------------------------------------- the review gate

def status_block(protocol_text):
    lines = []
    for line in protocol_text.splitlines():
        if line.startswith('## '):
            break
        lines.append(line)
    return '\n'.join(lines)


def check_review(protocol_text, protocol_sha256, harness, plan_hash_value, *, root=None):
    if REVIEW_PENDING_MARKER in status_block(protocol_text):
        raise PlanningError(f'The protocol status still says "{REVIEW_PENDING_MARKER}"; live execution refuses')
    expected_line = REVIEWED_LINE.format(harness=harness, plan=plan_hash_value)
    if not any(line.strip() == expected_line for line in protocol_text.splitlines()):
        raise PlanningError('The protocol has no bare "Reviewed for launch" line (no backticks, list marker or bold) '
                            'naming this harness sha256 and plan hash')
    path = _root(root) / REVIEW_RECORD
    try:
        record = json.loads(path.read_text())
    except (OSError, ValueError):
        raise PlanningError(f'No readable review record at {REVIEW_RECORD}; live execution refuses') from None
    expected = {'protocol_sha256': protocol_sha256, 'harness_sha256': harness, 'plan_hash': plan_hash_value}
    if not isinstance(record, dict) or any(record.get(key) != value for key, value in expected.items()):
        raise PlanningError('The review record does not name this protocol sha256, harness sha256 and plan hash')


def write_json(path, value):
    path = pathlib.Path(path)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + '\n')
    os.replace(temporary, path)


# ---------------------------------------------------------------- live execution

class Recorder:
    """Appends each response as it arrives and rewrites the manifest after every request."""

    def __init__(self, out, manifest, secrets=()):
        self.out, self.manifest, self.secrets = out, manifest, tuple(s for s in secrets if s)
        self.stream = (out / 'responses.jsonl').open('a', encoding='utf-8')

    def scrub(self, text):
        for secret in self.secrets:
            text = text.replace(secret, '[redacted]')
        return text

    def record(self, entry):
        self.stream.write(self.scrub(json.dumps(entry, sort_keys=True, ensure_ascii=False)) + '\n')
        self.stream.flush()
        os.fsync(self.stream.fileno())

    def save(self):
        path = self.out / MANIFEST_NAME
        temporary = path.with_suffix('.json.tmp')
        temporary.write_text(self.scrub(json.dumps(self.manifest, indent=2, ensure_ascii=False)) + '\n')
        os.replace(temporary, path)

    def close(self):
        self.stream.close()


def openai_client_factory(**kwargs):
    """The provider client RuntimeProvider would build itself (read at call time; tests replace it)."""
    from openai import AsyncOpenAI
    return AsyncOpenAI(**kwargs)


def _short_text(value):
    return value[:200] if isinstance(value, str) else None


def served_metadata(response):
    usage = getattr(response, 'usage', None)

    def count(name):
        value = getattr(usage, name, None)
        return value if type(value) is int else None
    return {'model': _short_text(getattr(response, 'model', None)),
            'system_fingerprint': _short_text(getattr(response, 'system_fingerprint', None)),
            'prompt_tokens': count('prompt_tokens'), 'completion_tokens': count('completion_tokens')}


class RequestMismatch(RuntimeError):
    pass


class RequestSender:
    """A client_factory for RuntimeProvider. RuntimeProvider builds the frozen Mechanic request (its own
    validation, token admission and secret check); this wrapper then applies the one per-request change
    the plan declares (the arm's temperature), recomputes the digest of the exact create() keywords and
    forwards only if it equals the planned request_hash. A mismatch is never sent: it is recorded and
    the run aborts. It also records what served each request (never enforced)."""

    def __init__(self, base=None):
        self.base, self.last, self.expected, self.mismatch = base, None, None, None

    def __call__(self, **kwargs):
        return _SendingClient((self.base or openai_client_factory)(**kwargs), self)

    def arm(self, request_hash, temperature):
        self.expected, self.last = (request_hash, temperature), None

    def take(self):
        value, self.last = self.last, None
        return value


class _SendingClient:
    def __init__(self, client, sender):
        self._client, self._sender = client, sender
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    async def _create(self, **kwargs):
        expected = self._sender.expected
        if expected is None:
            self._sender.mismatch = 'no planned request was armed'
            raise RequestMismatch(self._sender.mismatch)
        request_hash, temperature = expected
        if kwargs.get('temperature') != MODEL_REQUEST_SETTINGS['temperature']:
            self._sender.mismatch = 'the runtime did not build the frozen temperature'
            raise RequestMismatch(self._sender.mismatch)
        kwargs = {**kwargs, 'temperature': temperature}
        if request_digest(kwargs) != request_hash:
            self._sender.mismatch = 'the request about to be sent is not the planned one'
            raise RequestMismatch(self._sender.mismatch)
        response = await self._client.chat.completions.create(**kwargs)
        self._sender.last = served_metadata(response)
        return response

    async def close(self):
        await self._client.close()


def resend_eligible(entry):
    """A saved main-pass line whose every attempt failed with a code that says no generation was produced,
    and that shows no sign of a delivered generation: re-sending it is blind (pitfall 49). A local refusal,
    a request mismatch or anything delivered is never re-sent."""
    return (isinstance(entry, dict) and entry.get('status') == 'error' and not entry.get('request_mismatch')
            and not entry.get('resend') and bool(entry.get('attempts')) and not entry_delivered(entry)
            and all(isinstance(a, dict) and a.get('code') in RESEND_CODES for a in entry['attempts']))


async def run_requests(requests, prompts, provider, guard, recorder, *, sender=None, stop=lambda: False,
                       sleep=asyncio.sleep, backoff=BACKOFF_SECONDS, retry_wait=BLIND_RETRY_WAIT_SECONDS):
    """Send the planned requests in order, then (only if every planned request was attempted) re-send once
    each request that errored with nothing delivered. Returns the main pass's stop reason. Never re-rolls
    a response: only a failure that delivered no generation is retried or re-sent, and every attempt is
    charged. Each line is written and flushed before anything else can fail."""
    manifest = recorder.manifest
    for key, value in (('requests_done', 0), ('resend_lines', 0), ('statuses', {}), ('measured_input_tokens', 0),
                       ('measured_output_tokens', 0), ('generations_delivered', 0), ('backoff_waits', []),
                       ('resend_pass', None), ('in_flight_request', None), ('last_request', None)):
        manifest.setdefault(key, value)

    async def pause(seconds):
        remaining = float(seconds)
        while remaining > 0 and not stop():
            step = min(1.0, remaining)
            await sleep(step)
            remaining -= step

    async def send(request, resend):
        prompt = prompts[request['messages_hash']]
        # Replaced, never mutated: a stop-signal handler may copy it at any moment.
        manifest['in_flight_request'] = {'request_id': request['request_id'], 'resend': resend}
        entry = {key: request[key] for key in ('request_id', 'population', 'prompt_id', 'arm', 'repeat',
                                                'request_hash', 'messages_hash', 'temperature')}
        entry.update(attempts=[], status='error', raw=None)
        if resend:
            entry['resend'] = True
        generation, refused, delivered = None, False, False
        for attempt in (1, 2):
            if attempt == 2:
                await pause(retry_wait)
                if stop():
                    break
            if not guard.admit():
                refused = True
                break
            if sender is not None:
                sender.arm(request['request_hash'], request['temperature'])
            started = datetime.now(timezone.utc).isoformat()
            try:
                generation = await provider.complete(prompt['messages'], role='mechanic',
                                                     max_output_tokens=MECHANIC_MAX_OUTPUT_TOKENS,
                                                     timeout_seconds=MECHANIC_TIMEOUT_SECONDS)
                entry['attempts'].append({'attempt': attempt, 'started_at': started, 'error': None,
                                          'served': sender.take() if sender is not None else None})
                break
            except RuntimeProviderError as error:
                delivered = delivered or error.generation is not None
                entry['attempts'].append({'attempt': attempt, 'started_at': started, **error.diagnostics,
                                          'served': sender.take() if sender is not None else None})
                if sender is not None and sender.mismatch:
                    break
                if error.code == 'EMPTY_FINAL_RESPONSE':
                    entry['status'] = 'empty_response'
                    break
                if attempt == 1 and error.code in RETRYABLE_TRANSPORT_CODES:
                    continue
                break
        manifest['attempts'] = guard.attempts
        manifest['charged_upper_bound'] = guard.charged
        if generation is not None or delivered:
            manifest['generations_delivered'] += 1
        if generation is not None:
            entry.update(status='ok', raw=generation.content, requested_model=generation.model_id,
                         input_tokens=generation.input_tokens, output_tokens=generation.output_tokens)
        served_last = (entry['attempts'][-1].get('served') if entry['attempts'] else None) or {}
        entry['served_model'] = served_last.get('model')
        entry['system_fingerprint'] = served_last.get('system_fingerprint')
        if sender is not None and sender.mismatch:
            entry['request_mismatch'] = sender.mismatch
        # Review round 2: a live line carries no classification (no class, policy hash, raw sha256 or match
        # with the historical output), so nothing on disk states which arm is ahead while the run is live; the
        # read-outs classify the saved raw text afterwards. Nothing that can raise runs before the line is saved.
        if entry['attempts']:
            recorder.record(entry)
            manifest['resend_lines' if resend else 'requests_done'] += 1
            manifest['statuses'][entry['status']] = manifest['statuses'].get(entry['status'], 0) + 1
            if entry['status'] == 'ok':
                manifest['measured_input_tokens'] += entry.get('input_tokens') or 0
                manifest['measured_output_tokens'] += entry.get('output_tokens') or 0
        manifest['in_flight_request'] = None
        manifest['last_request'] = {'request_id': request['request_id'], 'resend': resend}
        recorder.save()
        if sender is not None and sender.mismatch:
            raise PlanningError(f'Request mismatch at {request["request_id"]}: {sender.mismatch}; nothing was sent '
                                'for it and the run stops')
        return entry, refused

    async def run_pass(batch, resend, lines):
        consecutive_errors = 0
        for request in batch:
            if stop():
                return 'operator_stop'
            entry, refused = await send(request, resend)
            if entry['attempts']:
                lines[request['request_id']] = entry
            if refused:
                return 'spend_guard'
            consecutive_errors = consecutive_errors + 1 if entry['status'] == 'error' else 0
            if consecutive_errors >= CONSECUTIVE_ERROR_ABORT:
                return 'consecutive_errors'
            if consecutive_errors:
                wait = backoff[min(consecutive_errors, len(backoff)) - 1]
                manifest['backoff_waits'].append({'after_request': request['request_id'], 'seconds': wait,
                                                  'consecutive_errors': consecutive_errors, 'resend': resend})
                recorder.save()
                await pause(wait)
        return 'completed'

    main = {}
    reason = await run_pass(requests, False, main)
    if reason != 'completed':
        return reason
    eligible = [request for request in requests if resend_eligible(main.get(request['request_id']))]
    manifest['resend_pass'] = {'eligible': len(eligible), 'request_ids': [r['request_id'] for r in eligible],
                               'ended': None}
    recorder.save()
    resent = {}
    ended = await run_pass(eligible, True, resent) if eligible else 'nothing_to_resend'
    manifest['resend_pass'].update(ended=ended, sent=len(resent),
                                   received=sum(1 for e in resent.values() if e['status'] in RECEIVED))
    recorder.save()
    return 'completed'


def load_results(path):
    """Saved responses. Only a trailing line cut off by a hard kill is skipped, and it is counted."""
    lines = pathlib.Path(path).read_text(encoding='utf-8').split('\n')
    results, partial = [], 0
    for index, line in enumerate(lines):
        if not line.strip():
            continue
        try:
            results.append(json.loads(line))
        except ValueError:
            if index == len(lines) - 1:
                partial += 1
                continue
            raise PlanningError(f'responses.jsonl line {index + 1} is not valid JSON') from None
    return results, partial


def load_run(directory):
    directory = pathlib.Path(directory)
    try:
        plan = json.loads((directory / 'plan.json').read_text())
        results, partial = load_results(directory / 'responses.jsonl')
    except PlanningError:
        raise
    except (OSError, ValueError) as error:
        raise PlanningError(f'The run in {directory} cannot be read ({type(error).__name__}); a run that stopped '
                            'before writing plan.json or responses.jsonl has no read-outs') from None
    return plan, results, partial


NOT_THE_RUNS_HARNESS = "NOT THE RUN'S HARNESS OR PLAN: a recomputation, not the declared read-out"


def recompute_readouts(directory, *, allow_other_harness=False):
    """The read-outs of a run that has ended. Review round 3: refuses while the run's manifest is not final
    (STARTING or RUNNING), with or without --not-the-runs-harness, so nothing states which arm is ahead while
    the run is live. A run whose process died is closed first with --finalize-abandoned."""
    directory = pathlib.Path(directory)
    try:
        manifest = json.loads((directory / MANIFEST_NAME).read_text())
    except (OSError, ValueError):
        raise PlanningError(f'No readable {MANIFEST_NAME} in {directory}; read-outs are tied to a run') from None
    if not isinstance(manifest, dict) or not _final(manifest):
        status = manifest.get('status') if isinstance(manifest, dict) else None
        raise PlanningError(f'The run in {directory} has not ended (manifest status {status}); --readouts refuses '
                            'until its manifest is final. If its process died, close its claim at $0 with '
                            '--finalize-abandoned first')
    plan, results, partial = load_run(directory)
    readouts = compute_readouts(plan['requests'], results, partial_lines_skipped=partial,
                                run_end=run_end_of(manifest))
    harness_matches = isinstance(manifest, dict) and sha256_file(__file__) == manifest.get('harness_sha256')
    plan_matches = isinstance(manifest, dict) and plan_hash(plan) == manifest.get('plan_hash')
    if harness_matches and plan_matches:
        return readouts
    if not allow_other_harness:
        raise PlanningError(f'{NOT_THE_RUNS_HARNESS} (harness matches the run: {harness_matches}; plan matches the '
                            f'run: {plan_matches}). Pass --not-the-runs-harness to print it labelled')
    return {'label': NOT_THE_RUNS_HARNESS, 'harness_matches_run': harness_matches, 'plan_matches_run': plan_matches,
            'readouts': readouts}


def run_live(args, plan, prompts, *, sleep=asyncio.sleep, status=None):
    out = check_output(args.out)
    check_other_paid_runs(args, status=status)
    harness = sha256_file(__file__)
    if args.expect_harness_sha256 != harness:
        raise PlanningError('--expect-harness-sha256 does not match this script')
    if not PROTOCOL.exists():
        raise PlanningError('No protocol at docs/part2/PHASE25_EXPERIMENT.md; live execution refuses until one is reviewed')
    protocol_sha256 = sha256_file(PROTOCOL)
    if args.expect_protocol_sha256 != protocol_sha256:
        raise PlanningError('--expect-protocol-sha256 does not match the protocol file')
    if args.expect_plan_hash != plan_hash(plan):
        raise PlanningError('The recomputed plan differs from the reviewed dry plan (--expect-plan-hash)')
    protocol_text = PROTOCOL.read_text()
    if harness not in protocol_text or plan_hash(plan) not in protocol_text:
        raise PlanningError('The protocol does not declare this harness sha256 and this plan hash')
    check_review(protocol_text, protocol_sha256, harness, plan_hash(plan))
    for request in plan['requests']:
        prompt = prompts.get(request['messages_hash'])
        if (prompt is None or content_hash(prompt['messages']) != request['messages_hash']
                or request_digest(request_body(prompt['messages'], request['temperature'])) != request['request_hash']):
            raise PlanningError(f'{request["request_id"]} has no verified prompt matching the plan; nothing may be sent')
    artifacts = (_root() / 'artifacts').resolve()
    earlier = earlier_live_runs(artifacts)
    spend_cap = effective_spend_cap(args.spend_cap, earlier)
    check_budget(plan['counts']['total_requests'], spend_cap)
    guard = SpendGuard(spend_cap)
    # The only credential read, after every offline check: the runtime's own loader.
    settings = settings_from_file(ROOT / DECLARED_SETTINGS, env_path=None)
    settings.require_wandb(require_model=True)
    if not args.confirm_entity or args.confirm_entity != settings.wandb_entity:
        raise PlanningError('--confirm-entity must match WANDB_ENTITY in the settings file')
    if settings.project_path != EXPECTED_PROJECT:
        raise PlanningError('Settings project is not the declared one')
    pins = configuration_pins(settings)
    check_pins(pins)
    if settings.model_for_role('mechanic') != EXPECTED_MECHANIC_MODEL:
        raise PlanningError('The Mechanic role does not resolve to the declared model')
    backend_state = check_other_paid_runs(args, status=status)
    stop_requested = False
    recorder = None
    # Review round 2: where the first stop signal arrived. The handler only reads the manifest (it may run in
    # the middle of a save); the record is copied into the manifest before its final save. Review round 3: the
    # handler cannot tell who sent the signal, so any SIGINT or SIGTERM (the operator's, an OS restart's or a
    # launching tool's) is recorded and counts as an operator stop: no round-1 fallback after it.
    signal_state = {'manifest': None, 'first': None, 'count': 0}

    def request_stop(signum=None, _frame=None):
        nonlocal stop_requested
        stop_requested = True
        signal_state['count'] += 1
        running = signal_state['manifest'] or {}
        if signal_state['first'] is None:
            in_flight = running.get('in_flight_request')
            signal_state['first'] = {
                'signal': signal.Signals(signum).name if signum in tuple(signal.Signals) else str(signum),
                'received_at': datetime.now(timezone.utc).isoformat(),
                'status_at_arrival': running.get('status'),
                'in_flight_request': dict(in_flight) if isinstance(in_flight, dict) else None,
                'last_request': dict(running['last_request']) if isinstance(running.get('last_request'), dict) else None,
                'requests_done_at_arrival': running.get('requests_done'),
                'resend_lines_at_arrival': running.get('resend_lines')}

    async def execute():
        from app.providers.runtime import RuntimeProvider
        sender = RequestSender()
        async with RuntimeProvider(settings, live_authorized=True, client_factory=sender) as provider:
            return await run_requests(plan['requests'], prompts, provider, guard, recorder, sender=sender,
                                      stop=lambda: stop_requested, sleep=sleep)

    previous = {sig: signal.signal(sig, request_stop) for sig in (signal.SIGINT, signal.SIGTERM)}
    try:
        if stop_requested:
            raise PlanningError('An operator stop arrived before the claim; nothing was claimed or sent')
        claim, earlier = take_claim(out, plan_hash(plan), harness, spend_cap=spend_cap, expected_earlier=earlier)
        out.mkdir(parents=True, exist_ok=False)
        manifest = {'schema_version': SCHEMA, 'mode': 'live', 'status': 'STARTING', 'pid': os.getpid(),
                    'plan_hash': plan_hash(plan), 'harness_sha256': harness, 'protocol_sha256': protocol_sha256,
                    'configuration_hash': pins['configuration_hash'], 'settings_sha256': DECLARED_SETTINGS_SHA256,
                    'mechanic_model': pins['mechanic_model'], 'spend_cap': spend_cap,
                    'spend_cap_requested': args.spend_cap, 'phase_spend_cap': HARD_SPEND_CAP,
                    'earlier_undelivered_charged': round(HARD_SPEND_CAP - phase_spend_remaining(earlier), 6),
                    'per_request_dollar_bound': PER_REQUEST_DOLLAR_BOUND,
                    'claim': str(claim.relative_to(artifacts.parent)), 'earlier_undelivered_runs': earlier,
                    'backend_state_at_launch': backend_state,
                    'ignored_manifests': list(getattr(args, 'ignore_manifest', None) or ()),
                    'requests_planned': plan['counts']['total_requests'], 'requests_done': 0, 'resend_lines': 0,
                    'attempts': 0, 'charged_upper_bound': 0.0, 'statuses': {}, 'generations_delivered': 0,
                    'measured_input_tokens': 0, 'measured_output_tokens': 0, 'backoff_waits': [], 'resend_pass': None,
                    'in_flight_request': None, 'last_request': None, 'stop_signal': None, 'stop_signals_received': 0,
                    'stop_reason': None, 'traceback': None,
                    'started_at': datetime.now(timezone.utc).isoformat(), 'ended_at': None}
        signal_state['manifest'] = manifest
        recorder = Recorder(out, manifest, secrets=(settings.wandb_api_key, settings.typesafe_api_key))
        try:
            recorder.save()
            # The last offline check, after the claim exists: a sibling runner that passed its own guard
            # before this claim was visible is caught here, and this run ends at $0 (nothing was sent).
            late, _ = other_paid_runs(ignore=getattr(args, 'ignore_manifest', None) or (), status=status)
            if late:
                manifest.update(status='ABORTED', stop_reason=OTHER_RUN_AFTER_CLAIM, blockers_after_claim=late)
            else:
                write_json(out / 'plan.json', plan)
                with (out / 'prompts.jsonl').open('w', encoding='utf-8') as handle:
                    for messages_hash in sorted(prompts):
                        handle.write(json.dumps(prompts[messages_hash], sort_keys=True, ensure_ascii=False) + '\n')
                manifest['status'] = 'RUNNING'
                recorder.save()
                manifest['stop_reason'] = asyncio.run(execute())
                manifest['status'] = 'COMPLETED' if manifest['stop_reason'] == 'completed' else 'STOPPED'
        except Exception as error:  # noqa: BLE001 - recorded with its traceback, never silently dropped
            manifest.update(status='ABORTED', stop_reason=f'{type(error).__name__}',
                            traceback=recorder.scrub(traceback.format_exc()[-8000:]))
        finally:
            manifest['stop_signal'] = signal_state['first']
            manifest['stop_signals_received'] = signal_state['count']
            manifest['ended_at'] = datetime.now(timezone.utc).isoformat()
            recorder.save()
            recorder.close()
    finally:
        for sig, handler in previous.items():
            signal.signal(sig, handler)
    summary = {'status': manifest['status'], 'stop_reason': manifest['stop_reason'],
               'requests_done': manifest['requests_done'], 'attempts': manifest['attempts'],
               'generations_delivered': manifest['generations_delivered'],
               'charged_upper_bound': manifest['charged_upper_bound'], 'output': str(out)}
    if manifest['stop_reason'] == OTHER_RUN_AFTER_CLAIM:
        summary['blockers_after_claim'] = manifest['blockers_after_claim']
        print(json.dumps(summary, indent=2))
        return 1
    try:
        results, partial = load_results(out / 'responses.jsonl')
        # From the saved final manifest, exactly as --readouts will read it.
        saved = json.loads((out / MANIFEST_NAME).read_text())
        readouts = compute_readouts(plan['requests'], results, partial_lines_skipped=partial,
                                    run_end=run_end_of(saved))
    except Exception as error:  # noqa: BLE001 - the run is already final; --readouts can recompute at $0
        summary['readouts_error'] = type(error).__name__
        print(json.dumps(summary, indent=2))
        return 1
    write_json(out / 'readouts.json', readouts)
    summary.update(decisions={arm: readouts['decisions'][arm]['declared'] for arm in readouts['decisions']},
                   mechanism=readouts['mechanism']['declared'])
    print(json.dumps(summary, indent=2))
    return 0 if manifest['status'] == 'COMPLETED' else 1


# ---------------------------------------------------------------- statistics and read-outs (pure)

def wilson(k, n, z=1.959963984540054):
    if n == 0:
        return [None, None]
    p = k / n
    denominator = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denominator
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denominator
    return [max(0.0, centre - half), min(1.0, centre + half)]


def newcombe(k1, n1, k2, n2):
    """Newcombe's hybrid score interval (method 10) for p1 - p2, from the two Wilson intervals."""
    if not n1 or not n2:
        return [None, None]
    p1, p2 = k1 / n1, k2 / n2
    (l1, u1), (l2, u2) = wilson(k1, n1), wilson(k2, n2)
    d = p1 - p2
    return [max(-1.0, d - math.sqrt((p1 - l1) ** 2 + (u2 - p2) ** 2)),
            min(1.0, d + math.sqrt((u1 - p1) ** 2 + (p2 - l2) ** 2))]


def sign_test_greater(positive, negative):
    """Exact one-sided sign test: P(X >= positive), X ~ Binomial(positive + negative, 1/2)."""
    if positive < 0 or negative < 0:
        raise ValueError('invalid counts')
    n = positive + negative
    if n == 0:
        return 1.0
    return sum(math.comb(n, x) for x in range(positive, n + 1)) / 2 ** n


def _ratio(k, n):
    return None if not n else k / n


def classify_results(requests, results):
    """One row per planned request: its classification recomputed from the saved raw text. A request can
    have a main-pass line and a re-send line; the received one is used, else the last one."""
    lines = defaultdict(list)
    for result in results:
        if isinstance(result, dict) and result.get('request_id'):
            lines[result['request_id']].append(result)
    rows = []
    for request in requests:
        found = lines.get(request['request_id'], [])
        received = [line for line in found if line.get('status') in RECEIVED]
        result = received[0] if received else (found[-1] if found else None)
        status = result.get('status') if result else None
        if status == 'ok':
            classified = classify_response(result.get('raw'), request['reference'])
        elif status == 'empty_response':
            classified = classify_response('', request['reference'])
        else:
            classified = None
        attempts = [a for line in found for a in (line.get('attempts') or []) if isinstance(a, dict)]
        rows.append({'request': request, 'result': result, 'received': status in RECEIVED, 'c': classified,
                     'lines': len(found), 'resent': any(line.get('resend') for line in found),
                     'received_on_resend': bool(received) and bool(result.get('resend')),
                     'received_on_blind_retry': bool(received) and len(result.get('attempts') or []) == 2,
                     'timeouts': sum(1 for a in attempts if a.get('code') == 'REQUEST_TIMEOUT')})
    return rows


def _reference(row):
    return row['request'].get('reference') or {}


def arm_summary(rows):
    """Counts over one arm's planned draws."""
    planned = len(rows)
    received = [r for r in rows if r['received']]
    classes = Counter(r['c']['class'] for r in received)
    distinct = [r for r in received if r['c']['distinct']]
    audits = [r['c']['audit'] for r in received if r['c']['audit']]
    distinct_audits = [r['c']['audit'] for r in distinct]
    count = lambda pred: sum(1 for r in received if pred(r['c']))  # noqa: E731
    n = len(received)
    out = {'planned': planned, 'received': n, 'missing': planned - n, 'classes': dict(sorted(classes.items())),
           'distinct': len(distinct), 'duplicate': count(lambda c: c['duplicate_of_slot1']),
           'byte_identical_to_slot1': count(lambda c: c['byte_identical_to_slot1']),
           'rules_text_identical_to_slot1': count(lambda c: c['rules_text_identical_to_slot1']),
           'invalid': classes.get('INVALID', 0) + classes.get('STALE_PARENT', 0),
           'no_change': classes.get('NO_CHANGE', 0),
           'distinct_firing': count(lambda c: c['distinct_firing']),
           'distinct_firing_harmful': count(lambda c: c['distinct_firing'] and c['audit']['harmful']),
           'working': count(lambda c: c['working']),
           'working_on_prompts_whose_slot1_policy_fires': sum(
               1 for r in received if r['c']['working'] and _reference(r).get('slot1_step_fires')),
           'step_present_in_distinct': sum(a['step_present'] for a in distinct_audits),
           'dead_step_in_distinct': sum(a['dead_step'] for a in distinct_audits),
           'harmful_in_distinct': sum(a['harmful'] for a in distinct_audits),
           'flags_in_candidates': {flag: sum(bool(a[flag]) for a in audits) for flag in (
               'step_present', 'step_fires', 'dead_step', 'premature_defer', 'stops_first_confirmation',
               'harmful', 'orders_retry')},
           'distinct_policies': len({r['c']['policy_hash'] for r in distinct}),
           'working_policies': len({r['c']['policy_hash'] for r in received if r['c']['working']}),
           # Descriptive: how each arm's draws arrived (safety review, round 1).
           'received_on_blind_retry': sum(1 for r in received if r.get('received_on_blind_retry')),
           'received_on_resend': sum(1 for r in received if r.get('received_on_resend')),
           'resent_requests': sum(1 for r in rows if r.get('resent')),
           'timeouts': sum(r.get('timeouts', 0) for r in rows),
           'missing_after_all_attempts': sum(1 for r in rows if not r['received'] and r.get('lines')),
           'never_attempted': sum(1 for r in rows if not r['received'] and not r.get('lines'))}
    for key in ('distinct', 'duplicate', 'byte_identical_to_slot1', 'rules_text_identical_to_slot1', 'invalid',
                'no_change', 'distinct_firing', 'working'):
        out[f'{key}_rate_received'] = _ratio(out[key], n)
        out[f'{key}_wilson95_received'] = wilson(out[key], n)
    out['harmful_share_of_distinct'] = _ratio(out['harmful_in_distinct'], len(distinct))
    out['complete'] = planned > 0 and Fraction(n, planned) >= COMPLETE_MIN
    return out


def per_prompt_means(rows, key):
    """Per prompt, the mean of a boolean over its received draws."""
    groups = defaultdict(list)
    for r in rows:
        if r['received']:
            groups[r['request']['prompt_id']].append(bool(r['c'][key]))
    return {p: Fraction(sum(v), len(v)) for p, v in groups.items() if v}


def paired_sign(x_rows, c_rows, key, *, greater='x'):
    """Exact one-sided sign test over prompts on the per-prompt mean of `key`: X above C (greater='x') or
    C above X (greater='c'). Ties and prompts without draws in both arms are dropped."""
    x, c = per_prompt_means(x_rows, key), per_prompt_means(c_rows, key)
    both = sorted(set(x) & set(c))
    plus = sum(1 for p in both if (x[p] > c[p] if greater == 'x' else c[p] > x[p]))
    minus = sum(1 for p in both if (x[p] < c[p] if greater == 'x' else c[p] < x[p]))
    return {'prompts_compared': len(both), 'favouring': plus, 'against': minus, 'ties': len(both) - plus - minus,
            'p_one_sided': sign_test_greater(plus, minus)}


def clustered_sign(x_rows, c_rows, key, *, greater='x'):
    """Descriptive: the same sign test after averaging the per-prompt means within prompts that share a
    slot-1 policy (their slot-2 prompts carry the same prior candidate), so each cluster counts once."""
    x, c = per_prompt_means(x_rows, key), per_prompt_means(c_rows, key)
    cluster = {r['request']['prompt_id']: _reference(r).get('slot1_policy_hash') or r['request']['prompt_id']
               for r in list(x_rows) + list(c_rows)}
    groups = defaultdict(list)
    for p in set(x) & set(c):
        groups[cluster[p]].append(p)
    plus = minus = 0
    for prompts in groups.values():
        mx = sum(x[p] for p in prompts) / len(prompts)
        mc = sum(c[p] for p in prompts) / len(prompts)
        plus += (mx > mc) if greater == 'x' else (mc > mx)
        minus += (mx < mc) if greater == 'x' else (mc < mx)
    return {'clusters_compared': len(groups), 'favouring': plus, 'against': minus,
            'ties': len(groups) - plus - minus, 'p_one_sided': sign_test_greater(plus, minus)}


def gain_label(value):
    """A threshold as it appears in a condition name, in the style of the other names (two decimals)."""
    return f'{float(value):.2f}'


def working_share(x_rows, c_rows):
    """Condition 5 (review round 2), over the prompts whose slot-1 policy's step does not already fire: the sum
    over those prompts of X's WORKING share of its planned draws minus C's WORKING-or-missing share of its
    planned draws. Worst case for X: a missing X draw is not WORKING, a missing C draw is. Each prompt adds
    between -1 and +1, and at equal per-draw WORKING rates the expectation is 0 however the draws cluster
    within a prompt, so the gain measures per-draw yield. The round-1 prompt count (at least one WORKING draw)
    is reported beside it as breadth, descriptive only: at equal per-draw rates it favours the arm whose draws
    vary more within a prompt."""
    eligible = {r['request']['prompt_id'] for r in list(x_rows) + list(c_rows) if not _reference(r).get('slot1_step_fires')}
    x_planned, x_working, c_planned, c_working = Counter(), Counter(), Counter(), Counter()
    for r in x_rows:
        prompt = r['request']['prompt_id']
        x_planned[prompt] += 1
        x_working[prompt] += bool(r['received'] and r['c']['working'])
    for r in c_rows:
        prompt = r['request']['prompt_id']
        c_planned[prompt] += 1
        c_working[prompt] += bool(not r['received'] or r['c']['working'])
    shares = {p: (Fraction(x_working[p], x_planned[p]) if x_planned[p] else Fraction(0))
              - (Fraction(c_working[p], c_planned[p]) if c_planned[p] else Fraction(1)) for p in eligible}
    gain = sum(shares.values(), Fraction(0))
    favouring = sum(1 for v in shares.values() if v > 0)
    against = sum(1 for v in shares.values() if v < 0)
    x_has = {p for p in eligible if x_working[p]}
    c_has = {p for p in eligible if c_working[p] or not c_planned[p]}
    breadth_favouring, breadth_against = len(x_has - c_has), len(c_has - x_has)
    return {'eligible_prompts': len(eligible), 'gain': float(gain), 'gain_exact': str(gain),
            'working_draws_X_on_eligible': sum(x_working[p] for p in eligible),
            'working_or_missing_draws_C_on_eligible': sum(c_working[p] for p in eligible),
            'prompts_favouring': favouring, 'prompts_against': against,
            'sign_test_p_one_sided_descriptive': sign_test_greater(favouring, against),
            'breadth_prompt_count_descriptive': {
                'note': ('round 1\'s count: prompts where X has a WORKING draw and C has no WORKING-or-missing draw, '
                         'minus the reverse. It measures breadth, not per-draw yield, and decides nothing'),
                'prompts_with_working_X': len(x_has), 'prompts_with_working_or_missing_C': len(c_has),
                'favouring': breadth_favouring, 'against': breadth_against,
                'gain': breadth_favouring - breadth_against}}


def contrast(x_rows, c_rows, arm, *, working_gain_min=WORKING_SHARE_GAIN_MIN):
    x, c = arm_summary(x_rows), arm_summary(c_rows)
    planned_x, planned_c = x['planned'], c['planned']
    d_x = Fraction(x['distinct'], planned_x) if planned_x else Fraction(0)
    d_c = Fraction(c['distinct'] + c['missing'], planned_c) if planned_c else Fraction(1)
    w_x = Fraction(x['working'], planned_x) if planned_x else Fraction(0)
    w_c = Fraction(c['working'] + c['missing'], planned_c) if planned_c else Fraction(1)
    inv_x = Fraction(x['invalid'], x['received']) if x['received'] else Fraction(1)
    inv_c = Fraction(c['invalid'], c['received']) if c['received'] else Fraction(0)
    harm_x = Fraction(x['harmful_in_distinct'], planned_x) if planned_x else Fraction(1)
    harm_c = Fraction(c['harmful_in_distinct'], planned_c) if planned_c else Fraction(0)
    firing_harm = (Fraction(x['distinct_firing_harmful'], x['distinct_firing']) if x['distinct_firing']
                   else Fraction(0))
    sign = paired_sign(x_rows, c_rows, 'distinct', greater='x')
    working = working_share(x_rows, c_rows)
    conditions = {
        'complete': x['complete'] and c['complete'],
        'distinct_at_least_0.70': d_x >= DISTINCT_MIN,
        'distinct_gain_at_least_0.30': d_x - d_c >= DISTINCT_GAIN_MIN,
        'sign_test_p_below_0.05': sign['p_one_sided'] < SIGN_ALPHA,
        f'working_share_gain_at_least_{gain_label(working_gain_min)}': (
            Fraction(working['gain_exact']) >= Fraction(working_gain_min)),
        'invalid_at_most_C_plus_0.10': inv_x - inv_c <= INVALID_MARGIN,
        'harmful_share_of_firing_at_most_0.50': firing_harm <= HARMFUL_FIRING_SHARE_MAX,
    }
    if not conditions['complete']:
        decision = 'INCOMPLETE'
    elif all(conditions.values()):
        decision = 'RECOMMEND_FOR_A_LATER_LOOP'
    else:
        decision = 'NOT_RECOMMENDED'
    return {'arm': arm, 'decision': decision, 'failed': [k for k, v in conditions.items() if not v],
            'conditions': conditions, 'planned_draws': {'X': planned_x, 'C': planned_c},
            'working_share_gain_min': str(Fraction(working_gain_min)),
            'worst_case': {'D_X': float(d_x), 'D_C': float(d_c), 'D_gain': float(d_x - d_c),
                           'W_X_descriptive': float(w_x), 'W_C_descriptive': float(w_c),
                           'W_gain_descriptive': float(w_x - w_c),
                           'harmful_per_draw_X_descriptive': float(harm_x),
                           'harmful_per_draw_C_descriptive': float(harm_c),
                           'harmful_per_draw_gain_descriptive': float(harm_x - harm_c)},
            'working_share': working,
            'received': {'distinct_X': [x['distinct'], x['received']], 'distinct_C': [c['distinct'], c['received']],
                         'distinct_difference_newcombe95': newcombe(x['distinct'], x['received'], c['distinct'], c['received']),
                         'working_X': [x['working'], x['received']], 'working_C': [c['working'], c['received']],
                         'working_difference_newcombe95': newcombe(x['working'], x['received'], c['working'], c['received']),
                         'distinct_firing_X': [x['distinct_firing'], x['received']],
                         'distinct_firing_harmful_X': x['distinct_firing_harmful'],
                         'harmful_share_of_firing_X': float(firing_harm),
                         'invalid_X': float(inv_x), 'invalid_C': float(inv_c),
                         'harmful_share_of_distinct_X_descriptive': x['harmful_share_of_distinct']},
            'sign_test_distinct': sign,
            'sign_test_distinct_clustered_by_slot1_policy_descriptive': clustered_sign(x_rows, c_rows, 'distinct'),
            'sign_test_working_draws_descriptive': paired_sign(x_rows, c_rows, 'working', greater='x')}


def mechanism_readout(c_rows, h_rows, t_rows, n_rows):
    c, h = arm_summary(c_rows), arm_summary(h_rows)
    rate = lambda k, s: Fraction(k, s['received']) if s['received'] else None  # noqa: E731
    dup_c, dup_h = rate(c['duplicate'], c), rate(h['duplicate'], h)
    dist_c, dist_h = rate(c['distinct'], c), rate(h['distinct'], h)
    other_c, other_h = rate(c['invalid'] + c['no_change'], c), rate(h['invalid'] + h['no_change'], h)
    measured = None not in (dup_c, dup_h)
    sign = paired_sign(h_rows, c_rows, 'duplicate_of_slot1', greater='c')
    conditions = {
        'complete': c['complete'] and h['complete'],
        'duplicate_drop_at_least_0.30': measured and dup_c - dup_h >= MECHANISM_GAIN_MIN,
        'sign_test_p_below_0.05': sign['p_one_sided'] < SIGN_ALPHA,
        # The drop in duplicates must come back as distinct policies, not as outputs that are no policy.
        'distinct_gain_at_least_0.30': measured and dist_h - dist_c >= MECHANISM_DISTINCT_GAIN_MIN,
        'non_candidate_at_most_C_plus_0.10': measured and other_h - other_c <= MECHANISM_NONCANDIDATE_MARGIN,
    }
    if not conditions['complete']:
        decision = 'INCOMPLETE'
    elif all(conditions.values()):
        decision = 'COPYING_OF_THE_PRIOR_TEXT_SHOWN'
    else:
        decision = 'NOT_SHOWN'
    t, n = arm_summary(t_rows), arm_summary(n_rows)
    as_float = lambda value: None if value is None else float(value)  # noqa: E731
    return {'decision': decision, 'failed': [k for k, v in conditions.items() if not v], 'conditions': conditions,
            'planned_draws': {'C': c['planned'], 'H': h['planned']},
            'duplicate_rate_C': as_float(dup_c), 'duplicate_rate_H': as_float(dup_h),
            'distinct_rate_C': as_float(dist_c), 'distinct_rate_H': as_float(dist_h),
            'non_candidate_rate_C': as_float(other_c), 'non_candidate_rate_H': as_float(other_h),
            'duplicate_difference_C_minus_H_newcombe95': newcombe(c['duplicate'], c['received'], h['duplicate'], h['received']),
            'sign_test_C_more_duplicates_than_H': sign,
            'duplicate_rate_T_descriptive': t['duplicate_rate_received'],
            'sign_test_C_more_duplicates_than_T_descriptive': paired_sign(t_rows, c_rows, 'duplicate_of_slot1', greater='c'),
            'N_writes_slot1_policy': [n['duplicate'], n['received']],
            'N_writes_slot1_policy_wilson95': wilson(n['duplicate'], n['received']),
            'N_distinct': [n['distinct'], n['received']], 'N_working': [n['working'], n['received']],
            'note': ('N is the evidence-alone reference: the slot-2 request with no prior candidate in view (candidate_'
                     'history empty), temperature 0, one draw per prompt. Its rate of writing slot 1\'s policy is how '
                     'often the evidence alone leads back to that policy. Descriptive; it decides nothing')}


def determinism_readout(rows_by_arm):
    """Temperature-0 repeats within one run (C and H), and C against the historical output of the same
    stored request. H, T and N have no historical output of their own, so none is compared."""
    out = {}
    for arm, rows in rows_by_arm.items():
        groups = defaultdict(list)
        for r in rows:
            if r['received']:
                groups[r['request']['prompt_id']].append(r)
        pairs = identical_pairs = policy_pairs = 0
        all_identical = 0
        for draws in groups.values():
            raws = [d['result'].get('raw') for d in draws]
            hashes = [d['c']['policy_hash'] for d in draws]
            for i in range(len(draws)):
                for j in range(i + 1, len(draws)):
                    pairs += 1
                    identical_pairs += raws[i] == raws[j]
                    policy_pairs += hashes[i] is not None and hashes[i] == hashes[j]
            all_identical += len(draws) > 1 and len(set(raws)) == 1
        out[arm] = {'repeat_pairs': pairs, 'byte_identical_pairs': identical_pairs, 'same_policy_pairs': policy_pairs,
                    'prompts_all_repeats_byte_identical': all_identical}
        if arm == 'C':
            received = [r for r in rows if r['received']]
            out[arm]['byte_identical_to_historical_output'] = [sum(
                1 for r in received if sha256_text(r['result'].get('raw')) == _reference(r).get('historical_raw_sha256')),
                len(received)]
            out[arm]['same_policy_as_historical_output'] = [sum(
                1 for r in received if r['c']['policy_hash'] is not None
                and r['c']['policy_hash'] == _reference(r).get('historical_policy_hash')), len(received)]
    return out


def _round1(rows):
    return [r for r in rows if r['request'].get('repeat', 0) == 0]


def _declared(full, fallback):
    chosen = fallback if fallback is not None else full
    return {'decision': chosen['decision'], 'basis': 'round_1_only' if fallback is not None else 'all_rounds',
            'failed': chosen['failed']}


# Review round 2: the round-1 fallback applies only after a stop the operator does not choose. An operator stop
# (SIGINT or SIGTERM, recorded as stop_signal, whoever sent it: review round 3), a stop of the re-send pass by
# the operator, and a process that died with no final manifest (kill -9 then --finalize-abandoned, recorded as
# 'abandoned') leave an INCOMPLETE decision INCOMPLETE, so stopping once round 1 has arrived can never choose
# which rule decides.
FALLBACK_STOP_REASONS = ('completed', 'spend_guard', 'consecutive_errors')


def run_end_of(manifest):
    """The facts about how a run ended that decide whether the round-1 fallback may apply (JSON values only, so
    a recomputation from the saved manifest equals the one made at the end of the run)."""
    if not isinstance(manifest, dict):
        return None
    resend = manifest.get('resend_pass')
    signal_record = manifest.get('stop_signal')
    return {'status': manifest.get('status'), 'stop_reason': manifest.get('stop_reason'),
            'crashed_with_traceback': bool(manifest.get('traceback')),
            'stop_signal': signal_record if isinstance(signal_record, dict) else None,
            'resend_pass_ended': resend.get('ended') if isinstance(resend, dict) else None}


def fallback_permitted(run_end):
    """(permitted, reason): whether an INCOMPLETE all-rounds decision may fall back to round 1."""
    if not isinstance(run_end, dict):
        return False, 'no run end is recorded, so the stop cannot be shown not to be the operator\'s'
    if run_end.get('stop_signal') is not None:
        return False, 'an operator stop signal arrived during the run'
    if run_end.get('stop_reason') in ('operator_stop', 'abandoned') or run_end.get('resend_pass_ended') == 'operator_stop':
        return False, f'the run ended by an operator stop or with no final manifest ({run_end.get("stop_reason")})'
    if run_end.get('status') in ('COMPLETED', 'STOPPED') and run_end.get('stop_reason') in FALLBACK_STOP_REASONS:
        return True, f'a stop the operator does not choose ({run_end["stop_reason"]})'
    if run_end.get('status') == 'ABORTED' and run_end.get('crashed_with_traceback'):
        return True, f'a crash recorded with its traceback ({run_end.get("stop_reason")})'
    return False, f'the stop ({run_end.get("status")}/{run_end.get("stop_reason")}) is not one the operator cannot choose'


def compute_readouts(requests, results, *, partial_lines_skipped=0, run_end=None):
    rows = classify_results(requests, results)
    by_arm = defaultdict(list)
    for row in rows:
        by_arm[row['request']['arm']].append(row)
    summaries = {arm: arm_summary(by_arm[arm]) for arm in ALL_ARMS}
    permitted, why = fallback_permitted(run_end)
    decisions = {}
    for arm in ('T', 'H'):
        full = contrast(by_arm[arm], by_arm['C'], arm)
        # Declared before any data: only when the all-rounds decision is INCOMPLETE, and only after a stop the
        # operator does not choose, round 1 alone decides. The all-rounds contrast stays beside it.
        fallback = (contrast(_round1(by_arm[arm]), _round1(by_arm['C']), arm,
                             working_gain_min=WORKING_SHARE_GAIN_MIN_ROUND1)
                    if full['decision'] == 'INCOMPLETE' and permitted else None)
        decisions[arm] = {**full, 'round1_fallback': fallback, 'declared': _declared(full, fallback)}
    full = mechanism_readout(by_arm['C'], by_arm['H'], by_arm['T'], by_arm['N'])
    fallback = (mechanism_readout(_round1(by_arm['C']), _round1(by_arm['H']), _round1(by_arm['T']), by_arm['N'])
                if full['decision'] == 'INCOMPLETE' and permitted else None)
    mechanism = {**full, 'round1_fallback': fallback, 'declared': _declared(full, fallback)}
    served = Counter(r['result'].get('served_model') for r in rows if r['result'] and r['result'].get('status') == 'ok')
    label = lambda d: d['declared']['decision'] + (' (round 1 only)' if d['declared']['basis'] == 'round_1_only' else '')  # noqa: E731
    recommended = [arm for arm, d in decisions.items() if d['declared']['decision'] == 'RECOMMEND_FOR_A_LATER_LOOP']
    statement = (('recommended for a later loop\'s own declaration: '
                  + ', '.join(arm + (' (round 1 only)' if decisions[arm]['declared']['basis'] == 'round_1_only' else '')
                              for arm in recommended)) if recommended
                 else 'no arm is recommended: ' + '; '.join(
                     f'{arm} {label(d)} ({", ".join(d["declared"]["failed"]) or "-"})' for arm, d in decisions.items()))
    return {'schema_version': READOUT_SCHEMA, 'requests_planned': len(requests),
            'requests_received': sum(r['received'] for r in rows),
            'partial_lines_skipped': partial_lines_skipped,
            'run_end': {**(run_end or {}), 'round1_fallback_permitted': permitted, 'reason': why},
            'arms': summaries, 'decisions': decisions, 'mechanism': mechanism,
            'determinism': determinism_readout({arm: by_arm[arm] for arm in ('C', 'H')}),
            'provider': {'served_model': dict(served),
                         'measured_input_tokens': sum((r['result'] or {}).get('input_tokens') or 0 for r in rows),
                         'measured_output_tokens': sum((r['result'] or {}).get('output_tokens') or 0 for r in rows)},
            'statement': statement, 'mechanism_statement': label(mechanism)}


# The simulation model's harm rates come from the store (the 35 distinct v4-era policies, audited at $0):
# 3 of the 9 whose step fires are harmful, 1 of the 26 whose step does not. 2 of the 26 census prompts have
# a slot-1 policy whose step fires.
SIM_HARMFUL_FIRING = Fraction(3, 9)
SIM_HARMFUL_NOT_FIRING = Fraction(1, 26)
SIM_SLOT1_FIRING_PROMPTS = 2
SIM_INVALID = 0.03


def simulated_draw(rng, prompt, repeat, *, distinct_p, firing_p, invalid=SIM_INVALID):
    """One simulated draw row: INVALID with probability `invalid`; otherwise DISTINCT with probability
    distinct_p; a DISTINCT draw fires with probability firing_p; a firing draw is harmful with probability
    3/9, a distinct non-firing draw with 1/26 (the store's rates); the rest duplicate slot 1."""
    is_invalid = rng.random() < invalid
    distinct = not is_invalid and rng.random() < distinct_p
    firing = distinct and rng.random() < firing_p
    harmful = distinct and rng.random() < float(SIM_HARMFUL_FIRING if firing else SIM_HARMFUL_NOT_FIRING)
    audit = None if is_invalid else {'harmful': harmful, 'step_present': firing, 'dead_step': False,
                                     'step_fires': firing, 'premature_defer': harmful,
                                     'stops_first_confirmation': False, 'orders_retry': False}
    c = {'class': 'INVALID' if is_invalid else 'CANDIDATE', 'distinct': distinct,
         'duplicate_of_slot1': not is_invalid and not distinct, 'distinct_firing': firing,
         'working': firing and not harmful, 'policy_hash': None, 'byte_identical_to_slot1': False,
         'rules_text_identical_to_slot1': False, 'audit': audit}
    reference = {'slot1_step_fires': prompt < SIM_SLOT1_FIRING_PROMPTS, 'slot1_policy_hash': f'p{prompt}'}
    return {'request': {'prompt_id': f'p{prompt}', 'repeat': repeat, 'reference': reference}, 'result': {},
            'received': True, 'c': c}


def power_table(*, simulations=2000, seed=SAMPLE_SEED, prompts=26, repeats=SLOT2_REPEATS):
    """P(RECOMMEND) by simulation under a declared model: every draw independent; each arm DISTINCT at d and
    firing at w (rates over draws); 3% invalid in both; harm at the store's rates (3 of 9 firing policies,
    1 of 26 non-firing); 2 of 26 prompts with a slot-1 policy that fires; every draw received. Independence
    ignores clustering by prompt; slot2_protocol_numbers.py adds clustered and shared-effect models."""
    rng = random.Random(seed)
    valid = 1 - SIM_INVALID

    def draws(d, w):
        return [simulated_draw(rng, p, r, distinct_p=min(1.0, d / valid), firing_p=(w / d) if d else 0.0)
                for p in range(prompts) for r in range(repeats)]
    table = []
    for d_c, w_c in ((0.3, 0.04),):
        for d_x, w_x in ((0.3, 0.04), (0.8, 0.04), (0.5, 0.10), (0.6, 0.10), (0.7, 0.10), (0.8, 0.10), (0.8, 0.15),
                         (0.8, 0.25), (0.9, 0.10), (0.9, 0.25)):
            passed = sum(contrast(draws(d_x, w_x), draws(d_c, w_c), 'X')['decision'] == 'RECOMMEND_FOR_A_LATER_LOOP'
                         for _ in range(simulations))
            table.append({'d_c': d_c, 'w_c': w_c, 'd_x': d_x, 'w_x': w_x,
                          'p_recommend': round(passed / simulations, 3)})
    return {'model': power_table.__doc__.split('\n\n')[0].strip(), 'simulations': simulations,
            'working_share_gain_min': str(WORKING_SHARE_GAIN_MIN), 'table': table}


def dry_summary(plan, store_wide=None):
    return {'status': 'DRY_RUN', 'plan_hash': plan_hash(plan), 'harness_sha256': plan['harness_sha256'],
            'configuration_hash': plan['configuration_hash'], 'mechanic_model': plan['mechanic_model'],
            'populations': {k: plan['populations'][k] for k in ('by_phase', 'slot2_prompts', 'excluded_in_scope',
                                                                 'prompts_whose_slot1_policy_fires',
                                                                 'verification_failures')},
            # Store-wide counts are reported here only, never in the hashed plan, so a study added to the
            # store later (another configuration, or after the cutoff) cannot move the plan hash.
            'store_wide_outside_scope_not_hashed': store_wide,
            'verification': plan['verification'], 'precheck': plan['precheck'],
            'investigation': {'mechanism_totals': plan['investigation']['mechanism']['totals'],
                              'slot1_layout_identity': plan['investigation']['slot1_layout_identity'],
                              'framing_tokens_observed': plan['investigation']['mechanism']['framing_tokens_observed'],
                              'slot1_distinct_policies': plan['investigation']['mechanism']['slot1_distinct_policies'],
                              'slot1_cross_study_coincident_pairs':
                                  plan['investigation']['mechanism']['slot1_cross_study_coincident_pairs'],
                              'auditor_validation': {k: v for k, v in plan['investigation']['auditor_validation'].items()
                                                     if k != 'premature_defer_vs_terminal_rejection'},
                              'premature_defer_vs_terminal_rejection':
                                  plan['investigation']['auditor_validation']['premature_defer_vs_terminal_rejection']},
            'counts': plan['counts'], 'cost': plan['cost']}


def arguments(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--store', default=str(STORE), help='read-only lab store')
    parser.add_argument('--settings', default=DECLARED_SETTINGS, help='the declared non-secret settings file')
    parser.add_argument('--spend-cap', type=float, default=HARD_SPEND_CAP)
    parser.add_argument('--write-plan', help='new directory under artifacts/phase25-<date>/ for the dry plan')
    parser.add_argument('--power', action='store_true', help='with --write-plan: also write power.json ($0)')
    parser.add_argument('--readouts', help='recompute read-outs from a saved run directory ($0); refuses until the '
                        "run's manifest is final, and unless this harness and the saved plan are the run's own")
    parser.add_argument('--not-the-runs-harness', action='store_true',
                        help="with --readouts: print a mismatched recomputation, labelled as not the run's")
    parser.add_argument('--finalize-abandoned', metavar='CLAIM',
                        help='close at $0 a claimed run whose process died before its manifest was final')
    parser.add_argument('--out', help='new directory under artifacts/phase25-<date>/ for a live run')
    parser.add_argument('--expect-plan-hash')
    parser.add_argument('--expect-harness-sha256')
    parser.add_argument('--expect-protocol-sha256')
    parser.add_argument('--execute-live', action='store_true')
    parser.add_argument('--confirm-entity')
    parser.add_argument('--ignore-manifest', action='append', default=[],
                        help='a crashed run manifest or claim (exact path) known not to be running')
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = arguments(argv)
    try:
        if args.finalize_abandoned:
            path, manifest = finalize_abandoned(args.finalize_abandoned)
            delivered = manifest['generations_delivered']
            print(json.dumps({'status': 'FINALIZED', 'manifest': str(path), 'generations_delivered': delivered,
                              'charged_upper_bound': manifest['charged_upper_bound'],
                              'a_new_run_is_allowed': delivered == 0,
                              'note': 'add charged_upper_bound to the ledger; a new run needs a new --out'}, indent=2))
            return 0
        if args.readouts:
            print(json.dumps(recompute_readouts(args.readouts, allow_other_harness=args.not_the_runs_harness),
                             indent=2))
            return 0
        if args.execute_live and not (args.out and args.confirm_entity and args.expect_plan_hash
                                      and args.expect_harness_sha256 and args.expect_protocol_sha256):
            raise PlanningError('--execute-live needs --out, --confirm-entity, --expect-plan-hash, '
                                '--expect-harness-sha256 and --expect-protocol-sha256')
        if args.execute_live:
            check_output(args.out)
            check_other_paid_runs(args)
        if args.write_plan:
            check_output(args.write_plan, live=False)
        settings_path = pathlib.Path(args.settings)
        settings_path = settings_path if settings_path.is_absolute() else ROOT / settings_path
        plan, prompts = build_plan(store=args.store, settings_path=settings_path, spend_cap=args.spend_cap)
        if not args.execute_live:
            connection = connect(args.store)
            try:
                store_wide = store_outside_scope(connection)
            finally:
                connection.close()
            summary = dry_summary(plan, store_wide)
            if args.write_plan:
                directory = check_output(args.write_plan, live=False)
                directory.mkdir(parents=True, exist_ok=False)
                write_json(directory / 'plan.json', plan)
                write_json(directory / 'dry-summary.json', summary)
                write_json(directory / 'investigation.json', plan['investigation'])
                if args.power:
                    write_json(directory / 'power.json', power_table())
                summary['written'] = str(directory)
            print(json.dumps(summary, indent=2))
            print('Dry plan only. Pass --execute-live with --confirm-entity, --out and the reviewed hashes to send.')
            return 0
        return run_live(args, plan, prompts)
    except PlanningError as error:
        print(json.dumps({'status': 'REJECTED', 'error_type': type(error).__name__, 'message': str(error)}))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
