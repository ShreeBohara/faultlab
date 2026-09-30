"""Discovery protocol v3: a frozen summary of the same agent's earlier verified development outcomes.

The history is extra, read-only Explorer context. It is computed once, when a Learn plan that
declares ``faultlab-discovery/v3-history`` (or ``…/v3-history-reachability``) is prepared, and
frozen into that plan with its content hash and the store's record cutoff. Execution recomputes
it at the same cutoff and refuses if anything differs; records written after the cutoff (the
campaign's own episodes included) never enter it. See docs/DISCOVERY_V3_HISTORY_2026-09-29.md.

Same agent (``SAME_AGENT_RULE``): same adapter entry point, model id, model request settings, scorer
hash, simulator contract and service, capability set and per-episode limits, and the same prompt —
for the native agent its native prompt hash and native source hash; for the reference Actor its Actor
prompt hash, context protocol and response protocol. Never the configuration hash or registration id,
which also change with campaign limits and the FaultLab runtime, and not the FaultLab runtime or
adapter code: each recipe row lists the runtime and adapter hashes its episodes ran under instead.

Only an allow-list is read: development-split, discovery-purpose, non-B1 episodes of this store
that came from one of two product paths, under the plan's starting policy:
* ``baseline_study``: a B0 slot of a product baseline study (the fixed six development cases x three
  trials; the operator cannot choose the cases);
* ``learn_discovery``: a learn campaign's own discovery pick (the Explorer chose it).
A single-case baseline run (the operator chooses its case) is never used: a few of them could hand the
Explorer an operator-curated history (review finding, September 29). A discovery v4 **history replay** slot
(its selection record has provenance ``history_replay``; app.lab.history_replay) is not an Explorer pick either:
FaultLab ran it by the plan's fixed replay rule. It is never used and not counted, so no later history calls it
"chosen by the Explorer" and the replay rule never counts a row's own replays (review finding MEDIUM-1, September
30). A store without a v4 campaign holds no replay record, so its history is byte-identical. Completed, non-lab-error,
Weave-verified episodes are used; lab errors, interrupted, unfinished and unverified ones are excluded
and counted. Promotion, held-out and final-audit records never pass the split filter, so they are
neither read into the summary nor counted. Recipes come only from public development sources: the
development manifest and the Explorer's own recorded selections (matched by the episode's content hash).
"""
from app.contracts.models import FaultSpec, canonical_json, content_hash
from app.lab.storage import StoreConflict

# v2 (review fixes, September 29): stricter same-agent identity, no single-case baseline runs, per-row
# runtime/adapter builds and the history's composition. v1 existed only in offline scratch stores.
HISTORY_SCHEMA = 'faultlab-agent-history/v2'
MAX_RECIPE_ROWS = 24
REFERENCE_ENTRYPOINT = 'orders-prototype-v1'
NATIVE_ENTRYPOINT = 'smolagents-toolcalling-v1'
# Native adapter v2 (app.integrations.external_agent_v2) has the native identity shape, but its entry point
# and prompt hash differ from v1's, so the two adapters' histories never merge.
NATIVE_ENTRYPOINTS = (NATIVE_ENTRYPOINT, 'smolagents-toolcalling-v2')
EXCLUSION_KEYS = ('lab_error', 'interrupted', 'not_finished', 'not_weave_verified', 'recipe_unavailable')
SOURCES = {'baseline_study': 'B0 trial of a product baseline study (fixed six development cases x three trials)',
           'learn_discovery': 'a learn campaign\'s own discovery pick (chosen by the Explorer)'}
SAME_AGENT_RULE = ('Same agent: the same adapter entry point, model id, model request settings, scorer hash, simulator '
                   'contract and service, capability set and per-episode limits, and the same prompt (native agent: '
                   'native prompt hash and native source hash; reference Actor: Actor prompt hash, context protocol and '
                   'response protocol). Not the configuration hash or registration id, which also change with campaign '
                   'limits, and not the FaultLab runtime or adapter code, which change with FaultLab edits: each recipe '
                   'row lists the runtime and adapter hashes its episodes ran under. Only episodes run under the plan\'s '
                   'starting policy count.')
