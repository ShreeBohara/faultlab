"""Provider-free ZIP review and separately admitted, idempotent fresh execution.

An imported decision is historical data. Importing never registers an agent,
creates a campaign, activates a policy, or verifies remote source evidence.
"""
import asyncio
from contextlib import contextmanager
import io
import json
from pathlib import Path
import stat
import struct
from tempfile import TemporaryDirectory
from typing import Literal
import zipfile

from pydantic import TypeAdapter, ValidationError

from app.contracts.task_text import task_text_problem
from app.contracts.models import (CampaignBudget, CampaignRequest, Digest, EpisodeBudget,
    Id, RegressionCase, RegressionExecution, StrictModel, Usage, canonical_json,
    content_hash, new_id, utc_now)
from app.integrations.regression_runner import INVENTORY, inspect_bundle, _json
from app.integrations.registry import AgentRegistry, current_registration_configuration
from app.lab.budgets import BudgetExhausted, CampaignLedger, protected_reservations
from app.lab.dashboard import store_descriptor
from app.lab.operator_actions import MAX_MANIFEST_BYTES, MAX_UPLOAD_BYTES, require_owner
from app.lab.regressions import (MAX_BUNDLE_BYTES, MAX_BUNDLE_FILE, RegressionCompiler,
    artifact_kind, manifest_payload, runnable_policy, validate_bundle)
from app.lab.storage import StoreConflict
from app.telemetry.safety import TelemetryError, public_json

IMPORT_KIND = 'reviewed_bundle_imports'
REQUEST_KIND = 'bundle_import_executions'
CANCEL_KIND = 'bundle_import_cancellations'
SHARED_SEMANTICS = ('contract_hash', 'capability_hash', 'scorer_hash', 'interpreter_hash')
SEMANTIC_NAMES = {'contract_hash': 'task contract and simulator', 'capability_hash': 'tool capabilities',
                  'scorer_hash': 'fixed scorer', 'interpreter_hash': 'policy interpreter'}
# Used only when a bundle records no execution task (older exports). Review shows
# whichever task will actually be sent, and whether it came from the bundle.
DEFAULT_TASK_TEXT = 'Upgrade the authorized order to express shipping, then record one truthful confirmation.'
DEFAULT_ORDER_ID = 'order-regression'
REQUIRED_TRIALS = 3
# Three trials of at most eight actor turns each are reserved before admission.
RESERVED_ACTOR_TURNS = REQUIRED_TRIALS * EpisodeBudget().actor_calls
# The reference and native agents may resend a request whose transport failed before
# any answer arrived (app.agents.transport_retry). Such retries are charged but never
# reserved; this ceiling bounds them per fresh execution, independently of the
# configured campaign caps.
TRANSPORT_RETRY_ALLOWANCE = RESERVED_ACTOR_TURNS
REQUEST_CEILING = RESERVED_ACTOR_TURNS + TRANSPORT_RETRY_ALLOWANCE
_ID = TypeAdapter(Id)


class ImportOwnerLedger(CampaignLedger):
    """Ledger of an accounting owner that holds exactly one imported execution.

    Charged transport retries use unreserved capacity, which for this owner is the
    whole configured cap. The ceiling bounds all charged calls of the execution, while
    keeping every still-reserved actor turn available. (budgets.py is part of the
    frozen interpreter fingerprint, so this bound lives here instead.)
    """
    call_ceiling = REQUEST_CEILING

    def consume_call(self, *, reservation=None, role='actor'):
        with self.store.lock:
            protected = self.reserved_calls
            held = self.reservations.get(reservation) if reservation else None
            if held and held['calls'] >= 1:
                protected -= 1
            if self.used_calls + 1 + protected > self.call_ceiling:
                raise BudgetExhausted('Execution request ceiling reached')
            return super().consume_call(reservation=reservation, role=role)


def _valid_id(value):
    if not isinstance(value, str):
        return False
    try:
        _ID.validate_python(value)
    except ValidationError:
        return False
    return True


