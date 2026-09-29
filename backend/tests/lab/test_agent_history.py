"""Discovery protocol v3 history (app.lab.agent_history): same-agent rule, eligibility, snapshot, exclusions.

Offline and $0: records are seeded directly into a scratch store with the shapes the product writes
(baseline-study B0 slots, a campaign's own discovery run, evidence records). No provider, model,
simulator, W&B or network call. Nothing here is model evidence.
"""
import asyncio

import pytest

from app.config import Settings
from app.contracts.models import FaultSpec, canonical_json, content_hash, new_id
from app.lab import agent_history
from app.lab.agent_history import EMPTY_STATEMENT, compute_history, history_row_match, target_identity
from app.lab.coordinator import LabCoordinator
from app.lab.discovery_protocol import DISCOVERY_V1, DISCOVERY_V2, DISCOVERY_V3, DISCOVERY_V3_PRECHECK
from app.lab.learning import discovery_history
from app.lab.operator_actions import register_agent
from app.lab.run_plans import (RunPlanRequest, TASK, TASK_TEXT, build_run_options, prepare_run_plan, read_run_plan,
                               validate_run_plan)
from app.lab.runner import B1_CONTROL_ID, B1_CONTROL_MODEL
from app.lab.storage import StoreConflict
from app.referee.manifests import load_manifest

ACTOR_MODEL = 'deepseek-ai/DeepSeek-V3.1'
EXPLORER_MODEL = 'deepseek-ai/DeepSeek-V4-Pro-0813'
CASES = {case['case_id']: case for case in load_manifest('development')['cases']}


def spec(value):
    return FaultSpec.model_validate_json(canonical_json(value))


def case(case_id):
    return spec(CASES[case_id]['fault_spec'])


def P(kind, tool, service, occurrence, **parameters):
    return {'kind': kind, 'target_tool': tool, 'target_service': service, 'occurrence': occurrence, 'parameters': parameters}


# An Explorer pick that is not a development case, and a recipe that exists ONLY in seeded protected
# records (promotion / held-out / final audit): it must never reach the summary or any Explorer message.
EXPLORED = spec({'seed': 41, 'primitives': [P('F4', 'send_confirmation', 'notifications', 1, failure_count=3)]})
PROTECTED = spec({'seed': 777, 'primitives': [P('F3', 'get_order', 'orders', 7, versions_back=3)]})
PROTECTED_WORDS = 'get_order:orders attempt 7'


@pytest.fixture
def anyio_backend(): return 'asyncio'


def settings_for(path, **overrides):
    return Settings(faultlab_artifact_dir=str(path), wandb_model=ACTOR_MODEL, wandb_explorer_model=EXPLORER_MODEL, **overrides)


@pytest.fixture
def owner(tmp_path):
    coordinator = LabCoordinator(settings_for(tmp_path / 'lab'))
    try: yield coordinator
    finally: asyncio.run(coordinator.close())


def plan_request(owner, registration, **overrides):
    options = build_run_options(owner.settings, owner.store)
    return RunPlanRequest(**{'expected_store_identity': options['data_store']['identity'],
        'expected_setup_hash': options['setup_hash'], 'task_definition_id': TASK, 'mode': 'learn',
        'config_profile_id': 'live-v1', 'task_text': TASK_TEXT, 'order_id': new_id('order'),
        'agent_registration_id': registration.registration_id, **overrides})


def planned(owner, registration, **overrides):
    prepared = prepare_run_plan(owner.store, owner.settings, plan_request(owner, registration, **overrides))
    return owner.create(prepared.campaign_request, run_plan=prepared)


