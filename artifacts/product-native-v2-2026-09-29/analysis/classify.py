#!/usr/bin/env python3
"""Classify why the native smolagents agent failed in three saved FaultLab stores.

$0 and read-only:
  * no provider, model, W&B/Weave or other network call (sockets are refused below);
  * every store is opened with a SQLite URI ``file:PATH?mode=ro&immutable=1`` and nothing
    is written under /Users/shree/FaultLab_Runs/;
  * launcher logs are read as text; raw log lines are never copied to the output (only the
    classified error kind, the failing TaskReport field names and the rejected evidence-ID
    strings, which are lab identifiers, not credentials);
  * the ``control-capability`` file in each run folder is never opened.

Data sources per store (record kinds as written by backend/app/lab/storage.py):
  episodes, trials, episode_executions, agent_registrations, events (actor/policy/referee),
  observations (evidence_id -> episode), baseline_studies (case labels), selections,
  counterexamples, reductions, interventions, source_validation_results, challenges, and
  private_episode_inputs.recipe for development-split episodes only (fault schedule label).
  Held-out, promotion or final-audit episodes (split != development or purpose in
  promotion/final_audit/portability) are skipped and counted, never read further.

Launcher log -> episode linkage: the simulator logs one ``POST /control/worlds`` (201) when an
episode's world is created and ``POST /control/worlds/<world_id>/stop`` when it ends; episodes
run one at a time, so every smolagents error printed between the two belongs to that world's
episode. The script checks (a) creates and stops strictly alternate, (b) every exact evidence ID
quoted in a rejected final_answer belongs to that same episode (observations table), and (c) per
episode, dispatched actor calls + logged step errors + submitted report = metered actor turns.

Usage:  python3 classify.py            (writes classify.out.json next to this file)
"""
from __future__ import annotations

import collections
import json
import re
import socket
import sqlite3
import sys
from pathlib import Path


# ---------------------------------------------------------------- network silence guard
def _refuse_network(*args, **kwargs):
    raise RuntimeError('classify.py is offline-only: network access refused')


socket.socket.connect = _refuse_network          # type: ignore[assignment]
socket.socket.connect_ex = _refuse_network       # type: ignore[assignment]
socket.create_connection = _refuse_network       # type: ignore[assignment]
socket.getaddrinfo = _refuse_network             # type: ignore[assignment]

HERE = Path(__file__).resolve().parent
OUT = HERE / 'classify.out.json'
RUNS = [
    ('native-probe', Path('/Users/shree/FaultLab_Runs/2026-09-28/native-probe')),
    ('native-learn', Path('/Users/shree/FaultLab_Runs/2026-09-29/native-learn')),
    ('native-learn-v3', Path('/Users/shree/FaultLab_Runs/2026-09-29/native-learn-v3')),
]
NATIVE_ENTRYPOINT = 'smolagents-toolcalling-v1'
ACTOR_CAP = 8            # EpisodeBudget.actor_calls default, and the run plans' episode_budget
SKIP_PURPOSES = {'promotion', 'final_audit', 'portability'}

BUCKETS = {
    'A': 'final_answer given but rejected by TaskReport validation: evidence-ID format/copying',
    'B': 'final_answer given but rejected for another schema reason',
    'C': 'final available turn spent on a business tool call (refused: Final report required)',
    'D': 'invalid single-tool action (unparseable) on the final turn',
    'E': 'smolagents max_steps / provide_final_answer / step-budget mismatch lost the final turn',
    'F': 'report blocked by a policy hook (before_final_report)',
    'G': 'provider/transport/budget error',
    'H': 'report submitted but judged untruthful by the referee (inferred from failed checks)',
    'U': 'unknown',
}


def open_ro(path: Path) -> sqlite3.Connection:
    db = sqlite3.connect(f'file:{path}?mode=ro&immutable=1', uri=True)
    db.execute('PRAGMA query_only=ON')
    return db


def records(db, kind):
    return [(i, json.loads(p)) for i, p in db.execute(
        'SELECT id,payload FROM records WHERE kind=? ORDER BY rowid', (kind,))]


# ---------------------------------------------------------------- launcher log parsing
CREATE_RE = re.compile(r'"POST /control/worlds HTTP/1\.1" 201')
STOP_RE = re.compile(r'"POST /control/worlds/(world-[0-9a-f]+)/stop HTTP/1\.1"')
BUSINESS_RE = re.compile(r'"(GET|POST) /business/(\S+) HTTP/1\.1" (\d{3})')
ERR_START_RE = re.compile(
    r"^(?:Error executing tool '(?P<tool>[^']+)' with arguments"
    r"|(?P<parse>Error while parsing tool call from model output:)"
    r"|(?P<max>Reached max steps\.))")