def recorded_execution_task(recording):
    """The exact task and order a fresh rerun sends to the agent, and their origin.

    The bundle's own recorded task is used when present; it must satisfy the same
    contract as a campaign request. A bundle that records no task uses the fixed
    default. Anything else is malformed and is refused, never guessed.
    """
    task = recording.get('execution_task') if isinstance(recording, dict) else None
    default = {'task_text': DEFAULT_TASK_TEXT, 'order_id': DEFAULT_ORDER_ID, 'origin': 'default'}
    if task is None:
        return default
    if not isinstance(task, dict) or not set(task) <= {'task_text', 'order_id'}:
        raise ValueError('Recorded execution task is malformed')
    text, order = task.get('task_text'), task.get('order_id')
    if text is None and order is None:
        return default
    # The same rule as every task request (app.contracts.task_text): at most 2000 code
    # points and at least one visible character, so an invisible task is refused here.
    if task_text_problem(text) is not None or not _valid_id(order):
        raise ValueError('Recorded execution task is malformed')
    return {'task_text': text, 'order_id': order, 'origin': 'bundled'}


def recorded_source_registration(recording):
    """The source registration ID copied into the saved summary: an ID or None."""
    registration = recording.get('agent_registration') if isinstance(recording, dict) else None
    if registration is None:
        return None
    if not isinstance(registration, dict):
        raise ValueError('Recorded source registration is malformed')
    value = registration.get('registration_id')
    if value is not None and not _valid_id(value):
        raise ValueError('Recorded source registration is malformed')
    return value


def _check_recorded_fields(payloads):
    """Every evidence field the importer copies or later uses must be well formed."""
    if 'evidence.json' not in payloads:
        return
    recording = _json(payloads['evidence.json'])
    if not isinstance(recording, dict):
        raise ValueError('Recorded evidence field is malformed')
    recorded_source_registration(recording)
    recorded_execution_task(recording)


class ImportedExecutionRequest(StrictModel):
    expected_store_identity: Digest
    expected_manifest_hash: Digest
    expected_target_configuration_hash: Digest
    agent_registration_id: Id
    request_id: Id
    execution_profile_id: Literal['sandbox-v1']
    execute_live: Literal[True]


async def read_zip_request(request):
    if request.headers.get('content-type', '').split(';', 1)[0].strip().lower() != 'application/zip':
        raise ValueError('Upload the downloaded FaultLab regression ZIP, not a recording JSON')
    try:
        length = request.headers.get('content-length')
        if length is not None and not 0 <= int(length) <= MAX_UPLOAD_BYTES:
            raise ValueError()
    except ValueError:
        raise ValueError('Bundle upload exceeds the transport bound') from None
    data = bytearray()
    async for chunk in request.stream():
        if len(data) + len(chunk) > MAX_UPLOAD_BYTES:
            raise ValueError('Bundle upload exceeds the transport bound')
        data.extend(chunk)
    return bytes(data)


def _zip_payloads(data):
    if len(data) > MAX_UPLOAD_BYTES:
        raise ValueError('Bundle upload exceeds the transport bound')
    # ZipFile eagerly constructs every central-directory entry. Bound that
    # allocation before invoking its parser, including forged entry counts.
    end = data.rfind(b'PK\x05\x06', max(0, len(data) - 65557))
    if end < 0 or len(data) - end < 22:
        raise ValueError('ZIP directory is unavailable')
    _, disk, directory_disk, disk_count, count, size, offset, comment = struct.unpack_from('<4s4H2LH', data, end)
    if (disk != 0 or directory_disk != 0 or disk_count != count or count not in (8, 9)
            or size > 65536 or offset + size != end or end + 22 + comment != len(data)
            or (end >= 20 and data[end-20:end-16] == b'PK\x06\x07')):
        raise ValueError('ZIP directory exceeds the reviewed inventory bound')
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        entries = archive.infolist()
        names = [entry.filename for entry in entries]
        if (len(names) != count or len(names) != len(set(names)) or set(names) not in
                (INVENTORY | {'manifest.json'}, INVENTORY | {'manifest.json', 'evidence.json'})):
            raise ValueError('Exact reviewed ZIP inventory required')
        total = 0
        payloads = {}
        for entry in entries:
            bound = MAX_MANIFEST_BYTES if entry.filename == 'manifest.json' else MAX_BUNDLE_FILE
            mode = entry.external_attr >> 16
            if (entry.orig_filename != entry.filename or entry.is_dir() or entry.flag_bits & 1
                    or entry.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED)
                    or stat.S_IFMT(mode) not in (0, stat.S_IFREG)
                    or not 0 <= entry.file_size <= bound):
                raise ValueError('ZIP entry type, encryption or size rejected')
            with archive.open(entry) as source:
                raw = source.read(bound + 1)
                if len(raw) > bound or len(raw) != entry.file_size:
                    raise ValueError('ZIP entry exceeds its reviewed bound')
            if entry.filename != 'manifest.json':
                total += len(raw)
                if total > MAX_BUNDLE_BYTES:
                    raise ValueError('Expanded bundle exceeds the total size bound')
            payloads[entry.filename] = raw.decode('utf-8')
        return payloads.pop('manifest.json'), payloads


