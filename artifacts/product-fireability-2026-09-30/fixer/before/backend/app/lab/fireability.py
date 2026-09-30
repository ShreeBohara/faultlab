"""Explorer selection v3: history fireability (declared September 30, 2026, after live runs v2d and v2f).

``faultlab-explorer-selection/v3-history-fireability`` (plan field ``explorer_selection``) is frozen into every new Learn
plan whose discovery protocol freezes a same-agent history with v1 dispatch: ``faultlab-discovery/v3-history`` and
``faultlab-discovery/v4-history-replay``. No other plan declares it, and a plan saved before it keeps its requests,
records and behaviour byte for byte.

Why. In live runs v2d and v2f every generated guardrail that passed source validation then ran a challenge with 0
failed checks, and every one ended INCONCLUSIVE, because the challenge Explorer picked one schedule (a lone F4 fault on
the orders ``get_operation_status`` read, failure_count 1) whose fault rarely fires: with a healthy upgrade neither arm
needs that read, so the pair is untriggered and the challenge ends. Discovery Explorer picks in v2c, v2e and v2f spent
slots on the same target. The agent's own frozen history already showed it: in store native-v2b that target is
scheduled in 4 verified history episodes and fired in none (docs/PRODUCT_HISTORY_FIREABILITY_2026-09-30.md).

What. When the plan is saved, FaultLab computes a table from exactly the episodes the plan's frozen agent history uses
(app.lab.agent_history.used_episodes: this agent, the starting policy, development discovery episodes from a baseline
study or a Learn campaign's own discovery pick, completed and Weave-verified; the same eligibility and exclusions, and
their ids must hash to the history's episode_ids_hash). For each (fault kind, target service, target tool): how many
verified episodes scheduled at least one fault there, and in how many of them every such fault fired (its
``fault_executions`` entry, matched by position, says triggered). The table is frozen into the plan with its hash, and
recomputed at the history's record cutoff before Start and before the first Explorer request; any difference refuses
(AGENT_HISTORY_CHANGED).

The rule. Before any episode runs, every Explorer pick (a discovery slot's pick, including the fixed fallback after an
invalid answer, or a challenge pick) is checked: it is refused if any of its faults targets a (kind, service, tool) with
at least 3 verified history episodes and a fired share below 1/2. No episode runs; the refusal is recorded on the
selection record with the table row. The Explorer gets one re-plan for that slot, told why; a refused re-plan gets none.
Every request is charged and bounded as today: a challenge re-plan is one of the challenge's existing 8 Explorer
requests (app/lab/challenge.py is unchanged); a discovery re-plan is one of the plan's declared ``explorer_requests_max``
discovery requests (a v4 replay slot uses none), so under v3-history a re-plan can leave a later slot without a request,
and that slot is recorded. Targets with fewer than 3 verified episodes, and targets not in the table, are allowed.
Discovery's duplicate rule runs first, unchanged. The Explorer's request states the rule and carries the table as
information (context keys ``explorer_selection_protocol`` and ``history_fireability``).

What it never reads. Candidate, challenge, source-validation, reproduction, reduction or intervention episodes, B1
controls, other agents, other policies, history replay episodes and protected data (promotion, held-out, final audit):
only the frozen history's own episodes. The table is fixed before any candidate exists, so it is the same for every
candidate in the campaign. This is the difference from the withdrawn ``faultlab-challenge-selection/v2-candidate-reach``,
which judged picks by the candidate's own source-validation calls (artifacts/product-loop-limits-2026-09-30/
review-integrity/REPORT.md).

What it does not change. Gates, the referee, the simulator, the C1-C8 contracts, challenge.py (4 schedules, 3 fresh
pairs each, every pair must fire, any candidate violation is a counterexample), evaluation, promotion, reproduction,
reduction, diagnosis and the verdict logic. Known limit, stated in the plan: the table is per target, not per recipe, so
a fault on a refused target is refused even inside a recipe where another fault would make it fire (for example a
pending upgrade before the status read); and a refused pick cannot expose a candidate violation it might have shown.
"""
from __future__ import annotations