class Seeder:
    """Writes episodes exactly as the product's baseline study and learn discovery would."""
    def __init__(self, owner, registration):
        self.owner, self.store, self.registration = owner, owner.store, registration
        self.configuration = self.store.get_record('configurations', registration.configuration_hash)
        self.policy_hash = owner.policies.baseline().policy_hash
        self.campaign = planned(owner, registration, mode='baseline', development_case_id='dev-1')
        self.learn = None
        self.study_id = new_id('baseline-study'); self.slots = []
        self._save_study()

    def _save_study(self):
        self.store.put_record('baseline_studies', self.study_id, {
            'schema_version': 'faultlab-baseline-study/v1', 'study_id': self.study_id, 'campaign_id': self.campaign.campaign_id,
            'configuration_hash': self.campaign.configuration_hash, 'status': 'COMPLETED', 'slots': self.slots})

    def learn_campaign(self):
        if self.learn is None:
            self.learn = planned(self.owner, self.registration, discovery_protocol=DISCOVERY_V1)
        return self.learn

    def select(self, recipe, campaign):
        """The Explorer's own recorded pick: the only public source of a non-case recipe."""
        ident = new_id('selection')
        self.store.put_record('selections', ident, {'selection_id': ident, 'challenge': False, 'search_decision': None,
            'context': {'campaign_id': campaign.campaign_id, 'selection_index': 0, 'development_history': []},
            'selected_output': {'fault_spec': recipe.model_dump(mode='json'), 'hypothesis': 'seeded'}})

    def episode(self, recipe, *, failed=(), outcome=None, lifecycle='COMPLETED', verified=True, arm='B0', via='study',
                split='development', purpose='discovery', policy_hash=None, triggered=True, registration_id=None,
                model=None, campaign=None, scorer_hash=None):
        episode_id = new_id('episode'); scenario = content_hash(recipe)
        campaign = campaign or (self.campaign if via == 'study' else self.learn_campaign())
        if via == 'study':
            study = self.study_id
            self.slots.append({'episode_id': episode_id, 'arm': arm, 'scenario_hash': scenario, 'status': lifecycle})
            self._save_study()
        elif via == 'campaign':
            study = campaign.campaign_id
        else:
            study = via
        verdict = None
        if lifecycle in ('COMPLETED', 'LAB_ERROR'):
            verdict = {'outcome': outcome or ('LAB_ERROR' if lifecycle == 'LAB_ERROR' else 'VIOLATION' if failed else 'COMPLETED'),
                       'checks': [{'check_id': f'C{i}', 'passed': f'C{i}' not in failed} for i in range(1, 9)],
                       'fault_executions': [{'triggered': triggered} for _ in recipe.primitives],
                       'scorer_hash': scorer_hash or self.configuration['scorer_hash']}
        control = arm == 'B1'
        self.store.put_record('episodes', episode_id, {
            'campaign_id': campaign.campaign_id, 'episode_id': episode_id, 'split': split, 'experiment_purpose': purpose,
            'arm': arm, 'source_mode': 'offline_fixture' if control else 'live', 'study_id': study, 'evidence_context_id': study,
            'selector_id': None, 'agent_registration_id': B1_CONTROL_ID if control else (registration_id or self.registration.registration_id),
            'configuration_hash': campaign.configuration_hash, 'model': B1_CONTROL_MODEL if control else (model or self.registration.model),
            'policy_hash': policy_hash or self.policy_hash, 'policy_version': 'policy-v0', 'scenario_hash': scenario,
            'lifecycle': lifecycle, 'verdict': verdict})
        if verified:
            self.store.put_record('evidence', episode_id, {'episode_id': episode_id, 'source': 'weave_verified'})
        return episode_id

    def history(self, identity=None, cutoff=None):
        identity = identity or target_identity(self.registration, self.configuration)
        return compute_history(self.store, identity=identity, policy_hash=self.policy_hash,
                               cutoff=self.store.max_record_rowid() if cutoff is None else cutoff)


def seed_screen(seeder):
    """dev-5 violated C3 and C5 in 3 of 3 (as the native probe did); dev-1 completed 3 of 3."""
    for _ in range(3):
        seeder.episode(case('dev-5'), failed=('C3', 'C5'))
        seeder.episode(case('dev-1'))


# ---------------------------------------------------------------- the same-agent rule
def test_same_agent_rule_is_entry_point_prompt_source_model_and_scorer_not_the_configuration_hash(owner, tmp_path):
    native = register_agent(owner.store, owner.settings, 'smolagents')
    config = owner.store.get_record('configurations', native.configuration_hash)
    # A second registration with different campaign caps: another configuration hash and registration id.
    capped = register_agent(owner.store, settings_for(tmp_path / 'other', faultlab_model_call_cap=5000), 'smolagents')
    capped_config = owner.store.get_record('configurations', capped.configuration_hash)
    assert native.configuration_hash != capped.configuration_hash and native.registration_id != capped.registration_id
    identity = target_identity(native, config)
    assert identity == target_identity(capped, capped_config)
    assert identity == {'adapter_entrypoint_id': 'smolagents-toolcalling-v1', 'model': ACTOR_MODEL,
                        'scorer_hash': config['scorer_hash'], 'prompt_hash': native.prompt_hash, 'source_hash': native.source_hash,
                        'contract_hash': config['contract_hash'], 'service_hash': config['service_hash'],
                        'capability_hash': config['capability_hash'], 'model_settings': config['model_settings'],
                        'episode_budget': config['episode_budget']}
    # Every named component matters; the registration and its configuration must agree.
    raw = native.model_dump(mode='json')
    for field, key, value in (('prompt_hash', 'actor_prompt_hash', 'e' * 64), ('source_hash', 'source_hash', 'f' * 64),
                              ('model', 'model', 'other/model'), ('oracle_hash', 'scorer_hash', 'a' * 64)):
        changed_config = {**config, key: value}
        changed = {**raw, field: value, 'configuration_hash': content_hash(changed_config)}
        assert target_identity(changed, changed_config) not in (None, identity)
        assert target_identity({**raw, field: value}, config) is None  # inconsistent pair: no identity at all
    assert target_identity({**raw, 'adapter_entrypoint_id': 'orders-prototype-v1'}, config) != identity
    assert target_identity({**raw, 'adapter_entrypoint_id': 'unreviewed-v1'}, config) is None
    # The reference Actor: its prompt, context protocol and response protocol; never its source tree hash.
    reference = register_agent(owner.store, owner.settings, 'reference')
    reference_config = owner.store.get_record('configurations', reference.configuration_hash)
    reference_identity = target_identity(reference, reference_config)
    assert set(reference_identity) == {'adapter_entrypoint_id', 'model', 'scorer_hash', 'prompt_hash',
                                       'actor_context_protocol', 'actor_response_protocol_hash', 'contract_hash',
                                       'service_hash', 'capability_hash', 'model_settings', 'episode_budget'}
    assert reference_identity['actor_context_protocol'] == reference_config['actor_context_protocol']
    older = {**reference_config, 'actor_context_protocol': 'faultlab-actor-context/v1'}
    assert target_identity({**reference.model_dump(mode='json'), 'configuration_hash': content_hash(older)}, older) != reference_identity