FIELD_RE = re.compile(r'^[a-z_][a-z0-9_]*(?:\.[A-Za-z0-9_\-]+)*$')
INPUT_RE = re.compile(r"input_value='([^']*)'")
EXACT_EVIDENCE_RE = re.compile(r'evidence-[0-9a-f]{32}(?![0-9a-f])')
NON_ASCII_RE = re.compile(r'[^\x00-\x7f]+')


def business_tool(path):
    if path.startswith('orders/') and path.endswith('/upgrade'):
        return 'update_order'
    if path.startswith('orders/'):
        return 'get_order'
    if path.startswith('notifications'):
        return 'send_confirmation'
    if path.startswith('operations/'):
        return 'get_operation_status'
    return 'business_other'


def classify_block(lines):
    head = lines[0]
    text = '\n'.join(lines)
    # rich wraps long messages at the console width; phrase checks use the unwrapped text
    flat = re.sub(r'\s+', ' ', ' '.join(line.strip() for line in lines))
    m = ERR_START_RE.match(head)
    if m.group('max'):
        return {'kind': 'MAX_STEPS'}
    if m.group('parse'):
        return {'kind': 'PARSE_INVALID_ACTION',
                'detail': 'External model returned an invalid single-tool action'
                if 'invalid single-tool action' in flat else 'other parse error'}
    tool = m.group('tool')
    if tool == 'final_answer':
        if 'blocked_report' in flat:
            return {'kind': 'FA_BLOCKED_BY_POLICY'}
        if 'Final answer requires the original report' in flat:
            return {'kind': 'FA_SCHEMA_OTHER', 'fields': ['<arguments must be exactly {answer}>']}
        if 'ValidationError' in flat:
            fields = []
            for i, line in enumerate(lines):
                s = line.strip()
                if FIELD_RE.match(s) and i + 1 < len(lines) and lines[i + 1].startswith('  '):
                    fields.append(s)
            inputs = INPUT_RE.findall(text)
            exact = sorted(set(EXACT_EVIDENCE_RE.findall(text)))
            bad = [v for v in inputs if v]
            tokens = sorted({t for v in bad for t in NON_ASCII_RE.findall(v)})
            if fields and all(f.split('.')[0] == 'evidence_ids' for f in fields):
                return {'kind': 'FA_INVALID_EVIDENCE_ID', 'fields': fields, 'rejected_values': bad,
                        'non_ascii_tokens': tokens,
                        'all_rejected_values_contain_non_ascii': bool(bad) and all(NON_ASCII_RE.search(v) for v in bad),
                        'exact_evidence_ids_quoted': exact}
            return {'kind': 'FA_SCHEMA_OTHER', 'fields': fields, 'rejected_values': bad,
                    'exact_evidence_ids_quoted': exact}
        return {'kind': 'FA_OTHER_ERROR'}
    if 'Final report required; business call was not dispatched' in flat:
        return {'kind': 'BUSINESS_REFUSED', 'tool': tool}
    return {'kind': 'TOOL_ERROR_OTHER', 'tool': tool}