from fractions import Fraction

from app.contracts.models import content_hash, new_id

EXPLORER_SELECTION_V3 = 'faultlab-explorer-selection/v3-history-fireability'
TABLE_SCHEMA = 'faultlab-history-fireability/v1'
# The discovery protocols whose new plans freeze the rule (a frozen same-agent history and v1 dispatch).
DISCOVERY_PROTOCOLS = ('faultlab-discovery/v3-history', 'faultlab-discovery/v4-history-replay')
APPLIES_TO = ('explorer_discovery', 'explorer_challenge')
MIN_VERIFIED_EPISODES = 3
MIN_FIRED_SHARE = Fraction(1, 2)
MIN_FIRED_SHARE_TEXT = '1/2'
ROW_FIELDS = ('kind', 'target_service', 'target_tool', 'verified_episodes', 'fired_episodes', 'fired_share', 'status')
# Table row statuses. A target not in the table is NOT_IN_HISTORY (allowed).
REFUSED = 'REFUSED'
ALLOWED = 'ALLOWED'
TOO_FEW = 'ALLOWED_FEWER_THAN_3'
NOT_IN_HISTORY = 'NOT_IN_HISTORY'
ROW_STATUSES = (REFUSED, ALLOWED, TOO_FEW)
# Pick decision statuses (the selection record's ``fireability`` field).
PICK_ALLOWED = 'ALLOWED'
PICK_REFUSED = 'REFUSED_LOW_FIRED_SHARE'
PICK_INVALID = 'INVALID_OUTPUT'
PICK_DUPLICATE = 'NOT_CHECKED_DUPLICATE'
PICK_STATUSES = (PICK_ALLOWED, PICK_REFUSED, PICK_INVALID, PICK_DUPLICATE)
# The discovery search decision of a refused discovery pick (v1-dispatch records only get it under this rule).
DISCOVERY_STATUS = 'SKIPPED_UNFIREABLE'
DISCOVERY_REASON = 'HISTORY_FIRED_SHARE_BELOW_HALF'

RULE = ('Before any episode runs, FaultLab checks every fault of each Explorer pick (a discovery slot\'s pick, including '
        'the fixed fallback after an invalid answer, and each challenge pick) against this plan\'s frozen history '
        'fireability table. The table was computed when the plan was saved, from exactly the verified episodes of the '
        'plan\'s frozen agent history (this agent, the starting policy, development discovery episodes only): for each '
        'fault kind, service and tool, how many verified episodes scheduled a fault there and in how many of them every '
        'such fault fired. A pick is refused if any of its faults targets a kind, service and tool with at least 3 verified '
        'episodes and a fired share below 1/2: no episode runs, and the refusal is recorded with the table row. The '
        'Explorer then gets one re-plan for that slot, told why; a refused re-plan gets none. Every request, re-plans '
        'included, is charged and bounded as before: a challenge re-plan is one of the challenge\'s 8 Explorer requests, '
        'and a discovery re-plan is one of the plan\'s declared discovery Explorer requests, so a re-plan can leave a later '
        'discovery slot without a request (that slot is recorded). Targets with fewer than 3 verified episodes, and '
        'targets not in the table, are allowed. Discovery\'s duplicate rule applies first, unchanged. The table never uses '
        'candidate, challenge, source-validation, reproduction, reduction or intervention episodes, other agents or '
        'protected data, and it is the same for every candidate. Nothing else changes: a challenge still needs 4 schedules '
        'with 3 fresh pairs each, every pair must fire its faults, and any candidate violation is a counterexample. The '
        'table is per target, not per recipe, so a fault on a refused target is refused even when another fault in the '
        'same pick might make it fire.')