@contextmanager
def _materialized(manifest, payloads):
    """Only our exact allowlisted paths enter a fresh trusted temporary directory."""
    if set(payloads) not in (INVENTORY, INVENTORY | {'evidence.json'}):
        raise ValueError('Exact reviewed bundle inventory required')
    with TemporaryDirectory(prefix='faultlab-reviewed-import-') as temporary:
        directory = Path(temporary).resolve()
        (directory / 'manifest.json').write_text(manifest, encoding='utf-8')
        for name, text in payloads.items():
            path = directory / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding='utf-8')
        yield directory


REJECTED = 'Import refused; nothing was saved.'
_UNKNOWN = 'The file is not a valid FaultLab regression export.'
_NOT_ZIP = 'Not a ZIP archive. A campaign recording JSON is evidence, not a runnable bundle; export a regression ZIP.'
_STRUCTURE = ('Structure or size: the ZIP must hold exactly the files of a FaultLab regression export, '
    'as plain files within the size limits.')
_VERSION = ('Unsupported version: an older or different FaultLab schema, runner or execution profile made it. '
    'Keep the file and open it with the FaultLab version that created it.')
_INTEGRITY = ('Contents do not match: the files differ from the checksums and identities recorded inside the '
    'bundle, so it may have been edited or be incomplete.')
# A correctly hashed bundle can still record a task that cannot be sent exactly; say so
# instead of blaming the checksums.
_TASK = ('Recorded task is malformed (such as empty, over 2000 characters, no visible character or '
    'an invalid order ID), so it cannot be shown or sent exactly.')
# Only our own fixed validator messages select a category. Any other error text may
# contain uploaded names or values, so it is never echoed and gets no category.
_CATEGORIES = {
    'ZIP directory is unavailable': _NOT_ZIP,
    **dict.fromkeys(('Bundle upload exceeds the transport bound', 'ZIP directory exceeds the reviewed inventory bound',
        'Exact reviewed ZIP inventory required', 'ZIP entry type, encryption or size rejected',
        'ZIP entry exceeds its reviewed bound', 'Expanded bundle exceeds the total size bound',
        'Exact reviewed bundle inventory required', 'Symlink or missing bundle directory rejected',
        'Symlink bundle entry rejected', 'Unknown bundle directory rejected', 'Nonregular bundle entry rejected',
        'Bundle file type/size rejected', 'Bundle file too large', 'Bundle exceeds total size bound'), _STRUCTURE),
    **dict.fromkeys(('Untrusted schema or runner version/digest', 'Unsupported execution profile or caps',
        'Runner bytes are not the reviewed installed template', 'Incident evidence version or kind mismatch'), _VERSION),
    **dict.fromkeys(('Manifest digest mismatch', 'Unknown, duplicate or missing inventory entry',
        'Bundle file digest/size mismatch', 'Transferred policy content digest mismatch',
        'Historical source configuration digest mismatch', 'Historical source identity does not match manifest',
        'Source budget mismatch', 'Source/retained recipe mismatch', 'Invalid trial inventory',
        'Historical trial inventory mismatch', 'Unsupported lineage fields',
        'Accepted-policy label contradicts recorded decision', 'Incident reset fixture mismatch',
        'Protected or mismatched incident episode', 'Unrelated incident event timeline',
        'Private or unordered incident event', 'Duplicate JSON key rejected', 'Nonfinite JSON rejected',
        'Recorded evidence field is malformed', 'Recorded source registration is malformed'), _INTEGRITY),
    'Recorded execution task is malformed': _TASK,
}


_PRIVATE = 'Private content: it contains private evaluator fields, non-public values or a configured credential.'
_PRIVATE_MESSAGES = {'Private or non-public payload field rejected.', 'Secret-bearing telemetry rejected.',
    'Only explicit public JSON values may be captured.', 'Invalid public JSON value.',
    'Public payload exceeds capture limit.'}


def rejection_message(error):
    if type(error) is ValueError:
        category = _CATEGORIES.get(str(error))
    elif isinstance(error, TelemetryError) and str(error) in _PRIVATE_MESSAGES:
        category = _PRIVATE
    else:
        category = None
    return f'{REJECTED} {_UNKNOWN if category is None else category}'


