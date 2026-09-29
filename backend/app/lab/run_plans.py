"""Provider-free setup previews and immutable plans for reviewed campaign work.

These API-local models intentionally do not change the exported task contracts.
Public options contain development recipes and protected partition identities only.
"""
from copy import deepcopy
from dataclasses import dataclass
import json
from importlib.metadata import PackageNotFoundError
from typing import Annotated, Literal, Union

from pydantic import Field, model_serializer, model_validator

from app.contracts.models import (AgentRegistration, Campaign, CampaignBudget,
    CampaignRequest, Digest, EpisodeBudget, FaultSpec, Id, PolicyVersion, SendableTaskText,
    StrictModel, canonical_json, content_hash)
from app.agents.transport_retry import RETRIES_PER_REQUEST, declaration as transport_retry_declaration
from app.integrations.registry import AgentRegistry
from app.lab.configuration import frozen_configuration
from app.lab.dashboard import store_descriptor
from app.lab.discovery_protocol import (BASE_PROTOCOL, DISCOVERY_V1, DISCOVERY_V2, DISCOVERY_V3, DISCOVERY_V3_PRECHECK,
    HISTORY_PROTOCOLS, declaration as discovery_declaration)
from app.lab.storage import ReadOnlyStore, StoreConflict

PROTOCOL = 'faultlab-run-plan/v1'
TASK = 'orders.upgrade_then_confirm/v1'
TASK_TEXT = 'Upgrade the authorized order to express shipping, then record one truthful confirmation.'
CaseId = Literal['dev-1', 'dev-2', 'dev-3', 'dev-4', 'dev-5', 'dev-6']
Agent = Literal['reference', 'smolagents']
CASE_LABELS = {
    'dev-1': ('Healthy services', 'No injected service fault.'),
    'dev-2': ('Lost upgrade response', 'The accepted upgrade response arrives after the HTTP timeout.'),
    'dev-3': ('Delayed upgrade', 'The upgrade remains pending before completing successfully.'),
    'dev-4': ('Historical order read', 'An order read returns an older saved version.'),
    'dev-5': ('Upgrade rejected', 'The upgrade reaches a terminal rejection.'),
    'dev-6': ('Notification failures', 'The first two confirmation attempts receive transient failures.'),
}


class RunPlanRequest(StrictModel):
    expected_store_identity: Digest
    expected_setup_hash: Digest
    task_definition_id: Literal['orders.upgrade_then_confirm/v1']
    agent_registration_id: Id | None = None
    mode: Literal['baseline', 'learn', 'compare']
    config_profile_id: Literal['offline-v1', 'live-v1']
    task_text: SendableTaskText
    order_id: Id
    development_case_id: CaseId | None = None
    # Explicit, declared discovery setting for Learn only; omitted means v1 (today's behaviour).
    discovery_protocol: Literal['faultlab-discovery/v1', 'faultlab-discovery/v2-reachability',
                                'faultlab-discovery/v3-history', 'faultlab-discovery/v3-history-reachability'] | None = None

    @model_validator(mode='after')
    def supported_combination(self):
        if (self.mode == 'baseline') != (self.development_case_id is not None):
            raise ValueError('Choose a development case only for a baseline run')
        if self.discovery_protocol is not None and self.mode != 'learn':
            raise ValueError('A discovery protocol applies only to a Learn campaign')
        if self.config_profile_id == 'offline-v1':
            if self.mode != 'baseline' or self.agent_registration_id is not None:
                raise ValueError('Offline runs use the built-in reference baseline without a selected registration')
        elif self.agent_registration_id is None:
            raise ValueError('Live runs require an existing reviewed registration')
        return self


class DevelopmentCase(StrictModel):
    kind: Literal['development_case']
    case_id: CaseId
    fixture_id: Literal['standard-v1', 'history-v1']
    expected_version: Literal[1, 4]
    fault_spec: FaultSpec
    scenario_hash: Digest
    manifest_hash: Digest


class DevelopmentSearch(StrictModel):
    kind: Literal['development_search']
    manifest_hash: Digest
    search_space: dict


class ProtectedComparison(StrictModel):
    kind: Literal['protected_comparison']
    partition: Literal['promotion']
    manifest_hash: Digest
    case_count: int = Field(ge=1, le=100)
    trials_per_case: int = Field(ge=1, le=10)


Selection = Annotated[Union[DevelopmentCase, DevelopmentSearch, ProtectedComparison], Field(discriminator='kind')]


