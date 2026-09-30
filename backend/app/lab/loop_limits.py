"""Two declared Learn-loop dependability rules, built after live run v2d (September 30, 2026).

Rule 1 is frozen into every new Learn plan (run_plans.prepare_run_plan). Rule 2 is WITHDRAWN before any live run
(fixer stage, after both $0 reviews): no new plan declares it, and a plan that does cannot be created or started
(run_plans.withdrawn_rule_problem). Its code stays here, unused, for the PM's decision. A plan saved before these
rules has neither block, and its campaign keeps today's behaviour exactly. Rule 1 changes no gate, check, threshold,
the challenge's completeness rule or what the Mechanic is asked to produce.

1. ``faultlab-mechanic-context/v2-bounded`` (``mechanic_context`` in the plan).
   Live campaign ea66672d ended ERROR because the Mechanic's next-candidate request (with the challenge feedback)
   came to 33,223 input tokens, over the frozen 32,000 limit, and was refused before dispatch. Under this rule a
   Mechanic candidate request (or diagnosis request) whose first turn would exceed the limit is compacted by fixed
   stages until it is at most ``COMPACTION_TARGET_TOKENS`` (the limit minus a reserve for its one format-repair
   turn). Only the rows of *clean* episodes (no failed check, not the source or one of its reproductions) are ever
   omitted, and each omitted episode is still named, with its own outcome, inside the request. If the request still
   does not fit, the candidate search for that source ends with a recorded reason and nothing is sent; the campaign
   then continues (or ends NO_CHANGE, whose reason then names the search that ended early) by the existing rules.
   A request that fits is sent byte-for-byte as today.

2. ``faultlab-challenge-selection/v2-candidate-reach`` (``challenge_selection`` in the plan). WITHDRAWN.
   The same campaign's challenge ended INCONCLUSIVE because its third pick (F4 on get_operation_status, orders, the
   pick's only fault) did not fire in every pair: with the upgrade healthy, neither arm needs to read the status (the
   fault fired in 1 of 3 incumbent episodes and 0 of 3 candidate episodes; the candidate policy reads the status only
   after an uncertain upgrade or a missing receipt, and it read nothing in that pick). Under this rule, before a
   challenge pick runs any pair, the Explorer's selection handling checks every fault target (tool and service)
   against the calls the agent under test itself made in the candidate arm's source-validation episodes of this
   campaign; a pick with a target the agent never called there is refused and the Explorer gets one re-plan, inside
   the challenge's existing Explorer requests (app/lab/challenge.py is unchanged). Only the agent's own calls count
   because a challenge pair counts only when its faults fire in BOTH arms, and the incumbent arm has no candidate
   policy reads. Both reviews found that this basis depends on the candidate: source validation runs only the
   source's fault, so the rule refuses faults on exactly the paths a candidate never exercised there (for v2d's
   candidate: the orders status read, send_confirmation and the notifications status, 3 of the 5 tool/service
   pairs, although its agent called all three in the same challenge). An offline replay with the real challenge.py
   turned COUNTEREXAMPLE_FOUND into PASSED_OBSERVED. That weakens the challenge, so the rule is withdrawn until the PM
   chooses a basis that does not depend on the candidate (or drops it).
"""
from __future__ import annotations

import json

from app.contracts.models import MODEL_INPUT_TOKEN_LIMIT, canonical_json, new_id

MECHANIC_CONTEXT_V2 = 'faultlab-mechanic-context/v2-bounded'
CHALLENGE_SELECTION_V2 = 'faultlab-challenge-selection/v2-candidate-reach'
# Rule 2 is not frozen into new plans, not offered in run options, and a plan that declares it cannot be created or
# started (run_plans.withdrawn_rule_problem). Kept as data so a saved plan that names it still reads and displays.
CHALLENGE_SELECTION_WITHDRAWN = (
    f'The challenge-pick rule {CHALLENGE_SELECTION_V2} was withdrawn before any live run: it refuses challenge picks '
    'by what the candidate\'s own agent did in source validation, so it can hide a counterexample (both $0 reviews, '
    'finding HIGH-1; docs/PRODUCT_LOOP_LIMITS_2026-09-30.md). This plan cannot start; create a new plan.')

# ----------------------------------------------------------------------------------------------- Mechanic context

