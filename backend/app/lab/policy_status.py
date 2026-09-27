"""Read-only display of development evidence, unseen-case checks and actual activation.

Qualification here is a conservative projection of saved public completion-study rows.
It neither promotes a policy nor changes any stored verdict. Held-out records are queried
only for the allowlisted identity/status fields; private cases and trials never enter the
response. A matching policy hash alone never transfers a check to another study.
"""
import json

from pydantic import ValidationError

from app.agents.progress import ACTOR_CONTEXT_PROTOCOL_V4
from app.contracts.models import PolicyVersion, TrialResult, canonical_json, content_hash
from app.lab.completion_study import (
    DEFAULT_CASE_MANIFEST, SCHEMA as COMPLETION_SCHEMA, assess_pairs,
    build_case_manifest, source_clause,
)
from app.lab.diagnosis import COMPACT_EVIDENCE_V2
from app.lab.reproduction import valid_trial
from app.lab.storage import StoreConflict

SCHEMA = 'faultlab-policy-status/v1'
CHECK_FIELDS = ('check_id', 'campaign_id', 'certified_study_id', 'policy_hash',
                'policy_version', 'status', 'decision', 'predicate')
CHECK_STATUSES = frozenset(('QUEUED', 'RUNNING', 'COMPLETED', 'INCOMPLETE', 'INTERRUPTED'))
CHECK_DECISIONS = frozenset(('PENDING', 'NO_HARM', 'HARM', 'INCOMPLETE'))
CHECK_PREDICATES = frozenset(('faultlab-heldout-no-harm/v1', 'faultlab-heldout-no-harm/v2'))


def _text(value):
    return value if isinstance(value, str) and value else None


def _identity(study):
    if study.get('replay_of') is not None:
        return _text(study.get('replay_of')), _text(study.get('replay_policy_hash'))
    return _text(study.get('selected_candidate_version')), _text(study.get('selected_candidate_hash'))


def _policy(store, version, expected_hash=None):
    raw = store.get_record('policies', version) if version else None
    if not raw:
        return None
    try:
        policy = PolicyVersion.model_validate_json(canonical_json(raw))
    except (ValidationError, TypeError):
        return None
    if (policy.version != version or content_hash(policy.content) != policy.policy_hash
            or (expected_hash is not None and policy.policy_hash != expected_hash)):
        return None
    return policy


def _result(status, reason):
    return {'status': status, 'reason': reason}


def _stage_rows(study, stage):
    selected = []
    for row in study['trial_rows']:
        if row.get('stage') == stage:
            selected.append({'case_id': row['case_id'], 'trial': TrialResult.model_validate(row['trial'])})
    return selected


def _rows_are_bound(study, rows, stages):
    """Bind source/validation rows to the saved execution slots and verified evidence."""
    slots = [s for s in study['slots'] if s.get('stage') in stages]
    by_episode = {s['episode_id']: s for s in slots}
    ids = [r['trial'].episode_id for r in rows]
    if (len(slots) != len(rows) or len(by_episode) != len(slots)
            or len(set(ids)) != len(ids) or set(ids) != set(by_episode)
            or len({r['trial'].world_id for r in rows}) != len(rows)):
        return False
    for row in rows:
        trial = row['trial']; slot = by_episode[trial.episode_id]
        if (slot.get('status') != 'COMPLETED' or slot.get('case_id') != row['case_id']
                or slot.get('trial_index') != trial.trial_index or slot.get('arm') != trial.arm
                or slot.get('scenario_hash') != trial.scenario_hash
                or slot.get('policy_hash') != trial.policy_hash
                or study['evidence'].get(trial.episode_id) != 'weave_verified'):
            return False
    return True