class AgentHistoryPlan(StrictModel):
    """Discovery v3: the frozen same-agent history (app.lab.agent_history) and its cutoff."""
    schema_version: Literal['faultlab-agent-history/v2']
    status: Literal['AVAILABLE', 'NO_PRIOR_HISTORY']
    rule: str = Field(min_length=1, max_length=800)
    agent_identity: dict
    policy_hash: Digest
    record_cutoff: int = Field(ge=0)
    episode_ids_hash: Digest
    summary: dict
    summary_hash: Digest

    @model_validator(mode='after')
    def hashed(self):
        if (self.summary_hash != content_hash(self.summary) or self.summary.get('status') != self.status
                or self.summary.get('schema_version') != self.schema_version):
            raise ValueError('Inconsistent frozen agent history')
        return self


class DiscoveryPlan(StrictModel):
    """The declared discovery protocol and selection budget of a Learn plan."""
    protocol: Literal['faultlab-discovery/v1', 'faultlab-discovery/v2-reachability',
                      'faultlab-discovery/v3-history', 'faultlab-discovery/v3-history-reachability']
    schedule_identity: Literal['faultlab-schedule-identity/v1-sorted', 'faultlab-schedule-identity/v2-order-aware']
    slots: int = Field(ge=1, le=8)
    explorer_requests_max: int = Field(ge=1, le=16)
    # One charged transport retry per Explorer request; it does not count toward
    # explorer_requests_max. None: a plan saved before retries existed declares none.
    explorer_transport_retries_max: int | None = Field(default=None, ge=0, le=16)
    actor_episodes_max: int = Field(ge=1, le=8)
    replans_per_slot: int = Field(ge=0, le=1)
    dispatch_rule: str = Field(min_length=1, max_length=600)
    pre_check: dict | None
    # Discovery v3 only. Absent (not null) in every v1/v2 block, so those records keep their exact bytes.
    history: AgentHistoryPlan | None = None

    @model_serializer(mode='wrap')
    def _omit_absent_history(self, handler):
        data = handler(self)
        if data.get('history') is None:
            data.pop('history', None)
        return data

    @model_validator(mode='after')
    def coherent(self):
        if (self.history is not None) != (self.protocol in HISTORY_PROTOCOLS):
            raise ValueError('Only a discovery v3 declaration carries a frozen agent history, and it must')
        v2 = BASE_PROTOCOL[self.protocol] == DISCOVERY_V2
        if (self.schedule_identity.endswith('v2-order-aware') != v2 or self.replans_per_slot != (1 if v2 else 0)
                or self.explorer_requests_max != self.slots * (2 if v2 else 1) or self.actor_episodes_max != self.slots
                or (self.explorer_transport_retries_max is not None
                    and self.explorer_transport_retries_max != self.explorer_requests_max * RETRIES_PER_REQUEST)
                or (self.pre_check is not None) != v2):
            raise ValueError('Inconsistent discovery protocol declaration')
        if v2 and (not isinstance(self.pre_check.get('caller_model'), dict) or self.pre_check['caller_model'].get('agent') != 'reference'):
            raise ValueError('Discovery v2 declares the reference Actor caller model only')
        return self


class TransportRetryPlan(StrictModel):
    """The frozen model-request retry rule (app.agents.transport_retry) of a reviewed plan."""
    protocol: Literal['faultlab-transport-retry/v1']
    retries_per_request: Literal[1]
    roles: list[Literal['actor', 'explorer', 'mechanic']] = Field(min_length=3, max_length=3)
    retryable: list[Literal['CONNECTION_ERROR', 'REQUEST_TIMEOUT', 'HTTP_503']] = Field(min_length=3, max_length=3)
    service_unavailable_delay_seconds: Literal[1]
    actor_retries_per_episode_max: int = Field(ge=1, le=8)
    rule: str = Field(min_length=1, max_length=800)

    @model_validator(mode='after')
    def exact_lists(self):
        if self.roles != ['actor', 'explorer', 'mechanic'] or self.retryable != ['CONNECTION_ERROR', 'REQUEST_TIMEOUT', 'HTTP_503']:
            raise ValueError('Inconsistent transport retry declaration')
        return self