FORMAT_REPAIR_RESERVE_TOKENS = 4000   # room for one format-repair turn: up to 2,000 output tokens plus the fixed instruction
COMPACTION_TARGET_TOKENS = MODEL_INPUT_TOKEN_LIMIT - FORMAT_REPAIR_RESERVE_TOKENS
STAGE_IDENTICAL = 'IDENTICAL_CLEAN_ROWS'
STAGE_ONE_PER_GROUP = 'ONE_CLEAN_EPISODE_PER_OUTCOME_GROUP'
STAGE_NO_CLEAN = 'NO_CLEAN_EPISODE_ROWS'
STAGES = (STAGE_IDENTICAL, STAGE_ONE_PER_GROUP, STAGE_NO_CLEAN)
STAGE_TEXT = {
    STAGE_IDENTICAL: 'a clean episode whose rows and outcome are identical to an earlier clean episode is listed by episode_id (same_as)',
    STAGE_ONE_PER_GROUP: 'one clean episode is kept in full per recipe, arm, policy, purpose and outcome (group_example); '
                         'the others are listed by episode_id, and their own rows can differ from that example',
    STAGE_NO_CLEAN: 'no clean episode is kept in full; each is listed by episode_id with its own outcome',
}
ALWAYS_KEPT = ('the source episode and its reproduction episodes', 'every episode with a failed check or a VIOLATION outcome',
               'every trial_outcomes group, candidate history, source validation and challenge feedback field, the runtime '
               'contract and the diagnostic')
MECHANIC_CONTEXT_RULE = (
    'When a Mechanic candidate request (or diagnosis request) would exceed the 32,000-token model input limit, FaultLab '
    'compacts only the evidence tables it carries, in fixed stages, stopping at the first stage after which the request '
    'is at most 28,000 tokens (4,000 tokens stay free for its one format-repair turn): (1) a clean episode (no failed '
    'check, trial outcome not VIOLATION, not the source or one of its reproductions) whose rows and outcome are '
    'identical to an earlier clean episode is listed by episode_id instead of repeated; (2) one clean episode is kept '
    'in full per recipe, arm, policy, experiment purpose and trial outcome, and the others are listed with that example, '
    'although their own rows can differ from it; (3) no clean episode is kept in full. The source, its reproductions '
    'and every episode with a failed check or a VIOLATION outcome are always kept in full, and every omitted episode '
    'is still named in the request with its own outcome. The request states what was compacted and how many rows were '
    'omitted. If it still does not fit, nothing is sent and the candidate search for that source ends with a recorded '
    'reason; the campaign continues, or ends NO_CHANGE with that search named, by the existing rules. An unsent '
    'request does not use one of the campaign\'s candidate requests. A request that fits is sent unchanged.')


def mechanic_context_declaration():
    """The rule as frozen into a reviewed Learn plan (run_plans.MechanicContextPlan)."""
    return {'protocol': MECHANIC_CONTEXT_V2, 'applies_to': ['mechanic_diagnosis', 'mechanic_proposal'],
            'input_token_limit': MODEL_INPUT_TOKEN_LIMIT, 'format_repair_reserve_tokens': FORMAT_REPAIR_RESERVE_TOKENS,
            'compaction_target_tokens': COMPACTION_TARGET_TOKENS, 'stages': list(STAGES), 'always_kept': list(ALWAYS_KEPT),
            'when_unfit': 'END_SOURCE_CANDIDATE_SEARCH', 'unsent_request_uses_candidate_request': False,
            'requests_over_limit_sent': 0, 'rule': MECHANIC_CONTEXT_RULE}


class MechanicContextUnfit(RuntimeError):
    """A Mechanic request that does not fit even after the declared compaction; it was never sent."""
    def __init__(self, reason, record_ref):
        super().__init__(reason)
        self.reason, self.record_ref = reason, record_ref


def _plan(store, campaign):
    from app.lab.runner import campaign_run_plan
    return campaign_run_plan(store, campaign) or {}


def mechanic_context_rule(store, campaign):
    """The declared rule of this campaign's saved plan, or None (plans saved before it: today's behaviour)."""
    return _plan(store, campaign).get('mechanic_context')


def challenge_selection_rule(store, campaign):
    """The declared rule of this campaign's saved plan, or None (plans saved before it: today's behaviour)."""
    return _plan(store, campaign).get('challenge_selection')


def mechanic_request_bound(mechanic, prompt, adapter, context):
    """The Mechanic's own first-turn admission count for this context (app/agents/mechanic.py _generate, attempt 0).

    Same system prompt, same user message (context plus output_schema, canonical JSON), same model resolution and
    the same frozen tokenizer (app.contracts.tokens.input_token_bound).
    """
    from app.agents.mechanic import PROMPTS
    from app.contracts.tokens import input_token_bound
    full = {**context, 'output_schema': adapter.json_schema()}
    messages = [{'role': 'system', 'content': (PROMPTS / prompt).read_text()}, {'role': 'user', 'content': canonical_json(full)}]
    # The real Mechanic always has provider and metadata; an object without them resolves as the Mechanic would with a
    # provider that names no role model and no metadata.
    role_model = getattr(getattr(mechanic, 'provider', None), 'role_model', None)
    expected = ((role_model('mechanic') if callable(role_model) else None)
                or (getattr(mechanic, 'metadata', None) or {}).get('model_id', context.get('model_id', 'openai/gpt-oss-120b')))
    return input_token_bound(messages, expected)


