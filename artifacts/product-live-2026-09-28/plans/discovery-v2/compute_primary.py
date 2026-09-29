"""Pre-declared read-out for the discovery-v2 run plan ($0, read-only, JSON files only).

Declared with PLAN.md before any paid request. It opens no SQLite store, starts no
service, imports no FaultLab module and makes no network call. Inputs are the two JSON
files the product itself produces for a campaign:

  --search-attempts  GET http://127.0.0.1:8000/api/campaigns/<ID>/search-attempts
  --export           ./scripts/export-evidence.sh --campaign <ID> --output <file>

Primary: fully-fired discovery slots out of 8. A slot is FULLY FIRED when it ran one
discovery Actor episode whose lifecycle is COMPLETED and every scheduled fault in that
episode's verdict has triggered=true. A slot with no episode (refused, duplicate, or
never reached), a LAB_ERROR / INTERRUPTED episode, an episode with no scheduled fault,
or a partly/never-triggered episode is NOT fully fired. Campaign c701e850 scores 4 of 8.

Mapping slot -> episode: each slot runs at most one discovery episode, in slot order, so
the n-th SELECTED selection (ordered by selection_index, then slot_request) is the n-th
discovery episode (ordered by started_at). The mapping is cross-checked: the episode's
scenario_hash must equal sha256 of the selected recipe's canonical JSON (FaultLab's
content_hash). Any mismatch is reported and makes the read-out INVALID.

Usage:
  python3 compute_primary.py --search-attempts SA.json --export EXPORT.json [--slots 8] [--out RESULT.json]
"""
import argparse
import hashlib
import json
import sys
from collections import Counter

REFUSED = ('SKIPPED_UNREACHABLE', 'SKIPPED_DUPLICATE', 'PRECHECK_FAILED', 'INVALID_OUTPUT')