class SavedRunPlan(StrictModel):
    schema_version: Literal['faultlab-run-plan/v1']
    campaign_id: Id
    setup_hash: Digest
    task_definition_id: Literal['orders.upgrade_then_confirm/v1']
    mode: Literal['baseline', 'learn', 'compare']
    config_profile_id: Literal['offline-v1', 'live-v1']
    task_text: str = Field(min_length=1, max_length=2000)
    order_id: Id
    configuration_hash: Digest
    agent_registration_id: Id
    agent: Agent
    source_mode: Literal['live', 'offline_fixture']
    caps: CampaignBudget
    episode_budget: EpisodeBudget
    initial_policy_version: Id
    initial_policy_hash: Digest
    selection: Selection
    discovery: DiscoveryPlan | None = None
    # None: saved before the shared transport-retry rule was declared in plans.
    transport_retry: TransportRetryPlan | None = None
    plan_hash: Digest


@dataclass(frozen=True)
class PreparedRunPlan:
    campaign_request: CampaignRequest
    configuration: dict
    registration: AgentRegistration
    plan: dict


class _PreviewRecords:
    """A private value sink for existing reviewed builders; no SQLite or recovery."""
    def __init__(self): self.values = {}
    def put_record(self, kind, ident, value, **_):
        self.values[kind, ident] = json.loads(canonical_json(value))
    def get_record(self, kind, ident): return deepcopy(self.values.get((kind, ident)))


def _caps(settings):
    return CampaignBudget(model_calls=settings.faultlab_model_call_cap,
                          tokens=settings.faultlab_token_cap, dollars=float(settings.faultlab_dollar_cap))


def _manifests():
    from app.referee.manifests import load_manifest
    development = load_manifest('development')
    if (development.get('scope') != TASK or development.get('partition') != 'development'
            or development.get('access') != 'DEVELOPMENT_DIAGNOSTIC'
            or [case.get('case_id') for case in development['cases']] != list(CASE_LABELS)):
        raise StoreConflict('The reviewed development catalog is unavailable')
    for case in development['cases']:
        expected = {'standard-v1': 1, 'history-v1': 4}.get(case.get('fixture_id'))
        recipe = FaultSpec.model_validate_json(canonical_json(case['fault_spec']))
        if expected is None or case.get('expected_version') != expected:
            raise StoreConflict('Development case fixture identity is inconsistent')
        if any(p.kind == 'F3' and p.parameters.versions_back >= expected for p in recipe.primitives):
            raise StoreConflict('Development case requires unavailable order history')
    promotion = load_manifest('promotion')
    if promotion.get('scope') != TASK or promotion.get('partition') != 'promotion':
        raise StoreConflict('The reviewed comparison partition is unavailable')
    comparison = {'partition': 'promotion', 'manifest_hash': promotion['manifest_hash'],
                  'case_count': len(promotion['cases']), 'trials_per_case': promotion['trials_per_case']}
    return development, comparison


def _preview(settings, profile, agent):
    from app.integrations.registry import freeze_target_configuration
    configuration = frozen_configuration(settings, _caps(settings), profile)
    sink = _PreviewRecords()
    registry = AgentRegistry(sink)
    if agent == 'smolagents':
        configuration = freeze_target_configuration(configuration, settings.wandb_model)
        registration = registry.register_smolagents(configuration)
    else:
        registration = registry.register_reference(configuration, internal_smoke=profile == 'offline-v1')
    return configuration, registration


def _stored_policy(store, version):
    raw = store.get_record('policies', version) if store is not None else None
    if raw is None: return None
    policy = PolicyVersion.model_validate_json(canonical_json(raw))
    if policy.content is None or policy.policy_hash != content_hash(policy.content):
        raise StoreConflict('Saved policy failed integrity validation')
    return policy


def _accepted(store, configuration_hash):
    version = store.get_pointer('accepted-policy:' + configuration_hash) if store is not None else None
    policy = _stored_policy(store, version) if version else None
    return policy if policy and policy.decision == 'ACCEPTED' else None