def _summary(value):
    return isinstance(value, dict) and all(isinstance(value.get(key), list) for key in ('episodes', 'results', 'reports', 'checks'))


def _blocks(context, request_kind):
    """Paths of the evidence summaries a request carries, in a fixed order."""
    if request_kind == 'mechanic_diagnosis':
        return [('observations',)] if _summary(context.get('observations')) else []
    paths = [('development_evidence',)] if _summary(context.get('development_evidence')) else []
    for index, item in enumerate(context.get('challenge_counterexamples') or []):
        if isinstance(item, dict) and _summary(item.get('evidence')):
            paths.append(('challenge_counterexamples', index, 'evidence'))
    return paths


def _get(context, path):
    value = context
    for key in path: value = value[key]
    return value


def _set(context, path, value):
    """A copy of context with the value at path replaced (lists and dicts on the path are copied)."""
    if len(path) == 1: return {**context, path[0]: value}
    head, rest = path[0], path[1:]
    child = context[head]
    if isinstance(child, list):
        copied = list(child); copied[rest[0]] = _set(child[rest[0]], rest[1:], value) if len(rest) > 1 else value
        return {**context, head: copied}
    return {**context, head: _set(child, rest, value)}


def _label(path):
    return '.'.join(str(p) if not isinstance(p, int) else f'[{p}]' for p in path).replace('.[', '[')


def filtered_summary(summary, keep):
    """The compact evidence summary of only the kept episodes, with its tables re-indexed.

    Equal to diagnosis.summarize_evidence() of the kept bundles alone: that function interns each episode's
    results (in observation order), then its report, then its checks, and every alias is per episode.
    """
    tables = {'results': [], 'reports': [], 'checks': []}; remap = {kind: {} for kind in tables}
    def take(kind, index):
        if index not in remap[kind]:
            remap[kind][index] = len(tables[kind]); tables[kind].append(summary[kind][index])
        return remap[kind][index]
    episodes = []
    for row in summary['episodes']:
        if row['episode_id'] not in keep: continue
        observations = [[evidence_id, tick, take('results', index)] for evidence_id, tick, index in row['observations']]
        episodes.append({**row, 'observations': observations, 'report_row': take('reports', row['report_row']),
                         'check_row': take('checks', row['check_row'])})
    return {**summary, 'episodes': episodes, **tables}


def _trial_facts(store, episode_id):
    trial = store.get_record('trials', episode_id) if store is not None else None
    if not trial: return None
    facts = {key: trial.get(key) for key in ('scenario_hash', 'arm', 'lifecycle', 'outcome', 'failed_checks', 'fault_scheduled',
                                             'fault_triggered', 'policy_hash')}
    # Development evidence mixes experiment purposes (intervention, source validation) and every candidate's policy.
    facts['purpose'] = (store.get_record('episodes', episode_id) or {}).get('experiment_purpose')
    return facts


def _row_failed(summary, row, facts):
    """A failed check row, a failed_checks entry or a VIOLATION outcome (as promotion.py and evaluation.py count it)."""
    checks = summary['checks'][row['check_row']] or []
    return (any(isinstance(check, dict) and check.get('passed') is False for check in checks)
            or bool(facts and (facts.get('failed_checks') or facts.get('outcome') == 'VIOLATION')))