def _inspect_upload(data, secrets):
    try:
        manifest, payloads = _zip_payloads(data)
        public_json(_json(manifest), max_bytes=MAX_MANIFEST_BYTES, secrets=secrets)
        with _materialized(manifest, payloads) as directory:
            inspected = inspect_bundle(directory)
        for name, text in payloads.items():
            if name.endswith('.json'):
                public_json(_json(text), max_bytes=MAX_BUNDLE_FILE, secrets=secrets)
        _check_recorded_fields(payloads)
        return inspected, payloads
    except Exception as error:
        # Never echo malicious filenames, document strings or decompressor errors.
        raise ValueError(rejection_message(error)) from None


def _runnable(bundle, policy):
    try:
        runnable_policy(bundle, policy)
    except ValueError:
        return False, 'The imported policy has no completed, runnable decision'
    return True, None


async def save_import(coordinator, expected_store_identity, data, *, prepared=None, with_status=False):
    """Save validated import data. with_status also reports whether this call created it."""
    require_owner(coordinator, expected_store_identity)
    settings = coordinator.settings
    inspected, payloads = prepared or await asyncio.to_thread(_inspect_upload, data,
        (settings.wandb_api_key, settings.typesafe_api_key, settings.faultlab_control_token))
    bundle, policy = inspected.bundle, inspected.policy
    recording = _json(payloads['evidence.json']) if 'evidence.json' in payloads else None
    runnable, reason = _runnable(bundle, policy)
    source_modes = sorted({episode['source_mode'] for episode in (recording or {}).get('episodes', [])})
    record = {'import_id': bundle.bundle_id, 'bundle_id': bundle.bundle_id,
        'manifest_hash': bundle.manifest_hash, 'imported_at': utc_now().isoformat(),
        'artifact_kind': artifact_kind(bundle, policy),
        'policy': {'version': policy.version, 'hash': policy.policy_hash, 'decision': policy.decision},
        'runnable': runnable, 'runnable_reason': reason,
        'source': {'configuration_hash': bundle.configuration_hash,
            'model': inspected.source_configuration['model'],
            'agent_registration_id': recorded_source_registration(recording),
            'source_mode': source_modes[0] if len(source_modes) == 1 else None,
            'source_modes': source_modes,
            'evidence_verification': 'NO_LOCAL_VERIFICATION'}}
    # This bounded transaction may run while another campaign is active. It writes
    # data only and cannot touch its world, usage, scheduler or policy pointers.
    def persist():
        require_owner(coordinator, expected_store_identity)
        with coordinator.store.transaction():
            old = coordinator.store.get_record(IMPORT_KIND, bundle.bundle_id)
            if old is not None and old['manifest_hash'] != bundle.manifest_hash:
                raise StoreConflict('Imported bundle identity conflicts with saved history')
            coordinator.store.put_record('bundles', bundle.bundle_id, manifest_payload(bundle), immutable=True)
            coordinator.store.put_record('bundle_files', bundle.bundle_id, payloads, immutable=True)
            if old is None:
                coordinator.store.put_record(IMPORT_KIND, bundle.bundle_id, record, immutable=True)
            return old is None
    created = await asyncio.to_thread(persist)
    detail = await asyncio.to_thread(import_detail, coordinator.store, settings, bundle.bundle_id)
    return (detail, created) if with_status else detail


def _saved(store, import_id):
    record = store.get_record(IMPORT_KIND, import_id)
    if record is None: raise KeyError(import_id)
    from app.contracts.models import RegressionBundle, PolicyVersion
    bundle = store.get_model('bundles', record['bundle_id'], RegressionBundle)
    payloads = store.get_record('bundle_files', record['bundle_id'])
    if bundle is None or record['manifest_hash'] != bundle.manifest_hash:
        raise StoreConflict('Saved import identity is inconsistent')
    validate_bundle(bundle, payloads)
    policy = PolicyVersion.model_validate_json(payloads['policy.json'])
    return record, bundle, payloads, policy


def _page(store, kind, *, import_id=None, before=None, limit=20):
    if not 1 <= limit <= 100 or (before is not None and before < 1):
        raise ValueError('Invalid import history cursor or limit')
    clauses = ['kind=?']; args = [kind]
    if import_id is not None:
        clauses.append("json_extract(payload,'$.import_id')=?"); args.append(import_id)
    if before is not None: clauses.append('rowid<?'); args.append(before)
    with store.lock:
        rows = store.db.execute('SELECT rowid,payload FROM records WHERE ' + ' AND '.join(clauses)
            + ' ORDER BY rowid DESC LIMIT ?', (*args, limit + 1)).fetchall()
    return rows[:limit], {'next_before': rows[limit-1]['rowid'] if len(rows) > limit else None,
                         'has_more': len(rows) > limit}