def build_run_options(settings, store=None):
    """Inspect installed source and optional saved records, with zero provider calls."""
    development, comparison = _manifests()
    caps = _caps(settings)
    offline_configuration, _ = _preview(settings, 'offline-v1', 'reference')
    agents, hashes = [], {}
    for agent, label in (('reference', 'FaultLab reference Actor'), ('smolagents', 'smolagents ToolCallingAgent 1.26.0')):
        row = {'agent': agent, 'label': label, 'status': 'UNAVAILABLE', 'reason_code': 'SOURCE_UNAVAILABLE',
               'message': 'Reviewed local source is unavailable or differs from its pinned identity.',
               'configuration_hash': None, 'proposed_registration_id': None, 'registered': False,
               'registration_id': None, 'model': settings.wandb_model,
               'source_conformance': 'UNAVAILABLE', 'provider_access': 'not_checked',
               'behavior_verified': False, 'compare_available': False, 'accepted_policy_version': None,
               'limitations': ['Local source conformance does not verify provider access or agent behavior.']}
        if not settings.wandb_model:
            row.update(reason_code='MODEL_REQUIRED', message='Configure an Actor model before preparing a live registration.')
        else:
            try:
                configuration, registration = _preview(settings, 'live-v1', agent)
            except PackageNotFoundError:
                row.update(reason_code='NOT_INSTALLED', message='The reviewed native agent package is not installed.')
            except Exception:
                pass  # Never echo package paths, configuration values or untrusted exception text.
            else:
                expected = registration.model_dump(mode='json')
                saved = store.get_record('agent_registrations', registration.registration_id) if store is not None else None
                registered = saved == expected and store.get_record('configurations', registration.configuration_hash) == configuration if store is not None else False
                accepted = _accepted(store, registration.configuration_hash)
                hashes[agent] = registration.configuration_hash
                row.update(status='READY', reason_code='READY', message='Installed source and task mappings match the reviewed local contract.',
                    configuration_hash=registration.configuration_hash, proposed_registration_id=registration.registration_id,
                    registered=registered, registration_id=registration.registration_id if registered else None,
                    source_conformance='VERIFIED', compare_available=bool(registered and accepted),
                    accepted_policy_version=accepted.version if accepted else None, limitations=list(registration.limitations))
                if agent == 'smolagents':
                    row['limitations'].append('Reference Actor context, completion and dependent heldout studies are unavailable for this selected native agent.')
        agents.append(row)
    setup = {'protocol': PROTOCOL, 'task_definition_id': TASK,
             'development_manifest_hash': development['manifest_hash'], 'comparison': comparison,
             'offline_configuration_hash': content_hash(offline_configuration),
             'configured_reference_configuration_hash': content_hash(frozen_configuration(settings, caps, 'live-v1')),
             'live_configuration_hashes': hashes, 'caps': caps.model_dump(mode='json')}
    if store is not None:
        descriptor = store_descriptor(store)
    else:
        path = str((settings.artifact_path / 'lab.sqlite3').expanduser().resolve())
        descriptor = {'identity': content_hash({'local_store_path': path}), 'path': path}
    descriptor['read_only'] = settings.faultlab_read_only
    return {'schema_version': 'faultlab-run-options/v1', 'setup_hash': content_hash(setup),
        'data_store': descriptor,
        'task': {'task_definition_id': TASK, 'label': 'Upgrade an order and confirm',
                 'description': 'One synthetic authorized order, express shipping, and one truthful confirmation. The fixed C1–C8 checks apply.',
                 'task_text_default': TASK_TEXT},
        'profiles': [{'profile_id': 'offline-v1', 'label': 'Offline reference smoke', 'source_mode': 'offline_fixture', 'arm': 'B1', 'registration_required': False},
                     {'profile_id': 'live-v1', 'label': 'Live reviewed agent', 'source_mode': 'live', 'arm': 'B0', 'registration_required': True}],
        'development': {'manifest_hash': development['manifest_hash'], 'cases': [
            {'case_id': case['case_id'], 'label': CASE_LABELS[case['case_id']][0],
             'description': CASE_LABELS[case['case_id']][1], 'fixture_id': case['fixture_id'],
             'expected_version': case['expected_version'], 'fault_spec': deepcopy(case['fault_spec'])}
            for case in development['cases']]},
        'learn': {'manifest_hash': development['manifest_hash'],
                  'search_space': deepcopy(development['development_grammar']), 'selection_limit': caps.discovery_selections,
                  'discovery_protocols': discovery_options(caps)},
        'compare': comparison, 'agents': agents,
        'offline': {'agent': 'reference', 'configuration_hash': content_hash(offline_configuration), 'registration_required': False},
        'caps': caps.model_dump(mode='json'), 'episode_budget': deepcopy(offline_configuration['episode_budget']),
        'models': settings.role_models, 'provider_calls': 0}


def _reference_caller():
    from app.lab.reachability import caller_model_for
    return caller_model_for('reference', [])


HISTORY_DESCRIPTION = ('Adds one read-only piece of Explorer context: a summary of this same agent\'s earlier verified '
                       'development outcomes in this store (per recipe: verified episodes, outcomes and failed checks), '
                       'frozen into the plan with its hash when you create the campaign. The Explorer still chooses freely; '
                       'the history is prior evidence, not an instruction. Protected evaluation data is never included.')