def development_status(store, study):
    """Stronger than OBSERVED_IMPROVEMENT: fresh gain >=2 outside source and healthy.

    This is saved development evidence only. It is not the original challenge/promotion
    decision, an unseen-case result, or a change to the active policy.
    """
    if study.get('replay_of') is not None:
        return _result('REPLAY_ONLY', 'Replay of an existing policy; no newly generated repair qualification.')
    if study.get('status') != 'COMPLETED':
        return _result('INCOMPLETE', 'The development study has not completed with a final result.')
    if study.get('decision') == 'NO_CHANGE':
        return _result('NOT_QUALIFIED', 'The completed study did not record a qualifying development improvement.')
    incomplete = _result('INCOMPLETE', 'Saved development evidence is missing, unsupported or inconsistent.')
    if study.get('decision') != 'OBSERVED_IMPROVEMENT':
        return incomplete
    try:
        if (study.get('schema_version') != COMPLETION_SCHEMA
                or study.get('actor_context_protocol') != ACTOR_CONTEXT_PROTOCOL_V4
                or study.get('evidence_protocol') != COMPACT_EVIDENCE_V2):
            return incomplete
        manifest = build_case_manifest(study.get('case_manifest_id', DEFAULT_CASE_MANIFEST))
        if (study.get('manifest') != manifest or study.get('manifest_hash') != content_hash(manifest)
                or study.get('validation_assessment', {}).get('decision') != 'OBSERVED_IMPROVEMENT'):
            return incomplete
        version, policy_hash = _identity(study)
        policy = _policy(store, version, policy_hash)
        incumbent_hash = study.get('incumbent_hash')
        baseline = _policy(store, 'policy-v0', incumbent_hash)
        if (not policy_hash or not policy or not policy.content.rules or policy_hash == incumbent_hash
                or policy.author != 'mechanic' or policy.parent_version != 'policy-v0'
                or not baseline or baseline.decision != 'BASELINE' or baseline.content.rules):
            return incomplete
        matches = [(index, candidate) for index, candidate in enumerate(study['candidates'])
                   if candidate.get('policy_version') == version and candidate.get('policy_hash') == policy_hash]
        if len(matches) != 1:
            return incomplete
        index, candidate = matches[0]
        if (content_hash(candidate.get('content')) != policy_hash
                or candidate.get('decision') != 'OBSERVED_IMPROVEMENT'
                or candidate.get('source_assessment', {}).get('decision') != 'SOURCE_QUALIFIED'):
            return incomplete
        stage = f'candidate-{index + 1}'
        controls = _stage_rows(study, 'controls')
        source_rows = _stage_rows(study, stage)
        validation_rows = _stage_rows(study, 'validation')
        if not _rows_are_bound(study, controls + source_rows + validation_rows, {'controls', stage, 'validation'}):
            return incomplete
        source_id, healthy_id = manifest['source_case_id'], manifest['control_case_id']
        control_cases = {case['case_id']: case for case in manifest['cases']
                         if case['case_id'] in (source_id, healthy_id)}
        expected_controls = {(case, index, 'B0') for case in control_cases for index in range(3)}
        if (len(controls) != 6 or {(r['case_id'], r['trial'].trial_index, r['trial'].arm)
                                 for r in controls} != expected_controls):
            return incomplete
        for row in controls:
            case = control_cases[row['case_id']]; trial = row['trial']
            if (trial.policy_hash != incumbent_hash or trial.scenario_hash != content_hash(case['fault_spec'])
                    or trial.fault_scheduled != bool(case['fault_spec']['primitives'])):
                return incomplete
        source_controls = [r['trial'] for r in controls if r['case_id'] == source_id and valid_trial(r['trial'])]
        healthy_controls = [r['trial'] for r in controls if r['case_id'] == healthy_id and valid_trial(r['trial'])]
        # Match the recorded study's original control rule, including retained untriggered
        # controls; do not invent a stricter three-valid-controls gate for this display.
        if (len(source_controls) < 2 or len(healthy_controls) < 2
                or any(t.outcome == 'COMPLETED' for t in source_controls)
                or any(t.outcome != 'COMPLETED' for t in healthy_controls)):
            return incomplete
        source = next(case for case in manifest['cases'] if case['case_id'] == source_id)
        source_result = assess_pairs(source_rows, [source], incumbent_hash, policy_hash)
        validation = source_clause(assess_pairs(validation_rows, manifest['cases'], incumbent_hash,
                                               policy_hash, validation=True), manifest)
        if (source_result['decision'] != 'SOURCE_QUALIFIED'
                or source_result['by_case'] != candidate['source_assessment'].get('by_case')
                or validation['decision'] != 'OBSERVED_IMPROVEMENT'
                or validation['by_case'] != study['validation_assessment'].get('by_case')
                or any(validation['by_case'][case]['L']['completed'] != 3 for case in (source_id, healthy_id))):
            return incomplete
        fresh_gain = any(counts['L']['completed'] - counts['B0']['completed'] >= 2
                         for case, counts in validation['by_case'].items() if case not in (source_id, healthy_id))
        if not fresh_gain:
            return _result('NOT_QUALIFIED', 'Improvement was recorded, but no other validation case gained at least two completions.')
        return _result('QUALIFIED', 'Saved source and validation trials meet the development qualification; this does not establish unseen-case safety.')
    except (KeyError, TypeError, ValueError, AttributeError, StopIteration):
        return incomplete