def _summary(record):
    """A saved summary as displayed. Summaries saved before field checks existed may
    hold a malformed source registration; show it as not recorded, and say so."""
    source = dict(record.get('source') or {})
    if source.get('agent_registration_id') is not None and not _valid_id(source['agent_registration_id']):
        source['agent_registration_id'] = None
        source['agent_registration_malformed'] = True
    return {**record, 'source': source}


def import_page(store, *, before=None, limit=20):
    """Saved imports, newest first, with the same runnable verdict as each detail view."""
    rows, page = _page(store, IMPORT_KIND, before=before, limit=limit)
    items = []; installed = []
    def semantics():
        if not installed: installed.append(_installed_semantics())
        return installed[0]
    for row in rows:
        record = _summary(json.loads(row['payload']))
        try:
            _, bundle, payloads, _ = _saved(store, record['import_id'])
        except Exception:
            # One damaged saved import must not hide the others; its detail view reports why.
            if record.get('runnable'):
                record = {**record, 'runnable': False,
                          'runnable_reason': 'The saved import failed its integrity check; open it for details'}
        else:
            record = _current_runnable(record, bundle, payloads, semantics)
        items.append(record)
    return {'items': items, **page}


def _current_runnable(record, bundle, payloads, installed=None):
    """A saved summary's runnable verdict re-checked against today's runtime.

    The summary saved at import time can be stale: a task check added later, or a bundle
    whose simulator/contract build differs from the installed one. The list and the detail
    view both use this, so they always agree.
    """
    if record['runnable'] and _saved_task(payloads) is None:
        # Summaries saved before task checks existed stay readable but cannot run.
        record = {**record, 'runnable': False,
                  'runnable_reason': 'The recorded execution task is malformed; stored for inspection only'}
    if record['runnable']:
        # A bundle from an earlier simulator/contract build cannot run on any target here; say so
        # at the bundle level too, instead of only when a target is selected.
        problem = semantics_mismatch((installed or _installed_semantics)(), bundle)
        if problem:
            record = {**record, 'runnable': False, 'runnable_reason': problem}
    return record


def _target(store, settings, registration_id, bundle):
    registry = AgentRegistry(store)
    registration = registry.get(registration_id)
    caps = CampaignBudget(model_calls=settings.faultlab_model_call_cap,
        tokens=settings.faultlab_token_cap, dollars=float(settings.faultlab_dollar_cap))
    if registration.model != settings.wandb_model:
        raise StoreConflict('The registered model differs from the configured runtime model; '
                            'register this agent again with the current settings')
    current = current_registration_configuration(settings, caps, 'live-v1', registration)
    target = store.get_record('configurations', registration.configuration_hash)
    if target != current or content_hash(current) != registration.configuration_hash:
        raise StoreConflict('The registration no longer matches current settings or installed source; '
                            'register this agent again, then refresh the review')
    registry.verify(registration_id, current)
    problem = semantics_mismatch(current, bundle)
    if problem:
        raise StoreConflict(problem)
    return registration, current


def semantics_mismatch(current, bundle):
    """Why a bundle cannot be rerun on the installed runtime, naming each differing identity, or None."""
    differing = [field for field in SHARED_SEMANTICS if current[field] != getattr(bundle, field)]
    if not differing:
        return None
    parts = '; '.join(f'{SEMANTIC_NAMES[field]}: bundle {getattr(bundle, field)[:8]}…, installed {current[field][:8]}…'
                      for field in differing)
    cause = (' The bundle was made by an earlier or different simulator build.' if 'contract_hash' in differing else '')
    return (f'Target task, oracle or policy semantics are incompatible with this bundle ({parts}).{cause} '
            'A fresh rerun needs a bundle exported under the installed runtime; the saved evidence stays reviewable')


def _installed_semantics():
    """The installed runtime's shared task, tool, oracle and interpreter identities (no settings are read)."""
    from app.config import Settings
    from app.lab.configuration import frozen_configuration
    installed = frozen_configuration(Settings(), CampaignBudget(), 'offline-v1')
    return {field: installed[field] for field in SHARED_SEMANTICS}