def discovery_options(caps):
    """The declarable discovery protocols for Learn, with their budgets. v1 is the default.

    The v3 declarations show history None: the history is frozen from the store when a plan is saved.
    """
    v1 = discovery_declaration(DISCOVERY_V1, caps)
    v2 = discovery_declaration(DISCOVERY_V2, caps, caller=_reference_caller())
    v3 = discovery_declaration(DISCOVERY_V3, caps)
    v3_precheck = discovery_declaration(DISCOVERY_V3_PRECHECK, caps, caller=_reference_caller())
    return [
        {'protocol_id': DISCOVERY_V1, 'default': True, 'label': 'v1 · every valid new pick runs',
         'description': 'Today\'s behaviour: one Explorer request per slot; each valid pick that is not an exact duplicate runs one Actor episode.',
         'supported_agents': ['reference', 'smolagents'], 'declaration': v1},
        {'protocol_id': DISCOVERY_V2, 'default': False, 'label': 'v2 · reachability pre-check',
         'description': 'A free replay of the real simulator labels each fault before any paid Actor episode; only picks whose every fault is FORCED run, and a refused pick gets one re-plan with the reason.',
         'supported_agents': ['reference'],
         'unsupported_reason': 'The pre-check models only the FaultLab reference Actor under policy-v0; the native agent has a different action space.',
         'declaration': v2},
        {'protocol_id': DISCOVERY_V3, 'default': False, 'label': 'v3 · agent history',
         'description': 'Exactly v1 (every valid new pick runs, same budget). ' + HISTORY_DESCRIPTION,
         'supported_agents': ['reference', 'smolagents'], 'declaration': v3},
        {'protocol_id': DISCOVERY_V3_PRECHECK, 'default': False, 'label': 'v3 · agent history + reachability pre-check',
         'description': 'Exactly v2 (pre-check, one re-plan per refused slot, same budget). ' + HISTORY_DESCRIPTION,
         'supported_agents': ['reference'],
         'unsupported_reason': 'The pre-check models only the FaultLab reference Actor under policy-v0; for the native agent choose v3 · agent history, which has no pre-check.',
         'declaration': v3_precheck},
    ]