def test_history_counts_the_same_agent_across_registrations_but_not_another_agent_policy_or_scorer(owner, tmp_path):
    native = register_agent(owner.store, owner.settings, 'smolagents')
    seeder = Seeder(owner, native)
    seed_screen(seeder)
    capped = register_agent(owner.store, settings_for(tmp_path / 'other', faultlab_model_call_cap=5000), 'smolagents')
    capped_identity = target_identity(capped, owner.store.get_record('configurations', capped.configuration_hash))
    assert seeder.history(capped_identity)['summary'] == seeder.history()['summary']
    assert seeder.history()['summary']['verified_episodes'] == 6
    # Out of scope, neither used nor counted: another agent, another policy, another scorer, a B1 control.
    reference = register_agent(owner.store, owner.settings, 'reference')
    other = Seeder(owner, reference)
    other.episode(case('dev-5'), failed=('C3',))
    seeder.episode(case('dev-5'), failed=('C3',), policy_hash='b' * 64)
    seeder.episode(case('dev-5'), failed=('C3',), scorer_hash='c' * 64)
    seeder.episode(case('dev-5'), arm='B1')
    after = seeder.history()['summary']
    assert after['verified_episodes'] == 6 and not any(after['excluded'].values())
    assert other.history()['summary']['verified_episodes'] == 1


# ---------------------------------------------------------------- eligibility and counts
def test_used_excluded_and_out_of_scope_episodes(owner):
    native = register_agent(owner.store, owner.settings, 'smolagents')
    seeder = Seeder(owner, native)
    seed_screen(seeder)
    for _ in range(3): seeder.episode(case('dev-5'), arm='B1')            # the handwritten control: never counted
    seeder.episode(case('dev-3'), lifecycle='LAB_ERROR')                  # excluded and counted
    seeder.episode(case('dev-3'), lifecycle='INTERRUPTED', verified=False)
    seeder.episode(case('dev-3'), lifecycle='RUNNING', verified=False)
    seeder.episode(case('dev-3'), verified=False)                         # completed, evidence never verified
    learn = seeder.learn_campaign()
    seeder.select(EXPLORED, learn)
    seeder.episode(EXPLORED, failed=('C7',), via='campaign')              # the Explorer's own earlier pick
    seeder.episode(spec({'seed': 5, 'primitives': [P('F1', 'send_confirmation', 'notifications', 2, response_delay_ms=2000)]}),
                   via='campaign')                                        # no public record of its recipe
    seeder.episode(case('dev-2'), via='campaign', purpose='reproduction')  # a later loop stage: out of scope
    seeder.episode(case('dev-2'), via='study-that-does-not-exist')       # not a known product path
    block = seeder.history()
    summary = block['summary']
    assert summary['status'] == 'AVAILABLE' and summary['verified_episodes'] == 7
    assert summary['excluded'] == {'lab_error': 1, 'interrupted': 1, 'not_finished': 1, 'not_weave_verified': 1,
                                   'recipe_unavailable': 1}
    rows = summary['recipes']
    assert [row['development_case_id'] for row in rows] == ['dev-1', 'dev-5', None]
    dev1, dev5, explored = rows
    build = ([seeder.configuration['runtime_hash'][:12]], [seeder.configuration['adapter_hash'][:12]])
    assert dev1 == {'development_case_id': 'dev-1', 'recipe': ['No injected fault'], 'primitives': [],
                    'sources': ['baseline_study'], 'verified_episodes': 3, 'every_fault_fired': None,
                    'outcomes': {'COMPLETED': 3}, 'failed_checks': {}, 'excluded': {},
                    'runtime_hashes': build[0], 'adapter_hashes': build[1]}
    assert summary['composition'] == {'baseline_studies': 1, 'baseline_study_episodes': 6, 'learn_campaigns': 1,
                                      'learn_discovery_episodes': 1}
    assert summary['builds'] == [{'runtime_hash': build[0][0], 'adapter_hash': build[1][0], 'verified_episodes': 7}]
    assert dev5['verified_episodes'] == 3 and dev5['outcomes'] == {'VIOLATION': 3}
    assert dev5['failed_checks'] == {'C3': 3, 'C5': 3} and dev5['every_fault_fired'] == 3
    assert dev5['recipe'] == ['F2 on update_order:orders attempt 1: the accepted upgrade stays PENDING for 2 ticks, then FAILED (UPGRADE_REJECTED)']
    assert explored['sources'] == ['learn_discovery'] and explored['failed_checks'] == {'C7': 1}
    assert explored['primitives'] == [p.model_dump(mode='json') for p in EXPLORED.primitives]
    assert summary['recipes_total'] == 3 and summary['excluded_only_recipes'] == 1 and summary['recipes_omitted'] == 0
    assert block['summary_hash'] == content_hash(summary)


