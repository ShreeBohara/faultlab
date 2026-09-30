"""Discovery protocol v4 (history replay): regression-first discovery, offline design of September 30, 2026.

``faultlab-discovery/v4-history-replay`` is exactly ``faultlab-discovery/v3-history`` (the same frozen same-agent
history with the same eligibility, exclusions, hash, record cutoff and checks; v1 dispatch, schedule identity and
budget for the Explorer slots) plus a **replay list** computed from that frozen history when the plan is saved and
frozen into the plan:

* eligible history rows: at least one scheduled fault (a no-fault row is never replayed), at least 2 verified
  episodes, every verified episode fired every scheduled fault, and a violation share (VIOLATION outcomes / verified
  episodes) of at least 2/3;
* ordered by violation share (highest first), then verified episodes (most first), then row order in the history;
  at most 3 rows.

Discovery runs the replay slots first. Each replay slot runs one agent episode of its row's recipe (the same schedule
under ``faultlab-schedule-identity/v2-order-aware``: a development case's public recipe, otherwise the listed faults
with seed 0; the seed never changes behaviour), uses one discovery slot and one Actor episode, and sends NO Explorer
request. It becomes a source by the unchanged discovery rule (COMPLETED, every fault fired, VIOLATION). The remaining
slots are v3-history's Explorer slots: the Explorer sees the history, and the replays as prior selections in its
search ledger, whose duplicate rule applies to them.

Every replay is labelled "history replay" with its row: on its selection record, in the fault-search panel, in the
source panel, in the campaign recording and in every export built from it. A replay source is never independent
discovery. An empty list (no prior history, or no eligible row) says so in the plan, and discovery then runs exactly
as v3-history (the Explorer's requests differ only by the declared protocol id).

This module only reads the frozen history summary and the public development manifest. It never reads the store's
records, protected evaluation data or anything outside the summary it is given.
"""
from fractions import Fraction

from app.contracts.models import ExplorerOutput, FaultSpec, canonical_json, new_id

REPLAY_SCHEMA = 'faultlab-history-replay/v1'
LABEL = 'history replay'
MAX_REPLAYS = 3
MIN_VERIFIED_EPISODES = 2
MIN_VIOLATION_SHARE = Fraction(2, 3)
MIN_VIOLATION_SHARE_TEXT = '2/3'
MATCH_BASIS = 'faultlab-schedule-identity/v2-order-aware'
RULE = ('History replay rule (faultlab-history-replay/v1). From the plan\'s frozen agent history, a recipe row is replayed '
        'only if it has at least one scheduled fault, at least 2 verified episodes, every verified episode fired every '
        'scheduled fault, and at least 2 of every 3 verified episodes ended in VIOLATION. Eligible rows are ordered by '
        'violation share (highest first), then verified episodes (most first), then their order in the history; at most 3 '
        'are replayed. Each replay runs that row\'s recipe (the same order-aware schedule; a development case\'s public '
        'recipe, otherwise the listed faults with seed 0) as one discovery slot and one agent episode, with no Explorer '
        'request, before any Explorer slot. A replay becomes a source exactly as any discovery pick does (completed, every '
        'fault fired, VIOLATION). A result from it is a history replay of that row, never independent discovery.')
AVAILABLE_STATEMENT = ('Replayed first, before any Explorer request: the recipes below, taken from the frozen agent history '
                       'by the fixed replay rule. Each uses one discovery slot and one agent episode and no Explorer request. '
                       'A source found by one is a history replay of that row, never independent discovery.')
EMPTY_NO_HISTORY = ('Replay list empty: this store has no prior history for this agent, so nothing is replayed. Discovery '
                    'runs exactly as v3 · agent history.')
EMPTY_NONE_ELIGIBLE = ('Replay list empty: no row of the frozen agent history meets the replay rule, so nothing is replayed. '
                       'Discovery runs exactly as v3 · agent history.')
CLAIM_RULE = ('A source found in a history replay slot re-ran a recipe from the frozen agent history, chosen by the plan\'s '
              'fixed replay rule and not by the Explorer. Report it as a history replay of that row (name the row, the '
              'store and the frozen summary hash), never as independent discovery or as an Explorer pick.')


def violation_share(row):
    verified = row.get('verified_episodes') or 0
    return Fraction((row.get('outcomes') or {}).get('VIOLATION', 0), verified) if verified else Fraction(0)


def eligible(row):
    """Whether one frozen history row meets the replay rule. A no-fault row never does."""
    verified = row.get('verified_episodes') or 0
    fired = row.get('every_fault_fired')
    return (bool(row.get('primitives')) and fired is not None and verified >= MIN_VERIFIED_EPISODES
            and fired == verified and violation_share(row) >= MIN_VIOLATION_SHARE)


def replay_recipe(row):
    """The recipe a replay slot runs: same order-aware schedule as the row; the seed is bookkeeping only."""
    from app.lab.challenge import schedule_identity_v2
    listed = FaultSpec.model_validate_json(canonical_json({'seed': 0, 'primitives': row['primitives']}))
    case_id = row.get('development_case_id')
    if case_id:
        from app.referee.manifests import development_case
        public = FaultSpec.model_validate_json(canonical_json(development_case(case_id)['fault_spec']))
        if schedule_identity_v2(public) == schedule_identity_v2(listed):
            return public
    return listed