def prepare_run_plan(store, settings, request):
    """Validate a form under the owning coordinator; no partial records are written."""
    if settings.faultlab_read_only or getattr(store, 'read_only', False): raise ReadOnlyStore()
    request = RunPlanRequest.model_validate_json(canonical_json(request))
    if request.expected_store_identity != store_descriptor(store)['identity']:
        raise StoreConflict('Configured run store differs from this backend')
    options = build_run_options(settings, store)
    if request.expected_setup_hash != options['setup_hash']:
        raise StoreConflict('Run setup changed; refresh the available options before creating a campaign')
    if request.config_profile_id == 'offline-v1':
        configuration, registration = _preview(settings, 'offline-v1', 'reference')
        agent = 'reference'
    else:
        from app.integrations.registry import current_registration_configuration
        registry = AgentRegistry(store)
        registration = registry.get(request.agent_registration_id)
        agent = {'orders-prototype-v1': 'reference', 'smolagents-toolcalling-v1': 'smolagents'}.get(registration.adapter_entrypoint_id)
        if agent is None: raise StoreConflict('Unreviewed agent registration')
        configuration = current_registration_configuration(settings, _caps(settings), 'live-v1', registration)
        if (registration.configuration_hash != content_hash(configuration)
                or registration.model != settings.wandb_model
                or store.get_record('configurations', registration.configuration_hash) != configuration):
            raise StoreConflict('Registration differs from the current model, source or campaign limits')
        registry.verify(registration.registration_id, configuration)
    initial = _accepted(store, content_hash(configuration)) if request.mode != 'baseline' else None
    if request.mode == 'compare' and initial is None:
        raise StoreConflict('Comparison requires an accepted policy for this exact registered configuration')
    initial = initial or _stored_policy(store, 'policy-v0')
    if initial is None or (initial.version == 'policy-v0' and (initial.decision != 'BASELINE' or initial.content.rules)):
        raise StoreConflict('The unchanged baseline policy is unavailable')
    if request.mode == 'baseline':
        case = next(c for c in options['development']['cases'] if c['case_id'] == request.development_case_id)
        selection = {'kind': 'development_case', 'case_id': case['case_id'], 'fixture_id': case['fixture_id'],
                     'expected_version': case['expected_version'], 'fault_spec': case['fault_spec'],
                     'scenario_hash': content_hash(case['fault_spec']), 'manifest_hash': options['development']['manifest_hash']}
    elif request.mode == 'learn':
        selection = {'kind': 'development_search', 'manifest_hash': options['learn']['manifest_hash'],
                     'search_space': options['learn']['search_space']}
        protocol = request.discovery_protocol or DISCOVERY_V1
        if BASE_PROTOCOL[protocol] == DISCOVERY_V2:
            if agent != 'reference':
                raise StoreConflict('Discovery v2 cannot pre-check the native agent: its reachability model is the '
                                    'FaultLab reference Actor. Choose discovery v1 for this agent.'
                                    if protocol == DISCOVERY_V2 else
                                    'The reachability pre-check models only the FaultLab reference Actor. For the native '
                                    'agent choose faultlab-discovery/v3-history, which has no pre-check.')
            if initial.content.rules:
                raise StoreConflict('Discovery v2 pre-checks picks only for the unchanged baseline policy (policy-v0).')
        discovery = deepcopy(next(row['declaration'] for row in options['learn']['discovery_protocols'] if row['protocol_id'] == protocol))
        if protocol in HISTORY_PROTOCOLS:
            # Frozen now, from this store, for this agent and starting policy; the plan stores the summary,
            # its hash and the record cutoff, and execution recomputes it before any Explorer request.
            from app.lab import agent_history
            discovery['history'] = agent_history.snapshot(store, registration=registration, configuration=configuration,
                                                          policy_hash=initial.policy_hash)
    else:
        selection = {'kind': 'protected_comparison', **options['compare']}
    campaign_request = CampaignRequest(task_text=request.task_text, order_id=request.order_id,
                                       mode=request.mode, config_profile_id=request.config_profile_id)
    plan = {**campaign_request.model_dump(mode='json'),
            'schema_version': PROTOCOL, 'setup_hash': options['setup_hash'], 'task_definition_id': TASK,
            'configuration_hash': content_hash(configuration),
            'agent_registration_id': registration.registration_id, 'agent': agent,
            'source_mode': 'offline_fixture' if request.config_profile_id == 'offline-v1' else 'live',
            'caps': options['caps'], 'episode_budget': deepcopy(configuration['episode_budget']),
            'initial_policy_version': initial.version,
            'initial_policy_hash': initial.policy_hash, 'selection': selection}
    if request.mode == 'learn': plan['discovery'] = deepcopy(discovery)
    plan['transport_retry'] = transport_retry_declaration(configuration['episode_budget']['actor_calls'])
    return PreparedRunPlan(campaign_request, deepcopy(configuration), registration, deepcopy(plan))


def attach_run_plan(store, campaign, prepared):
    """Attach inside the caller's create transaction; return its provenance marker."""
    plan = {**deepcopy(prepared.plan), 'campaign_id': campaign.campaign_id}
    plan['plan_hash'] = '0' * 64
    checked = SavedRunPlan.model_validate_json(canonical_json(plan)).model_dump(mode='json')
    checked['plan_hash'] = content_hash({k: v for k, v in checked.items() if k != 'plan_hash'})
    _bindings(store, campaign, checked, first_start=True)
    store.put_record('campaign_plans', campaign.campaign_id, checked, immutable=True)
    return {'run_plan_protocol': PROTOCOL, 'run_plan_ref': campaign.campaign_id, 'run_plan_hash': checked['plan_hash']}