MEANING = ('Prior evidence from this plan\'s frozen agent history, not about any candidate: for each fault target (kind, '
           'service, tool), verified_episodes is how many verified episodes of this agent under the starting policy '
           'scheduled a fault there, and fired_episodes is how many of them fired every such fault. REFUSED marks a target '
           'with at least 3 verified episodes and a fired share below 1/2: a pick with a fault on it is refused before any '
           'episode runs. ALLOWED_FEWER_THAN_3 and targets not listed are allowed.')
REPLAN_INSTRUCTION = ('Your previous pick was refused before any episode ran, because a fault in it targets a kind, '
                      'service and tool that history_fireability marks REFUSED. This request is its one re-plan: choose a '
                      'pick with no fault on a REFUSED target.')


def declaration():
    """The rule as the run options offer it (no table; the plan freezes the table when it is saved)."""
    return {'protocol': EXPLORER_SELECTION_V3, 'applies_to': list(APPLIES_TO), 'discovery_protocols': list(DISCOVERY_PROTOCOLS),
            'basis': 'frozen_agent_history_verified_episodes', 'target': 'fault_kind_service_tool',
            'min_verified_episodes': MIN_VERIFIED_EPISODES, 'min_fired_share': MIN_FIRED_SHARE_TEXT,
            'replans_per_refused_pick': 1, 'explorer_request_budget_changed': False, 'refused_pick_runs_episodes': False,
            'candidate_dependent': False, 'challenge_rules_changed': False, 'rule': RULE}


def campaign_rule(store, campaign):
    """The frozen block (the rule and its table) of this campaign's saved plan, or None (every other plan)."""
    from app.lab.runner import campaign_run_plan
    return (campaign_run_plan(store, campaign) or {}).get('explorer_selection')


def row_status(verified, fired):
    if verified < MIN_VERIFIED_EPISODES:
        return TOO_FEW
    return REFUSED if Fraction(fired, verified) < MIN_FIRED_SHARE else ALLOWED


def target_text(row):
    return f'{row["kind"]} on {row["target_tool"]} ({row["target_service"]})'


def refused_text(row):
    return (f'{target_text(row)}: fired in {row["fired_episodes"]} of {row["verified_episodes"]} verified history episodes '
            f'(below {MIN_FIRED_SHARE_TEXT} of at least {MIN_VERIFIED_EPISODES})')


def compute_table(store, history):
    """The fireability table of one frozen history block, from exactly the episodes that history uses.

    Raises agent_history.HistoryChanged if the store's episodes at the history's cutoff are not the history's own.
    """
    from app.lab import agent_history
    used = agent_history.used_episodes(store, identity=history['agent_identity'], policy_hash=history['policy_hash'],
                                       cutoff=history['record_cutoff'])
    ids = [episode['episode_id'] for episode, _ in used]
    if content_hash(sorted(ids)) != history['episode_ids_hash'] or len(ids) != history['summary']['verified_episodes']:
        raise agent_history.HistoryChanged('The store\'s verified history episodes differ from the plan\'s frozen agent history '
                                           f'(summary {history["summary_hash"][:12]}…); create a new plan')
    counts = {}
    for episode, recipe in used:
        executions = (episode.get('verdict') or {}).get('fault_executions') or []
        targets = {}
        for index, primitive in enumerate(recipe.primitives):
            key = (primitive.kind, primitive.target_service, primitive.target_tool)
            execution = executions[index] if index < len(executions) and isinstance(executions[index], dict) else {}
            targets.setdefault(key, []).append(execution.get('triggered') is True)
        for key, fired in targets.items():
            verified, all_fired = counts.get(key, (0, 0))
            counts[key] = (verified + 1, all_fired + all(fired))
    rows = []
    for (kind, service, tool), (verified, fired) in sorted(counts.items()):
        rows.append({'kind': kind, 'target_service': service, 'target_tool': tool, 'verified_episodes': verified,
                     'fired_episodes': fired, 'fired_share': f'{fired}/{verified}', 'status': row_status(verified, fired)})
    return {'schema_version': TABLE_SCHEMA, 'meaning': MEANING, 'history_summary_hash': history['summary_hash'],
            'history_episode_ids_hash': history['episode_ids_hash'], 'record_cutoff': history['record_cutoff'],
            'verified_episodes': len(ids), 'rows': rows, 'refused_targets': [refused_text(row) for row in rows if row['status'] == REFUSED]}


