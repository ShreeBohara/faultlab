"""Reviewer check (1) ($0, offline): the native citation-status block on a scratch copy of the native-v2b store.

Run from faultlab/backend with the project .venv:
  ../.venv/bin/python -B ../artifacts/product-mechanic-citations-2026-09-30/review-product/review_saved_store.py OUT.json

* Copies /Users/shree/FaultLab_Runs/2026-09-30/native-v2b/lab.sqlite3 (opened mode=ro&immutable=1) to
  /Users/shree/FaultLab_Scratch/review-product/v2b/ and deletes the copy at the end.
* INDEPENDENT of the product code: reads each diagnosed episode's report_submitted event with raw SQL and recomputes
  cited / decoded / undecoded, and also checks every decoded ID against that episode's own observation_delivered events.
* PRODUCT path: registers native adapter v2, prepares a NEW Learn plan (v4 history replay) and creates it in the copy,
  then rebuilds v2e's (and v2d's) diagnosis request through the real wrapping order
  CitationStatusMechanic(BoundedMechanic(capture)) and compares the block with the independent numbers.
* Sizes with the Mechanic's frozen tokenizer; also v2d's recorded challenge Explorer requests with the block added.
"""
import asyncio
import json
import shutil
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import rguard  # noqa: E402,F401

from app.contracts.models import canonical_json  # noqa: E402

SAVED = '/Users/shree/FaultLab_Runs/2026-09-30/native-v2b/lab.sqlite3'
SCRATCH = Path('/Users/shree/FaultLab_Scratch/review-product/v2b')
V2D = 'campaign-ea66672d7a904bd8a011d6922790c963'
V2E = 'campaign-37e66b6c3a544a4d9bde4161db6bf0aa'
MECHANIC_MODEL = 'deepseek-ai/DeepSeek-V4-Pro-0813'


def copy_store(target):
    src = sqlite3.connect(f'file:{SAVED}?mode=ro&immutable=1', uri=True); dst = sqlite3.connect(target)
    try:
        src.backup(dst); dst.execute('PRAGMA journal_mode=DELETE')
    finally:
        dst.close(); src.close()


def independent_rows(db, campaign_id):
    """Raw SQL only: the diagnosed counterexample's episodes and their last public actor report_submitted event."""
    link = next(json.loads(p) for (p,) in db.execute("select payload from records where kind='diagnostic_campaigns'")
                if json.loads(p)['campaign_id'] == campaign_id)
    counter = json.loads(db.execute("select payload from records where kind='counterexamples' and id=?", (link['counterexample_id'],)).fetchone()[0])
    episodes = [counter['source_episode_id'], *counter['reproduction_trial_ids']]
    rows = []
    for episode in episodes:
        events = [json.loads(p) for (p,) in db.execute('select payload from events where episode_id=? order by seq', (episode,))]
        delivered = {e.get('evidence_id') for e in events if e.get('type') == 'observation_delivered'}
        reports = [e for e in events if e.get('type') == 'report_submitted' and e.get('role') == 'actor'
                   and e.get('visibility') != 'PRIVATE_EVALUATOR']
        payload = reports[-1]['payload']
        cited = payload['cited_evidence_tokens']; shown = payload['labels_shown_to_agent']
        label_to_id = {label: eid for eid, label in payload['evidence_labels'].items()}
        decoded_ids = payload['decoded_evidence_ids']
        decoded = sum(1 for t, d in zip(cited, decoded_ids) if t in shown and label_to_id.get(t) == d)
        decoded_and_delivered = sum(1 for t, d in zip(cited, decoded_ids) if t in shown and label_to_id.get(t) == d and d in delivered)
        rows.append({'episode_id': episode, 'reports_in_episode': len(reports), 'protocol': payload.get('citation_protocol'),
                     'cited': len(cited), 'decoded': decoded, 'decoded_and_delivered_per_observation_events': decoded_and_delivered,
                     'undecoded_recorded': payload['cited_tokens_not_decoded'],
                     'undecoded_recomputed': [t for t in cited if t not in shown],
                     'cited_tokens': cited, 'labels_shown': len(shown)})
    return counter, rows


async def product_diagnosis(owner, store, campaign, source_campaign_id, wrap_rule):
    from app.lab import citation_status, loop_limits
    import citation_status_saved as saved
    from app.lab.diagnosis import Diagnostician
    _, counter, retained, incumbent, reproduction, evidence, reduction = saved.diagnosis_inputs(store, source_campaign_id)
    capture = saved.CaptureMechanic()
    inner = loop_limits.BoundedMechanic(capture, store, campaign_id=campaign.campaign_id, counterexample=counter)
    mechanic = citation_status.CitationStatusMechanic(inner, store) if wrap_rule else inner
    try:
        await Diagnostician(store, None, None, mechanic).run(campaign, counter, retained, incumbent, reproduction,
                                                             evidence=evidence, reduction=reduction)
    except saved.Captured:
        pass
    context, = capture.contexts
    return counter, context