def replay_rows(summary):
    """The ordered, capped replay list for one frozen history summary (a pure function of the summary)."""
    from app.lab.challenge import schedule_identity_v2
    candidates = [(index, row) for index, row in enumerate((summary or {}).get('recipes') or [], start=1) if eligible(row)]
    candidates.sort(key=lambda item: (-violation_share(item[1]), -item[1]['verified_episodes'], item[0]))
    rows = []
    for replay, (index, row) in enumerate(candidates[:MAX_REPLAYS], start=1):
        recipe = replay_recipe(row)
        violations = (row.get('outcomes') or {}).get('VIOLATION', 0)
        rows.append({'replay': replay, 'history_row': index, 'development_case_id': row.get('development_case_id'),
                     'recipe': list(row['recipe']), 'fault_spec': recipe.model_dump(mode='json'),
                     'schedule_identity_v2': schedule_identity_v2(recipe),
                     'verified_episodes': row['verified_episodes'], 'violations': violations,
                     'violation_share': f'{violations}/{row["verified_episodes"]}',
                     'every_fault_fired': row['every_fault_fired'], 'outcomes': dict(row.get('outcomes') or {}),
                     'failed_checks': dict(row.get('failed_checks') or {}), 'sources': list(row.get('sources') or [])})
    return rows


def plan_block(history):
    """The replay block frozen into a v4 plan, computed from the plan's frozen history block."""
    summary = history['summary']
    rows = replay_rows(summary)
    statement = AVAILABLE_STATEMENT if rows else (EMPTY_NO_HISTORY if summary.get('status') != 'AVAILABLE' else EMPTY_NONE_ELIGIBLE)
    return {'schema_version': REPLAY_SCHEMA, 'status': 'AVAILABLE' if rows else 'EMPTY', 'statement': statement,
            'rule': RULE, 'basis': MATCH_BASIS, 'max_rows': MAX_REPLAYS,
            'min_verified_episodes': MIN_VERIFIED_EPISODES, 'min_violation_share': MIN_VIOLATION_SHARE_TEXT,
            'history_summary_hash': history['summary_hash'], 'rows': rows}


def verify(block, history):
    """Recompute the replay list from the plan's (already verified) frozen history; refuse if it differs."""
    from app.lab.agent_history import HistoryChanged
    if block is None or block != plan_block(history):
        raise HistoryChanged('The frozen history replay list does not match this plan\'s frozen agent history '
                             f'(summary {history["summary_hash"][:12]}…); create a new plan')
    return block


def replay_marker(row):
    return {'replay': row['replay'], 'history_row': row['history_row'], 'development_case_id': row['development_case_id']}


def record_replay(store, slot_context, row, *, protocol, identity, summary, episode_id, replays_total):
    """Save one replay slot's selection record and return (selection id, output) as an Explorer pick would.

    No Explorer request and no model charge: the record says so (provenance ``history_replay``, usage 0 model calls,
    empty raw text). Its search decision is SELECTED under the protocol's discovery schedule identity, so the Explorer's
    later search ledger lists it as a prior selection and its duplicate rule applies to it.
    """
    from app.lab.agent_history import history_row_match
    recipe = FaultSpec.model_validate_json(canonical_json(row['fault_spec']))
    case = f' ({row["development_case_id"]})' if row['development_case_id'] else ''
    output = ExplorerOutput(fault_spec=recipe, hypothesis=(
        f'History replay {row["replay"]} of {replays_total}: re-runs agent history row {row["history_row"]}{case}, '
        f'which violated in {row["violation_share"]} verified episodes with every fault fired. Chosen by the plan\'s fixed '
        'replay rule, not by the Explorer; no learned selection claim.'))
    marker = replay_marker(row)
    decision = {'status': 'SELECTED', 'schedule_hash': identity(recipe), 'reason': None, 'prior_selection_refs': [],
                'prior_episode_refs': [], 'history_replay': marker}
    replay = {'label': LABEL, 'protocol': protocol, **marker, 'of': replays_total, 'recipe': list(row['recipe']),
              'verified_episodes': row['verified_episodes'], 'violations': row['violations'],
              'violation_share': row['violation_share'], 'every_fault_fired': row['every_fault_fired'],
              'failed_checks': dict(row['failed_checks']), 'schedule_identity_v2': row['schedule_identity_v2'],
              'basis': MATCH_BASIS, 'episode_id': episode_id, 'explorer_request': False}
    selection_id = new_id('selection')
    dumped = output.model_dump(mode='json')
    store.put_record('selections', selection_id, {
        'selection_id': selection_id, 'context': {**slot_context, 'discovery_protocol': protocol}, 'raw': '',
        'model_id': None, 'challenge': False, 'valid': True, 'error': None, 'provenance': 'history_replay',
        'output': dumped, 'selected_output': dumped, 'search_decision': decision,
        'usage': {'model_calls': 0, 'input_tokens': 0, 'output_tokens': 0, 'cost_dollars': 0.0},
        'matches_history_row': history_row_match(summary, recipe), 'history_replay': replay}, immutable=True)
    return selection_id, output


def campaign_replays(store, campaign_id):
    """{episode id: history replay block} of one campaign's replay selection records."""
    found = {}
    for row in store.list_records('selections'):
        block = row.get('history_replay')
        if block and (row.get('context') or {}).get('campaign_id') == campaign_id and not row.get('challenge'):
            found[block['episode_id']] = {**block, 'selection_id': row['selection_id']}
    return found