def plan_block(store, history):
    """The block frozen into a new v3-history or v4 Learn plan: the rule and the table computed from its frozen history."""
    table = compute_table(store, history)
    return {**declaration(), 'table': table, 'table_hash': content_hash(table)}


def verify(store, block, history):
    """Recompute the table from the plan's (already verified) history; refuse if the rule or the table differs."""
    from app.lab.agent_history import HistoryChanged
    if block is None or {key: value for key, value in block.items() if key not in ('table', 'table_hash')} != declaration():
        raise HistoryChanged('The frozen Explorer selection rule differs from the installed rule; create a new plan')
    table = compute_table(store, history)
    if block['table'] != table or block['table_hash'] != content_hash(table):
        raise HistoryChanged('The frozen history fireability table no longer matches the store at the plan\'s record cutoff '
                             f'(frozen {block["table_hash"][:12]}…, now {content_hash(table)[:12]}…); create a new plan')
    return block


# ----------------------------------------------------------------------------------------------- one campaign's state

class ChallengeState:
    """One challenge's refusals and its pending re-plan (keyed by campaign, candidate and incumbent)."""
    def __init__(self, key):
        self.key = key; self.pending = None; self.refused = []


class Session:
    """One Learn campaign's execution under the rule: the frozen table, the discovery request count and challenge state.

    The learning loop sets it on its Explorer (``explorer.fireability``); None (every other plan) keeps today's requests.
    """
    def __init__(self, block, *, discovery_requests_max):
        self.block = block
        self.table = block['table']
        self.rows = {(row['kind'], row['target_service'], row['target_tool']): row for row in self.table['rows']}
        self.discovery_requests_max = discovery_requests_max
        self.discovery_requests = 0
        self.discovery_replans = 0
        self.discovery_refused = []
        self.challenge = None

    def admit_discovery_request(self):
        """Count one discovery Explorer request, or refuse (False) when the declared number is used up."""
        if self.discovery_requests >= self.discovery_requests_max:
            return False
        self.discovery_requests += 1
        return True

    def challenge_state(self, context):
        key = (context.get('campaign_id'), context.get('candidate_hash'), context.get('incumbent_hash'))
        if self.challenge is None or self.challenge.key != key or context.get('proposal_index') == 0:
            self.challenge = ChallengeState(key)
        return self.challenge


def _readable(spec):
    from app.lab.reachability import readable_recipe
    return readable_recipe(spec)


def request_context(session, context, *, challenge):
    """What the Explorer is told under the rule, added to its request context (discovery and challenge)."""
    if challenge:
        state = session.challenge_state(context)
        refused = [dict(item) for item in state.refused]
    else:
        state = None
        refused = [dict(item) for item in session.discovery_refused]
    block = {'rule': RULE, 'meaning': MEANING, 'min_verified_episodes': MIN_VERIFIED_EPISODES,
             'min_fired_share': MIN_FIRED_SHARE_TEXT, 'verified_history_episodes': session.table['verified_episodes'],
             'rows': [dict(row) for row in session.table['rows']], 'refused_targets': list(session.table['refused_targets']),
             'refused_picks': refused}
    extra = {'explorer_selection_protocol': EXPLORER_SELECTION_V3, 'history_fireability': block}
    if challenge:
        extra['slot_request'] = 2 if state.pending else 1
        if state.pending:
            extra['replan_of'] = state.pending['refused_selection_id']
            extra['slot_feedback'] = {**state.pending, 'instruction': REPLAN_INSTRUCTION + ' It must also not be in '
                                      'already_tested_fault_specs.'}
    return extra