def _compact_block(summary, stage_index, protected, store):
    """Apply stages 1..stage_index (0-based) to one summary. Returns (compacted summary, omitted rows, kept count)."""
    kept = set(); omitted = []; identical = {}; groups = {}
    for row in summary['episodes']:
        episode_id = row['episode_id']; facts = _trial_facts(store, episode_id)
        if episode_id in protected or _row_failed(summary, row, facts):
            kept.add(episode_id); continue
        outcome = {'arm': facts['arm'], 'lifecycle': facts['lifecycle'], 'outcome': facts['outcome'],
                   'failed_checks': facts['failed_checks'], 'fault_triggered': facts['fault_triggered']} if facts else {'trial_record': None}
        entry = {'episode_id': episode_id, 'observations': len(row['observations']),
                 'original_report_present': row['original_report_present'], **outcome}
        same = canonical_json({'source': row['source'], 'observations': [[tick, index] for _, tick, index in row['observations']],
                               'report_present': row['original_report_present'], 'report_row': row['report_row'],
                               'check_row': row['check_row'], 'facts': facts})
        group = (canonical_json({'scenario_hash': facts['scenario_hash'], 'policy_hash': facts['policy_hash'], 'purpose': facts['purpose'],
                                 **outcome}) if facts else canonical_json({'episode_id': episode_id}))
        if stage_index >= 0 and same in identical:
            omitted.append({**entry, 'omitted_as': STAGE_IDENTICAL, 'same_as': identical[same]}); continue
        if stage_index >= 1 and group in groups:
            omitted.append({**entry, 'omitted_as': STAGE_ONE_PER_GROUP, 'group_example': groups[group]}); continue
        if stage_index >= 2:
            omitted.append({**entry, 'omitted_as': STAGE_NO_CLEAN}); continue
        kept.add(episode_id); identical.setdefault(same, episode_id); groups.setdefault(group, episode_id)
    in_full = len(summary['episodes']) - len(omitted)   # rows kept in full (an episode listed twice counts twice)
    if not omitted: return summary, [], in_full
    compacted = filtered_summary(summary, kept)
    kinds = {o['omitted_as'] for o in omitted}
    compacted['interpretation'] = (summary['interpretation'] + ' COMPACTED under ' + MECHANIC_CONTEXT_V2 + ': this block keeps '
                                   f'{in_full} of {len(summary["episodes"])} episodes in full; each episode in compaction.omitted '
                                   'is named with its own outcome and its rows are left out'
                                   + ('; same_as rows are identical' if STAGE_IDENTICAL in kinds else '')
                                   + ('; rows can differ from their group_example (same recipe, arm, policy, purpose and '
                                      'outcome only)' if STAGE_ONE_PER_GROUP in kinds else '')
                                   + '. "All trials are retained" applies to the kept episodes only.')
    compacted['compaction'] = {'protocol': MECHANIC_CONTEXT_V2, 'episodes_total': len(summary['episodes']),
                               'episodes_in_full': in_full, 'episodes_omitted': len(omitted), 'omitted': omitted}
    return compacted, omitted, in_full


def compact_request(context, *, request_kind, protected_episode_ids, store, bound, full_bound):
    """Deterministic, staged compaction of a Mechanic request's evidence tables.

    bound(context) returns the request's admission count. Returns (compacted context or None, summary dict).
    The summary always says which stages ran and how many rows each block omitted.
    """
    protected = set(protected_episode_ids)
    paths = _blocks(context, request_kind)
    attempts = []
    for stage_index, stage in enumerate(STAGES):
        compacted = context; blocks = []
        for path in paths:
            summary = _get(context, path)
            block, omitted, kept = _compact_block(summary, stage_index, protected, store)
            blocks.append({'field': _label(path), 'episodes_total': len(summary['episodes']), 'episodes_in_full': kept,
                           'episodes_omitted': len(omitted),
                           'omitted_by_stage': {s: sum(1 for o in omitted if o['omitted_as'] == s) for s in STAGES[:stage_index + 1]}})
            if omitted: compacted = _set(compacted, path, block)
        stages = list(STAGES[:stage_index + 1])
        omitted_total = sum(b['episodes_omitted'] for b in blocks)
        if not omitted_total:
            # Nothing to omit at this stage: the request is unchanged (no statement is added), so it still does not fit.
            attempts.append({'stages_applied': stages, 'episode_rows_omitted': 0, 'request_tokens': full_bound})
            continue
        statement = compaction_statement(full_bound, stages, blocks)
        request = {**compacted, 'context_compaction': {'protocol': MECHANIC_CONTEXT_V2, 'statement': statement,
                   'full_request_tokens': full_bound, 'input_token_limit': MODEL_INPUT_TOKEN_LIMIT,
                   'compaction_target_tokens': COMPACTION_TARGET_TOKENS, 'stages_applied': stages,
                   'episode_rows_omitted': omitted_total, 'blocks': blocks}}
        size = bound(request)
        attempts.append({'stages_applied': stages, 'episode_rows_omitted': omitted_total, 'request_tokens': size})
        if size <= COMPACTION_TARGET_TOKENS:
            return request, {'fits': True, 'compacted_tokens': size, 'stages_applied': stages, 'blocks': blocks,
                             'statement': statement, 'attempts': attempts}
    return None, {'fits': False, 'compacted_tokens': None, 'stages_applied': list(STAGES), 'blocks': blocks if paths else [],
                  'statement': None, 'attempts': attempts}


