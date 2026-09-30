"""Rebuild, offline and at $0, live runs v2e's and v2d's Mechanic requests with and without the native citation-status
block (faultlab-mechanic-evidence/v2-native-citation-status), from a scratch copy of the saved store.

Run from faultlab/backend with the project .venv:
  ../.venv/bin/python -B ../artifacts/product-mechanic-citations-2026-09-30/builder/rebuild_requests.py OUT.json EXCERPT.json

* Copies /Users/shree/FaultLab_Runs/2026-09-30/native-v2b/lab.sqlite3 (opened mode=ro&immutable=1) to
  /Users/shree/FaultLab_Scratch/mechanic-citations-builder/, opens the copy read-only, deletes it at the end.
* Diagnosis requests (v2e, v2d): the real Diagnostician builds each context (the Mechanic is a capture that raises
  before anything is sent or saved); then the real citation_status.CitationStatusMechanic wraps the capture.
* v2d's refused candidate request (33,223 tokens): the loop-limits test's rebuild, then citation_status.attach, then
  the real compaction (loop_limits.compact_request).
Counts use the Mechanic's own admission count (loop_limits.mechanic_request_bound, frozen tokenizer). The guard refuses
the real .env and every non-loopback connection.
"""
import asyncio
import json
import re
import sys
from pathlib import Path
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import guard  # noqa: E402,F401  (refuses .env and outbound connections; adds backend and backend/tests to sys.path)
sys.path.insert(0, str(Path.cwd() / 'tests' / 'lab'))

from pydantic import TypeAdapter  # noqa: E402
from app.contracts.models import DiagnosticProposal, MechanicOutput, canonical_json  # noqa: E402
from app.lab import citation_status, loop_limits  # noqa: E402
from app.lab.diagnosis import V2_MEMORY  # noqa: E402
from app.lab.storage import ReadOnlyLabStore  # noqa: E402
import citation_status_saved as saved  # noqa: E402
from test_loop_limits_mechanic_context import rebuild_v2d_request  # noqa: E402

SCRATCH = Path('/Users/shree/FaultLab_Scratch/mechanic-citations-builder')
PROVIDER_REPORTED = {saved.V2E: 8952, saved.V2D: 8854}   # input_tokens in each campaign's diagnosis mechanic_outputs record
MECHANIC = SimpleNamespace(provider=SimpleNamespace(role_model=lambda role: saved.MECHANIC_MODEL), metadata=None)


def bound(prompt, adapter, context):
    return loop_limits.mechanic_request_bound(MECHANIC, prompt, adapter, context)


def diagnosis_bound(context):
    return bound('diagnosis.md', TypeAdapter(DiagnosticProposal), context)


def proposal_bound(context):
    return bound('mechanic.md', TypeAdapter(MechanicOutput), context)


def block_only_tokens(block):
    """Tokens of the block alone as one message (an indication; the request difference is the exact cost)."""
    from app.contracts.tokens import input_token_bound
    return input_token_bound([{'role': 'user', 'content': canonical_json(block)}], saved.MECHANIC_MODEL)


def fake_ids(value):
    """The same text with every episode/evidence/counterexample/intervention ID replaced by a short fake one, consistently."""
    text = canonical_json(value); names = {}
    def swap(match):
        kind = match.group(1)
        if match.group(0) not in names:
            names[match.group(0)] = f'{kind}-FAKE{sum(1 for k in names if k.startswith(kind)) + 1:02d}'
        return names[match.group(0)]
    return json.loads(re.sub(r'\b(episode|evidence|counterexample|intervention|campaign|diagnostic)-[0-9a-f]{24,32}\b', swap, text))


async def diagnosis(store, campaign_id):
    counter, before = await saved.rebuild_diagnosis_request(store, campaign_id)
    _, after = await saved.rebuild_diagnosis_request(store, campaign_id, wrap=lambda m: citation_status.CitationStatusMechanic(m, store))
    rest_after = {k: v for k, v in after.items() if k not in (citation_status.BLOCK, 'runtime_contract')}
    rest_before = {k: v for k, v in before.items() if k != 'runtime_contract'}
    contract_after = {**after['runtime_contract'], 'actor_contract': {**after['runtime_contract']['actor_contract'], 'memory': V2_MEMORY}}
    rows = after[citation_status.BLOCK]['episodes']
    return counter, before, after, {
        'campaign_id': campaign_id, 'counterexample_id': counter.counterexample_id, 'target_invariant': counter.target_invariant,
        'provider_reported_input_tokens': PROVIDER_REPORTED[campaign_id],
        'rebuilt_request_tokens_without_block': diagnosis_bound(before),
        'request_tokens_with_block': diagnosis_bound(after),
        'block_cost_tokens': diagnosis_bound(after) - diagnosis_bound(before),
        'block_alone_tokens': block_only_tokens(after[citation_status.BLOCK]),
        'every_other_field_unchanged': rest_after == rest_before and contract_after == before['runtime_contract'],
        'memory_before_is_v2_memory': before['runtime_contract']['actor_contract']['memory'] == V2_MEMORY,
        'memory_after_is_v2_memory_plus_pointer': after['runtime_contract']['actor_contract']['memory'] == citation_status.V2_MEMORY_WITH_CITATION_STATUS,
        'episodes_in_evidence': [row['episode_id'] for row in before['observations']['episodes']],
        'block_rows': rows,
        'every_episode_zero_undecoded': all(row['undecoded'] == [] for row in rows),
        'every_cited_token_decoded': all(row['cited'] == row['decoded'] for row in rows),
    }