def check_targets(session, spec):
    """Each distinct target of a pick, in pick order, with its table row (None when not in the table) and status."""
    checked, seen = [], set()
    for primitive in spec.primitives:
        key = (primitive.kind, primitive.target_service, primitive.target_tool)
        if key in seen: continue
        seen.add(key)
        row = session.rows.get(key)
        checked.append({'kind': key[0], 'target_service': key[1], 'target_tool': key[2],
                        'table_row': dict(row) if row else None, 'status': row['status'] if row else NOT_IN_HISTORY})
    return checked


def _base(session, context, *, challenge, provenance):
    return {'protocol': EXPLORER_SELECTION_V3, 'purpose': 'challenge' if challenge else 'discovery',
            'table_hash': session.block['table_hash'],
            'request_index': context.get('proposal_index') if challenge else context.get('selection_index'),
            'slot_request': context.get('slot_request', 1), 'replan_of': context.get('replan_of'), 'pick': provenance,
            'targets': [], 'refused_targets': [], 'refused_fault_spec': None, 'reason': None}


def _next_step(session, decision, *, challenge):
    if decision['slot_request'] != 1:
        return ('This was already the re-plan, so there is no further re-plan for it; the challenge continues with its '
                'remaining requests.' if challenge else 'This was already the slot\'s re-plan, so the slot ends without an episode.')
    if challenge:
        return 'The next request in this challenge is its one re-plan (one of the challenge\'s 8 Explorer requests).'
    if session.discovery_requests < session.discovery_requests_max:
        return ('The next request is this slot\'s one re-plan (it is one of the plan\'s '
                f'{session.discovery_requests_max} declared discovery Explorer requests).')
    return (f'The plan\'s {session.discovery_requests_max} declared discovery Explorer requests are used up, so this slot '
            'gets no re-plan and ends without an episode.')


def decide(session, context, selected, error, *, challenge, provenance):
    """(decision saved on the selection record, the pick to run or None). Never guesses: an invalid answer is not a pick."""
    decision = _base(session, context, challenge=challenge, provenance=provenance)
    if selected is None:
        decision.update(status=PICK_INVALID, reason=error)
        return decision, None
    decision['targets'] = check_targets(session, selected.fault_spec)
    refused = [item['table_row'] for item in decision['targets'] if item['status'] == REFUSED]
    if not refused:
        decision['status'] = PICK_ALLOWED
        return decision, selected
    named = '; '.join(refused_text(row) for row in refused)
    decision.update(status=PICK_REFUSED, refused_targets=refused, refused_fault_spec=selected.fault_spec.model_dump(mode='json'),
                    reason=f'Refused before any episode ran: {named}. ' + _next_step(session, decision, challenge=challenge))
    return decision, None


def not_checked(session, context, *, provenance, reason):
    """A discovery request whose pick was refused before this rule ran (a duplicate) or that had no pick at all."""
    decision = _base(session, context, challenge=False, provenance=provenance)
    decision.update(status=PICK_DUPLICATE if reason == 'DUPLICATE_DISCOVERY_SCHEDULE' else PICK_INVALID, reason=reason)
    return decision


def after_pick(session, selection_id, decision, *, challenge):
    """Keep a refusal for the Explorer's later requests and set (or clear) a challenge's pending re-plan."""
    if decision['status'] == PICK_REFUSED:
        item = {'refused_selection_id': selection_id, 'request_index': decision['request_index'],
                'slot_request': decision['slot_request'], 'refused_recipe': _readable(decision['refused_fault_spec']),
                'refused_targets': [dict(row) for row in decision['refused_targets']], 'reason': decision['reason']}
        if challenge:
            state = session.challenge
            state.refused.append(item)
            state.pending = item if decision['slot_request'] == 1 else None
        else:
            session.discovery_refused.append(item)
    elif challenge and session.challenge is not None:
        session.challenge.pending = None


# ----------------------------------------------------------------------------------------------- discovery slots