def test_a_discovery_pick_equal_to_a_case_joins_that_case_row_whatever_its_seed(owner):
    seeder = Seeder(owner, register_agent(owner.store, owner.settings, 'smolagents'))
    seed_screen(seeder)
    same = spec({**CASES['dev-5']['fault_spec'], 'seed': 9})
    seeder.select(same, seeder.learn_campaign())
    seeder.episode(same, failed=('C3',), via='campaign')
    dev5 = next(row for row in seeder.history()['summary']['recipes'] if row['development_case_id'] == 'dev-5')
    assert dev5['sources'] == ['baseline_study', 'learn_discovery'] and dev5['verified_episodes'] == 4
    assert dev5['failed_checks'] == {'C3': 4, 'C5': 3}
    # A pick with a case's schedule is named after that case even when the case itself never ran here.
    like_dev3 = spec({**CASES['dev-3']['fault_spec'], 'seed': 12})
    seeder.select(like_dev3, seeder.learn_campaign())
    seeder.episode(like_dev3, via='campaign')
    rows = seeder.history()['summary']['recipes']
    assert [row['development_case_id'] for row in rows] == ['dev-1', 'dev-3', 'dev-5']
    assert rows[1]['sources'] == ['learn_discovery'] and rows[1]['verified_episodes'] == 1


# ---------------------------------------------------------------- protected data
def seed_protected(seeder):
    """Promotion, held-out, final-audit and portability records, including partly mislabelled ones."""
    store = seeder.store
    check_id = new_id('heldout-check')
    store.put_record('heldout_checks', check_id, {'check_id': check_id, 'campaign_id': seeder.campaign.campaign_id})
    store.put_record('selections', new_id('selection'), {'challenge': False, 'search_decision': None,
        'context': {'campaign_id': 'protected', 'selection_index': 0},
        'selected_output': {'fault_spec': PROTECTED.model_dump(mode='json'), 'hypothesis': 'protected'}})
    ids = []
    for arm in ('B0', 'L'):
        ids.append(seeder.episode(PROTECTED, failed=('C3',), arm=arm, via=check_id, split='promotion', purpose='promotion'))
    ids.append(seeder.episode(PROTECTED, failed=('C3',), via=check_id, split='final_audit', purpose='final_audit'))
    ids.append(seeder.episode(PROTECTED, failed=('C3',), via=check_id, split='final_audit', purpose='portability'))
    # Disguised: a protected split with a discovery label, a development split with a protected purpose,
    # and a development discovery label on a held-out check's trial.
    ids.append(seeder.episode(PROTECTED, failed=('C3',), via=check_id, split='promotion', purpose='discovery'))
    ids.append(seeder.episode(PROTECTED, failed=('C3',), via=check_id, split='development', purpose='promotion'))
    ids.append(seeder.episode(PROTECTED, failed=('C3',), via=check_id))
    ids.append(seeder.episode(case('dev-5'), failed=('C3',), via=check_id, split='promotion', purpose='promotion'))
    # A learn campaign's own promotion and final-audit trials carry study_id == campaign_id exactly like its
    # discovery episodes; only the split and purpose tell them apart.
    for arm in ('B0', 'L'):
        ids.append(seeder.episode(PROTECTED, failed=('C3',), arm=arm, via='campaign', split='promotion', purpose='promotion'))
    ids.append(seeder.episode(PROTECTED, failed=('C3',), via='campaign', split='final_audit', purpose='final_audit'))
    return ids


def test_seeded_promotion_heldout_and_final_audit_records_are_excluded_and_never_counted(owner):
    seeder = Seeder(owner, register_agent(owner.store, owner.settings, 'smolagents'))
    seed_screen(seeder)
    before = seeder.history()['summary']
    protected_ids = seed_protected(seeder)
    block = seeder.history()
    # Identical summary: the protected records are neither used nor counted in any exclusion.
    assert block['summary'] == before and not any(block['summary']['excluded'].values())
    text = canonical_json(block)
    assert PROTECTED_WORDS not in text and '"occurrence":7' not in text
    assert not any(ident in text for ident in protected_ids)


