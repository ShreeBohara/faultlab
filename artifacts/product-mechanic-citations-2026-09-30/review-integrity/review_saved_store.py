"""Integrity review ($0, offline, read-only): independent check of the native_citation_status block on a scratch copy of
the saved native-v2b store. Run from faultlab/backend with the project .venv:
  ../.venv/bin/python -B ../artifacts/product-mechanic-citations-2026-09-30/review-integrity/review_saved_store.py OUT.json
Uses the builder's guard (refuses .env and non-loopback sockets). Copies the store with mode=ro&immutable=1 to
/Users/shree/FaultLab_Scratch/review-integrity/ and deletes the copy at the end.
Independent parts: rows are recomputed from raw SQL over the events table (not through citation_status), and the
wrapped vs plain requests are diffed key by key.
"""
import asyncio, json, sqlite3, sys, shutil
from pathlib import Path
sys.path.insert(0, '/Users/shree/Desktop/Coreweave_AGI_Hackthon/faultlab/artifacts/product-mechanic-citations-2026-09-30/builder')
import guard  # noqa
sys.path.insert(0, str(Path.cwd() / 'tests' / 'lab'))
import citation_status_saved as saved
from app.lab import citation_status, loop_limits
from app.lab.storage import ReadOnlyLabStore
from app.lab.diagnosis import V2_MEMORY

SCRATCH = Path('/Users/shree/FaultLab_Scratch/review-integrity/store')
V21 = 'faultlab-native-adapter/v2.1-shown-order-labels'


def raw_rows(db, episode_ids):
    """Independent: last PUBLIC actor report_submitted event per episode, straight from SQL."""
    out = []
    for e in episode_ids:
        found = None; private_reports = 0
        for (payload,) in db.execute('SELECT payload FROM events WHERE episode_id=? ORDER BY seq', (e,)):
            ev = json.loads(payload)
            if ev.get('type') == 'report_submitted' and ev.get('role') == 'actor':
                if ev.get('visibility') == 'PRIVATE_EVALUATOR': private_reports += 1; continue
                found = ev.get('payload') or {}
        if not found or found.get('citation_protocol') != V21:
            out.append({'episode_id': e, 'cited': None, 'decoded': None, 'undecoded': None, 'private_reports': private_reports}); continue
        cited = found['cited_evidence_tokens']; shown = set(found['labels_shown_to_agent'])
        und = [t for t in cited if t not in shown]
        # delivered check, independent of the adapter's label map: decoded id must be an observation in the evidence record
        out.append({'episode_id': e, 'cited': len(cited), 'decoded': len(cited) - len(und), 'undecoded': und,
                    'adapter_undecoded': found['cited_tokens_not_decoded'], 'private_reports': private_reports,
                    'decoded_ids': [d for t, d in zip(cited, found['decoded_evidence_ids']) if t in shown]})
    return out