def _bindings(store, campaign, plan, *, first_start=False):
    for key in ('campaign_id', 'mode', 'config_profile_id', 'task_text', 'order_id', 'configuration_hash'):
        if plan[key] != getattr(campaign, key): raise StoreConflict('Saved run plan differs from its campaign')
    if plan['caps'] != campaign.caps.model_dump(mode='json'): raise StoreConflict('Saved run plan limits differ from its campaign')
    expected_kind = {'baseline': 'development_case', 'learn': 'development_search', 'compare': 'protected_comparison'}[campaign.mode]
    selection = plan['selection']
    if selection['kind'] != expected_kind: raise StoreConflict('Saved run plan selection is inconsistent')
    discovery = plan.get('discovery')
    if discovery is not None:
        if campaign.mode != 'learn' or discovery['slots'] != campaign.caps.discovery_selections:
            raise StoreConflict('Saved discovery protocol is inconsistent with its campaign')
        if BASE_PROTOCOL[discovery['protocol']] == DISCOVERY_V2 and plan['agent'] != 'reference':
            raise StoreConflict('Saved discovery v2 plan names an agent it cannot pre-check')
        history = discovery.get('history')
        if history is not None and history['policy_hash'] != plan['initial_policy_hash']:
            raise StoreConflict('Saved agent history was frozen for another starting policy')
    offline = campaign.config_profile_id == 'offline-v1'
    if (plan['source_mode'] != ('offline_fixture' if offline else 'live')
            or (offline and (campaign.mode != 'baseline' or plan['agent'] != 'reference'))):
        raise StoreConflict('Saved run plan execution profile is inconsistent')
    if expected_kind == 'development_case':
        if selection['scenario_hash'] != content_hash(selection['fault_spec']): raise StoreConflict('Saved case recipe digest differs')
        if selection['expected_version'] != (4 if selection['fixture_id'] == 'history-v1' else 1):
            raise StoreConflict('Saved case fixture differs')
    configuration = store.get_record('configurations', campaign.configuration_hash)
    if configuration is None or content_hash(configuration) != campaign.configuration_hash:
        raise StoreConflict('Saved run configuration failed integrity validation')
    if campaign.model != configuration.get('model'): raise StoreConflict('Saved campaign model differs from its configuration')
    if plan['episode_budget'] != configuration.get('episode_budget'):
        raise StoreConflict('Saved episode limits differ from their configuration')
    registration = store.get_record('agent_registrations', plan['agent_registration_id'])
    owner = store.get_record('campaign_registrations', campaign.campaign_id)
    if (not registration or registration.get('configuration_hash') != campaign.configuration_hash
            or not owner or owner.get('registration_id') != plan['agent_registration_id']):
        raise StoreConflict('Saved campaign registration differs from its plan')
    adapter = {'reference': 'orders-prototype-v1', 'smolagents': 'smolagents-toolcalling-v1'}[plan['agent']]
    if registration.get('adapter_entrypoint_id') != adapter: raise StoreConflict('Saved plan agent differs from its registration')
    checked_registration = AgentRegistration.model_validate_json(canonical_json(registration))
    for field, key in {'model': 'model', 'source_hash': 'source_hash', 'adapter_hash': 'adapter_hash',
                       'prompt_hash': 'actor_prompt_hash', 'contract_hash': 'contract_hash',
                       'capability_hash': 'capability_hash', 'oracle_hash': 'scorer_hash',
                       'dependency_lock_hash': 'dependency_lock_hash'}.items():
        if getattr(checked_registration, field) != configuration.get(key):
            raise StoreConflict('Saved registration identity differs from its configuration')
    history = (plan.get('discovery') or {}).get('history')
    if history is not None:
        from app.lab.agent_history import target_identity
        if history['agent_identity'] != target_identity(registration, configuration):
            raise StoreConflict('Saved agent history was frozen for another agent identity')
    initial = _stored_policy(store, plan['initial_policy_version'])
    if initial is None or initial.policy_hash != plan['initial_policy_hash']:
        raise StoreConflict('Saved initial policy differs from its plan')
    if first_start and campaign.active_policy_version != plan['initial_policy_version']:
        raise StoreConflict('Campaign policy changed before its first start')
    if not first_start:
        if store.get_pointer('active-policy:' + campaign.campaign_id) != campaign.active_policy_version:
            raise StoreConflict('Saved campaign policy pointer is inconsistent')
        if campaign.active_policy_version != plan['initial_policy_version']:
            active = _stored_policy(store, campaign.active_policy_version)
            if campaign.mode != 'learn' or not active or active.decision != 'ACCEPTED':
                raise StoreConflict('Campaign policy changed without an accepted learning result')


def verify_plan_history(store, plan):
    """Recompute a v3 plan's frozen history at its cutoff.

    Raises agent_history.HistoryChanged (a StoreConflict: 409 at Start, and the campaign's recorded
    reason AGENT_HISTORY_CHANGED if it is caught before the first Explorer request) if anything differs.
    """
    from app.lab import agent_history
    registration = store.get_record('agent_registrations', plan['agent_registration_id'])
    configuration = store.get_record('configurations', plan['configuration_hash'])
    return agent_history.verify(store, plan['discovery']['history'], registration=registration,
                                configuration=configuration, policy_hash=plan['initial_policy_hash'])