# ---------------------------------------------------------------- snapshot and cutoff
def test_plan_freezes_the_summary_hash_and_cutoff_and_later_records_never_leak(owner):
    native = register_agent(owner.store, owner.settings, 'smolagents')
    seeder = Seeder(owner, native)
    seed_screen(seeder)
    running = seeder.episode(case('dev-3'), lifecycle='RUNNING', verified=False)
    campaign = planned(owner, native, discovery_protocol=DISCOVERY_V3)
    plan = read_run_plan(owner.store, campaign)['plan']
    history = plan['discovery']['history']
    assert history['summary']['verified_episodes'] == 6 and history['summary']['excluded']['not_finished'] == 1
    assert history['summary_hash'] == content_hash(history['summary'])
    assert history['record_cutoff'] < owner.store.record_rowid('campaigns', campaign.campaign_id)
    assert history['agent_identity'] == target_identity(native, seeder.configuration)
    assert history['policy_hash'] == plan['initial_policy_hash'] == seeder.policy_hash
    # Records written after the cutoff (new episodes of the same agent) never enter this plan's history.
    for _ in range(3): seeder.episode(case('dev-6'), failed=('C4',))
    assert validate_run_plan(owner.store, owner.settings, owner.get(campaign.campaign_id)) == plan
    assert discovery_history(owner.store, owner.get(campaign.campaign_id)) == {
        'discovery_protocol': DISCOVERY_V3, 'agent_history': history['summary']}
    later = planned(owner, native, discovery_protocol=DISCOVERY_V3)
    assert read_run_plan(owner.store, later)['plan']['discovery']['history']['summary']['verified_episodes'] == 9
    # A record at or before the cutoff that changes afterwards refuses execution, before any Explorer request.
    record = owner.store.get_record('episodes', running)
    owner.store.put_record('episodes', running, {**record, 'lifecycle': 'COMPLETED', 'verdict': {
        'outcome': 'COMPLETED', 'checks': [{'check_id': f'C{i}', 'passed': True} for i in range(1, 9)],
        'fault_executions': [{'triggered': True}], 'scorer_hash': seeder.configuration['scorer_hash']}})
    owner.store.put_record('evidence', running, {'episode_id': running, 'source': 'weave_verified'})
    with pytest.raises(StoreConflict, match='changed at or before the plan.s record cutoff'):
        validate_run_plan(owner.store, owner.settings, owner.get(campaign.campaign_id))
    with pytest.raises(StoreConflict, match='create a new plan'):
        discovery_history(owner.store, owner.get(campaign.campaign_id))
    # The frozen plan itself is unchanged and still reads; only execution is refused.
    assert read_run_plan(owner.store, campaign)['plan'] == plan


def test_a_tampered_or_mismatched_history_block_is_refused(owner):
    native = register_agent(owner.store, owner.settings, 'smolagents')
    seeder = Seeder(owner, native)
    seed_screen(seeder)
    block = agent_history.snapshot(owner.store, registration=native, configuration=seeder.configuration,
                                   policy_hash=seeder.policy_hash)
    kwargs = {'registration': native, 'configuration': seeder.configuration, 'policy_hash': seeder.policy_hash}
    assert agent_history.verify(owner.store, block, **kwargs) == block
    tampered = {**block, 'summary': {**block['summary'], 'verified_episodes': 7}}
    for bad, arguments in ((tampered, kwargs), (block, {**kwargs, 'policy_hash': 'd' * 64}),
                           ({**block, 'record_cutoff': 0}, kwargs)):
        with pytest.raises(agent_history.HistoryChanged):
            agent_history.verify(owner.store, bad, **arguments)


# ---------------------------------------------------------------- no history, declarations and budgets
def test_no_prior_history_is_said_plainly_and_the_block_is_its_base_protocol(owner):
    native = register_agent(owner.store, owner.settings, 'smolagents')
    campaign = planned(owner, native, discovery_protocol=DISCOVERY_V3)
    discovery = read_run_plan(owner.store, campaign)['plan']['discovery']
    history = discovery['history']
    assert history['status'] == 'NO_PRIOR_HISTORY' == history['summary']['status']
    assert history['summary']['statement'] == EMPTY_STATEMENT and history['summary']['recipes'] == []
    assert history['summary']['verified_episodes'] == 0
    v1_campaign = planned(owner, native)
    v1 = read_run_plan(owner.store, v1_campaign)['plan']['discovery']
    # The stored v1 record has no history key at all (not even null), so v1 plan bytes are unchanged.
    assert 'history' not in owner.store.get_record('campaign_plans', v1_campaign.campaign_id)['discovery']
    assert {key: value for key, value in discovery.items() if key not in ('protocol', 'history')} == \
        {key: value for key, value in v1.items() if key != 'protocol'}
    assert 'history' not in v1


