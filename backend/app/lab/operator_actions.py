"""Bounded CLI actions performed by the backend that already owns the store."""
import asyncio
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Annotated, Literal

from pydantic import Field, model_validator

from app.contracts.models import (CampaignRequest, Digest, Id, RegressionCase,
                                  CampaignBudget, StrictModel, canonical_json, new_id)
from app.integrations.regression_runner import INVENTORY, RegressionRunner, _json
from app.integrations.registry import AgentRegistry
from app.lab.dashboard import store_descriptor
from app.lab.regressions import (MAX_BUNDLE_BYTES, MAX_BUNDLE_FILE, artifact_kind,
                                 manifest_payload, runnable_policy, validate_bundle)
from app.lab.storage import ReadOnlyStore, StoreConflict

# Bound transport before JSON decoding as well as decoded file count and bytes.
MAX_UPLOAD_BYTES = 24 * 1024 * 1024
MAX_MANIFEST_BYTES = 2 * 1024 * 1024
BundleText = Annotated[str, Field(max_length=MAX_BUNDLE_FILE)]
BundlePath = Annotated[str, Field(max_length=80)]


class ImportExecutionRequest(StrictModel):
    expected_store_identity: Digest
    manifest: str = Field(max_length=MAX_MANIFEST_BYTES)
    files: dict[BundlePath, BundleText] = Field(min_length=7, max_length=8)
    agent_registration_id: Id
    execution_profile_id: Literal['sandbox-v1']
    execute_live: Literal[True]

    @model_validator(mode='after')
    def bounded_files(self):
        if set(self.files) not in (INVENTORY, INVENTORY | {'evidence.json'}):
            raise ValueError('Exact trusted bundle inventory required')
        lengths = [len(value.encode('utf-8')) for value in self.files.values()]
        if (len(self.manifest.encode('utf-8')) > MAX_MANIFEST_BYTES
                or max(lengths) > MAX_BUNDLE_FILE or sum(lengths) > MAX_BUNDLE_BYTES):
            raise ValueError('Bundle size bound exceeded')
        return self


class FreezePortabilityRequest(StrictModel):
    expected_store_identity: Digest
    agent_registration_id: Id
    policy_version: Id | None = None
    execute_live: Literal[True]


class RegistrationRequest(StrictModel):
    expected_store_identity: Digest
    # 'smolagents' is native adapter v1 (unchanged); 'smolagents-v2' is the declared adapter v2.
    agent: Literal['reference', 'smolagents', 'smolagents-v2']


def current_configuration(settings):
    from app.lab.configuration import frozen_configuration
    caps = CampaignBudget(model_calls=settings.faultlab_model_call_cap,
                          tokens=settings.faultlab_token_cap, dollars=float(settings.faultlab_dollar_cap))
    return frozen_configuration(settings, caps, 'live-v1' if settings.wandb_model else 'offline-v1')


def register_agent(store, settings, agent):
    """Freeze only installed reviewed entrypoints; never install or execute an agent."""
    from app.integrations.registry import AGENT_ENTRYPOINTS, NATIVE_AGENTS, freeze_target_configuration
    registry = AgentRegistry(store)
    current = current_configuration(settings)
    if agent in NATIVE_AGENTS:
        if not settings.wandb_model:
            raise ValueError('Configure the target model before native-agent registration')
        entrypoint = AGENT_ENTRYPOINTS[agent]
        return registry.register_smolagents(freeze_target_configuration(current, settings.wandb_model, entrypoint),
                                            entrypoint)
    if agent != 'reference':
        raise ValueError('Unknown reviewed agent')
    return registry.register_reference(current, internal_smoke=not bool(settings.wandb_model))


def register_owned_agent(coordinator, request):
    require_owner(coordinator, request.expected_store_identity)
    if coordinator.active_id is not None:
        raise StoreConflict('Wait for the active execution to finish before changing registrations')
    with coordinator.store.transaction():
        return register_agent(coordinator.store, coordinator.settings, request.agent)