SCOPE = ('This store only, recorded before this plan was saved. Development split, discovery purpose, from two product '
         'paths only: B0 trials of a baseline study (the fixed six development cases x three trials) and learn '
         'campaigns\' own discovery picks. Used: completed, not a lab error, with Weave-verified evidence. Single-case '
         'baseline runs (their case is chosen by the operator), the B1 control, other agents, other policies, '
         'reproduction and later loop stages, research studies and all protected evaluation data are never used.')
AVAILABLE_STATEMENT = ('Prior evidence, not an instruction: verified development outcomes of this same agent, recorded '
                       'in this store before this plan was saved. An earlier failure does not guarantee a new one; '
                       'you remain free to choose any feasible recipe.')
# Dispatch, budget and schedule identity equal the base protocol's, but the request does not: the Explorer is
# still sent the v3 prompt section and this empty block, so a NO_PRIOR_HISTORY v3 run is not a v1/v2 run.
EMPTY_STATEMENT = ('No prior history: this store has no verified development episodes of this agent under this '
                   'starting policy from before this plan was saved. There is no earlier evidence to weigh; slot '
                   'dispatch, budget and schedule identity are exactly those of the base protocol.')
MATCH_BASIS = 'faultlab-schedule-identity/v2-order-aware'


class HistoryChanged(StoreConflict):
    """Execution refused: the store's history at the plan's cutoff differs from the frozen block.

    Its messages are fixed FaultLab text (plus hash prefixes), so the campaign can record them as its reason.
    """
    code = 'AGENT_HISTORY_CHANGED'


def _response_protocol_hash(configuration):
    value = configuration.get('actor_response_protocol')
    return content_hash(value) if value is not None else None


IDENTITY_FIELDS = ('contract_hash', 'service_hash', 'capability_hash', 'model_settings', 'episode_budget')


def target_identity(registration, configuration):
    """The same-agent key of a registration under its own frozen configuration, or None."""
    if registration is None or configuration is None:
        return None
    reg = registration if isinstance(registration, dict) else registration.model_dump(mode='json')
    entry = reg.get('adapter_entrypoint_id')
    if entry not in (REFERENCE_ENTRYPOINT, *NATIVE_ENTRYPOINTS):
        return None
    if (reg.get('configuration_hash') != content_hash(configuration) or reg.get('model') != configuration.get('model')
            or reg.get('oracle_hash') != configuration.get('scorer_hash')
            or reg.get('prompt_hash') != configuration.get('actor_prompt_hash')
            or reg.get('source_hash') != configuration.get('source_hash')
            or reg.get('contract_hash') != configuration.get('contract_hash')
            or reg.get('capability_hash') != configuration.get('capability_hash')
            or any(configuration.get(field) is None for field in IDENTITY_FIELDS)):
        return None
    identity = {'adapter_entrypoint_id': entry, 'model': reg['model'], 'scorer_hash': reg['oracle_hash'],
                'prompt_hash': reg['prompt_hash']}
    # Review finding (September 29): the simulator contract and service, the capability set, the model request
    # settings and the per-episode limits all shape what the agent faces, so they are part of "same agent".
    identity.update({field: configuration[field] for field in IDENTITY_FIELDS})
    if entry in NATIVE_ENTRYPOINTS:
        identity['source_hash'] = reg['source_hash']
    else:
        from app.lab.configuration import resolve_actor_context_protocol
        try:
            identity['actor_context_protocol'] = resolve_actor_context_protocol(configuration)
        except ValueError:
            return None
        identity['actor_response_protocol_hash'] = _response_protocol_hash(configuration)
    return identity