def content_hash(value):
    # Same encoding as app.contracts.models.canonical_json / content_hash.
    text = json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False)
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def primitive_key(p):
    return f"{p['kind']} {p['target_service']}.{p['target_tool']} #{p['occurrence']}"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument('--search-attempts', required=True)
    parser.add_argument('--export', required=True)
    parser.add_argument('--slots', type=int, default=8)
    parser.add_argument('--out')
    args = parser.parse_args(argv)

    with open(args.search_attempts) as f: attempts = json.load(f)
    with open(args.export) as f: export = json.load(f)
    campaign_id = export.get('campaign_id') or (export.get('campaign') or {}).get('campaign_id')
    problems = []

    if any(row.get('campaign_id') != campaign_id for row in attempts):
        problems.append('search-attempts rows belong to a different campaign than the export')

    rows = sorted(attempts, key=lambda r: (r['selection_index'], r['search_decision'].get('slot_request', 1)))
    episodes = sorted([e for e in export.get('episodes', [])
                       if e.get('experiment_purpose') == 'discovery' and e.get('study_id') == campaign_id],
                      key=lambda e: e['started_at'])
    selected = [r for r in rows if r['search_decision']['status'] == 'SELECTED']
    if len(selected) != len(episodes):
        problems.append(f'{len(selected)} SELECTED selections but {len(episodes)} discovery episodes')

    by_selection = {}
    for row, episode in zip(selected, episodes):
        recipe = row['selected_output']['fault_spec']
        if content_hash(recipe) != episode['scenario_hash']:
            problems.append(f"selection {row['selection_ref']} does not match episode {episode['episode_id']} (scenario hash)")
        by_selection[row['selection_ref']] = episode

    slots = []
    for index in range(args.slots):
        slot_rows = [r for r in rows if r['selection_index'] == index]
        ran = next((r for r in slot_rows if r['search_decision']['status'] == 'SELECTED'), None)
        slot = {'slot': index, 'requests': len(slot_rows),
                'decisions': [r['search_decision']['status'] + (' (re-plan)' if r['search_decision'].get('slot_request') == 2 else '')
                              for r in slot_rows],
                'fallback_used': any(r.get('provenance') == 'fixed_invalid_output_fallback' for r in slot_rows)}
        if not slot_rows:
            slot.update(result='NOT_REACHED', fully_fired=False)
        elif ran is None:
            slot.update(result='NO_EPISODE', fully_fired=False)
        else:
            episode = by_selection.get(ran['selection_ref'])
            recipe = ran['selected_output']['fault_spec']['primitives']
            if episode is None:
                slot.update(result='EPISODE_MISSING', fully_fired=False, recipe=[primitive_key(p) for p in recipe])
            else:
                executions = (episode.get('verdict') or {}).get('fault_executions') or []
                fired = [bool(f.get('triggered')) for f in executions]
                labels = ((ran['search_decision'].get('reachability') or {}).get('faults') or [])
                full = episode['lifecycle'] == 'COMPLETED' and bool(fired) and all(fired)
                slot.update(result='FULLY_FIRED' if full else 'PARTLY_FIRED' if any(fired) else 'NONE_FIRED',
                            fully_fired=full, episode_id=episode['episode_id'], lifecycle=episode['lifecycle'],
                            outcome=(episode.get('verdict') or {}).get('outcome'),
                            recipe=[primitive_key(p) for p in recipe], fired=fired,
                            not_fired_reasons=[f.get('reason') for f in executions if not f.get('triggered')],
                            predicted=[l.get('verdict') for l in labels],
                            actor_requests=(episode.get('usage') or {}).get('model_calls'))
        slots.append(slot)

    decisions = Counter(r['search_decision']['status'] for r in rows)
    replans = [r for r in rows if r['search_decision'].get('slot_request') == 2]
    refusal_codes = Counter(f.get('reason_code') or f.get('verdict')
                            for r in rows if r['search_decision']['status'] == 'SKIPPED_UNREACHABLE'
                            for f in (r['search_decision'].get('reachability') or {}).get('faults', [])
                            if f.get('verdict') != 'FORCED')
    forced_total = sum(1 for s in slots for p in s.get('predicted', []) if p == 'FORCED')
    forced_fired = sum(1 for s in slots for p, f in zip(s.get('predicted', []), s.get('fired', [])) if p == 'FORCED' and f)
    full_kinds = sorted({k.split(' #')[0] for s in slots if s['fully_fired'] for k in s['recipe']})
    result = {
        'campaign_id': campaign_id, 'valid': not problems, 'problems': problems,
        'primary_fully_fired_slots': sum(s['fully_fired'] for s in slots), 'slots_declared': args.slots,
        'baseline_c701e850': 4,
        'slots': slots,
        'secondary': {
            'explorer_requests': len(rows), 'discovery_episodes': len(episodes),
            'decisions': dict(decisions),
            'refused_picks': sum(decisions.get(s, 0) for s in REFUSED),
            'refused_not_forced_or_impossible': decisions.get('SKIPPED_UNREACHABLE', 0),
            'refused_duplicate': decisions.get('SKIPPED_DUPLICATE', 0),
            'refusal_reason_codes': dict(refusal_codes),
            'replans': len(replans),
            'replans_that_ran': sum(r['search_decision']['status'] == 'SELECTED' for r in replans),
            'slots_without_episode': sum(s['result'] in ('NO_EPISODE', 'NOT_REACHED') for s in slots),
            'fallback_slots': sum(s['fallback_used'] for s in slots),
            'forced_faults_fired': f'{forced_fired} of {forced_total}' if forced_total else 'no v2 labels',
            'outcomes': dict(Counter(s.get('outcome') for s in slots if 'outcome' in s)),
            'distinct_fault_targets_fully_fired': full_kinds,
            'multi_fault_or_deeper_fully_fired': sum(1 for s in slots if s['fully_fired'] and
                                                     (len(s['recipe']) > 1 or any(not k.endswith('#1') for k in s['recipe']))),
        },
    }
    text = json.dumps(result, indent=2)
    if args.out:
        with open(args.out, 'x') as f: f.write(text + '\n')
    print(text)
    return 0 if not problems else 1


if __name__ == '__main__':
    sys.exit(main())