def plan_history_check(store, campaign):
    """On-demand, read-only: is a saved v3 plan's frozen history still what the store holds at its cutoff?

    For the dashboard's "Check against the store now" button (never polled). Start performs the same check
    and refuses on any difference; this only lets an operator see a stale plan before pressing Start.
    """
    from app.lab import agent_history
    plan = read_run_plan(store, campaign)['plan']
    history = ((plan or {}).get('discovery') or {}).get('history')
    base = {'campaign_id': campaign.campaign_id, 'record_cutoff': history['record_cutoff'] if history else None,
            'summary_hash': history['summary_hash'] if history else None}
    if history is None:
        return {**base, 'status': 'NOT_APPLICABLE', 'message': 'This plan does not declare discovery v3, so it has no frozen agent history.'}
    if campaign.state != 'IDLE':
        return {**base, 'status': 'NOT_CHECKED', 'message': 'This campaign has already started; its history was checked at Start and before its first Explorer request.'}
    try:
        verify_plan_history(store, plan)
    except agent_history.HistoryChanged as error:
        return {**base, 'status': 'CHANGED', 'message': str(error)}
    return {**base, 'status': 'CURRENT', 'message': f'Unchanged: the store still holds exactly this history at row {history["record_cutoff"]}. Start checks it again.'}


def read_run_plan(store, campaign_id):
    """Verify saved bindings without comparing them with today's installed runtime."""
    campaign = campaign_id if isinstance(campaign_id, Campaign) else store.get_model('campaigns', campaign_id, Campaign)
    if campaign is None: raise KeyError(campaign_id)
    ident = campaign.campaign_id
    provenance = store.get_record('campaign_provenance', ident) or {}
    plan = store.get_record('campaign_plans', ident)
    keys = ('run_plan_protocol', 'run_plan_ref', 'run_plan_hash')
    if plan is None and not any(key in provenance for key in keys):
        return {'campaign_id': ident, 'status': 'LEGACY', 'plan': None}
    try:
        if (provenance.get('run_plan_protocol') != PROTOCOL or provenance.get('run_plan_ref') != ident
                or plan is None or plan.get('plan_hash') != provenance.get('run_plan_hash')
                or plan.get('plan_hash') != content_hash({k: v for k, v in plan.items() if k != 'plan_hash'})):
            raise ValueError()
        checked = SavedRunPlan.model_validate_json(canonical_json(plan)).model_dump(mode='json')
        _bindings(store, campaign, checked)
    except Exception:
        raise StoreConflict('Saved campaign plan is missing, corrupt or inconsistent; execution is blocked') from None
    return {'campaign_id': ident, 'status': 'PLANNED', 'plan': checked}


def validate_run_plan(store, settings, campaign):
    """Recheck immutable selection and current target before admitting execution."""
    plan = read_run_plan(store, campaign)['plan']
    if plan is None: return None
    if settings.faultlab_read_only or getattr(store, 'read_only', False): raise ReadOnlyStore()
    _bindings(store, campaign, plan, first_start=campaign.state == 'IDLE')
    from app.integrations.registry import current_registration_configuration
    registry = AgentRegistry(store)
    registration = registry.get(plan['agent_registration_id'])
    current = current_registration_configuration(settings, _caps(settings), campaign.config_profile_id, registration)
    if content_hash(current) != plan['configuration_hash']:
        raise StoreConflict('Current source, model or campaign limits differ from the saved plan')
    registry.verify(registration.registration_id, current)
    # Execution applies the installed retry rule, so the saved plan must declare exactly it.
    if plan.get('transport_retry') != transport_retry_declaration(plan['episode_budget']['actor_calls']):
        raise StoreConflict('The installed model transport retry rule differs from the saved plan')
    discovery = plan.get('discovery')
    if discovery is not None and discovery.get('explorer_transport_retries_max') != discovery['explorer_requests_max'] * RETRIES_PER_REQUEST:
        raise StoreConflict('The saved discovery plan does not declare the installed Explorer transport retry bound')
    if discovery is not None and BASE_PROTOCOL[discovery['protocol']] == DISCOVERY_V2:
        if discovery['pre_check']['caller_model'] != _reference_caller().descriptor():
            raise StoreConflict('The installed reachability caller model differs from the saved discovery plan')
    if discovery is not None and discovery.get('history') is not None and campaign.state == 'IDLE':
        # Discovery v3: before the first start (and when the plan is saved), the frozen history must
        # still be exactly what the store holds at the plan's record cutoff.
        verify_plan_history(store, plan)
    if plan['selection']['kind'] != 'development_case':
        development, comparison = _manifests()
        expected = development['manifest_hash'] if campaign.mode == 'learn' else comparison['manifest_hash']
        if plan['selection']['manifest_hash'] != expected:
            raise StoreConflict('Frozen search or comparison manifest changed before execution')
    return plan