async def read_import_request(request):
    length = request.headers.get('content-length')
    if length is not None:
        try:
            if not 0 <= int(length) <= MAX_UPLOAD_BYTES:
                raise ValueError()
        except ValueError:
            raise ValueError('Bundle upload exceeds the transport bound') from None
    body = bytearray()
    async for chunk in request.stream():
        if len(body) + len(chunk) > MAX_UPLOAD_BYTES:
            raise ValueError('Bundle upload exceeds the transport bound')
        body.extend(chunk)
    return await asyncio.to_thread(_decode_import_request, body)


def _decode_import_request(body):
    try:
        # Reject duplicate keys, including duplicate file entries.
        return ImportExecutionRequest.model_validate_json(canonical_json(_json(body)))
    except (ValueError, TypeError, UnicodeError):
        raise ValueError('Bundle upload does not match the trusted import contract') from None


def require_owner(coordinator, expected):
    if getattr(coordinator, 'read_only', False) or getattr(coordinator.store, 'read_only', False):
        raise ReadOnlyStore()
    if store_descriptor(coordinator.store)['identity'] != expected:
        raise StoreConflict('Configured CLI store differs from this backend. Select the same data directory before execution.')


def import_bundle(store, inspected, payloads, campaign_id):
    """Retain validated imported data without changing any active policy pointer."""
    bundle, policy = inspected.bundle, inspected.policy
    validate_bundle(bundle, payloads)
    previous = store.get_record('policies', policy.version)
    if previous and (previous.get('policy_hash') != policy.policy_hash
                     or previous.get('content') != policy.content.model_dump(mode='json')):
        raise ValueError('Imported policy identity conflicts with local history')
    with store.transaction():
        if not previous:
            store.put_record('policies', policy.version, policy, immutable=True)
            # A foreign version keeps its historical decision label; mark it so local
            # acceptance gates (comparison, audit, portability, freeze) refuse it.
            store.put_record('policy_imports', policy.version, {
                'imported': True, 'import_id': bundle.bundle_id, 'source_policy_version': policy.version,
                'source_policy_hash': policy.policy_hash, 'historical_decision': policy.decision,
                'local_acceptance': False, 'source_policy': policy.model_dump(mode='json'),
                'path': 'cli_import_and_execute'}, immutable=True)
        store.put_record('bundles', bundle.bundle_id, manifest_payload(bundle), immutable=True)
        store.put_record('bundle_files', bundle.bundle_id, payloads, immutable=True)
        store.put_record('bundle_imports', bundle.bundle_id, {
            'bundle_id': bundle.bundle_id, 'manifest_hash': bundle.manifest_hash,
            'source_configuration_hash': bundle.configuration_hash,
            'mode': 'validated_data_import', 'source_evidence_verified_locally': False}, immutable=True)
        lineage = json.loads(payloads['lineage.json'])
        counter, kind = lineage['counterexample'], artifact_kind(bundle, policy)
        case = RegressionCase(regression_id=new_id('regression'), artifact_kind=kind,
            campaign_id=campaign_id, counterexample_id=counter['counterexample_id'],
            target_invariant=bundle.target_invariant, first_failing_policy=policy.version,
            accepted_policy=policy.version if kind == 'accepted_policy_bundle' else None,
            reduction_ref=counter['counterexample_id'] if lineage['reduction'] else None,
            diagnostic_ref=lineage['diagnostic']['diagnostic_id'] if lineage['diagnostic'] else None,
            challenge_ref=lineage['challenge']['challenge_id'] if lineage['challenge'] else None,
            bundle_id=bundle.bundle_id)
        store.put_record('regressions', case.regression_id, case, immutable=True)
    return case