def slot_feedback(record):
    """What a discovery re-plan request is told about its slot's refused pick: readable, templated, no hashes."""
    decision = record['fireability']
    return {'refused_selection_id': record['selection_id'], 'status': DISCOVERY_STATUS, 'reason': decision['reason'],
            'refused_recipe': _readable(decision['refused_fault_spec']),
            'refused_targets': [dict(row) for row in decision['refused_targets']],
            'instruction': REPLAN_INSTRUCTION + ' It must also not be already listed in search_ledger.'}


def record_unrequested_slot(store, session, slot_context):
    """A discovery slot that sent no Explorer request because re-plans used the plan's declared requests (recorded)."""
    ident = new_id('explorer-slot')
    used = session.discovery_requests
    store.put_record('explorer_selection_slots', ident, {
        'record_id': ident, 'campaign_id': slot_context['campaign_id'], 'protocol': EXPLORER_SELECTION_V3,
        'selection_index': slot_context['selection_index'], 'status': 'NO_EXPLORER_REQUEST',
        'explorer_requests_used': used, 'explorer_requests_max': session.discovery_requests_max,
        'replans_after_refusals': session.discovery_replans,
        'reason': (f'This discovery slot sent no Explorer request and ran no episode: the plan declares at most '
                   f'{session.discovery_requests_max} discovery Explorer requests, and all {used} were used, including '
                   're-plans after picks the history fireability rule refused.')}, immutable=True)
    return ident


async def discovery_slot(explorer, store, session, slot_context, *, fallback, discovery_history, stop):
    """One discovery Explorer slot under the rule: a request, and one re-plan if the rule refused its pick.

    Returns (selection id or None, the pick to run or None), as explorer.select does.
    """
    if not session.admit_discovery_request():
        record_unrequested_slot(store, session, slot_context)
        return None, None
    ref, output = await explorer.select({**slot_context, 'slot_request': 1}, fallback=fallback, discovery_history=discovery_history)
    record = store.get_record('selections', ref) or {}
    refused = (record.get('fireability') or {}).get('status') == PICK_REFUSED
    if output is None and refused and not stop() and session.admit_discovery_request():
        session.discovery_replans += 1
        ref, output = await explorer.select({**slot_context, 'slot_request': 2, 'replan_of': ref,
                                             'slot_feedback': slot_feedback(record)},
                                            fallback=fallback, discovery_history=discovery_history)
    return ref, output


# ----------------------------------------------------------------------------------------------- dashboard and recording

def campaign_decisions(store, campaign_id):
    """Every pick decision recorded under the rule for this campaign (discovery and challenge), in record order."""
    challenge_of = {}
    for challenge in store.list_records('challenges'):
        for ref in challenge.get('selection_refs', []):
            challenge_of[ref] = challenge['challenge_id']
    rows = []
    for selection in store.list_records('selections'):
        decision = selection.get('fireability')
        if decision is None or (selection.get('context') or {}).get('campaign_id') != campaign_id:
            continue
        spec = (selection.get('output') or {}).get('fault_spec') or (selection.get('selected_output') or {}).get('fault_spec')
        rows.append({'selection_id': selection['selection_id'], 'challenge_id': challenge_of.get(selection['selection_id']),
                     'recipe': _readable(spec) if spec else None, **decision})
    return rows


def campaign_summary(store, campaign_id, block):
    """The rule's saved outcome for one campaign (API and recording): the frozen table, every pick decision, unrequested slots."""
    decisions = campaign_decisions(store, campaign_id)
    slots = [row for row in store.list_records('explorer_selection_slots') if row.get('campaign_id') == campaign_id]
    return {'protocol': block['protocol'], 'table_hash': block['table_hash'], 'refused_targets': list(block['table']['refused_targets']),
            'picks_checked': sum(row['status'] in (PICK_ALLOWED, PICK_REFUSED) for row in decisions),
            'picks_refused': sum(row['status'] == PICK_REFUSED for row in decisions),
            'decisions': decisions, 'slots_without_request': slots}