def _public_recipes(store, cutoff):
    """(content_hash(recipe) -> (recipe, development case id), history replay episode ids), public sources only.

    Recipes come from the development manifest and the Explorer's own recorded selections. A discovery v4 history
    replay selection (provenance ``history_replay``) is FaultLab's, not the Explorer's: its recipe is not read, and
    its episode id is returned so the episode is never used (it precedes its episode, so the cutoff covers both).
    """
    from app.referee.manifests import load_manifest
    known = {}
    for case in load_manifest('development')['cases']:
        recipe = FaultSpec.model_validate_json(canonical_json(case['fault_spec']))
        known[content_hash(recipe)] = (recipe, case['case_id'])
    healthy = FaultSpec(seed=0, primitives=[])  # an unplanned baseline run's fixed no-fault recipe
    known.setdefault(content_hash(healthy), (healthy, None))
    replayed = set()
    # Only four small fields of each selection are read; the large Explorer contexts are never loaded.
    for _, selection in store.record_fields_upto('selections', cutoff, ('challenge', 'selected_output.fault_spec',
                                                                        'provenance', 'history_replay.episode_id')):
        if selection['provenance'] == 'history_replay':
            if isinstance(selection['history_replay.episode_id'], str):
                replayed.add(selection['history_replay.episode_id'])
            continue
        spec = selection['selected_output.fault_spec']
        if selection['challenge'] or not isinstance(spec, dict):
            continue
        try:
            recipe = FaultSpec.model_validate_json(canonical_json(spec))
        except Exception:
            continue
        known.setdefault(content_hash(recipe), (recipe, None))
    return known, replayed


def _at_or_before(store, kind, ident, cutoff):
    rowid = store.record_rowid(kind, ident)
    return store.get_record(kind, ident) if rowid is not None and rowid <= cutoff else None


def _provenance(store, episode, cutoff, cache):
    """'baseline_study', 'learn_discovery', or None (not an allowed product path).

    A baseline campaign's own single-case run (study_id == campaign_id) is not allowed: its development
    case is the operator's choice, so a few of them could curate what the Explorer reads.
    """
    study, campaign_id = episode.get('study_id'), episode.get('campaign_id')
    if episode.get('selector_id') is not None:
        return None
    if study and study == campaign_id == episode.get('evidence_context_id'):
        key = ('campaign', campaign_id)
        if key not in cache:
            campaign = _at_or_before(store, 'campaigns', campaign_id, cutoff)
            ok = bool(campaign and campaign.get('mode') == 'learn'
                      and campaign.get('configuration_hash') == episode.get('configuration_hash'))
            cache[key] = 'learn_discovery' if ok else None
        return cache[key]
    if study and study == episode.get('evidence_context_id'):
        key = ('study', study)
        if key not in cache:
            record = _at_or_before(store, 'baseline_studies', study, cutoff)
            slots = {}
            if record and record.get('schema_version') == 'faultlab-baseline-study/v1':
                slots = {slot.get('episode_id'): slot for slot in record.get('slots', []) if slot.get('arm') == 'B0'}
            cache[key] = (record, slots)
        record, slots = cache[key]
        if (not record or record.get('campaign_id') != campaign_id
                or record.get('configuration_hash') != episode.get('configuration_hash')
                or episode.get('episode_id') not in slots
                or slots[episode['episode_id']].get('scenario_hash') != episode.get('scenario_hash')):
            return None
        return 'baseline_study'
    return None


def _episode_identity(store, episode, cache):
    key = ('identity', episode.get('agent_registration_id'), episode.get('configuration_hash'))
    if key not in cache:
        registration = store.get_record('agent_registrations', key[1]) if key[1] else None
        configuration = store.get_record('configurations', key[2]) if key[2] else None
        cache[key] = target_identity(registration, configuration)
    return cache[key]


def _prefix(value):
    return value[:12] if isinstance(value, str) and value else 'unrecorded'


def _build(store, episode, cache):
    """(runtime hash prefix, adapter hash prefix) of the FaultLab build an episode ran under."""
    key = ('build', episode.get('configuration_hash'))
    if key not in cache:
        configuration = (store.get_record('configurations', key[1]) if key[1] else None) or {}
        cache[key] = (_prefix(configuration.get('runtime_hash')), _prefix(configuration.get('adapter_hash')))
    return cache[key]


def _classify(store, episode, cutoff):
    """(used, exclusion key or None). Assumes the episode is already in scope."""
    lifecycle = episode.get('lifecycle')
    verdict = episode.get('verdict') or None
    if lifecycle == 'LAB_ERROR' or (lifecycle == 'COMPLETED' and (not verdict or verdict.get('outcome') == 'LAB_ERROR')):
        return False, 'lab_error'
    if lifecycle == 'INTERRUPTED':
        return False, 'interrupted'
    if lifecycle != 'COMPLETED':
        return False, 'not_finished'
    evidence = _at_or_before(store, 'evidence', episode['episode_id'], cutoff)
    if not evidence or evidence.get('source') != 'weave_verified' or evidence.get('episode_id') != episode['episode_id']:
        return False, 'not_weave_verified'
    return True, None


