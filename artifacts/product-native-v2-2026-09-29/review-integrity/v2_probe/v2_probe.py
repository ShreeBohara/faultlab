"""Integrity reviewer's adversarial v2 probe (offline, $0). Working tree only.

Usage: python v2_probe.py ROOT LABEL OUT_JSON

Runs native adapter v1 and v2 on the same scripted episodes (deterministic IDs) and checks:
  1. ordinary turns: v2 bytes == v1 bytes with each real evidence_id replaced by its journal label;
  2. final turns: the only differences are the offered tool list and the response_contract kwarg;
  3. no real evidence ID ever reaches the v2 model transport;
  4. 'hidden_hook_read': a non-blocking before_confirmation hook read is written to the journal but is never
     shown to the agent (v1 or v2). Does v2 still decode that observation's label if the agent writes it?
Same safety as v1_probe (no .env open, no socket, scripted transport).
"""
import sys
from pathlib import Path

exec(compile(Path(__file__).with_name('_common.py').read_text(), '_common.py', 'exec'))

from app.integrations.external_agent_v2 import SmolagentsActorV2, FINAL_TURN_TOOL_DESCRIPTION  # noqa: E402
import re  # noqa: E402

REAL = re.compile(r'evidence-[0-9a-f]{32}')


def s_hidden(call, m):
    """Upgrade, confirm (a non-blocking before_confirmation read lands in the journal, unseen), then cite every
    label the agent was shown PLUS the one missing label in the obs-1..obs-N sequence (a guess)."""
    if call == 1:
        return {'name': 'update_order', 'arguments': {'desired_shipping': 'express'}}
    if call == 2:
        return {'name': 'send_confirmation', 'arguments': {}}
    shown = shown_ids(m)
    nums = sorted(int(x[4:]) for x in shown if x.startswith('obs-') and x[4:].isdigit())
    missing = [f'obs-{n}' for n in range(1, max(nums) + 1) if n not in nums] if nums else []
    return report(shown + missing)


def s_hidden_v1(call, m):
    """v1 equivalent: cite the IDs shown (no way to write the unseen observation's real ID)."""
    if call <= 2:
        return s_hidden(call, m)
    return report(shown_ids(m))


EPISODES_V2 = dict(EPISODES)
EPISODES_V2['hidden_hook_read'] = dict(script=s_hidden, policy=BLOCK_CONFIRMATION)


def final_flag(req):
    return json.loads(req['messages'][-1]['content']).get('final_report_required')


def main():
    out = {'label': LABEL, 'episodes': {}}
    for name, spec in EPISODES_V2.items():
        v1spec = dict(spec, script=s_hidden_v1) if name == 'hidden_hook_read' else spec
        v1 = asyncio.run(episode(name, v1spec, SmolagentsActor))
        v2 = asyncio.run(episode(name, spec, SmolagentsActorV2))
        ids = v2['journal_ids']
        labels = {e: f'obs-{i}' for i, e in enumerate(ids, 1)}
        rows = []
        for i, (a, b) in enumerate(zip(v1['requests'], v2['requests']), 1):
            ta = json.dumps(a['messages'], ensure_ascii=False)
            for e, lab in labels.items():
                ta = ta.replace(e, lab)
            tb = json.dumps(b['messages'], ensure_ascii=False)
            row = {'request': i, 'final_turn_v2': final_flag(b), 'v2_equals_v1_relabelled': ta == tb,
                   'kwargs_v1': a['kwargs'], 'kwargs_v2': b['kwargs'], 'real_id_in_v2_request': bool(REAL.search(tb))}
            if final_flag(b) and ta != tb:
                # Allowed final-turn difference: only the transport message's tool list.
                ma, mb = json.loads(ta), b['messages']
                same_prefix = ma[:-1] == mb[:-1]
                la, lb = json.loads(ma[-1]['content']), json.loads(mb[-1]['content'])
                row['final_turn_prefix_identical'] = same_prefix
                row['final_turn_transport_diff_keys'] = sorted(k for k in set(la) | set(lb) if la.get(k) != lb.get(k))
                row['final_turn_tools_v2'] = lb['tools']
            rows.append(row)
        submitted = v2['report_submitted_payloads']
        out['episodes'][name] = {
            'v1_requests': len(v1['requests']), 'v2_requests': len(v2['requests']),
            'v1_outcome': v1['outcome'], 'v2_outcome': v2['outcome'],
            'journal_ids': ids, 'rows': rows,
            'v2_report_submitted': submitted,
            'v1_event_types': v1['event_types'], 'v2_event_types': v2['event_types'],
        }
        if name == 'hidden_hook_read':
            last = v2['requests'][-1]
            shown_v2 = shown_ids(last['messages'])
            shown_v1 = shown_ids(v1['requests'][-1]['messages'])
            hidden = [e for e in ids if e not in shown_v1]
            hidden_labels = [labels[e] for e in hidden]
            rep = v2['outcome'].get('report', {})
            out['episodes'][name]['analysis'] = {
                'journal_size_at_report': len(ids),
                'labels_shown_to_v2_agent': shown_v2,
                'real_ids_shown_to_v1_agent': shown_v1,
                'journal_observations_never_shown_to_either_agent': hidden,
                'their_labels': hidden_labels,
                'v2_cited_tokens': submitted[0]['cited_evidence_tokens'] if submitted else None,
                'v2_decoded_ids': rep.get('evidence_ids'),
                'unseen_observation_label_was_decoded_to_its_real_id': bool(hidden) and all(e in (rep.get('evidence_ids') or []) for e in hidden),
                'labels_shown_to_agent_recorded': submitted[0].get('labels_shown_to_agent') if submitted else None,
            }
    out['blocked_network_or_env'] = BLOCKED
    OUT.write_text(json.dumps(out, indent=1, sort_keys=True, ensure_ascii=False) + '\n')
    for name, ep in out['episodes'].items():
        ordinary = [r for r in ep['rows'] if not r['final_turn_v2']]
        finals = [r for r in ep['rows'] if r['final_turn_v2']]
        print(f"{name}: v1 {ep['v1_requests']} req, v2 {ep['v2_requests']} req | ordinary turns v2==v1 relabelled: "
              f"{all(r['v2_equals_v1_relabelled'] and r['kwargs_v1'] == r['kwargs_v2'] for r in ordinary)} ({len(ordinary)}) | "
              f"final turns: {[(r['v2_equals_v1_relabelled'], r.get('final_turn_prefix_identical'), r.get('final_turn_transport_diff_keys'), r['kwargs_v2'].get('response_contract')) for r in finals]} | "
              f"real ID in any v2 request: {any(r['real_id_in_v2_request'] for r in ep['rows'])} | "
              f"v1 {str(ep['v1_outcome'])[:50]} | v2 {str(ep['v2_outcome'])[:50]}")
    print('hidden_hook_read analysis:', json.dumps(out['episodes']['hidden_hook_read']['analysis'], indent=1))
    print('blocked', BLOCKED)


main()