def test_declarations_budgets_and_agent_support(owner):
    native = register_agent(owner.store, owner.settings, 'smolagents')
    reference = register_agent(owner.store, owner.settings, 'reference')
    options = {row['protocol_id']: row for row in build_run_options(owner.settings, owner.store)['learn']['discovery_protocols']}
    assert list(options) == [DISCOVERY_V1, DISCOVERY_V2, DISCOVERY_V3, DISCOVERY_V3_PRECHECK]
    assert [row['protocol_id'] for row in options.values() if row['default']] == [DISCOVERY_V1]
    assert options[DISCOVERY_V3]['supported_agents'] == ['reference', 'smolagents']
    assert options[DISCOVERY_V3_PRECHECK]['supported_agents'] == ['reference']
    for v3, base in ((DISCOVERY_V3, DISCOVERY_V1), (DISCOVERY_V3_PRECHECK, DISCOVERY_V2)):
        declared = options[v3]['declaration']
        assert declared['history'] is None
        assert {k: v for k, v in declared.items() if k not in ('protocol', 'history')} == \
            {k: v for k, v in options[base]['declaration'].items() if k != 'protocol'}
    with pytest.raises(StoreConflict, match='v3-history, which has no pre-check'):
        prepare_run_plan(owner.store, owner.settings, plan_request(owner, native, discovery_protocol=DISCOVERY_V3_PRECHECK))
    plans = {}
    for protocol, registration in ((DISCOVERY_V1, reference), (DISCOVERY_V2, reference), (DISCOVERY_V3, reference),
                                   (DISCOVERY_V3_PRECHECK, reference), (DISCOVERY_V3, native)):
        plans[protocol, registration.adapter_entrypoint_id] = read_run_plan(owner.store, planned(owner, registration, discovery_protocol=protocol))['plan']
    reference_v3 = plans[DISCOVERY_V3_PRECHECK, 'orders-prototype-v1']['discovery']
    reference_v2 = plans[DISCOVERY_V2, 'orders-prototype-v1']['discovery']
    assert (reference_v3['slots'], reference_v3['explorer_requests_max'], reference_v3['explorer_transport_retries_max'],
            reference_v3['actor_episodes_max'], reference_v3['replans_per_slot']) == (8, 16, 16, 8, 1)
    assert reference_v3['pre_check'] == reference_v2['pre_check']
    assert plans[DISCOVERY_V3, 'smolagents-toolcalling-v1']['discovery']['pre_check'] is None
    assert len({canonical_json(plan['transport_retry']) for plan in plans.values()}) == 1  # one retry rule for all
    assert all('history' not in plans[p, 'orders-prototype-v1']['discovery'] for p in (DISCOVERY_V1, DISCOVERY_V2))


def test_record_cutoff_reads_keep_row_numbers_on_update_and_read_only_named_fields(tmp_path):
    from app.lab.storage import LabStore
    store = LabStore(tmp_path / 'lab.sqlite3')
    try:
        store.put_record('episodes', 'e-1', {'campaign_id': 'c', 'split': 'development', 'lifecycle': 'RUNNING'})
        store.put_record('selections', 's-1', {'challenge': False, 'context': {'big': 'x' * 1000}, 'selected_output': {'fault_spec': {'seed': 1}}})
        cutoff = store.max_record_rowid()
        store.put_record('episodes', 'e-1', {'campaign_id': 'c', 'split': 'development', 'lifecycle': 'COMPLETED'})  # same row
        store.put_record('episodes', 'e-2', {'campaign_id': 'c', 'split': 'development', 'lifecycle': 'COMPLETED'})  # after
        assert store.record_rowid('episodes', 'e-1') <= cutoff < store.record_rowid('episodes', 'e-2')
        assert [payload['lifecycle'] for _, payload in store.records_upto('episodes', cutoff)] == ['COMPLETED']
        assert [payload['episode_id'] if 'episode_id' in payload else 'e-1' for _, payload in
                store.records_upto('episodes', cutoff, where={'split': 'development'})] == ['e-1']
        assert store.records_upto('episodes', cutoff, where={'split': 'promotion'}) == []
        assert [fields for _, fields in store.record_fields_upto('selections', cutoff, ('challenge', 'selected_output.fault_spec', 'missing'))] \
            == [{'challenge': 0, 'selected_output.fault_spec': {'seed': 1}, 'missing': None}]
        for bad in ("split') OR 1=1 --", 'a b'):
            with pytest.raises(ValueError):
                store.records_upto('episodes', cutoff, where={bad: 'x'})
            with pytest.raises(ValueError):
                store.record_fields_upto('selections', cutoff, (bad,))
    finally:
        store.close()