def mechanic_size(context, prompt):
    from pydantic import TypeAdapter
    from types import SimpleNamespace
    from app.contracts.models import DiagnosticProposal, MechanicOutput
    from app.lab import loop_limits
    adapter = TypeAdapter(DiagnosticProposal) if prompt == 'diagnosis.md' else TypeAdapter(MechanicOutput)
    m = SimpleNamespace(provider=SimpleNamespace(role_model=lambda role: MECHANIC_MODEL), metadata=None)
    return loop_limits.mechanic_request_bound(m, prompt, adapter, context)


def explorer_size(context, model):
    from app.agents.explorer import PROMPT, CHALLENGER
    from app.contracts.tokens import input_token_bound
    messages = [{'role': 'system', 'content': PROMPT + '\n' + CHALLENGER}, {'role': 'user', 'content': canonical_json(context)}]
    return input_token_bound(messages, model)


async def main(out):
    from app.config import Settings
    from app.contracts.models import Campaign, MODEL_INPUT_TOKEN_LIMIT
    from app.lab import citation_status
    from app.lab.coordinator import LabCoordinator
    from app.lab.operator_actions import register_agent
    from app.lab.run_plans import prepare_run_plan, read_run_plan
    from app.lab.diagnosis import V2_MEMORY
    from test_discovery_v2_flow import EXPLORER_MODEL, request
    result = {'saved_store': SAVED}
    if SCRATCH.exists(): shutil.rmtree(SCRATCH)
    SCRATCH.mkdir(parents=True)
    target = SCRATCH / 'lab.sqlite3'
    copy_store(target)
    try:
        db = sqlite3.connect(f'file:{target}?mode=ro', uri=True)
        independent = {}
        for name, cid in (('v2e', V2E), ('v2d', V2D)):
            counter, rows = independent_rows(db, cid)
            independent[name] = {'counterexample_id': counter['counterexample_id'], 'rows': rows}
        db.close()
        result['independent_raw_sql'] = independent
        owner = LabCoordinator(Settings(faultlab_artifact_dir=str(SCRATCH), wandb_model='deepseek-ai/DeepSeek-V3.1',
                                        wandb_explorer_model=EXPLORER_MODEL, wandb_mechanic_model=MECHANIC_MODEL))
        try:
            store = owner.store
            registration = register_agent(store, owner.settings, 'smolagents-v2')
            prepared = prepare_run_plan(store, owner.settings, request(owner, registration, discovery_protocol='faultlab-discovery/v4-history-replay'))
            campaign = owner.create(prepared.campaign_request, run_plan=prepared)
            plan = read_run_plan(store, campaign)['plan']
            result['new_plan'] = {'agent': plan['agent'], 'discovery_protocol': plan['discovery']['protocol'],
                                  'has_mechanic_evidence': 'mechanic_evidence' in plan,
                                  'mechanic_evidence_equals_declaration': plan.get('mechanic_evidence') == citation_status.declaration(),
                                  'campaign_rule_is_declaration': citation_status.campaign_rule(store, campaign) == citation_status.declaration()}
            old = {}
            for name, cid in (('v2e', V2E), ('v2d', V2D)):
                c = store.get_model('campaigns', cid, Campaign)
                p = read_run_plan(store, c)['plan']
                old[name] = {'reads': p is not None, 'agent': p['agent'], 'has_mechanic_evidence': 'mechanic_evidence' in p,
                             'campaign_rule': citation_status.campaign_rule(store, c)}
            result['old_plans_in_copy'] = old
            comparisons = {}
            for name, cid in (('v2e', V2E), ('v2d', V2D)):
                counter, plain = await product_diagnosis(owner, store, campaign, cid, False)
                _, got = await product_diagnosis(owner, store, campaign, cid, True)
                block = got.get(citation_status.BLOCK)
                ind = {r['episode_id']: r for r in independent[name]['rows']}
                agree = all(ind[r['episode_id']]['cited'] == r['cited'] and ind[r['episode_id']]['decoded'] == r['decoded']
                            and ind[r['episode_id']]['undecoded_recorded'] == r['undecoded'] for r in block['episodes'])
                others_equal = ({k: v for k, v in got.items() if k not in (citation_status.BLOCK, 'runtime_contract')}
                                == {k: v for k, v in plain.items() if k != 'runtime_contract'})
                rc_plain, rc_got = plain['runtime_contract'], got['runtime_contract']
                rc_only_memory = ({**rc_got, 'actor_contract': {k: v for k, v in rc_got['actor_contract'].items() if k != 'memory'}}
                                  == {**rc_plain, 'actor_contract': {k: v for k, v in rc_plain['actor_contract'].items() if k != 'memory'}})
                block_only = mechanic_size({'native_citation_status': block}, 'diagnosis.md') - mechanic_size({}, 'diagnosis.md')
                comparisons[name] = {
                    'block': block, 'block_rows_match_independent_sql': agree,
                    'block_episode_order_is_source_then_reproductions': [r['episode_id'] for r in block['episodes']] == [counter.source_episode_id, *counter.reproduction_trial_ids],
                    'every_other_field_identical': others_equal, 'runtime_contract_differs_only_in_memory': rc_only_memory,
                    'plain_memory_is_V2_MEMORY': rc_plain['actor_contract']['memory'] == V2_MEMORY,
                    'rule_memory_is_pointer_text': rc_got['actor_contract']['memory'] == citation_status.V2_MEMORY_WITH_CITATION_STATUS,
                    'tokens_plain': mechanic_size(plain, 'diagnosis.md'), 'tokens_with_block': mechanic_size(got, 'diagnosis.md'),
                    'block_marginal_tokens_in_empty_context': block_only}
                comparisons[name]['tokens_added'] = comparisons[name]['tokens_with_block'] - comparisons[name]['tokens_plain']
            result['diagnosis_requests'] = comparisons
            # v2d's recorded challenge Explorer requests, with the block added exactly as the wrapper would.
            challenge = []
            for row in store.list_records('selections'):
                if not row.get('challenge') or (row.get('context') or {}).get('campaign_id') != V2D: continue
                ctx = row['context']; model = row.get('model_id')
                withb = citation_status.attach(store, ctx, request_kind='explorer_challenge')
                usage = row.get('usage') or {}
                challenge.append({'proposal_index': ctx.get('proposal_index'), 'model': model,
                                  'episodes_in_block': len(withb.get(citation_status.BLOCK, {}).get('episodes', [])),
                                  'rows': [(r['cited'], r['decoded'], len(r['undecoded'])) for r in withb.get(citation_status.BLOCK, {}).get('episodes', [])],
                                  'tokens_recorded_context': explorer_size(ctx, model), 'tokens_with_block': explorer_size(withb, model),
                                  'provider_reported_input_tokens': usage.get('input_tokens')})
            challenge.sort(key=lambda r: r['proposal_index'] if r['proposal_index'] is not None else -1)
            result['v2d_challenge_explorer_requests'] = challenge
            result['input_token_limit'] = MODEL_INPUT_TOKEN_LIMIT
            # v2d's refused candidate request (34 episodes): block, size, compaction.
            from test_loop_limits_mechanic_context import rebuild_v2d_request
            from app.lab import loop_limits
            counter, context = rebuild_v2d_request(store)
            attached = citation_status.attach(store, context, request_kind='mechanic_proposal')
            bound = lambda value: mechanic_size(value, 'mechanic.md')
            full = bound(attached)
            req, summary = loop_limits.compact_request(attached, request_kind='mechanic_proposal', store=store, bound=bound, full_bound=full,
                                                       protected_episode_ids=[counter.source_episode_id, *counter.reproduction_trial_ids])
            req0, summary0 = loop_limits.compact_request(context, request_kind='mechanic_proposal', store=store, bound=bound, full_bound=bound(context),
                                                         protected_episode_ids=[counter.source_episode_id, *counter.reproduction_trial_ids])
            rows = attached[citation_status.BLOCK]['episodes']
            result['v2d_refused_candidate_request'] = {
                'tokens_without_block': bound(context), 'tokens_with_block': full, 'episodes_in_block': len(rows),
                'rows_all_zero_undecoded': all(r['undecoded'] == [] for r in rows),
                'rows_cited_equals_decoded': all(r['cited'] == r['decoded'] for r in rows),
                'null_rows': sum(1 for r in rows if r['cited'] is None),
                'with_block_attempts': [a['request_tokens'] for a in summary['attempts']], 'with_block_fits': summary['fits'],
                'with_block_stages_applied': summary['stages_applied'],
                'without_block_attempts': [a['request_tokens'] for a in summary0['attempts']], 'without_block_fits': summary0['fits'],
                'block_unchanged_by_compaction': req[citation_status.BLOCK] == attached[citation_status.BLOCK],
                'kept_evidence_episodes': len(req['development_evidence']['episodes']),
                'block_rows_for_episodes_not_in_compacted_evidence': len({r['episode_id'] for r in rows} - {r['episode_id'] for r in req['development_evidence']['episodes']}
                                                                         - {r['episode_id'] for item in req.get('challenge_counterexamples') or [] for r in item['evidence']['episodes']})}
        finally:
            await owner.close()
    finally:
        shutil.rmtree(SCRATCH, ignore_errors=True)
        result['scratch_deleted'] = not SCRATCH.exists()
    Path(out).write_text(json.dumps(result, indent=1, sort_keys=True, default=str) + '\n')
    print(json.dumps({k: v for k, v in result.items() if k != 'independent_raw_sql'}, indent=1, sort_keys=True, default=str)[:12000])


if __name__ == '__main__':
    asyncio.run(main(sys.argv[1]))
