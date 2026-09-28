"""Read-only dashboard projections, isolated from scheduler connection locks."""
from contextlib import contextmanager
from pathlib import Path

from app.contracts.models import Campaign, PolicyVersion, canonical_json, content_hash
from app.lab.storage import ReadOnlyLabStore


def store_descriptor(store):
    path = ':memory:' if store.path == ':memory:' else str(Path(store.path).expanduser().resolve())
    return {'identity': content_hash({'local_store_path': path}), 'path': path,
            'read_only': bool(getattr(store, 'read_only', False))}


def read_campaign(store, ident):
    campaign = store.get_model('campaigns', ident, Campaign)
    if campaign is None:
        raise KeyError(ident)
    budget = store.get_record('budgets', ident)
    if budget:
        campaign.reserved_calls = sum(r['calls'] for r in budget['reservations'].values())
        campaign.usage.model_calls = budget['used_calls']
        campaign.usage.input_tokens = budget.get('measured_input_tokens', 0)
        campaign.usage.output_tokens = budget.get('measured_output_tokens', 0)
        campaign.usage.cost_dollars = budget.get('actual_cost_dollars')
    return campaign


class ReadPolicies:
    def __init__(self, store):
        self.store = store

    def get(self, version):
        return self.store.get_model('policies', version, PolicyVersion)

    def list(self):
        return [PolicyVersion.model_validate_json(canonical_json(value))
                for value in self.store.list_records('policies')]


class DashboardView:
    """Only the methods needed by saved-data GET routes, never a scheduler."""
    def __init__(self, owner, store):
        self.store = store
        self.settings = owner.settings
        self.policies = ReadPolicies(store)
        self._config_status = owner.config_status
        self.read_only = getattr(owner, 'read_only', False)

    def get(self, ident):
        return read_campaign(self.store, ident)

    def config_status(self):
        return self._config_status()


@contextmanager
def dashboard_view(owner):
    # Explicit injected doubles and private in-memory test stores retain their
    # existing semantics. Production file stores get an independent SQL reader.
    if not hasattr(owner, 'settings') or owner.store.path == ':memory:':
        yield owner
        return
    store = ReadOnlyLabStore(owner.store.path)
    try:
        store.begin_snapshot()
        yield DashboardView(owner, store)
    finally:
        store.close()


class ArchiveCoordinator:
    """Saved browsing without constructing LabCoordinator or doing recovery."""
    read_only = True
    active_id = None

    def __init__(self, settings):
        self.settings = settings
        self.store = ReadOnlyLabStore(settings.artifact_path / 'lab.sqlite3')
        self.policies = ReadPolicies(self.store)

    def get(self, ident):
        return read_campaign(self.store, ident)

    def config_status(self):
        # Configuration describes recorded evidence; it grants no live access.
        page = self.store.campaign_page(limit=1)
        campaign = self.get(page['campaign_ids'][0]) if page['campaign_ids'] else None
        config = self.store.get_record('configurations', campaign.configuration_hash) if campaign else {}
        config = config or {}
        models = config.get('models') or {role: config.get('model', 'not-configured')
                                          for role in ('actor', 'explorer', 'mechanic')}
        return {'schema_version': 'faultlab/v1', 'model': models['actor'],
                'lab_model': models['explorer'], 'models': models,
                'actor_context_protocol': config.get('actor_context_protocol', 'faultlab-actor-context/v1'),
                'model_configured': False, 'live_enabled': False,
                'profile_ids': ['offline-v1', 'live-v1'],
                'sponsor': {'weave': 'PENDING', 'aria': 'PENDING'},
                'active_campaign_id': None, 'execution_profiles': [],
                'data_store': store_descriptor(self.store)}

    async def readiness(self):
        return {'ready': False, 'simulator': {'ready': False, 'code': 'READ_ONLY_ARCHIVE',
                'message': 'Read-only archive; saved evidence is available and execution is disabled.'},
                'live_configuration': {'ready': False, 'missing_fields': []},
                'provider_access': 'not_checked', 'provider_calls': 0,
                'models': self.config_status()['models']}

    async def close(self):
        self.store.close()