def _target_description(registration):
    return {'agent_registration_id': registration.registration_id,
        'configuration_hash': registration.configuration_hash, 'model': registration.model,
        'agent': {'orders-prototype-v1': 'reference', 'smolagents-toolcalling-v1': 'smolagents'}.get(
            registration.adapter_entrypoint_id, 'unsupported')}


def _saved_task(payloads):
    recording = _json(payloads['evidence.json']) if 'evidence.json' in payloads else None
    try:
        return recorded_execution_task(recording)
    except ValueError:
        return None


def import_detail(store, settings, import_id):
    record, bundle, payloads, policy = _saved(store, import_id)
    record = _summary(record)
    targets = []
    for raw in store.list_records('agent_registrations'):
        from app.contracts.models import AgentRegistration
        registration = AgentRegistration.model_validate_json(canonical_json(raw))
        # The built-in offline smoke registration proves harness plumbing only; it
        # can never run an imported regression, so it is not offered as a target.
        if registration.provenance_class == 'internal_smoke':
            continue
        target = _target_description(registration)
        try:
            _target(store, settings, registration.registration_id, bundle)
        except StoreConflict as error:
            # Only our own fixed messages; registrations are local reviewed records.
            target.update(compatible=False, reason=str(error))
        except Exception:
            target.update(compatible=False, reason='This registration failed the current source and settings '
                                                   'review; register the agent again, then refresh the review')
        else:
            target.update(compatible=True, reason=None)
        targets.append(target)
    descriptor = store_descriptor(store)
    descriptor['read_only'] = settings.faultlab_read_only
    task = _saved_task(payloads)
    record = _current_runnable(record, bundle, payloads)
    return {**record,
        'historical': {'trials': bundle.model_dump(mode='json')['trial_results'],
            'recording': _json(payloads['evidence.json']) if 'evidence.json' in payloads else None,
            'evidence_available': 'evidence.json' in payloads,
            'label': 'Imported historical observations; not verified locally'},
        'recipe': {'source': bundle.source_recipe.model_dump(mode='json'),
            'retained': bundle.retained_recipe.model_dump(mode='json') if bundle.retained_recipe else None,
            'fixture_id': bundle.fixture_id, 'target_invariant': bundle.target_invariant},
        'execution_task': task,
        'limits': {'required_trials': REQUIRED_TRIALS, 'episode_budget': bundle.caps.model_dump(mode='json'),
            'reserved_actor_turns': RESERVED_ACTOR_TURNS, 'transport_retry_allowance': TRANSPORT_RETRY_ALLOWANCE,
            'max_model_requests': REQUEST_CEILING},
        'targets': targets, 'data_store': descriptor, 'provider_calls': 0}


def owner_charges(store, owner_campaign_id):
    """The accounting ledger of an owner that holds exactly one imported execution.

    Its charges include transport retries and calls made during a trial that was
    interrupted before its usage was saved, so it is the complete charge record.
    """
    budget = store.get_record('budgets', owner_campaign_id)
    if budget is None:
        return None
    return {'model_calls': budget.get('used_calls', 0),
            'reserved_model_calls': sum(r['calls'] for r in (budget.get('reservations') or {}).values()),
            'measured_input_tokens': budget.get('measured_input_tokens', 0),
            'measured_output_tokens': budget.get('measured_output_tokens', 0),
            'actual_cost_dollars': budget.get('actual_cost_dollars'),
            'charged_dollar_upper_bound': budget.get('charged_dollar_upper_bound'),
            'request_ceiling': REQUEST_CEILING}


def execution_view(store, binding):
    execution = store.get_record('regression_executions', binding['execution_id'])
    if execution is None: raise StoreConflict('Saved import execution is unavailable; no automatic rerun')
    return {key: binding[key] for key in ('import_id', 'request_id', 'owner_campaign_id', 'regression_id', 'target')} | {
        'execution': execution, 'assertions': store.get_record('regression_assertions', binding['execution_id']),
        'error': store.get_record('regression_execution_errors', binding['execution_id']),
        'trial_errors': store.get_record('regression_trial_errors', binding['execution_id']),
        'owner_charges': owner_charges(store, binding['owner_campaign_id']),
        'source_evidence_verified_locally': False}


def execution_page(store, import_id, *, before=None, limit=20):
    if store.get_record(IMPORT_KIND, import_id) is None: raise KeyError(import_id)
    rows, page = _page(store, REQUEST_KIND, import_id=import_id, before=before, limit=limit)
    return {'items': [execution_view(store, json.loads(row['payload'])) for row in rows], **page}