def _prepare_import(coordinator, request):
    """No database writes or caller-chosen filesystem paths during validation."""
    registry = AgentRegistry(coordinator.store)
    registration = registry.get(request.agent_registration_id)
    target = coordinator.store.get_record('configurations', registration.configuration_hash)
    if registration.model != coordinator.settings.wandb_model:
        raise ValueError('Registered target model differs from configured runtime')
    with TemporaryDirectory(prefix='faultlab-import-') as temporary:
        # macOS may expose its trusted temporary root through /var -> /private/var.
        # Canonicalize our own new directory; uploaded paths remain an exact allowlist.
        directory = Path(temporary).resolve()
        (directory / 'manifest.json').write_text(request.manifest, encoding='utf-8')
        for name, value in request.files.items():
            path = directory / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(value, encoding='utf-8')
        inspected, _ = RegressionRunner(coordinator.store, registry)._check(
            directory, target, registration.registration_id)
    runnable_policy(inspected.bundle, inspected.policy)
    from app.telemetry.safety import public_json
    settings = coordinator.settings
    for name, text in request.files.items():
        if name.endswith('.json'):
            public_json(_json(text), max_bytes=MAX_BUNDLE_FILE,
                        secrets=(settings.wandb_api_key, settings.typesafe_api_key, settings.faultlab_control_token))
    recording = _json(request.files.get('evidence.json', '{}'))
    # Same checked task as the dashboard import; a malformed task is refused, never guessed.
    from app.lab.bundle_imports import recorded_execution_task
    task = recorded_execution_task(recording)
    campaign_request = CampaignRequest(task_text=task['task_text'], order_id=task['order_id'],
                                       mode='baseline', config_profile_id='live-v1')
    return inspected, campaign_request


async def import_and_execute(coordinator, request):
    require_owner(coordinator, request.expected_store_identity)
    coordinator.settings.require_live()
    if coordinator.active_id is not None:
        raise StoreConflict('Another fresh execution is active')
    try:
        inspected, campaign_request = await asyncio.to_thread(_prepare_import, coordinator, request)
    except Exception:
        # Untrusted bundle validation must not echo input or credential values.
        raise ValueError('Bundle or registration failed the trusted import contract') from None
    if coordinator.active_id is not None:
        raise StoreConflict('Another fresh execution is active')
    with coordinator.store.transaction():
        campaign = coordinator.create(campaign_request)
        case = import_bundle(coordinator.store, inspected, request.files, campaign.campaign_id)
    from types import SimpleNamespace
    from app.lab.regression_executions import execute_regression
    return await execute_regression(coordinator, case.regression_id, SimpleNamespace(
        agent_registration_id=request.agent_registration_id,
        execution_profile_id=request.execution_profile_id,
        policy_version=inspected.policy.version, execute_live=True))


async def freeze_and_queue_portability(coordinator, campaign_id, request):
    require_owner(coordinator, request.expected_store_identity)
    from app.lab.policies import require_ordinary_campaign
    require_ordinary_campaign(coordinator.store, campaign_id)
    coordinator.settings.require_live()
    campaign = coordinator.get(campaign_id)
    if coordinator.active_id is not None:
        raise StoreConflict('Another fresh execution is active')
    frozen = coordinator.store.get_record('audit_freezes', campaign_id)
    if not frozen or not frozen.get('learned_arm_available'):
        raise ValueError('Freeze a completed campaign with accepted policy first')
    registry = AgentRegistry(coordinator.store)
    registration = registry.get(request.agent_registration_id)
    registry.verify(registration.registration_id,
                    coordinator.store.get_record('configurations', registration.configuration_hash))
    if registration.model != coordinator.settings.wandb_model:
        raise ValueError('Target model differs from configured runtime')
    source = coordinator.store.get_record('campaign_registrations', campaign_id)
    if not source: raise ValueError('Source registration unavailable')
    from app.integrations.portability import require_independent_target
    require_independent_target(registry.get(source['registration_id']), registration)
    previous = coordinator.store.get_record('external_freezes', campaign_id)
    if previous:
        if previous.get('registration', {}).get('registration_id') != registration.registration_id:
            raise StoreConflict('External freeze belongs to another registration')
    else:
        directory = coordinator.settings.artifact_path / 'campaigns' / campaign_id / 'audit'
        if Path(frozen['path']).resolve() != (directory / 'freeze.json').resolve():
            raise StoreConflict('Core freeze is outside the configured campaign directory')
        from app.referee.freeze import freeze_external
        value = freeze_external(directory, registration)
        coordinator.store.put_record('external_freezes', campaign_id, value, immutable=True)
    from app.lab.portability import queue_portability
    return await queue_portability(coordinator, campaign.campaign_id, request)