def compaction_statement(full_bound, stages, blocks):
    omitted = sum(b['episodes_omitted'] for b in blocks)
    per_block = '; '.join(f'{b["field"]}: {b["episodes_omitted"]} of {b["episodes_total"]} episodes omitted' for b in blocks) or 'no evidence table'
    return (f'This request was compacted under {MECHANIC_CONTEXT_V2}: in full it was {full_bound:,} input tokens, over the '
            f'{MODEL_INPUT_TOKEN_LIMIT:,}-token model input limit. Stages applied, in order: '
            + '; '.join(f'({i + 1}) {STAGE_TEXT[s]}' for i, s in enumerate(stages)) + '. '
            f'The observation, report and check rows of {omitted} clean episode(s) were omitted ({per_block}); each omitted '
            'episode is still listed by episode_id with its own outcome in its block\'s compaction.omitted, and every '
            'trial_outcomes group is unchanged. The source episode, its reproductions and every episode with a failed '
            'check are kept in full, as is every VIOLATION outcome. Nothing else in this request was changed.')


def _record(store, **fields):
    ref = new_id('mechanic-context')
    store.put_record('mechanic_context_records', ref, {'record_id': ref, 'protocol': MECHANIC_CONTEXT_V2,
                     'input_token_limit': MODEL_INPUT_TOKEN_LIMIT, 'compaction_target_tokens': COMPACTION_TARGET_TOKENS,
                     **fields}, immutable=True)
    return ref


UNFIT_REASON = ('The Mechanic {kind} request is {full:,} input tokens (limit {limit:,}). With every declared compaction stage '
                'applied it is still {last:,} tokens, above the {target:,}-token target ({reserve:,} tokens are kept for its one '
                'format-repair turn): the source episode, its reproductions, every episode with a failed check, the '
                'runtime contract and the feedback fields are never omitted. Nothing was sent; the {what} for this source '
                'ended here.')
REPAIR_REFUSED_REASON = ('The Mechanic {kind} request\'s format-repair turn would exceed the {limit:,}-token model input limit '
                         '({count:,} tokens) and was refused before sending; the first turn was sent and its answer is saved. '
                         'The {what} for this source ended here.')
FIRST_TURN_REFUSED_REASON = ('The Mechanic\'s own input check refused the {kind} request\'s first turn before sending ({count:,} '
                             'tokens; limit {limit:,}). Nothing was sent; the {what} for this source ended here.')
KIND_TEXT = {'mechanic_proposal': ('candidate', 'candidate search'), 'mechanic_diagnosis': ('diagnosis', 'diagnosis and candidate search')}


def fit_request(store, mechanic, context, *, request_kind, campaign_id, counterexample, extra=None):
    """Return (request to send, record ref or None), or raise MechanicContextUnfit after recording why.

    A request whose first turn fits the limit is returned unchanged (no record). Otherwise the declared stages run.
    """
    from pydantic import TypeAdapter
    from app.contracts.models import DiagnosticProposal, MechanicOutput
    prompt, adapter = (('diagnosis.md', TypeAdapter(DiagnosticProposal)) if request_kind == 'mechanic_diagnosis'
                       else ('mechanic.md', TypeAdapter(MechanicOutput)))
    bound = lambda value: mechanic_request_bound(mechanic, prompt, adapter, value)
    full = bound(context)
    if full <= MODEL_INPUT_TOKEN_LIMIT: return context, None
    protected = [counterexample.source_episode_id, *(counterexample.reproduction_trial_ids or [])]
    request, summary = compact_request(context, request_kind=request_kind, protected_episode_ids=protected, store=store,
                                       bound=bound, full_bound=full)
    base = {'campaign_id': campaign_id, 'request_kind': request_kind, 'counterexample_id': counterexample.counterexample_id,
            'source_episode_id': counterexample.source_episode_id, 'full_request_tokens': full, **(extra or {}),
            'stages_applied': summary['stages_applied'], 'blocks': summary['blocks'], 'attempts': summary['attempts']}
    if request is not None:
        ref = _record(store, **base, outcome='COMPACTED', compacted_request_tokens=summary['compacted_tokens'],
                      statement=summary['statement'], reason=None, provider_dispatch=True)
        return request, ref
    noun, what = KIND_TEXT[request_kind]
    reason = UNFIT_REASON.format(kind=noun, full=full, limit=MODEL_INPUT_TOKEN_LIMIT, last=summary['attempts'][-1]['request_tokens'],
                                 target=COMPACTION_TARGET_TOKENS, reserve=MODEL_INPUT_TOKEN_LIMIT - COMPACTION_TARGET_TOKENS, what=what)
    ref = _record(store, **base, outcome='SEARCH_ENDED', stage='BEFORE_SEND', compacted_request_tokens=None, statement=None,
                  reason=reason, provider_dispatch=False)
    raise MechanicContextUnfit(reason, ref)


PROMPT_OF = {'mechanic_proposal': 'mechanic.md', 'mechanic_diagnosis': 'diagnosis.md'}


