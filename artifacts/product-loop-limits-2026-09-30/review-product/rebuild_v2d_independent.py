"""Product reviewer, $0: an independent offline rebuild of the Mechanic candidate request live run v2d refused.

Run from faultlab/backend:
  ../.venv/bin/python -B ../artifacts/product-loop-limits-2026-09-30/review-product/rebuild_v2d_independent.py <ro-copy> <rw-copy> <out.json>

Both paths must be scratch COPIES outside the Desktop and outside /Users/shree/FaultLab_Runs.

Independent of the builder's script: the context is re-derived by reading backend/app/lab/learning.py (lines 229-236
and 285-295 of the working tree), with different record routes where the store allows it (intervention trials from the
interventions record's trial_pairs, reduction trials from the reductions record's attempts, source-validation trials from
the evaluation batch). The count is taken from the REAL Mechanic (app/agents/mechanic.py): its own validate_model_input
call is intercepted, so the number is what the Mechanic itself would admit or refuse. The compacted request is then
sent through the real Mechanic.propose to a capturing stand-in provider (no network) to prove the dispatched first turn
fits. fit_request runs on the writable copy so its mechanic_context_records row is written exactly as the loop writes it.
"""
import asyncio
import json
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent))
import rguard  # noqa: E402,F401

import app.agents.mechanic as mechanic_module  # noqa: E402
from app.agents.mechanic import Mechanic  # noqa: E402
from app.contracts.models import (MODEL_INPUT_TOKEN_LIMIT, Campaign, ChallengeResult, Counterexample, DiagnosticResult,  # noqa: E402
                                  EvidenceBundle, FaultSpec, PolicyVersion, ReductionResult, TrialResult, canonical_json)
from app.contracts.tokens import ModelInputLimit, input_token_bound  # noqa: E402
from app.lab import loop_limits  # noqa: E402
from app.lab.diagnosis import reduction_context, runtime_contract, summarize_evidence, trial_outcomes  # noqa: E402
from app.lab.learning import discovery_session  # noqa: E402
from app.lab.storage import LabStore, ReadOnlyLabStore  # noqa: E402
from app.providers.runtime import RuntimeGeneration  # noqa: E402

CAMPAIGN = 'campaign-ea66672d7a904bd8a011d6922790c963'
MODEL = 'deepseek-ai/DeepSeek-V4-Pro-0813'
SV_REASON = ('Qualification requires three valid pairs: the incumbent still fails the target in all three, and every candidate '
             'has no check failure. Source flakiness and candidate violations are recorded separately.')


def guard_path(path):
    if 'Desktop' in path or '/FaultLab_Runs/' in path:
        raise SystemExit('refusing: pass scratch copies only')