def parse_log(path: Path):
    segments, orphans = {}, []
    current, block = None, None
    sequence = []            # C/S markers for the alternation check
    anomalies = []

    def close_block():
        nonlocal block
        if block is not None:
            item = {'type': 'error', **classify_block(block)}
            (current['items'] if current is not None else orphans).append(item)
            block = None

    for raw in path.read_text(encoding='utf-8', errors='replace').splitlines():
        if raw.startswith('INFO:'):
            close_block()
            if CREATE_RE.search(raw):
                sequence.append('C')
                if current is not None:
                    anomalies.append('create before previous stop')
                current = {'items': []}
                continue
            stop = STOP_RE.search(raw)
            if stop:
                sequence.append('S')
                if current is None:
                    anomalies.append('stop without create')
                    continue
                current['world_id'] = stop.group(1)
                segments[stop.group(1)] = current
                current = None
                continue
            biz = BUSINESS_RE.search(raw)
            if biz and current is not None:
                current['items'].append({'type': 'business', 'tool': business_tool(biz.group(2)),
                                         'status': int(biz.group(3))})
            continue
        if ERR_START_RE.match(raw):
            close_block()
            block = [raw]
        elif block is not None:
            block.append(raw)
    close_block()
    alternating = ''.join(sequence) == 'CS' * (len(sequence) // 2)
    return {'segments': segments, 'orphan_errors': orphans, 'alternating': alternating,
            'creates': sequence.count('C'), 'stops': sequence.count('S'), 'anomalies': anomalies}


# ---------------------------------------------------------------- labels
def recipe_label(recipe):
    if not recipe or not recipe.get('primitives'):
        return 'no fault'
    parts = []
    for p in recipe['primitives']:
        params = {k: v for k, v in (p.get('parameters') or {}).items() if v is not None}
        if p['kind'] == 'F2':
            desc = (f"F2 upgrade {params.get('terminal_status')}"
                    + (f"/{params['failure_code']}" if params.get('failure_code') else '')
                    + f" after {params.get('completion_delay_ticks')} ticks")
        elif p['kind'] == 'F1':
            desc = f"F1 {p['target_tool']} response delay {params.get('response_delay_ms')} ms"
        elif p['kind'] == 'F3':
            desc = f"F3 stale get_order ({params.get('versions_back')} version back)"
        elif p['kind'] == 'F4':
            desc = f"F4 {p['target_tool']} fails x{params.get('failure_count')}"
        else:
            desc = f"{p['kind']} {p.get('target_tool')} {params}"
        if p.get('occurrence', 1) != 1:
            desc += f" (occurrence {p['occurrence']})"
        parts.append(desc)
    return ' + '.join(parts)


def build_roles(db):
    """episode_id -> short role text from the product's own stage records."""
    roles = {}
    selections = [i for i, _ in records(db, 'selections')]
    sel_index = {sid: n + 1 for n, sid in enumerate(selections)}
    for cid, cx in records(db, 'counterexamples'):
        short = cid.split('-')[1][:8]
        roles.setdefault(cx['source_episode_id'], f'source of cx {short}')
        for eid in cx.get('reproduction_trial_ids', []):
            roles[eid] = f'reproduction of cx {short}'
    for cid, red in records(db, 'reductions'):
        short = cid.split('-')[1][:8]
        for attempt in red.get('attempts', []):
            for eid in attempt.get('trial_ids', []):
                roles[eid] = f"reduction of cx {short}: {attempt['transform']} ({attempt['reason']})"
    for iid, iv in records(db, 'interventions'):
        short = iv['counterexample_id'].split('-')[1][:8]
        for pair in iv.get('trial_pairs', []):
            for eid in pair:
                roles[eid] = f'intervention on cx {short} ({iv["result"]})'
    for bid, sv in records(db, 'source_validation_results'):
        cand = sv['candidate_version'].split('-')[1][:8]
        for row in sv.get('trial_outcomes', []):
            for eid in row.get('episode_ids', []):
                roles[eid] = f'source validation of policy-{cand} ({sv["classification"]})'
    for chid, ch in records(db, 'challenges'):
        for pair in ch.get('trial_pairs', []):
            for eid in pair:
                roles[eid] = f'challenge ({ch["status"]})'
    return roles, sel_index


# ---------------------------------------------------------------- report inference (bucket H)
def observed_statuses(observations):
    upgrade, notify = [], []
    for o in observations:
        r = o.get('result') or {}
        op = r.get('operation_id') or o.get('observed_operation_id') or ''
        status = r.get('status') or (f"{r.get('transport')}:{r.get('error_code')}" if r.get('error_code') else None)
        if r.get('tool') == 'get_order' or status is None:
            continue
        (upgrade if op.startswith('upgrade-') else notify if op.startswith('notify-') else []).append(status)
    return upgrade, notify


def report_inference(report, observations, failed, caller_of_call):
    upgrade, notify = observed_statuses(observations)
    delivered = {o['evidence_id'] for o in observations}
    cited = report.get('evidence_ids', [])
    notes = []
    last_up = upgrade[-1] if upgrade else 'none'
    last_no = notify[-1] if notify else 'none'
    if report.get('upgrade_outcome') != last_up:
        notes.append(f"report upgrade_outcome={report.get('upgrade_outcome')} but last delivered upgrade status={last_up}")
    if report.get('notification_outcome') not in (last_no, 'NOT_REQUIRED') and not (
            last_no == 'none' and report.get('notification_outcome') == 'NOT_STARTED'):
        notes.append(f"report notification_outcome={report.get('notification_outcome')} but last delivered notification status={last_no}")
    if 'FAILED' in upgrade and report.get('overall') in ('COMPLETED', 'CORRECTLY_REJECTED') and notify:
        notes.append(f"a confirmation was sent after a FAILED upgrade and report overall={report.get('overall')}")
    if report.get('overall') == 'COMPLETED' and (report.get('upgrade_outcome') != 'SUCCEEDED'
                                                 or report.get('notification_outcome') != 'SUCCEEDED'):
        notes.append(f"report overall=COMPLETED while upgrade_outcome={report.get('upgrade_outcome')} "
                     f"and notification_outcome={report.get('notification_outcome')}")
    undelivered = [e for e in cited if e not in delivered]
    if undelivered:
        notes.append(f'{len(undelivered)} cited evidence ID(s) never delivered to this episode')
    by_id = {o['evidence_id']: o for o in observations}
    cited_callers = collections.Counter(caller_of_call.get(by_id[e]['call_id'], 'unknown') if e in by_id else 'not delivered'
                                        for e in cited)
    cited_tools = [((by_id[e].get('result') or {}).get('tool'), (by_id[e].get('result') or {}).get('status'),
                    caller_of_call.get(by_id[e]['call_id'], 'unknown')) if e in by_id else ('not delivered', None, None)
                   for e in cited]
    for field, prefix in (('upgrade_outcome', 'upgrade-'), ('notification_outcome', 'notify-')):
        if report.get(field) != 'SUCCEEDED':
            continue
        cited_status = [(by_id[e].get('result') or {}).get('status') for e in cited if e in by_id
                        and ((by_id[e].get('result') or {}).get('operation_id') or '').startswith(prefix)]
        if 'SUCCEEDED' not in cited_status:
            seen_by = sorted({caller_of_call.get(o['call_id'], 'unknown') for o in observations
                              if (o.get('result') or {}).get('status') == 'SUCCEEDED'
                              and ((o.get('result') or {}).get('operation_id') or '').startswith(prefix)})
            notes.append(f"claims {field}=SUCCEEDED but no cited evidence shows SUCCEEDED for it "
                         f"(cited statuses {cited_status}; a SUCCEEDED observation was delivered via "
                         f"{seen_by or 'no call'})")
    if cited_callers.get('policy'):
        notes.append(f"{cited_callers['policy']} cited evidence ID(s) came from calls made by the policy, not the agent")
    sends = sum(1 for o in observations if (o.get('result') or {}).get('tool') == 'send_confirmation')
    return {'upgrade_statuses_seen': upgrade, 'notification_statuses_seen': notify,
            'send_confirmation_observations': sends, 'cited': len(cited),
            'cited_undelivered': len(undelivered), 'cited_by_caller': dict(cited_callers),
            'cited_observations': cited_tools, 'notes': notes}


def closest_delivered(value, delivered):
    """For a rejected evidence-ID string, the delivered ID it most resembles (prefix+suffix)."""
    best = None
    for real in delivered:
        pre = 0
        while pre < min(len(value), len(real)) and value[pre] == real[pre]:
            pre += 1
        suf = 0
        while (suf < min(len(value), len(real)) - pre and value[-1 - suf] == real[-1 - suf]):
            suf += 1
        score = pre + suf
        if best is None or score > best[0]:
            best = (score, real, pre, suf)
    if best is None:
        return None
    score, real, pre, suf = best
    middle_bad = value[pre:len(value) - suf] if suf else value[pre:]
    middle_real = real[pre:len(real) - suf] if suf else real[pre:]
    return {'shared_prefix': pre, 'shared_suffix': suf, 'real_length': len(real),
            'rejected_length': len(value), 'rejected_middle': middle_bad, 'real_middle': middle_real,
            'shape': ('token replaced hex char(s)' if middle_real and NON_ASCII_RE.fullmatch(middle_bad or '')
                      else 'token inserted' if not middle_real and middle_bad
                      else 'token plus other corruption')}


# ---------------------------------------------------------------- main per store
def analyse_store(label, folder: Path):
    db = open_ro(folder / 'lab.sqlite3')
    log = parse_log(folder / 'launcher.log')
    episodes = dict(records(db, 'episodes'))
    trials = dict(records(db, 'trials'))
    executions = dict(records(db, 'episode_executions'))
    registrations = dict(records(db, 'agent_registrations'))
    campaigns = dict(records(db, 'campaigns'))
    obs_by_episode = collections.defaultdict(list)
    evidence_owner = {}
    for eid, o in records(db, 'observations'):
        obs_by_episode[o['episode_id']].append(o)
        evidence_owner[o['evidence_id']] = o['episode_id']
    caller_of_call = {cid: tc.get('caller') for cid, tc in records(db, 'tool_calls')}
    case_of = {}
    for sid, study in records(db, 'baseline_studies'):
        for slot in study.get('slots', []):
            case_of[slot['episode_id']] = slot['case_id']
    roles, sel_index = build_roles(db)
    events = collections.defaultdict(list)
    for (pl,) in db.execute('SELECT payload FROM events ORDER BY episode_id,seq'):
        e = json.loads(pl)
        events[e['episode_id']].append(e)

    native_regs = {rid for rid, r in registrations.items() if r.get('adapter_entrypoint_id') == NATIVE_ENTRYPOINT}
    out_rows, all_native, controls = [], [], collections.Counter()
    skipped = collections.Counter()
    linkage = collections.Counter()
    reconcile = collections.Counter()
    mangled = []

    for eid, ep in episodes.items():
        if ep.get('split') != 'development' or ep.get('experiment_purpose') in SKIP_PURPOSES:
            skipped[f"{ep.get('split')}/{ep.get('experiment_purpose')}"] += 1
            continue
        ex = executions.get(eid, {})
        trial = trials.get(eid, {})
        failed = trial.get('failed_checks', [])
        if ex.get('kind') == 'deterministic_reference_control':
            controls[(ep['arm'], trial.get('outcome'), tuple(failed))] += 1
            continue
        is_native = (ex.get('adapter_entrypoint_id') == NATIVE_ENTRYPOINT
                     and ep.get('agent_registration_id') in native_regs)
        if not is_native:
            skipped['not native and not reference control'] += 1
            continue

        # ---- private recipe label: development split only (checked above)
        inputs = db.execute("SELECT payload FROM records WHERE kind='private_episode_inputs' AND id=?", (eid,)).fetchone()
        recipe = json.loads(inputs[0]).get('recipe') if inputs else None
        schedule = recipe_label(recipe)
        purpose = ep['experiment_purpose']
        if eid in case_of:
            role = f'baseline {case_of[eid]}'
        elif purpose == 'discovery':
            # learn-campaign discovery episodes carry no selector_id; do not guess the pick
            role = (f"discovery pick {sel_index[ep['selector_id']]}" if ep.get('selector_id') in sel_index
                    else 'discovery (Explorer pick)') + (f', {roles[eid]}' if eid in roles else '')
        else:
            role = roles.get(eid, purpose)
        usage = trial.get('usage') or ep.get('usage') or {}
        ev = events.get(eid, [])
        dispatched_actor = [e for e in ev if e['type'] == 'tool_dispatched' and e['role'] == 'actor']
        # one logical call can record two dispatch events (a timed-out request and its
        # attempt bookkeeping share one call_id); the trace uses one entry per logical call
        dispatched_all, seen_calls = [], set()
        for e in ev:
            if e['type'] == 'tool_dispatched' and e.get('call_id') not in seen_calls:
                seen_calls.add(e.get('call_id'))
                dispatched_all.append(e)
        reports = [e for e in ev if e['type'] == 'report_submitted']
        retries = [e for e in ev if e['type'] == 'actor_transport_retry']
        policy_steps = [e for e in ev if e['type'] == 'policy_step']
        seg = log['segments'].get(ep['world_id'])
        errors = [i for i in (seg['items'] if seg else []) if i['type'] == 'error']
        step_errors = [i for i in errors if i['kind'] != 'MAX_STEPS']
        max_steps_logged = any(i['kind'] == 'MAX_STEPS' for i in errors)
        business_lines = [i for i in (seg['items'] if seg else []) if i['type'] == 'business']

        # ---- linkage check (b): exact evidence IDs quoted in rejected reports
        for item in step_errors:
            for quoted in item.get('exact_evidence_ids_quoted', []):
                owner = evidence_owner.get(quoted)
                linkage['match' if owner == eid else 'unknown_id' if owner is None else 'MISMATCH'] += 1

        # ---- reconciliation check (c)
        accounted = len({e.get('call_id') for e in dispatched_actor}) + len(step_errors) + len(reports)
        actor_calls = usage.get('actor_calls', 0)
        reconciled = accounted == actor_calls
        reconcile['ok' if reconciled else 'mismatch'] += 1

        # ---- turn trace: log order, business lines mapped to dispatched events in order
        trace = []
        if seg and len(business_lines) == len(dispatched_all):
            it = iter(dispatched_all)
            for item in seg['items']:
                if item['type'] == 'business':
                    d = next(it)
                    trace.append(('' if d['role'] == 'actor' else 'policy:') + d['payload'].get('tool', '?'))
                else:
                    k = item['kind']
                    trace.append({'FA_INVALID_EVIDENCE_ID': 'final_answer REJECTED (evidence id)',
                                  'FA_SCHEMA_OTHER': 'final_answer REJECTED (schema)',
                                  'FA_BLOCKED_BY_POLICY': 'final_answer BLOCKED (policy)',
                                  'BUSINESS_REFUSED': f"{item.get('tool')} REFUSED (final report required)",
                                  'PARSE_INVALID_ACTION': 'INVALID single-tool action',
                                  'MAX_STEPS': 'smolagents: Reached max steps'}.get(k, k))
            if reports:
                trace.append('final_answer ACCEPTED (report_submitted)')
            trace_source = 'log order + events'
        else:
            trace = [('' if d['role'] == 'actor' else 'policy:') + d['payload'].get('tool', '?') for d in dispatched_all]
            trace += [i['kind'] for i in errors] + (['report_submitted'] if reports else [])
            trace_source = 'events then log errors (order between them not proven)'

        # ---- mangled-ID shapes (for all native episodes, failed or not)
        delivered_ids = [o['evidence_id'] for o in obs_by_episode.get(eid, [])]
        for item in step_errors:
            if item['kind'] == 'FA_INVALID_EVIDENCE_ID':
                for value in item['rejected_values']:
                    mangled.append({'store': label, 'episode_id': eid, 'value': value,
                                    'closest': closest_delivered(value, delivered_ids)})

        fa_attempts = [i for i in step_errors if i['kind'].startswith('FA_')]
        row = {
            'store': label, 'campaign_id': ep['campaign_id'], 'episode_id': eid,
            'world_id': ep['world_id'], 'purpose': purpose, 'arm': ep['arm'], 'role': role,
            'schedule': schedule, 'scenario_hash': ep['scenario_hash'][:12],
            'outcome': trial.get('outcome'), 'failed_checks': failed, 'reason': trial.get('reason'),
            'actor_calls': actor_calls, 'model_calls': usage.get('model_calls'),
            'transport_retries': len(retries), 'http_attempts': usage.get('http_attempts'),
            'ticks': usage.get('ticks'), 'policy_steps': len(policy_steps),
            'dispatched_actor_calls': len({e.get('call_id') for e in dispatched_actor}),
            'report_submitted': bool(reports),
            'log_segment_found': seg is not None, 'max_steps_logged': max_steps_logged,
            'step_errors': [{k: v for k, v in i.items() if k in ('kind', 'tool', 'fields', 'non_ascii_tokens', 'rejected_values')}
                            for i in step_errors],
            'rejected_report_attempts': len(fa_attempts),
            'last_upgrade_status_seen': (observed_statuses(sorted(obs_by_episode.get(eid, []),
                                         key=lambda o: o['delivered_tick']))[0] or ['none'])[-1],
            'confirmation_sent': any((o.get('result') or {}).get('tool') == 'send_confirmation'
                                     for o in obs_by_episode.get(eid, [])),
            'reconciled': reconciled, 'turn_trace': trace, 'turn_trace_source': trace_source,
        }

        # ---- cause of C5
        cause, secondary, evidence = None, [], []
        if failed and reports:
            row['report'] = reports[-1]['payload']['report']
            row['report_inference'] = report_inference(row['report'], obs_by_episode.get(eid, []), failed,
                                                       caller_of_call)
        if 'C5' in failed:
            if reports:
                cause = 'H'
                inf = row['report_inference']
                evidence.append('report_submitted event present; referee failed C5 (checks.py not opened); '
                                + ('; '.join(inf['notes']) or 'no simple mismatch found'))
            elif actor_calls >= ACTOR_CAP and step_errors:
                last = step_errors[-1]
                cause = {'FA_INVALID_EVIDENCE_ID': 'A', 'FA_SCHEMA_OTHER': 'B', 'BUSINESS_REFUSED': 'C',
                         'PARSE_INVALID_ACTION': 'D', 'FA_BLOCKED_BY_POLICY': 'F'}.get(last['kind'], 'U')
                evidence.append(f"turn {ACTOR_CAP} (the last metered turn, final_report_required=true) ended in {last['kind']}"
                                + (f" on {last.get('tool')}" if last.get('tool') else '')
                                + (f" fields {last.get('fields')}" if last.get('fields') else ''))
                if max_steps_logged:
                    secondary.append('E-mechanism: smolagents reached max_steps=8 and called provide_final_answer; '
                                     'the meter refused that 9th generation (model_calls='
                                     f"{usage.get('model_calls')}, retries={len(retries)}), so no second chance")
                earlier = [i['kind'] for i in step_errors[:-1] if i['kind'].startswith('FA_')]
                if earlier:
                    secondary.append(f'{len(earlier)} earlier final_answer attempt(s) rejected: {sorted(set(earlier))}')
                if not fa_attempts:
                    secondary.append('never called final_answer in 8 turns')
                refused_before_final = [i for i in step_errors[:-1] if i['kind'] == 'BUSINESS_REFUSED']
                if refused_before_final:
                    secondary.append(f'{len(refused_before_final)} business call(s) refused before turn 8 '
                                     '(business calls closed by a policy final request or budget)')
            elif actor_calls < ACTOR_CAP and not reports:
                reason = trial.get('reason') or ''
                cause = 'G' if any(w in reason for w in ('deadline', 'PROVIDER', 'provider', 'limit', 'TRANSPORT')) else 'U'
                evidence.append(f'only {actor_calls} actor turns; reason={reason!r}')
            else:
                cause = 'U'
                evidence.append('no report and no logged step error for the final turn')
        row['c5_cause'] = cause
        row['c5_cause_label'] = BUCKETS.get(cause) if cause else None
        row['c5_secondary'] = secondary
        row['c5_evidence'] = evidence
        all_native.append(row)
        if failed:
            out_rows.append(row)

    campaign_info = {cid: {'mode': c.get('mode'), 'state': c.get('state'),
                           'terminal_reason': c.get('terminal_reason')} for cid, c in campaigns.items()}
    return {
        'store': label, 'path': str(folder / 'lab.sqlite3'),
        'campaigns': campaign_info,
        'native_registrations': sorted(native_regs),
        'log_check': {'creates': log['creates'], 'stops': log['stops'], 'strictly_alternating': log['alternating'],
                      'anomalies': log['anomalies'], 'orphan_error_blocks': len(log['orphan_errors']),
                      'segments': len(log['segments'])},
        'evidence_id_linkage': dict(linkage),
        'turn_reconciliation': dict(reconcile),
        'skipped_episodes': dict(skipped),
        'reference_controls': [{'arm': a, 'outcome': o, 'failed_checks': list(f), 'count': n}
                               for (a, o, f), n in sorted(controls.items(), key=str)],
        'native_total': len(all_native),
        'native_failed_rows': out_rows,
        '_all_native': all_native,
        '_mangled': mangled,
    }


def summarise(stores):
    summary = {}
    rows = [r for s in stores for r in s['native_failed_rows']]
    natives = [r for s in stores for r in s['_all_native']]
    summary['native_episodes'] = len(natives)
    summary['native_failed_episodes'] = len(rows)
    summary['native_by_store'] = {s['store']: {'native': s['native_total'], 'failed': len(s['native_failed_rows'])} for s in stores}
    summary['c5_episodes'] = sum(1 for r in rows if 'C5' in r['failed_checks'])
    summary['c5_by_cause'] = dict(collections.Counter(r['c5_cause'] for r in rows if 'C5' in r['failed_checks']))
    summary['c5_by_cause_by_store'] = {
        s['store']: dict(collections.Counter(r['c5_cause'] for r in s['native_failed_rows'] if 'C5' in r['failed_checks']))
        for s in stores}
    summary['c5_by_cause_by_purpose'] = {}
    for r in rows:
        if 'C5' in r['failed_checks']:
            key = f"{r['store']}:{r['purpose']}/{r['arm']}"
            summary['c5_by_cause_by_purpose'].setdefault(key, collections.Counter())[r['c5_cause']] += 1
    summary['c5_by_cause_by_purpose'] = {k: dict(v) for k, v in summary['c5_by_cause_by_purpose'].items()}
    summary['failed_check_sets'] = dict(collections.Counter(','.join(r['failed_checks']) for r in rows))
    summary['non_c5_failures'] = [{k: r[k] for k in ('store', 'episode_id', 'role', 'schedule', 'failed_checks')}
                                  for r in rows if 'C5' not in r['failed_checks']]
    # C5 cause per fault schedule (all stores, all purposes)
    by_sched = collections.defaultdict(collections.Counter)
    for r in natives:
        key = r['schedule']
        by_sched[key]['episodes'] += 1
        if 'C5' in r['failed_checks']:
            by_sched[key]['C5'] += 1
            by_sched[key][r['c5_cause']] += 1
    summary['c5_cause_by_schedule'] = {k: dict(v) for k, v in sorted(by_sched.items(), key=lambda kv: -kv[1]['episodes'])}
    # baseline studies: per development case
    base = collections.defaultdict(lambda: collections.Counter())
    for r in natives:
        if r['role'].startswith('baseline '):
            key = f"{r['store']} {r['role'].split()[1]}"
            base[key]['trials'] += 1
            base[key]['violations'] += bool(r['failed_checks'])
            for check in r['failed_checks']:
                base[key][check] += 1
            if 'C5' in r['failed_checks']:
                base[key]['C5:' + r['c5_cause']] += 1
    summary['baseline_by_case'] = {k: dict(v) for k, v in sorted(base.items())}
    # C3 per schedule
    c3 = collections.defaultdict(lambda: {'episodes': 0, 'c3': 0, 'c3_and_c5': 0, 'c3_no_report': 0, 'roles': set()})
    for r in natives:
        key = f"{r['store']} | {r['schedule']} | {r['scenario_hash']}"
        c3[key]['episodes'] += 1
        c3[key]['roles'].add(r['role'].split(':')[0])
        if 'C3' in r['failed_checks']:
            c3[key]['c3'] += 1
            if 'C5' in r['failed_checks']:
                c3[key]['c3_and_c5'] += 1
            if not r['report_submitted']:
                c3[key]['c3_no_report'] += 1
    summary['c3_by_schedule'] = {k: {**v, 'roles': sorted(v['roles'])} for k, v in c3.items() if v['c3']}
    summary['c3_total'] = sum(v['c3'] for v in c3.values())
    summary['c3_with_c5'] = sum(v['c3_and_c5'] for v in c3.values())
    summary['schedules_without_c3_that_had_a_rejected_upgrade'] = sorted(
        k for k, v in c3.items() if not v['c3'] and 'FAILED' in k)
    # final-turn action for all no-report native episodes
    no_report = [r for r in natives if not r['report_submitted']]
    summary['no_report_episodes'] = len(no_report)
    summary['no_report_final_turn_action'] = dict(collections.Counter(
        (r['step_errors'][-1]['kind'] + (':' + r['step_errors'][-1].get('tool', '') if r['step_errors'][-1].get('tool') else ''))
        if r['step_errors'] else 'none' for r in no_report))
    summary['no_report_state_at_final_turn'] = dict(collections.Counter(
        f"{r['c5_cause']} | turn-8 {(r['step_errors'][-1].get('tool') or r['step_errors'][-1]['kind']) if r['step_errors'] else 'none'}"
        f" | last upgrade status {r['last_upgrade_status_seen']} | "
        + ('confirmation sent' if r['confirmation_sent'] else 'no confirmation') for r in no_report))
    parse = collections.defaultdict(lambda: {'episodes': 0, 'with_invalid_action': 0, 'invalid_actions': 0})
    for r in natives:
        key = r['c5_cause'] or ('passed' if not r['failed_checks'] else 'failed without C5')
        n = sum(1 for e in r['step_errors'] if e['kind'] == 'PARSE_INVALID_ACTION')
        parse[key]['episodes'] += 1
        parse[key]['with_invalid_action'] += bool(n)
        parse[key]['invalid_actions'] += n
    summary['invalid_actions_by_c5_cause'] = dict(parse)
    summary['no_report_never_called_final_answer'] = sum(1 for r in no_report if r['rejected_report_attempts'] == 0)
    summary['no_report_with_any_rejected_evidence_id_attempt'] = sum(
        1 for r in no_report if any(e['kind'] == 'FA_INVALID_EVIDENCE_ID' for e in r['step_errors']))
    summary['no_report_actor_calls'] = dict(collections.Counter(r['actor_calls'] for r in no_report))
    summary['no_report_max_steps_logged'] = sum(1 for r in no_report if r['max_steps_logged'])
    summary['no_report_model_calls_equal_actor_calls_plus_retries'] = sum(
        1 for r in no_report if r['model_calls'] == r['actor_calls'] + r['transport_retries'])
    # reports that survived a rejected attempt
    reported = [r for r in natives if r['report_submitted']]
    summary['reported_episodes'] = len(reported)
    summary['reported_after_rejected_attempt'] = sum(1 for r in reported if r['rejected_report_attempts'])
    summary['all_final_answer_attempts'] = dict(collections.Counter(
        e['kind'] for r in natives for e in r['step_errors'] if e['kind'].startswith('FA_')))
    summary['accepted_final_answers'] = len(reported)
    summary['all_step_errors'] = dict(collections.Counter(
        e['kind'] + (':' + e['tool'] if e.get('tool') else '') for r in natives for e in r['step_errors']))
    # final_answer attempts: first attempt per episode vs. retries after a rejection
    first_total = first_rejected = retries_total = retries_clean = 0
    for r in natives:
        kinds = [e['kind'] for e in r['step_errors'] if e['kind'].startswith('FA_')]
        attempts = kinds + (['ACCEPTED'] if r['report_submitted'] else [])
        if not attempts:
            continue
        first_total += 1
        first_rejected += attempts[0] != 'ACCEPTED'
        retries_total += len(attempts) - 1
        retries_clean += sum(1 for a in attempts[1:] if a == 'ACCEPTED')
    summary['final_answer_first_attempts'] = {'episodes_with_any_final_answer': first_total,
                                              'first_attempt_rejected': first_rejected,
                                              'retries_after_rejection': retries_total,
                                              'retries_accepted': retries_clean}
    summary['report_turn_of_accepted_reports'] = dict(sorted(collections.Counter(
        r['actor_calls'] for r in reported).items()))
    summary['transport_retry_episodes'] = [{k: r[k] for k in ('store', 'episode_id', 'transport_retries', 'actor_calls',
                                                              'model_calls', 'failed_checks', 'c5_cause')}
                                           for r in natives if r['transport_retries']]
    # mangled-ID anatomy
    mangled = [m for s in stores for m in s['_mangled']]
    tokens = collections.Counter(t for m in mangled for t in NON_ASCII_RE.findall(m['value']))
    summary['rejected_evidence_id_values'] = len(mangled)
    summary['rejected_evidence_id_values_with_non_ascii'] = sum(1 for m in mangled if NON_ASCII_RE.search(m['value']))
    summary['rejected_evidence_id_non_ascii_tokens'] = dict(tokens)
    summary['rejected_evidence_id_shapes'] = dict(collections.Counter(
        (m['closest'] or {}).get('shape', 'no delivered id') for m in mangled))
    summary['checks'] = {s['store']: {'log': s['log_check'], 'evidence_id_linkage': s['evidence_id_linkage'],
                                      'turn_reconciliation': s['turn_reconciliation'],
                                      'skipped': s['skipped_episodes']} for s in stores}
    return summary


def main():
    stores = [analyse_store(label, folder) for label, folder in RUNS]
    summary = summarise(stores)
    result = {
        'schema': 'faultlab-native-failure-classification/v1',
        'generated_by': 'artifacts/product-native-v2-2026-09-29/analysis/classify.py',
        'buckets': BUCKETS,
        'summary': summary,
        'stores': [{k: v for k, v in s.items() if not k.startswith('_')} for s in stores],
        'rejected_evidence_ids': [m for s in stores for m in s['_mangled']],
    }
    OUT.write_text(json.dumps(result, indent=1, ensure_ascii=False, sort_keys=False) + '\n', encoding='utf-8')
    print(json.dumps({k: summary[k] for k in (
        'native_episodes', 'native_failed_episodes', 'c5_episodes', 'c5_by_cause', 'c5_by_cause_by_store',
        'no_report_final_turn_action', 'c3_total', 'c3_with_c5', 'checks')}, indent=1, ensure_ascii=False))


if __name__ == '__main__':
    sys.exit(main())