def request_cutoff(store):
    """The record row number before a Mechanic request: its first-turn answer, if saved, lands above it."""
    return store.max_record_rowid()


def first_turn_output(store, campaign_id, request_kind, cutoff):
    """(record id, payload) of this campaign's first-turn Mechanic answer of this kind saved after the cutoff, or None.

    app/agents/mechanic.py saves every answer (mechanic_outputs, attempt 0 for the first turn) before its format-repair
    turn is checked, so a saved first-turn answer is the proof that the first turn was sent.
    """
    with store.lock:
        row = store.db.execute(
            "SELECT id,payload FROM records WHERE kind='mechanic_outputs' AND rowid>? AND json_extract(payload,'$.campaign_id')=? "
            "AND json_extract(payload,'$.prompt')=? AND json_extract(payload,'$.attempt')=0 ORDER BY rowid LIMIT 1",
            (int(cutoff), campaign_id, PROMPT_OF[request_kind])).fetchone()
    return None if row is None else (row['id'], json.loads(row['payload']))


def record_refusal(store, error, *, request_kind, campaign_id, counterexample, cutoff, compaction_ref=None, extra=None):
    """The Mechanic's own check (tokens.py) refused a turn of a fitted request before dispatch. Returns (record, reason,
    first-turn output or None).

    With this request's first-turn answer saved, the refused turn was its one format-repair turn (FORMAT_REPAIR: the
    first turn was sent and charged). Without it, the first turn itself was refused and nothing was sent (BEFORE_SEND).
    """
    noun, what = KIND_TEXT[request_kind]
    count = getattr(error, 'token_bound', 0) or 0
    first = first_turn_output(store, campaign_id, request_kind, cutoff)
    common = {'campaign_id': campaign_id, 'request_kind': request_kind, 'counterexample_id': counterexample.counterexample_id,
              'source_episode_id': counterexample.source_episode_id, **(extra or {}), 'outcome': 'SEARCH_ENDED',
              'compaction_ref': compaction_ref, 'provider_dispatch': False}
    if first is None:
        reason = FIRST_TURN_REFUSED_REASON.format(kind=noun, count=count, limit=MODEL_INPUT_TOKEN_LIMIT, what=what)
        ref = _record(store, **common, stage='BEFORE_SEND', first_turn_tokens=count or None, reason=reason)
    else:
        reason = REPAIR_REFUSED_REASON.format(kind=noun, limit=MODEL_INPUT_TOKEN_LIMIT, count=count, what=what)
        ref = _record(store, **common, stage='FORMAT_REPAIR', format_repair_tokens=count or None,
                      first_turn_output_ref=first[0], reason=reason)
    return ref, reason, first


def search_ended_note(store, campaign_id):
    """The NO_CHANGE reason's addition when the size rule ended a search early (None when every search finished)."""
    ended = [r['record_id'] for r in campaign_mechanic_context(store, campaign_id) if r.get('outcome') == 'SEARCH_ENDED']
    if not ended: return None
    shown = ', '.join(ended[:3]) + (f' and {len(ended) - 3} more' if len(ended) > 3 else '')
    if len(ended) == 1:
        return f'1 candidate or diagnosis search ended before it finished under {MECHANIC_CONTEXT_V2} (Mechanic request size; record {shown})'
    return (f'{len(ended)} candidate or diagnosis searches ended before they finished under {MECHANIC_CONTEXT_V2} '
            f'(Mechanic request size; records {shown})')


class BoundedMechanic:
    """The Mechanic as the Diagnostician sees it under the declared rule: its diagnosis request is fitted first.

    It delegates to the real Mechanic (app/agents/mechanic.py, unchanged). A request that does not fit, or a turn the
    Mechanic's own check refuses (its format-repair turn, or its first turn, recorded as which one it was), raises
    MechanicContextUnfit after the record is saved; nothing over the limit is ever sent.
    """
    def __init__(self, mechanic, store, *, campaign_id, counterexample):
        self.mechanic, self.store, self.campaign_id, self.counterexample = mechanic, store, campaign_id, counterexample
    def __getattr__(self, name): return getattr(self.mechanic, name)
    async def diagnose(self, context, *, reservation=None):
        from app.contracts.tokens import ModelInputLimit
        request, ref = fit_request(self.store, self.mechanic, context, request_kind='mechanic_diagnosis',
                                   campaign_id=self.campaign_id, counterexample=self.counterexample)
        cutoff = request_cutoff(self.store)
        try:
            return await self.mechanic.diagnose(request, reservation=reservation)
        except ModelInputLimit as error:
            record, reason, _ = record_refusal(self.store, error, request_kind='mechanic_diagnosis', campaign_id=self.campaign_id,
                                               counterexample=self.counterexample, cutoff=cutoff, compaction_ref=ref)
            raise MechanicContextUnfit(reason, record) from None