def build(store):
    get = lambda kind, ident, cls: cls.model_validate_json(canonical_json(store.get_record(kind, ident)))
    bundles = lambda ids: [EvidenceBundle.model_validate_json(canonical_json(store.get_record('evidence', e))) for e in ids]
    trials = lambda ids: [get('trials', e, TrialResult) for e in ids]
    campaign = store.get_model('campaigns', CAMPAIGN, Campaign)
    incumbent = get('policies', 'policy-v0', PolicyVersion)
    identity, _ = discovery_session(store, campaign, incumbent)
    counter = next(Counterexample.model_validate_json(canonical_json(r)) for r in store.list_records('counterexamples') if r['campaign_id'] == CAMPAIGN)
    source_evidence = bundles([counter.source_episode_id])
    reproduced_evidence = bundles([t.episode_id for t in trials(counter.reproduction_trial_ids)])
    reduction = get('reductions', counter.counterexample_id, ReductionResult)
    # Reproducer.reduce returns every trial the fixed reducer ran (run.trials). The reductions record's attempts list
    # names only 6 of the 9 reduction episodes, so the trials are taken from this campaign's reduction episodes in
    # creation order (REVIEW_REDUCTION=attempts reproduces the first, wrong, route for comparison).
    import os
    purposes = {}
    for row in store.list_records('episodes'):
        if row['campaign_id'] == CAMPAIGN: purposes.setdefault(row['experiment_purpose'], []).append(row['episode_id'])
    reduced_trials = trials([e for a in reduction.attempts for e in a.trial_ids] if os.environ.get('REVIEW_REDUCTION') == 'attempts'
                            else purposes['reduction'])
    reduction_summary = reduction_context(reduction, reduced_trials, bundles([t.episode_id for t in reduced_trials if t.lifecycle == 'COMPLETED']))
    retained = FaultSpec.model_validate(store.get_record('retained_recipes', counter.counterexample_id)['retained_recipe'])
    link = next(r for r in store.list_records('diagnostic_campaigns') if r['campaign_id'] == CAMPAIGN)
    diagnostic = get('diagnostics', link['diagnostic_id'], DiagnosticResult)
    intervention = next(r for r in store.list_records('interventions') if r['counterexample_id'] == counter.counterexample_id)
    intervention_trials = trials([e for pair in intervention['trial_pairs'] for e in pair] if os.environ.get('REVIEW_INTERVENTION') == 'pairs'
                                 else purposes['intervention'])
    intervention_evidence = bundles([t.episode_id for t in intervention_trials if t.lifecycle == 'COMPLETED'])
    qualification = next(r for r in store.list_records('candidate_qualifications') if r['campaign_id'] == CAMPAIGN)
    candidate_record = {k: qualification[k] for k in ('candidate_version', 'candidate_hash', 'candidate', 'qualification_ref')}
    batch = store.get_record('evaluations', qualification['source_validation_ref'])
    sv_trials = [TrialResult.model_validate_json(canonical_json(t)) for t in batch['trials']]
    retest = bundles([t.episode_id for t in sv_trials if t.lifecycle == 'COMPLETED'])
    source_result = store.get_record('source_validation_results', batch['batch_id'])
    source_feedback = [{**source_result, 'reason': SV_REASON, 'verified_episode_ids': [b.episode_id for b in retest]}]
    challenge = get('challenges', qualification['challenge_ref'], ChallengeResult)
    by_id = {}
    for raw in store.list_records('evaluations'):
        if raw['purpose'] != 'challenge' or (raw['candidate_hash'], raw['incumbent_hash']) != (challenge.candidate_hash, challenge.incumbent_hash):
            continue
        for t in raw['trials']:
            trial = TrialResult.model_validate_json(canonical_json(t)); by_id[trial.episode_id] = trial
    for a, b in challenge.trial_pairs:
        for e in (a, b):
            if e not in by_id: by_id[e] = get('trials', e, TrialResult)
    challenge_trials = list(by_id.values())
    challenge_evidence = bundles([t.episode_id for t in challenge_trials if t.lifecycle == 'COMPLETED'])
    schedules = []
    for ref in challenge.selection_refs:
        fault = ((store.get_record('selections', ref) or {}).get('output') or {}).get('fault_spec')
        if fault is not None and identity(FaultSpec.model_validate_json(canonical_json(fault))) in challenge.schedule_hashes: schedules.append(fault)
    counterexample_record = store.get_record('challenge_counterexamples', qualification['candidate_version']) or {}
    decision = qualification['decision']
    feedback = [{'challenge_id': challenge.challenge_id, **candidate_record, 'decision': decision, 'status': challenge.status,
                 'reason': challenge.stopping_reason, 'failed_checks': challenge.failed_checks, 'fault_spec': counterexample_record.get('recipe'),
                 'fixture_id': counterexample_record.get('fixture_id'), 'tested_fault_specs': schedules,
                 'trial_outcomes': trial_outcomes(challenge_trials), 'evidence': summarize_evidence(challenge_evidence)}]
    history = [{**candidate_record, 'decision': decision, 'source_validation_ref': batch['batch_id'], 'challenge_ref': challenge.challenge_id,
                'classification': challenge.status}]
    context = {'campaign_id': CAMPAIGN, 'source_context_id': qualification['source_context_id'], 'parent_version': incumbent.version,
               'target_invariant': counter.target_invariant, 'diagnostic': diagnostic.model_dump(mode='json'),
               'development_evidence': summarize_evidence(source_evidence + reproduced_evidence + intervention_evidence + retest),
               'candidate_history': history, 'challenge_counterexamples': feedback, 'source_validation_feedback': source_feedback,
               'runtime_contract': runtime_contract(store, campaign), 'retained_fault_spec': retained.model_dump(mode='json'),
               'reduction': reduction_summary}
    return counter, context, {'intervention_trials': [t.episode_id for t in intervention_trials], 'reduction_trials': len(reduced_trials),
                              'sv_trials': len(sv_trials), 'challenge_trials': len(challenge_trials)}


class Capture:
    """Stand-in provider: records the size of every first-turn request it is handed and answers NO_CHANGE."""
    def __init__(self): self.sent = []
    def role_model(self, role): return MODEL
    async def complete(self, messages, **kwargs):
        self.sent.append(input_token_bound(messages, MODEL))
        return RuntimeGeneration(canonical_json({'no_change_reason': 'review stand-in'}), MODEL, input_tokens=1, output_tokens=1)


class Ledger:
    def __init__(self): self.calls = 0
    def consume_call(self, **kwargs): self.calls += 1
    def reconcile(self, generation): pass


def mechanic_admission(store, context):
    """What the real Mechanic.propose would count for this context (its own validate_model_input), without sending."""
    seen = []
    original = mechanic_module.validate_model_input
    def capture(messages, model):
        seen.append(input_token_bound(messages, model)); raise ModelInputLimit(seen[-1])
    mechanic_module.validate_model_input = capture
    try:
        try: asyncio.run(Mechanic(Capture(), store, Ledger()).propose(context))
        except ModelInputLimit: pass
    finally:
        mechanic_module.validate_model_input = original
    return seen[0]