def _row(recipe, case_id):
    from app.lab.reachability import readable_recipe
    spec = recipe.model_dump(mode='json')
    return {'development_case_id': case_id, 'recipe': readable_recipe(spec) if spec['primitives'] else ['No injected fault'],
            'primitives': spec['primitives'], 'sources': [], 'verified_episodes': 0,
            'every_fault_fired': 0 if spec['primitives'] else None, 'outcomes': {}, 'failed_checks': {},
            'excluded': {}, 'runtime_hashes': [], 'adapter_hashes': []}


def compute_history(store, *, identity, policy_hash, cutoff):
    """The history block for one agent identity and starting policy, at a fixed record cutoff."""
    from app.lab.challenge import schedule_identity_v2
    if not isinstance(cutoff, int) or cutoff < 0:
        raise ValueError('A history record cutoff is a non-negative row number')
    known, replayed = _public_recipes(store, cutoff)
    # A row is named after a development case when its schedule matches the case's, whatever the seed.
    case_of = {schedule_identity_v2(recipe): case_id for recipe, case_id in known.values() if case_id}
    cache = {}; rows = {}; order = []; used_ids = []; builds = {}
    contributors = {source: set() for source in SOURCES}; contributed = {source: 0 for source in SOURCES}
    excluded = {key: 0 for key in EXCLUSION_KEYS}
    candidates = store.records_upto('episodes', cutoff, where={'split': 'development', 'experiment_purpose': 'discovery'})
    for _, episode in candidates:
        # The SQL filter is repeated here: nothing outside the development discovery scope is ever read further.
        if (episode.get('split') != 'development' or episode.get('experiment_purpose') != 'discovery'
                or episode.get('arm') == 'B1' or episode.get('policy_hash') != policy_hash):
            continue
        source = _provenance(store, episode, cutoff, cache)
        if source is None or identity is None or _episode_identity(store, episode, cache) != identity:
            continue
        if episode.get('episode_id') in replayed:
            continue  # a discovery v4 history replay: FaultLab's pick, not the Explorer's; never used, not counted
        if episode.get('model') != identity['model']:
            continue
        verdict = episode.get('verdict') or {}
        if verdict and verdict.get('scorer_hash') not in (None, identity['scorer_hash']):
            continue
        entry = known.get(episode.get('scenario_hash'))
        if entry is None:
            excluded['recipe_unavailable'] += 1
            continue
        used, reason = _classify(store, episode, cutoff)
        recipe = entry[0]
        key = schedule_identity_v2(recipe)
        if key not in rows:
            rows[key] = _row(recipe, case_of.get(key)); order.append(key)
        row = rows[key]
        if not used:
            excluded[reason] += 1
            row['excluded'][reason] = row['excluded'].get(reason, 0) + 1
            continue
        used_ids.append(episode['episode_id'])
        if source not in row['sources']: row['sources'].append(source)
        contributors[source].add(episode['study_id']); contributed[source] += 1
        runtime, adapter = _build(store, episode, cache)
        builds[runtime, adapter] = builds.get((runtime, adapter), 0) + 1
        if runtime not in row['runtime_hashes']: row['runtime_hashes'].append(runtime)
        if adapter not in row['adapter_hashes']: row['adapter_hashes'].append(adapter)
        row['verified_episodes'] += 1
        outcome = verdict.get('outcome')
        row['outcomes'][outcome] = row['outcomes'].get(outcome, 0) + 1
        for check in verdict.get('checks', []):
            if not check.get('passed'):
                row['failed_checks'][check['check_id']] = row['failed_checks'].get(check['check_id'], 0) + 1
        executions = verdict.get('fault_executions') or []
        if row['every_fault_fired'] is not None and executions and all(item.get('triggered') for item in executions):
            row['every_fault_fired'] += 1
    # Development cases first, in case order; every other recipe by its first stored episode.
    ordered = sorted(order, key=lambda key: (0, rows[key]['development_case_id'], 0) if rows[key]['development_case_id']
                     else (1, '', order.index(key)))
    recipes = []
    for key in ordered:
        row = rows[key]
        row['sources'] = sorted(row['sources'])
        row['runtime_hashes'] = sorted(row['runtime_hashes']); row['adapter_hashes'] = sorted(row['adapter_hashes'])
        row['outcomes'] = dict(sorted(row['outcomes'].items()))
        row['failed_checks'] = dict(sorted(row['failed_checks'].items(), key=lambda item: int(item[0][1:])))
        row['excluded'] = dict(sorted(row['excluded'].items()))
        recipes.append(row)
    verified = len(used_ids)
    summary = {'schema_version': HISTORY_SCHEMA, 'status': 'AVAILABLE' if verified else 'NO_PRIOR_HISTORY',
               'statement': AVAILABLE_STATEMENT if verified else EMPTY_STATEMENT, 'scope': SCOPE,
               'agent': {'adapter_entrypoint_id': identity['adapter_entrypoint_id'] if identity else None,
                         'model': identity['model'] if identity else None},
               'verified_episodes': verified, 'recipes_total': sum(1 for row in recipes if row['verified_episodes']),
               # Where the history comes from, so a result can name its composition (store shopping is visible).
               'composition': {'baseline_studies': len(contributors['baseline_study']),
                               'baseline_study_episodes': contributed['baseline_study'],
                               'learn_campaigns': len(contributors['learn_discovery']),
                               'learn_discovery_episodes': contributed['learn_discovery']},
               'builds': [{'runtime_hash': runtime, 'adapter_hash': adapter, 'verified_episodes': count}
                          for (runtime, adapter), count in sorted(builds.items())],
               'excluded': excluded,
               'recipes': [row for row in recipes if row['verified_episodes']][:MAX_RECIPE_ROWS],
               'recipes_omitted': max(0, sum(1 for row in recipes if row['verified_episodes']) - MAX_RECIPE_ROWS),
               'excluded_only_recipes': sum(1 for row in recipes if not row['verified_episodes'])}
    return {'schema_version': HISTORY_SCHEMA, 'status': summary['status'], 'rule': SAME_AGENT_RULE,
            'agent_identity': identity, 'policy_hash': policy_hash, 'record_cutoff': cutoff,
            'episode_ids_hash': content_hash(sorted(used_ids)), 'summary': summary,
            'summary_hash': content_hash(summary)}


