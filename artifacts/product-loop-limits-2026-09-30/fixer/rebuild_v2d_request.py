"""Rebuild, offline and at $0, the Mechanic candidate request that live run v2d refused (33,223 > 32,000 tokens).

Run from faultlab/backend with the project .venv, on a SCRATCH COPY of the saved store (never the original):
  ../.venv/bin/python ../artifacts/product-loop-limits-2026-09-30/builder/rebuild_v2d_request.py /Users/shree/FaultLab_Scratch/<stage>/lab.sqlite3 [--compact]

It opens the copy read-only (ReadOnlyLabStore), re-derives every field of the learning loop's proposal_context for the
campaign's second candidate request exactly as backend/app/lab/learning.py builds it (the same helper functions, the
same record order), builds the Mechanic's messages exactly as app/agents/mechanic.py does (mechanic.md system prompt,
canonical_json(context + output_schema)), and counts them with the frozen tokenizer (app.contracts.tokens) for the
campaign's Mechanic model. It also rebuilds the first candidate request, whose provider-reported input was 14,168.
With --compact it then applies the declared compaction (app.lab.loop_limits, when present) and reports the result.
No provider, W&B or Weave call is made; the guard refuses any non-loopback connection and the real .env.
"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import guard  # noqa: E402,F401  (refuses .env and outbound connections)

from pydantic import TypeAdapter  # noqa: E402
from app.contracts.models import (Campaign, ChallengeResult, Counterexample, DiagnosticResult, EvidenceBundle, FaultSpec,  # noqa: E402
                                  MechanicOutput, PolicyVersion, ReductionResult, TrialResult, canonical_json)
from app.contracts.tokens import input_token_bound  # noqa: E402
from app.contracts.models import MODEL_INPUT_TOKEN_LIMIT  # noqa: E402
from app.lab.storage import ReadOnlyLabStore  # noqa: E402
from app.lab.diagnosis import summarize_evidence, runtime_contract, reduction_context, trial_outcomes  # noqa: E402
from app.lab.learning import source_validation_assessment, discovery_session  # noqa: E402

CAMPAIGN = 'campaign-ea66672d7a904bd8a011d6922790c963'
MODEL = 'deepseek-ai/DeepSeek-V4-Pro-0813'  # the campaign's Mechanic model, from its mechanic_outputs records
PROMPT = (Path('app/agents/prompts/mechanic.md')).read_text()
REFUSED_BOUND = 33223


def model(store, kind, ident, cls):
    return cls.model_validate_json(canonical_json(store.get_record(kind, ident)))


def bundles(store, episode_ids):
    out = []
    for episode_id in episode_ids:
        raw = store.get_record('evidence', episode_id)
        if raw is None:
            raise SystemExit(f'missing evidence for {episode_id}')
        out.append(EvidenceBundle.model_validate_json(canonical_json(raw)))
    return out


def trial(store, episode_id):
    return model(store, 'trials', episode_id, TrialResult)


def tokens(context):
    messages = [{'role': 'system', 'content': PROMPT},
                {'role': 'user', 'content': canonical_json({**context, 'output_schema': TypeAdapter(MechanicOutput).json_schema()})}]
    return input_token_bound(messages, MODEL)


def rebuild(store):
    campaign = store.get_model('campaigns', CAMPAIGN, Campaign)
    incumbent = model(store, 'policies', 'policy-v0', PolicyVersion)
    identity, _ = discovery_session(store, campaign, incumbent)
    episodes = sorted((row for row in store.list_records('episodes') if row['campaign_id'] == CAMPAIGN),
                      key=lambda row: 0)  # list_records is already rowid (creation) order
    by_purpose = {}
    for row in episodes:
        by_purpose.setdefault(row['experiment_purpose'], []).append(row['episode_id'])
    counter_raw = next(r for r in store.list_records('counterexamples') if r['campaign_id'] == CAMPAIGN)
    counter = Counterexample.model_validate_json(canonical_json(counter_raw))
    source_id = counter.source_episode_id
    source_evidence = bundles(store, [source_id])
    reproduction_trials = [trial(store, e) for e in counter.reproduction_trial_ids]
    reproduced_evidence = bundles(store, [t.episode_id for t in reproduction_trials])
    reduction = model(store, 'reductions', counter.counterexample_id, ReductionResult)
    reduced_trials = [trial(store, e) for e in by_purpose['reduction']]
    reduction_evidence = bundles(store, [t.episode_id for t in reduced_trials if t.lifecycle == 'COMPLETED'])
    reduction_summary = reduction_context(reduction, reduced_trials, reduction_evidence)
    retained = FaultSpec.model_validate(store.get_record('retained_recipes', counter.counterexample_id)['retained_recipe'])
    diagnostic_link = next(r for r in store.list_records('diagnostic_campaigns') if r['campaign_id'] == CAMPAIGN)
    diagnostic = model(store, 'diagnostics', diagnostic_link['diagnostic_id'], DiagnosticResult)
    intervention_trials = [trial(store, e) for e in by_purpose['intervention']]
    intervention_evidence = bundles(store, [t.episode_id for t in intervention_trials if t.lifecycle == 'COMPLETED'])
    qualification = next(r for r in store.list_records('candidate_qualifications') if r['campaign_id'] == CAMPAIGN)
    source_context = qualification['source_context_id']
    candidate_record = {k: qualification[k] for k in ('candidate_version', 'candidate_hash', 'candidate', 'qualification_ref')}
    common = {'campaign_id': CAMPAIGN, 'source_context_id': source_context, 'parent_version': incumbent.version,
              'target_invariant': counter.target_invariant, 'diagnostic': diagnostic.model_dump(mode='json'),
              'runtime_contract': runtime_contract(store, campaign), 'retained_fault_spec': retained.model_dump(mode='json'),
              'reduction': reduction_summary}
    first = {**common, 'development_evidence': summarize_evidence(source_evidence + reproduced_evidence + intervention_evidence),
             'candidate_history': [], 'challenge_counterexamples': [], 'source_validation_feedback': []}
    # Source validation, exactly as the loop records its feedback.
    batch_raw = store.get_record('evaluations', qualification['source_validation_ref'])
    batch_trials = [TrialResult.model_validate_json(canonical_json(raw)) for raw in batch_raw['trials']]
    source_retest_evidence = bundles(store, [t.episode_id for t in batch_trials if t.lifecycle == 'COMPLETED'])
    source_result = store.get_record('source_validation_results', batch_raw['batch_id'])
    source_feedback = [{**source_result, 'reason': 'Qualification requires three valid pairs: the incumbent still fails the target in all three, and every candidate has no check failure. Source flakiness and candidate violations are recorded separately.',
                        'verified_episode_ids': [b.episode_id for b in source_retest_evidence]}]
    # Challenge, exactly as the loop gathers its trials and feedback.
    challenge = model(store, 'challenges', qualification['challenge_ref'], ChallengeResult)
    challenge_trials_by_id = {}
    for batch in store.list_records('evaluations'):
        if batch['purpose'] != 'challenge' or (batch['candidate_hash'], batch['incumbent_hash']) != (challenge.candidate_hash, challenge.incumbent_hash):
            continue
        for raw in batch['trials']:
            t = TrialResult.model_validate_json(canonical_json(raw)); challenge_trials_by_id[t.episode_id] = t
    for a, b in challenge.trial_pairs:
        for episode_id in (a, b):
            if episode_id not in challenge_trials_by_id: challenge_trials_by_id[episode_id] = trial(store, episode_id)
    challenge_trials = list(challenge_trials_by_id.values())
    challenge_evidence = bundles(store, [t.episode_id for t in challenge_trials if t.lifecycle == 'COMPLETED'])
    schedules = []
    for selection_ref in challenge.selection_refs:
        selection = store.get_record('selections', selection_ref) or {}
        fault = (selection.get('output') or {}).get('fault_spec')
        if fault is not None and identity(FaultSpec.model_validate_json(canonical_json(fault))) in challenge.schedule_hashes: schedules.append(fault)
    counterexample_record = store.get_record('challenge_counterexamples', qualification['candidate_version']) or {}
    feedback = [{'challenge_id': challenge.challenge_id, **candidate_record, 'decision': qualification['decision'], 'status': challenge.status,
                 'reason': challenge.stopping_reason, 'failed_checks': challenge.failed_checks, 'fault_spec': counterexample_record.get('recipe'),
                 'fixture_id': counterexample_record.get('fixture_id'), 'tested_fault_specs': schedules,
                 'trial_outcomes': trial_outcomes(challenge_trials), 'evidence': summarize_evidence(challenge_evidence)}]
    history = [{**candidate_record, 'decision': qualification['decision'], 'source_validation_ref': batch_raw['batch_id'],
                'challenge_ref': challenge.challenge_id, 'classification': challenge.status}]
    second = {**common, 'development_evidence': summarize_evidence(source_evidence + reproduced_evidence + intervention_evidence + source_retest_evidence),
              'candidate_history': history, 'challenge_counterexamples': feedback, 'source_validation_feedback': source_feedback}
    counts = {'source': 1, 'reproduction': len(reproduced_evidence), 'reduction_trials': len(reduced_trials),
              'intervention': len(intervention_evidence), 'source_validation': len(source_retest_evidence),
              'challenge_trials': len(challenge_trials), 'challenge_evidence': len(challenge_evidence)}
    return first, second, counts, counter


def breakdown(context):
    """Tokens each top-level field adds (bound with the field minus bound without it), and the evidence tables."""
    full = tokens(context)
    rows = {}
    for key in context:
        rows[key] = full - tokens({k: v for k, v in context.items() if k != key})
    for key in ('development_evidence',):
        ev = context[key]
        for part in ('episodes', 'results', 'reports', 'checks', 'interpretation'):
            rows[f'{key}.{part}'] = full - tokens({**context, key: {k: v for k, v in ev.items() if k != part}})
    for index, item in enumerate(context['challenge_counterexamples']):
        for part in item:
            reduced = [dict(x) for x in context['challenge_counterexamples']]
            reduced[index] = {k: v for k, v in item.items() if k != part}
            rows[f'challenge_counterexamples[{index}].{part}'] = full - tokens({**context, 'challenge_counterexamples': reduced})
    for index, item in enumerate(context['source_validation_feedback']):
        for part in item:
            reduced = [dict(x) for x in context['source_validation_feedback']]
            reduced[index] = {k: v for k, v in item.items() if k != part}
            rows[f'source_validation_feedback[{index}].{part}'] = full - tokens({**context, 'source_validation_feedback': reduced})
    return full, dict(sorted(rows.items(), key=lambda kv: -kv[1]))


def main():
    path = sys.argv[1]
    if '/FaultLab_Runs/' in path or 'Desktop' in path:
        raise SystemExit('Refusing: pass a scratch copy outside the saved run stores and outside the Desktop')
    store = ReadOnlyLabStore(path)
    first, second, counts, counter = rebuild(store)
    out = {'store_copy': path, 'campaign_id': CAMPAIGN, 'mechanic_model': MODEL, 'input_token_limit': MODEL_INPUT_TOKEN_LIMIT,
           'episode_counts': counts}
    out['first_request_bound'] = tokens(first)
    out['first_request_provider_input_tokens'] = 14168
    full, rows = breakdown(second)
    out['second_request_bound'] = full
    out['second_request_bound_matches_refused_33223'] = full == REFUSED_BOUND
    out['second_request_tokens_by_field'] = rows
    out['second_request_evidence_shape'] = {
        'development_evidence_episodes': len(second['development_evidence']['episodes']),
        'development_evidence_result_rows': len(second['development_evidence']['results']),
        'challenge_evidence_episodes': len(second['challenge_counterexamples'][0]['evidence']['episodes']),
        'challenge_evidence_result_rows': len(second['challenge_counterexamples'][0]['evidence']['results']),
        'challenge_trial_outcome_groups': len(second['challenge_counterexamples'][0]['trial_outcomes'])}
    if '--compact' in sys.argv:
        # The declared compaction exactly as the learning loop applies it (app.lab.loop_limits.fit_request without its
        # record write: this store copy is opened read-only). The bound is the Mechanic's own first-turn admission count.
        from types import SimpleNamespace
        from app.lab import loop_limits
        mechanic = SimpleNamespace(provider=SimpleNamespace(role_model=lambda role: MODEL), metadata=None)
        bound = lambda value: loop_limits.mechanic_request_bound(mechanic, 'mechanic.md', TypeAdapter(MechanicOutput), value)
        full = bound(second)
        request, summary = loop_limits.compact_request(second, request_kind='mechanic_proposal', store=store, bound=bound, full_bound=full,
                                                      protected_episode_ids=[counter.source_episode_id, *counter.reproduction_trial_ids])
        out['compaction'] = {'mechanic_request_bound_before': full, 'fits': summary['fits'], 'bound_after': summary['compacted_tokens'],
                             'target': loop_limits.COMPACTION_TARGET_TOKENS, 'stages_applied': summary['stages_applied'],
                             'attempts': summary['attempts'], 'blocks': summary['blocks'], 'statement': summary['statement']}
        # For information only: the size after each stage, all three forced (the target set to 0 so no stage stops early).
        target = loop_limits.COMPACTION_TARGET_TOKENS
        try:
            loop_limits.COMPACTION_TARGET_TOKENS = 0
            _, every = loop_limits.compact_request(second, request_kind='mechanic_proposal', store=store, bound=bound, full_bound=full,
                                                   protected_episode_ids=[counter.source_episode_id, *counter.reproduction_trial_ids])
        finally:
            loop_limits.COMPACTION_TARGET_TOKENS = target
        out['compaction']['every_stage_forced'] = every['attempts']
        if request is not None:
            out['compaction']['statement_in_request'] = request['context_compaction']['statement'] == summary['statement']
            out['compaction']['bound_after_recount'] = tokens(request)
            kept = {k: v for k, v in request.items() if k not in ('development_evidence', 'challenge_counterexamples', 'context_compaction')}
            out['compaction']['other_fields_unchanged'] = kept == {k: v for k, v in second.items() if k not in ('development_evidence', 'challenge_counterexamples')}
            feedback = {k: v for k, v in request['challenge_counterexamples'][0].items() if k != 'evidence'}
            out['compaction']['challenge_feedback_fields_unchanged'] = feedback == {k: v for k, v in second['challenge_counterexamples'][0].items() if k != 'evidence'}
            kept_ids = {row['episode_id'] for row in request['development_evidence']['episodes']} | {row['episode_id'] for row in request['challenge_counterexamples'][0]['evidence']['episodes']}
            protected = {counter.source_episode_id, *counter.reproduction_trial_ids}
            failed = {row['episode_id'] for block in (second['development_evidence'], second['challenge_counterexamples'][0]['evidence'])
                      for row in block['episodes'] if any(c.get('passed') is False for c in block['checks'][row['check_row']])}
            out['compaction']['source_and_failed_kept'] = (protected | failed) <= kept_ids
            out['compaction']['kept_in_full'] = len(kept_ids)
            out['compaction']['failed_check_episodes'] = len(failed)
            omitted = [o['episode_id'] for block in (request['development_evidence'], request['challenge_counterexamples'][0]['evidence']) for o in (block.get('compaction') or {}).get('omitted', [])]
            everyone = {row['episode_id'] for block in (second['development_evidence'], second['challenge_counterexamples'][0]['evidence']) for row in block['episodes']}
            out['compaction']['every_episode_kept_or_named'] = kept_ids | set(omitted) == everyone and not kept_ids & set(omitted)
            Path(HERE / 'rebuilt-v2d-request-compacted.json').write_text(json.dumps(request, indent=1, sort_keys=True))
    Path(HERE / 'rebuilt-v2d-request-full.json').write_text(json.dumps(second, indent=1, sort_keys=True))
    print(json.dumps(out, indent=2))
    store.close()


if __name__ == '__main__':
    main()