def request_view(store, import_id, request_id):
    binding = store.get_record(REQUEST_KIND, request_id)
    if binding is None:
        cancellation = store.get_record(CANCEL_KIND, request_id)
        if cancellation is not None and cancellation['import_id'] == import_id:
            return {'cancelled': True, 'import_id': import_id, 'request_id': request_id}
        raise KeyError(request_id)
    if binding['import_id'] != import_id: raise KeyError(request_id)
    return execution_view(store, binding)


def policy_import_provenance(store, version):
    if store.get_record('policies', version) is None: raise KeyError(version)
    from app.lab.policies import import_provenance
    return import_provenance(store, version) or {'imported': False}


def import_owner(store, campaign_id):
    if store.get_record('campaigns', campaign_id) is None: raise KeyError(campaign_id)
    binding = store.get_record('import_execution_owners', campaign_id)
    if binding is None: return {'imported_owner': False}
    return {'imported_owner': True, **{key: binding[key] for key in
        ('import_id', 'request_id', 'execution_id', 'target')},
        'reserved_actor_turns': RESERVED_ACTOR_TURNS, 'request_ceiling': REQUEST_CEILING}


def _duplicate(store, import_id, request):
    cancellation = store.get_record(CANCEL_KIND, request.request_id)
    if cancellation is not None:
        raise StoreConflict('Execution request was cancelled; create a new reviewed request to run again')
    binding = store.get_record(REQUEST_KIND, request.request_id)
    if binding is None: return None
    if binding['import_id'] != import_id or binding['request'] != request.model_dump(mode='json'):
        raise StoreConflict('Execution request identity was already used with different reviewed inputs')
    return execution_view(store, binding)


async def cancel_request(coordinator, import_id, request_id, request):
    """Resolve an uncertain HTTP admission without ever stopping admitted work."""
    require_owner(coordinator, request.expected_store_identity)
    if request_id != request.request_id:
        raise StoreConflict('Cancellation identity differs from the original execution request')
    async with coordinator.lock:
        if coordinator.store.get_record(IMPORT_KIND, import_id) is None: raise KeyError(import_id)
        cancellation = coordinator.store.get_record(CANCEL_KIND, request_id)
        if cancellation is not None:
            if cancellation['import_id'] != import_id or cancellation['request'] != request.model_dump(mode='json'):
                raise StoreConflict('Request identity already refers to different reviewed inputs')
        else:
            existing = _duplicate(coordinator.store, import_id, request)
            if existing is not None: return {'cancelled': False, 'execution': existing}
            coordinator.store.put_record(CANCEL_KIND, request_id, {'import_id': import_id,
                'request_id': request_id, 'request': request.model_dump(mode='json'),
                'cancelled_at': utc_now().isoformat()}, immutable=True)
        return {'cancelled': True, 'import_id': import_id, 'request_id': request_id}


def _prepare_execution(store, settings, import_id, request):
    record, bundle, payloads, source_policy = _saved(store, import_id)
    if bundle.manifest_hash != request.expected_manifest_hash:
        raise StoreConflict('Imported bundle changed; refresh its review before execution')
    registration, target = _target(store, settings, request.agent_registration_id, bundle)
    if request.expected_target_configuration_hash != registration.configuration_hash:
        raise StoreConflict('Selected target changed; refresh its review before execution')
    with _materialized(canonical_json(manifest_payload(bundle)), payloads) as directory:
        from app.integrations.regression_runner import RegressionRunner
        inspected, _ = RegressionRunner(store, AgentRegistry(store))._check(directory, target, registration.registration_id)
    runnable_policy(bundle, source_policy)
    version = 'imported-' + content_hash({'manifest': bundle.manifest_hash, 'version': source_policy.version})[:40]
    policy = source_policy.model_copy(update={'version': version, 'parent_version': None,
        'raw_proposal_ref': None, 'development_episode_ids': [], 'decision_ref': None, 'evaluation_refs': []})
    # Exactly the task the review displayed (see import_detail); never a silent substitute.
    task = _saved_task(payloads)
    if task is None:
        raise StoreConflict('The recorded execution task is malformed; this import cannot run')
    campaign_request = CampaignRequest(mode='baseline', config_profile_id='live-v1',
        task_text=task['task_text'], order_id=task['order_id'])
    return inspected, registration, target, policy, source_policy, campaign_request, _json(payloads['lineage.json'])