# ----------------------------------------------------------------------------------------------- Challenge selection

CHALLENGE_REACH_RULE = (
    'Before a challenge pick runs any pair, FaultLab checks every fault target (tool and service) against the calls the '
    'agent under test itself made in the candidate arm\'s source-validation episodes of this campaign. A pick with a '
    'target the agent never called there is refused: no episode runs, and the refusal is recorded with its reason. The '
    'candidate policy\'s own hook reads are not agent calls: a pair counts only when its faults fire in both arms, and '
    'the incumbent arm has no candidate policy reads. The Explorer\'s next request in the same challenge is a '
    're-plan told why (one re-plan per refused pick; a refused re-plan gets none). Every request, re-plans included, is '
    'one of the challenge\'s existing 8 Explorer requests, charged and bounded exactly as before. The challenge itself '
    'is unchanged: 4 schedules, 3 fresh pairs each, every pair must fire its faults, and any candidate violation is a '
    'counterexample. If the candidate arm has no source-validation episode, no pick is refused.')


def challenge_selection_declaration():
    """The rule as frozen into a reviewed Learn plan (run_plans.ChallengeSelectionPlan)."""
    return {'protocol': CHALLENGE_SELECTION_V2, 'basis': 'candidate_arm_source_validation_agent_calls',
            'caller_counted': 'actor', 'target': 'tool_and_service', 'replans_per_refused_pick': 1,
            'explorer_requests_per_challenge': 8, 'refused_pick_runs_episodes': False,
            'challenge_rules_changed': False, 'rule': CHALLENGE_REACH_RULE}


def _call_targets(store, episode_id, calls):
    """(caller, 'tool:service') for every HTTP attempt of this episode's recorded tool calls, in record order.

    Same service resolution as explorer.attempts_by_tool_and_service: a status check names its service in its
    delivered data, or else by the operation id the agent was given in its task.
    """
    intent = (store.get_record('private_episode_inputs', episode_id) or {}).get('intent') or {}
    operations = {intent.get('upgrade_operation_id'): 'orders', intent.get('notification_operation_id'): 'notifications'}
    out = []
    for call in calls:
        tool = call['tool']; observations = call.get('observation_ids', [])
        for index, _ in enumerate(call['attempt_ids']):
            service = {'get_order': 'orders', 'update_order': 'orders', 'send_confirmation': 'notifications'}.get(tool)
            if service is None:
                result = ((store.get_record('observations', observations[index]) or {}).get('result') or {}) if index < len(observations) else {}
                service = (result.get('data') or {}).get('service') or operations.get(result.get('operation_id')) or 'unknown'
            out.append((call.get('caller', 'actor'), f'{tool}:{service}'))
    return out


def candidate_reach(store, campaign_id, candidate_hash):
    """Which tool/service pairs the candidate arm reached in this campaign's source-validation episodes, by caller."""
    episodes = [e['episode_id'] for e in store.list_records('episodes')
                if e.get('campaign_id') == campaign_id and e.get('experiment_purpose') == 'source_validation'
                and e.get('policy_hash') == candidate_hash and e.get('arm', 'L') == 'L']
    wanted = set(episodes); by_episode = {}
    for call in store.list_records('tool_calls'):
        if call.get('episode_id') in wanted: by_episode.setdefault(call['episode_id'], []).append(call)
    agent, policy = set(), set()
    for episode_id in episodes:
        for caller, target in _call_targets(store, episode_id, by_episode.get(episode_id, [])):
            (agent if caller == 'actor' else policy).add(target)
    return {'episode_ids': episodes, 'agent': sorted(agent), 'policy_only': sorted(policy - agent)}


class ChallengeReachSession:
    """One challenge's refusals and its pending re-plan, kept on the Explorer between the Challenger's requests."""
    def __init__(self, key):
        self.key = key; self.pending = None; self.refused = []


def challenge_session(explorer, context):
    key = (context.get('campaign_id'), context.get('candidate_hash'), context.get('incumbent_hash'))
    session = getattr(explorer, '_challenge_reach_session', None)
    if session is None or session.key != key or context.get('proposal_index') == 0:
        session = ChallengeReachSession(key); explorer._challenge_reach_session = session
    return session


def _readable(spec):
    from app.lab.reachability import readable_recipe
    return readable_recipe(spec)