# ---------------------------------------------------------------- review fixes (September 29)
def test_single_case_baseline_runs_never_shape_the_history(owner):
    """Review finding 1: operator-chosen single-case baseline runs (here three dev-5 runs) are out of scope.

    The reviewer's probe showed they alone froze a dev-5-only history. Now they are neither used nor counted;
    only the fixed baseline study and learn campaigns' own discovery picks feed the history.
    """
    native = register_agent(owner.store, owner.settings, 'smolagents')
    seeder = Seeder(owner, native)
    for _ in range(3):  # the coordinator's live baseline run: study_id == evidence_context_id == campaign_id
        chosen = planned(owner, native, mode='baseline', development_case_id='dev-5')
        seeder.episode(case('dev-5'), failed=('C3',), via='campaign', campaign=chosen)
    learn = planned(owner, native, discovery_protocol=DISCOVERY_V3)
    summary = read_run_plan(owner.store, learn)['plan']['discovery']['history']['summary']
    assert summary['status'] == 'NO_PRIOR_HISTORY' and summary['recipes'] == [] and summary['verified_episodes'] == 0
    assert not any(summary['excluded'].values())  # out of scope: not even counted
    assert summary['composition'] == {'baseline_studies': 0, 'baseline_study_episodes': 0, 'learn_campaigns': 0,
                                      'learn_discovery_episodes': 0}
    assert discovery_history(owner.store, owner.get(learn.campaign_id))['agent_history'] == summary
    # With a baseline study in the store, only the study's balanced trials appear; the three dev-5 runs still do not.
    seed_screen(seeder)
    later = read_run_plan(owner.store, planned(owner, native, discovery_protocol=DISCOVERY_V3))['plan']['discovery']['history']['summary']
    assert [(row['development_case_id'], row['verified_episodes'], row['sources']) for row in later['recipes']] == \
        [('dev-1', 3, ['baseline_study']), ('dev-5', 3, ['baseline_study'])]
    assert later['composition'] == {'baseline_studies': 1, 'baseline_study_episodes': 6, 'learn_campaigns': 0,
                                    'learn_discovery_episodes': 0}
    assert 'Single-case baseline runs' in later['scope'] and set(agent_history.SOURCES) == {'baseline_study', 'learn_discovery'}


def test_same_agent_includes_contract_service_capability_limits_and_model_settings(owner):
    """Review finding 2: these five configuration facts are now part of the identity; runtime and adapter
    code are not (they change with every FaultLab edit) and are listed per row instead."""
    native = register_agent(owner.store, owner.settings, 'smolagents')
    config = owner.store.get_record('configurations', native.configuration_hash)
    raw = native.model_dump(mode='json')
    base = target_identity(native, config)
    changes = {'contract_hash': '1' * 64, 'service_hash': '2' * 64, 'capability_hash': '4' * 64,
               'model_settings': {**config['model_settings'], 'temperature': 1.7},
               'episode_budget': {**config['episode_budget'], 'actor_calls': 3}}
    for field, value in changes.items():
        changed = {**config, field: value}
        registration = {**raw, 'configuration_hash': content_hash(changed),
                        **({field: value} if field in ('contract_hash', 'capability_hash') else {})}
        assert target_identity(registration, changed) not in (None, base), field
    for field in ('contract_hash', 'capability_hash'):  # registration and configuration must agree
        changed = {**config, field: '9' * 64}
        assert target_identity({**raw, 'configuration_hash': content_hash(changed)}, changed) is None
    # Same agent across FaultLab builds: runtime, adapter and dependency lock changes keep the identity.
    rebuilt = {**config, 'runtime_hash': '6' * 64, 'algorithm_hash': '7' * 64, 'adapter_hash': '3' * 64,
               'dependency_lock_hash': '5' * 64}
    assert target_identity({**raw, 'configuration_hash': content_hash(rebuilt), 'adapter_hash': '3' * 64,
                            'dependency_lock_hash': '5' * 64}, rebuilt) == base
    assert 'simulator contract and service' in agent_history.SAME_AGENT_RULE and 'runtime and adapter hashes' in agent_history.SAME_AGENT_RULE