def rows_by_id(summary):
    out = {}
    for row in summary['episodes']:
        out[row['episode_id']] = {'results': [summary['results'][i] for _, _, i in row['observations']],
                                  'ticks': [t for _, t, _ in row['observations']],
                                  'report': summary['reports'][row['report_row']], 'checks': summary['checks'][row['check_row']]}
    return out


def main():
    ro, rw, out_path = sys.argv[1:4]
    guard_path(ro); guard_path(rw)
    store = ReadOnlyLabStore(ro)
    counter, context, shape = build(store)
    before = mechanic_admission(store, context)
    report = {'campaign_id': CAMPAIGN, 'mechanic_model': MODEL, 'limit': MODEL_INPUT_TOKEN_LIMIT, 'shape': shape,
              'real_mechanic_admission_count_full': before, 'matches_live_refusal_33223': before == 33223,
              'recorded_live_refusal': next(r for r in store.list_records('execution_errors') if r['campaign_id'] == CAMPAIGN)['input_token_bound']}
    store.close()
    # fit_request exactly as learning.py calls it, on a writable copy (it writes one mechanic_context_records row).
    wstore = LabStore(rw)
    mechanic = Mechanic(Capture(), wstore, Ledger())
    request, ref = loop_limits.fit_request(wstore, mechanic, context, request_kind='mechanic_proposal', campaign_id=CAMPAIGN,
                                           counterexample=counter, extra={'source_context_id': context['source_context_id'], 'candidate_index': 1})
    record = wstore.get_record('mechanic_context_records', ref)
    after = mechanic_admission(wstore, request)
    # Now actually hand it to the real Mechanic.propose with the capturing stand-in provider.
    provider = Capture(); ledger = Ledger()
    proposal_ref, proposal, raws = asyncio.run(Mechanic(provider, wstore, ledger).propose(request))
    dev_full, dev_after = rows_by_id(context['development_evidence']), rows_by_id(request['development_evidence'])
    ch_full, ch_after = rows_by_id(context['challenge_counterexamples'][0]['evidence']), rows_by_id(request['challenge_counterexamples'][0]['evidence'])
    lost = []
    for label, full, block in (('development_evidence', dev_full, request['development_evidence']),
                               ('challenge_counterexamples[0].evidence', ch_full, request['challenge_counterexamples'][0]['evidence'])):
        for item in (block.get('compaction') or {}).get('omitted', []):
            rep = item.get('same_as') or item.get('represented_by')
            mine, theirs = full[item['episode_id']], full[rep] if rep else None
            diff = None if theirs is None else sorted(k for k in mine if canonical_json(mine[k]) != canonical_json(theirs[k]))
            lost.append({'block': label, 'episode_id': item['episode_id'], 'omitted_as': item['omitted_as'], 'representative': rep,
                         'arm': item.get('arm'), 'outcome': item.get('outcome'), 'fault_triggered': item.get('fault_triggered'),
                         'differs_from_representative_in': diff})
    failing = {e for block in (context['development_evidence'], context['challenge_counterexamples'][0]['evidence'])
               for e, row in rows_by_id(block).items() if any(isinstance(c, dict) and c.get('passed') is False for c in row['checks'])}
    kept = set(dev_after) | set(ch_after)
    unchanged = {k: request[k] == context[k] for k in context if k not in ('development_evidence', 'challenge_counterexamples')}
    report.update({
        'fit_request': {'record_outcome': record['outcome'], 'stages_applied': record['stages_applied'], 'attempts': record['attempts'],
                        'compacted_request_tokens': record['compacted_request_tokens'], 'provider_dispatch': record['provider_dispatch'],
                        'blocks': record['blocks']},
        'real_mechanic_admission_count_compacted': after, 'compacted_under_target_28000': after <= loop_limits.COMPACTION_TARGET_TOKENS,
        'dispatched_first_turn_tokens': provider.sent, 'dispatched_count': len(provider.sent), 'mechanic_answer_parsed': proposal is not None,
        'statement_in_request': request['context_compaction']['statement'],
        'development_evidence_interpretation_tail': request['development_evidence']['interpretation'][-420:],
        'failing_episodes_total': len(failing), 'failing_all_kept': failing <= kept,
        'source_and_reproductions_kept': {counter.source_episode_id, *counter.reproduction_trial_ids} <= set(dev_after),
        'kept_in_full': {'development_evidence': len(dev_after), 'challenge': len(ch_after)},
        'other_top_level_fields_unchanged': unchanged,
        'challenge_feedback_non_evidence_fields_unchanged': {k: v for k, v in request['challenge_counterexamples'][0].items() if k != 'evidence'}
                                                            == {k: v for k, v in context['challenge_counterexamples'][0].items() if k != 'evidence'},
        'omitted_episodes': lost,
        'omitted_that_differ_from_their_representative': sum(1 for x in lost if x['differs_from_representative_in']),
    })
    wstore.close()
    Path(out_path).write_text(json.dumps(report, indent=1, default=str))
    print(json.dumps({k: v for k, v in report.items() if k not in ('omitted_episodes',)}, indent=1, default=str)[:6000])


if __name__ == '__main__':
    main()