async def main(out):
    SCRATCH.mkdir(parents=True, exist_ok=True)
    target = SCRATCH / 'lab.sqlite3'
    saved.copy_read_only(saved.SAVED_STORE, target)
    result = {}
    try:
        db = sqlite3.connect(f'file:{target}?mode=ro', uri=True)
        store = ReadOnlyLabStore(target)
        mech = type('M', (), {'provider': type('P', (), {'role_model': staticmethod(lambda role: saved.MECHANIC_MODEL)})(), 'metadata': None})()
        from pydantic import TypeAdapter
        from app.contracts.models import DiagnosticProposal, EvidenceBundle, canonical_json
        size = lambda v: loop_limits.mechanic_request_bound(mech, 'diagnosis.md', TypeAdapter(DiagnosticProposal), v)
        for name, cid in (('v2e', saved.V2E), ('v2d', saved.V2D)):
            counter, plain = await saved.rebuild_diagnosis_request(store, cid)
            _, got = await saved.rebuild_diagnosis_request(store, cid, wrap=lambda m: citation_status.CitationStatusMechanic(m, store))
            changed_keys = sorted(k for k in set(plain) | set(got) if plain.get(k) != got.get(k))
            rc_changed = sorted(k for k in set(plain['runtime_contract']) | set(got['runtime_contract'])
                                if plain['runtime_contract'].get(k) != got['runtime_contract'].get(k))
            ac_changed = sorted(k for k in set(plain['runtime_contract']['actor_contract']) | set(got['runtime_contract']['actor_contract'])
                                if plain['runtime_contract']['actor_contract'].get(k) != got['runtime_contract']['actor_contract'].get(k))
            memory_suffix = got['runtime_contract']['actor_contract']['memory'][len(V2_MEMORY):]
            ep_ids = [r['episode_id'] for r in got['native_citation_status']['episodes']]
            indep = raw_rows(db, ep_ids)
            block_rows = got['native_citation_status']['episodes']
            match = all(b == {k: i[k] for k in ('episode_id', 'cited', 'decoded', 'undecoded')} for b, i in zip(block_rows, indep))
            # delivered: every decoded id is an observation in that episode's saved evidence bundle
            delivered = []
            for i in indep:
                bundle = EvidenceBundle.model_validate_json(canonical_json(store.get_record('evidence', i['episode_id'])))
                obs = {o.evidence_id for o in bundle.observations}
                delivered.append(all(d in obs for d in i.get('decoded_ids') or []))
            # what the Mechanic already saw about checks (count of failed findings per episode) -- no names printed
            checks = plain['observations']['checks']
            failed_in_plain = {r['episode_id']: sum(1 for c in (checks[r['check_row']] or []) if isinstance(c, dict) and c.get('passed') is False)
                               for r in plain['observations']['episodes']}
            block_text = canonical_json(got['native_citation_status']).lower()
            result[name] = {'campaign': cid, 'changed_top_keys': changed_keys, 'runtime_contract_changed_keys': rc_changed,
                            'actor_contract_changed_keys': ac_changed, 'memory_suffix': memory_suffix,
                            'plain_memory_is_V2_MEMORY': plain['runtime_contract']['actor_contract']['memory'] == V2_MEMORY,
                            'block_keys': sorted(got['native_citation_status']), 'row_keys': sorted({tuple(r) for r in block_rows}),
                            'rows': block_rows, 'independent_rows_match': match,
                            'adapter_undecoded_equals_recomputed': all(i.get('adapter_undecoded') == i['undecoded'] for i in indep),
                            'private_report_events': sum(i['private_reports'] for i in indep),
                            'every_decoded_id_delivered': delivered,
                            'episodes_with_failed_findings_already_in_plain_request': {k[-8:]: v for k, v in failed_in_plain.items()},
                            'scoring_words_in_block': [w for w in ('check', 'fail', 'violat', 'verdict', 'scor', 'c5', 'c3', 'truthful', 'pass')
                                                       if w in block_text],
                            'tokens_plain': size(plain), 'tokens_with_block': size(got)}
        # Scan every native v2.1 report in the store: is there any real episode with an undecoded token?
        eps = {}
        for (episode_id, payload) in db.execute("SELECT episode_id,payload FROM events"):
            ev = json.loads(payload)
            if ev.get('type') == 'report_submitted' and ev.get('role') == 'actor' and ev.get('visibility') != 'PRIVATE_EVALUATOR':
                p = ev.get('payload') or {}
                if p.get('citation_protocol') == V21: eps[episode_id] = p
        with_undecoded = [e for e, p in eps.items() if p['cited_tokens_not_decoded']]
        sample = with_undecoded[:3]
        blk = citation_status.block(store, sample)['episodes'] if sample else []
        result['store_scan'] = {'v21_reports': len(eps), 'episodes_with_undecoded': len(with_undecoded),
                                'block_rows_for_first_3_with_undecoded': [{**r, 'episode_id': r['episode_id'][-8:]} for r in blk],
                                'raw_rows_for_same': [{k: (v[-8:] if k == 'episode_id' else v) for k, v in r.items() if k in ('episode_id', 'cited', 'decoded', 'undecoded')} for r in raw_rows(db, sample)]}
        store.close(); db.close()
    finally:
        removed = saved.remove_copy(target)
        shutil.rmtree(SCRATCH, ignore_errors=True)
        result['scratch_copy_removed'] = removed and not SCRATCH.exists()
    Path(out).write_text(json.dumps(result, indent=1, sort_keys=True) + '\n')
    print(json.dumps(result, indent=1, sort_keys=True))

asyncio.run(main(sys.argv[1]))