def test_rows_list_the_runtime_and_adapter_builds_their_episodes_ran_under(owner):
    """The same agent under another FaultLab build merges into one row, and the row says so."""
    native = register_agent(owner.store, owner.settings, 'smolagents')
    seeder = Seeder(owner, native)
    seed_screen(seeder)
    # An earlier build of the same agent (other runtime and native bridge code): its own configuration,
    # registration and complete baseline-study trial, written as that build's product path would have.
    older = {**seeder.configuration, 'runtime_hash': 'c0a8aad7' + '0' * 56, 'adapter_hash': '8a579f99' + '0' * 56}
    older_hash = content_hash(older)
    owner.store.put_record('configurations', older_hash, older)
    older_registration = {**native.model_dump(mode='json'), 'registration_id': 'smolagents-1.26.0-older0000000000',
                          'configuration_hash': older_hash, 'adapter_hash': older['adapter_hash']}
    owner.store.put_record('agent_registrations', older_registration['registration_id'], older_registration)
    study, episode_id = new_id('baseline-study'), new_id('episode')
    owner.store.put_record('baseline_studies', study, {'schema_version': 'faultlab-baseline-study/v1', 'study_id': study,
        'campaign_id': 'campaign-older', 'configuration_hash': older_hash, 'status': 'COMPLETED',
        'slots': [{'episode_id': episode_id, 'arm': 'B0', 'scenario_hash': content_hash(case('dev-5')), 'status': 'COMPLETED'}]})
    owner.store.put_record('episodes', episode_id, {'campaign_id': 'campaign-older', 'episode_id': episode_id,
        'split': 'development', 'experiment_purpose': 'discovery', 'arm': 'B0', 'source_mode': 'live', 'study_id': study,
        'evidence_context_id': study, 'selector_id': None, 'agent_registration_id': older_registration['registration_id'],
        'configuration_hash': older_hash, 'model': native.model, 'policy_hash': seeder.policy_hash, 'policy_version': 'policy-v0',
        'scenario_hash': content_hash(case('dev-5')), 'lifecycle': 'COMPLETED',
        'verdict': {'outcome': 'VIOLATION', 'checks': [{'check_id': f'C{i}', 'passed': i != 3} for i in range(1, 9)],
                    'fault_executions': [{'triggered': True}], 'scorer_hash': seeder.configuration['scorer_hash']}})
    owner.store.put_record('evidence', episode_id, {'episode_id': episode_id, 'source': 'weave_verified'})
    summary = seeder.history()['summary']
    current = (seeder.configuration['runtime_hash'][:12], seeder.configuration['adapter_hash'][:12])
    dev1, dev5 = summary['recipes']
    assert dev5['verified_episodes'] == 4 and dev5['failed_checks'] == {'C3': 4, 'C5': 3}
    assert dev5['runtime_hashes'] == sorted(['c0a8aad70000', current[0]]) and dev5['adapter_hashes'] == sorted(['8a579f990000', current[1]])
    assert (dev1['runtime_hashes'], dev1['adapter_hashes']) == ([current[0]], [current[1]])
    assert summary['builds'] == sorted([{'runtime_hash': 'c0a8aad70000', 'adapter_hash': '8a579f990000', 'verified_episodes': 1},
                                        {'runtime_hash': current[0], 'adapter_hash': current[1], 'verified_episodes': 6}],
                                       key=lambda row: (row['runtime_hash'], row['adapter_hash']))
    assert summary['composition']['baseline_studies'] == 2 and summary['composition']['baseline_study_episodes'] == 7


def test_history_row_match_uses_the_order_aware_schedule_and_ignores_the_seed():
    first, second = P('F4', 'update_order', 'orders', 1, failure_count=1), P('F4', 'update_order', 'orders', 1, failure_count=2)
    summary = {'recipes': [{'development_case_id': 'dev-5', 'primitives': CASES['dev-5']['fault_spec']['primitives']},
                           {'development_case_id': None, 'primitives': [first, second]}]}
    assert history_row_match(summary, spec({**CASES['dev-5']['fault_spec'], 'seed': 99})) == \
        {'row': 1, 'development_case_id': 'dev-5', 'basis': 'faultlab-schedule-identity/v2-order-aware'}
    assert history_row_match(summary, spec({'seed': 3, 'primitives': [first, second]}))['row'] == 2
    assert history_row_match(summary, spec({'seed': 3, 'primitives': [second, first]})) is None  # order matters here
    assert history_row_match(summary, EXPLORED) is None and history_row_match(None, EXPLORED) is None
    assert history_row_match({'recipes': []}, EXPLORED) is None


def test_the_no_history_statement_claims_only_what_is_true():
    """Review finding 3: dispatch, budget and schedule identity equal the base protocol's; the request does not."""
    assert 'runs exactly as its base protocol' not in EMPTY_STATEMENT
    assert 'slot dispatch, budget and schedule identity are exactly those of the base protocol' in EMPTY_STATEMENT


def test_a_changed_history_keeps_its_plain_reason_when_recorded_as_an_execution_failure():
    """Review item (product): the campaign records the plain reason, not a generic EXECUTION_ERROR."""
    from app.lab.readiness import execution_failure
    try:
        raise agent_history.HistoryChanged('The store\'s prior history for this agent changed at or before the plan\'s record '
                                           'cutoff (frozen summary aaaaaaaaaaaa…, now bbbbbbbbbbbb…); create a new plan')
    except agent_history.HistoryChanged as error:
        failure = execution_failure(error)
    assert failure['code'] == 'AGENT_HISTORY_CHANGED' and failure['error_class'] == 'HistoryChanged'
    assert failure['message'].endswith('create a new plan') and failure['provider_dispatch'] is False
    assert isinstance(agent_history.HistoryChanged('x'), StoreConflict)  # still a 409 conflict at Start
    try:
        raise StoreConflict('another conflict with private detail')
    except StoreConflict as error:
        assert execution_failure(error)['message'] == 'Execution failed; inspect the saved error class and code location.'