async def main(out, excerpt_out):
    SCRATCH.mkdir(parents=True, exist_ok=True)
    copy = SCRATCH / 'rebuild-requests-copy.sqlite3'
    saved.copy_read_only(saved.SAVED_STORE, copy)
    try:
        store = ReadOnlyLabStore(copy)
        try:
            result = {}
            excerpt = {}
            for name, campaign_id in (('v2e', saved.V2E), ('v2d', saved.V2D)):
                counter, before, after, summary = await diagnosis(store, campaign_id)
                result[f'{name}_diagnosis'] = summary
                if name == 'v2e':
                    excerpt = {
                        'note': ('v2e diagnosis request, rebuilt from a scratch copy of the saved store; IDs replaced by fake '
                                 'ones consistently; only the changed parts and the first evidence row are shown.'),
                        'before': {'runtime_contract.actor_contract.memory': before['runtime_contract']['actor_contract']['memory'],
                                   'native_citation_status': '(absent)',
                                   'observations.episodes[0]': before['observations']['episodes'][0]},
                        'after': {'runtime_contract.actor_contract.memory': after['runtime_contract']['actor_contract']['memory'],
                                  'native_citation_status': after[citation_status.BLOCK],
                                  'observations.episodes[0]': after['observations']['episodes'][0]},
                    }
                    excerpt = fake_ids(excerpt)
            # v2d's refused candidate request: the block is added before the size rule counts it.
            counter, context = rebuild_v2d_request(store)
            full = proposal_bound(context)
            attached = citation_status.attach(store, context, request_kind='mechanic_proposal')
            with_block = proposal_bound(attached)
            protected = [counter.source_episode_id, *counter.reproduction_trial_ids]
            compacted, summary = loop_limits.compact_request(attached, request_kind='mechanic_proposal', store=store, bound=proposal_bound,
                                                             full_bound=with_block, protected_episode_ids=protected)
            plain, plain_summary = loop_limits.compact_request(context, request_kind='mechanic_proposal', store=store, bound=proposal_bound,
                                                               full_bound=full, protected_episode_ids=protected)
            kept = set()
            for path in (('development_evidence',), ('challenge_counterexamples', 0, 'evidence')):
                value = compacted
                for key in path: value = value[key]
                kept |= {row['episode_id'] for row in value['episodes']}
            rows = compacted[citation_status.BLOCK]['episodes']
            result['v2d_candidate_request'] = {
                'request_tokens_without_block': full, 'request_tokens_with_block': with_block, 'block_cost_tokens': with_block - full,
                'block_alone_tokens': block_only_tokens(attached[citation_status.BLOCK]),
                'episodes_in_block': len(rows), 'episodes_with_zero_undecoded': sum(1 for r in rows if r['undecoded'] == []),
                'episodes_with_every_cited_token_decoded': sum(1 for r in rows if r['cited'] is not None and r['cited'] == r['decoded']),
                'episodes_without_recorded_report': sum(1 for r in rows if r['cited'] is None),
                'compaction_without_block': {'fits': plain_summary['fits'], 'attempts': [a['request_tokens'] for a in plain_summary['attempts']],
                                             'stages_applied': plain_summary['stages_applied']},
                'compaction_with_block': {'fits': summary['fits'], 'attempts': [a['request_tokens'] for a in summary['attempts']],
                                          'stages_applied': summary['stages_applied'], 'compacted_tokens': summary['compacted_tokens']},
                'block_unchanged_by_compaction': compacted[citation_status.BLOCK] == attached[citation_status.BLOCK],
                'kept_episodes_all_in_block': kept <= {r['episode_id'] for r in rows},
                'within_target': summary['compacted_tokens'] is not None and summary['compacted_tokens'] <= loop_limits.COMPACTION_TARGET_TOKENS,
            }
        finally:
            store.close()
    finally:
        result['scratch_copy_deleted'] = saved.remove_copy(copy)
    Path(out).write_text(json.dumps(result, indent=1, sort_keys=True) + '\n')
    Path(excerpt_out).write_text(json.dumps(excerpt, indent=1, sort_keys=True) + '\n')
    print(json.dumps({k: {kk: vv for kk, vv in v.items() if kk not in ('block_rows', 'episodes_in_evidence')} if isinstance(v, dict) else v
                      for k, v in result.items()}, indent=1, sort_keys=True))


if __name__ == '__main__':
    asyncio.run(main(sys.argv[1], sys.argv[2]))