def _public_checks(store):
    # Select individual public scalars, never deserialize a private held-out plan/batch.
    columns = ', '.join(f"json_extract(payload, '$.{key}')" for key in CHECK_FIELDS)
    with store.lock:
        rows = store.db.execute(f"SELECT {columns} FROM records WHERE kind=? ORDER BY rowid",
                                ('heldout_checks',)).fetchall()
    return [dict(zip(CHECK_FIELDS, row)) for row in rows]


def _check_matches(check, study):
    version, policy_hash = _identity(study)
    return (bool(version and policy_hash) and check.get('certified_study_id') == study.get('study_id')
            and check.get('policy_hash') == policy_hash and check.get('policy_version') == version
            and all(_text(check.get(key)) for key in ('check_id', 'campaign_id'))
            and _text(check.get('predicate')) in CHECK_PREDICATES)


def _check_view(check):
    status = check['status'] if _text(check.get('status')) in CHECK_STATUSES else 'INCOMPLETE'
    decision = check['decision'] if _text(check.get('decision')) in CHECK_DECISIONS else 'INCOMPLETE'
    if ((decision in ('HARM', 'NO_HARM') and status != 'COMPLETED')
            or (decision == 'PENDING' and status not in ('QUEUED', 'RUNNING'))
            or (status == 'COMPLETED' and decision not in ('HARM', 'NO_HARM'))):
        status = decision = 'INCOMPLETE'
    return {'check_id': check['check_id'], 'campaign_id': check['campaign_id'],
            'source_study_id': check['certified_study_id'], 'policy_hash': check['policy_hash'],
            'status': status, 'decision': decision, 'predicate': check['predicate']}


def policy_status(store, campaign_id):
    campaign = store.get_record('campaigns', campaign_id)
    if campaign is None:
        raise StoreConflict('Unknown campaign')
    active_version = _text(campaign.get('active_policy_version'))
    active = _policy(store, active_version)
    # Read just this campaign's public studies. Parsing every large study on each dashboard
    # poll would reintroduce the whole-store responsiveness problem fixed in Phase 19.
    with store.lock:
        rows = store.db.execute("SELECT payload FROM records WHERE kind=? "
                                "AND json_extract(payload, '$.campaign_id')=? ORDER BY rowid",
                                ('completion_studies', campaign_id)).fetchall()
    studies = {}
    for row in rows:
        study = json.loads(row[0])
        if _text(study.get('study_id')):
            studies[study['study_id']] = study
    checks = _public_checks(store)
    for check in checks:
        if check.get('campaign_id') == campaign_id and _text(check.get('certified_study_id')):
            source = store.get_record('completion_studies', check['certified_study_id'])
            if isinstance(source, dict) and _text(source.get('campaign_id')) and _check_matches(check, source):
                studies[source['study_id']] = source
    summaries = []
    for study in studies.values():
        version, policy_hash = _identity(study)
        summaries.append({'study_id': study['study_id'], 'source_campaign_id': study['campaign_id'],
                          'policy_hash': policy_hash, 'policy_version': version,
                          'development': development_status(store, study),
                          'unseen_checks': [_check_view(check) for check in checks if _check_matches(check, study)]})
    return {'schema_version': SCHEMA, 'campaign_id': campaign_id,
            'active_policy': {'version': active_version, 'hash': active.policy_hash if active else None},
            'studies': summaries}