async def execute_import(coordinator, import_id, request):
    require_owner(coordinator, request.expected_store_identity)
    previous = _duplicate(coordinator.store, import_id, request)
    if previous is not None: return previous
    coordinator.settings.require_live()
    if coordinator.active_id is not None: raise StoreConflict('Another fresh execution is active')
    prepared = await asyncio.to_thread(_prepare_execution, coordinator.store, coordinator.settings, import_id, request)
    checked, registration, target, policy, source_policy, campaign_request, lineage = prepared
    async with coordinator.lock:
        previous = _duplicate(coordinator.store, import_id, request)
        if previous is not None: return previous
        if coordinator.active_id is not None: raise StoreConflict('Another fresh execution is active')
        await coordinator.require_simulator()
        # Refuse stale identities before writing the new job's materialization.
        _target(coordinator.store, coordinator.settings, request.agent_registration_id, checked.bundle)
        execution_id = new_id('execution'); reservation = 'regression:' + execution_id
        # Each admission owns its materialization; a concurrent/retried upload
        # cannot truncate the files while a prior worker is inspecting them.
        directory = coordinator.settings.artifact_path / 'import-executions' / execution_id / 'bundle'
        await asyncio.to_thread(RegressionCompiler(coordinator.store).export, checked.bundle.bundle_id, directory)
        # No await separates this final check from durable admission.
        _target(coordinator.store, coordinator.settings, request.agent_registration_id, checked.bundle)
        ledger = None
        with coordinator.store.transaction():
            campaign = coordinator.create(campaign_request)
            campaign.execution_epoch += 1
            coordinator.save(campaign)
            coordinator.store.put_record('policies', policy.version, policy, immutable=True)
            coordinator.store.put_record('policy_imports', policy.version, {
                'imported': True, 'import_id': import_id, 'source_policy_version': source_policy.version,
                'source_policy_hash': source_policy.policy_hash, 'historical_decision': source_policy.decision,
                'local_acceptance': False, 'source_policy': source_policy.model_dump(mode='json')}, immutable=True)
            counter = lineage['counterexample']; kind = artifact_kind(checked.bundle, source_policy)
            case = RegressionCase(regression_id=new_id('regression'), artifact_kind=kind,
                campaign_id=campaign.campaign_id, counterexample_id=counter['counterexample_id'],
                target_invariant=checked.bundle.target_invariant, first_failing_policy=policy.version,
                accepted_policy=policy.version if kind == 'accepted_policy_bundle' else None,
                reduction_ref=None, diagnostic_ref=None, challenge_ref=None, bundle_id=checked.bundle.bundle_id)
            coordinator.store.put_record('regressions', case.regression_id, case, immutable=True)
            ledger = ImportOwnerLedger(coordinator.store, campaign.campaign_id, campaign.caps,
                dollar_bounds=coordinator.settings.model_call_dollar_bounds)
            # This owner can run only the declared regression. Whole-learning
            # reserves belong to ordinary campaigns, never this three-trial job.
            for name in protected_reservations(campaign.caps): ledger.release(name)
            ledger.reserve(reservation, RESERVED_ACTOR_TURNS)
            execution = RegressionExecution(execution_id=execution_id, bundle_id=checked.bundle.bundle_id,
                manifest_hash=checked.bundle.manifest_hash, registration_id=registration.registration_id,
                profile_id='sandbox-v1', mode='FRESH_SANDBOX', explicit_action=True, policy_hash=policy.policy_hash,
                configuration_hash=registration.configuration_hash, declared_budget=EpisodeBudget(), usage=Usage(),
                episode_ids=[], world_ids=[], status='PENDING')
            coordinator.store.put_record('regression_executions', execution_id, execution)
            binding = {'import_id': import_id, 'request_id': request.request_id,
                'request': request.model_dump(mode='json'), 'execution_id': execution_id,
                'owner_campaign_id': campaign.campaign_id, 'regression_id': case.regression_id,
                'target': _target_description(registration)}
            coordinator.store.put_record(REQUEST_KIND, request.request_id, binding, immutable=True)
            coordinator.store.put_record('import_execution_owners', campaign.campaign_id,
                {**binding, 'role': 'regression_budget_owner', 'policy_activation': False}, immutable=True)
        coordinator.ledgers[campaign.campaign_id] = ledger
        coordinator.active_id = campaign.campaign_id
        from app.lab.regression_executions import schedule_regression
        schedule_regression(coordinator, campaign=campaign, checked=checked, registration=registration,
            target=target, policy=policy, ledger=ledger, execution_id=execution_id, reservation=reservation,
            directory=directory, record=execution)
    return execution_view(coordinator.store, binding)