def request_context(reach, session):
    """What the challenge Explorer is told under the rule (added to the Challenger's own context)."""
    block = {'rule': CHALLENGE_REACH_RULE, 'source_validation_episode_ids': reach['episode_ids'],
             'tool_services_called_by_agent': reach['agent'], 'called_only_by_candidate_policy': reach['policy_only'],
             'refused_picks_this_challenge': [dict(item) for item in session.refused]}
    extra = {'challenge_selection_protocol': CHALLENGE_SELECTION_V2, 'candidate_reach': block,
             'slot_request': 2 if session.pending else 1}
    if session.pending:
        extra['replan_of'] = session.pending['refused_selection_id']
        extra['slot_feedback'] = {**session.pending, 'instruction': (
            'Your previous pick was refused before any pair ran. This request is its one re-plan: choose a schedule whose '
            'every fault targets a tool and service in candidate_reach.tool_services_called_by_agent and that is not in '
            'already_tested_fault_specs.')}
    return extra


def _targets(spec):
    seen = []
    for primitive in spec.primitives:
        target = f'{primitive.target_tool}:{primitive.target_service}'
        if target not in seen: seen.append(target)
    return seen


def decide(reach, session, context, selected, error):
    """(decision recorded on the selection, the pick to run or None). Never guesses: no evidence, no refusal."""
    slot_request = context.get('slot_request', 1)
    decision = {'protocol': CHALLENGE_SELECTION_V2, 'proposal_index': context.get('proposal_index'),
                'slot_request': slot_request, 'replan_of': context.get('replan_of'),
                'basis': {'source_validation_episode_ids': reach['episode_ids'],
                          'tool_services_called_by_agent': reach['agent'],
                          'called_only_by_candidate_policy': reach['policy_only']},
                'targets': [], 'unreached': [], 'refused_fault_spec': None, 'reason': None}
    if selected is None:
        decision.update(status='INVALID_OUTPUT', reason=error)
        return decision, None
    decision['targets'] = _targets(selected.fault_spec)
    if not reach['episode_ids']:
        decision.update(status='NOT_CHECKED', reason='The candidate arm has no source-validation episode in this campaign, '
                        'so there is no evidence to refuse a pick on; it runs as before.')
        return decision, selected
    unreached = [t for t in decision['targets'] if t not in reach['agent']]
    if not unreached:
        decision['status'] = 'SELECTED'
        return decision, selected
    named = ', '.join(f'{t.split(":")[0]} ({t.split(":")[1]})' for t in unreached)
    policy = [t for t in unreached if t in reach['policy_only']]
    reason = (f'Refused before any pair ran: this pick puts a fault on {named}, which the agent never called in the candidate '
              f'arm\'s {len(reach["episode_ids"])} source-validation episode(s) of this campaign'
              + (' (only the candidate policy\'s own hook steps read it there; those are not agent calls)' if policy else '')
              + '. ' + ('The next request in this challenge is its one re-plan.' if slot_request == 1 else
                        'This was already the re-plan, so there is no further re-plan for it; the challenge continues with its '
                        'remaining requests.'))
    decision.update(status='REFUSED_UNREACHED', unreached=unreached, reason=reason,
                    refused_fault_spec=selected.fault_spec.model_dump(mode='json'))
    return decision, None


def after_pick(session, selection_id, decision):
    """Keep the refusal for the challenge's later requests and set (or clear) the pending re-plan."""
    if decision['status'] == 'REFUSED_UNREACHED':
        item = {'refused_selection_id': selection_id, 'refused_recipe': _readable(decision['refused_fault_spec']),
                'unreached_tool_services': decision['unreached'], 'reason': decision['reason']}
        session.refused.append(item)
        session.pending = item if decision['slot_request'] == 1 else None
    else:
        session.pending = None


def campaign_challenge_reach(store, campaign_id):
    """Every challenge selection decision recorded under the rule for this campaign, in record order (dashboard)."""
    from app.lab.reachability import readable_recipe
    challenge_of = {}
    for challenge in store.list_records('challenges'):
        for ref in challenge.get('selection_refs', []): challenge_of[ref] = challenge['challenge_id']
    rows = []
    for selection in store.list_records('selections'):
        decision = selection.get('challenge_reach')
        if not selection.get('challenge') or decision is None or (selection.get('context') or {}).get('campaign_id') != campaign_id:
            continue
        spec = (selection.get('output') or {}).get('fault_spec')
        rows.append({'selection_id': selection['selection_id'], 'challenge_id': challenge_of.get(selection['selection_id']),
                     'candidate_hash': (selection.get('context') or {}).get('candidate_hash'),
                     'recipe': readable_recipe(spec) if spec else None, **decision})
    return rows


def campaign_mechanic_context(store, campaign_id):
    """Every Mechanic request-size record of this campaign, in record order (dashboard and recording)."""
    return [r for r in store.list_records('mechanic_context_records') if r.get('campaign_id') == campaign_id]