def snapshot(store, *, registration, configuration, policy_hash):
    """Freeze the history now: read the store's current record cutoff, then compute at it."""
    identity = target_identity(registration, configuration)
    if identity is None:
        raise ValueError('The registered agent has no supported same-agent identity')
    return compute_history(store, identity=identity, policy_hash=policy_hash, cutoff=store.max_record_rowid())


def history_row_match(summary, recipe):
    """The listed history row whose schedule equals this recipe's, or None.

    Compared with the order-aware schedule identity (seed ignored), the identity the rows are grouped by.
    A match means the pick re-tries a recipe the Explorer was shown, so a result from it is history-informed.
    """
    if not summary or recipe is None:
        return None
    from app.lab.challenge import schedule_identity_v2
    recipe = recipe if isinstance(recipe, FaultSpec) else FaultSpec.model_validate_json(canonical_json(recipe))
    target = schedule_identity_v2(recipe)
    for index, row in enumerate(summary.get('recipes') or [], start=1):
        listed = FaultSpec.model_validate_json(canonical_json({'seed': 0, 'primitives': row['primitives']}))
        if schedule_identity_v2(listed) == target:
            return {'row': index, 'development_case_id': row.get('development_case_id'), 'basis': MATCH_BASIS}
    return None


def verify(store, block, *, registration, configuration, policy_hash):
    """Recompute a frozen block at its own cutoff; raise HistoryChanged if anything differs."""
    identity = target_identity(registration, configuration)
    if (identity is None or block.get('agent_identity') != identity or block.get('policy_hash') != policy_hash
            or block.get('summary_hash') != content_hash(block.get('summary'))):
        raise HistoryChanged('The frozen agent history does not match this plan\'s agent, policy or summary hash')
    current = compute_history(store, identity=identity, policy_hash=policy_hash, cutoff=block['record_cutoff'])
    if current != block:
        raise HistoryChanged('The store\'s prior history for this agent changed at or before the plan\'s record cutoff '
                             f'(frozen summary {block["summary_hash"][:12]}…, now {current["summary_hash"][:12]}…); '
                             'create a new plan')
    return block
