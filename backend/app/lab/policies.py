"""Immutable policy content and preserved raw generated proposals."""
from app.contracts.models import RecoveryPolicy, CandidatePolicy, PolicyVersion, content_hash, new_id, canonical_json

class PolicyRepository:
    def __init__(self,store):
        self.store=store
        if not store.get_record('policies','policy-v0'):
            policy=RecoveryPolicy(parent_version='policy-v0',rules=[])
            self.save(PolicyVersion(version='policy-v0',parent_version=None,content=policy,policy_hash=content_hash(policy),author='baseline',raw_proposal_ref=None,development_episode_ids=[],decision='BASELINE'))

    def save(self,version):
        if version.content is not None and content_hash(version.content)!=version.policy_hash: raise ValueError('Policy digest mismatch')
        existing=self.get(version.version)
        if existing and (canonical_json(existing.content)!=canonical_json(version.content) or existing.policy_hash!=version.policy_hash or existing.parent_version!=version.parent_version): raise ValueError('Immutable policy changed')
        self.store.put_record('policies',version.version,version)
        return version

    def get(self,version): return self.store.get_model('policies',version,PolicyVersion)
    def list(self): return [PolicyVersion.model_validate_json(canonical_json(v)) for v in self.store.list_records('policies')]
    def baseline(self): return self.get('policy-v0')

    def proposal(self,candidate,*,parent,raw,episode_ids,author='mechanic'):
        version=new_id('policy'); proposal_ref=new_id('proposal')
        self.store.put_record('proposals',proposal_ref,{'raw':raw,'author':author,'parent_version':parent},immutable=True)
        if candidate.parent_version!=parent: raise ValueError('Stale policy parent')
        CandidatePolicy.model_validate_json(candidate.model_dump_json())
        return self.save(PolicyVersion(version=version,parent_version=parent,content=candidate,policy_hash=content_hash(candidate),author=author,raw_proposal_ref=proposal_ref,development_episode_ids=episode_ids,decision='PROPOSED'))

    def rejected_raw(self,raw,parent,reason):
        ref=new_id('proposal')
        self.store.put_record('proposals',ref,{'raw':raw,'parent_version':parent,'reason':reason},immutable=True)
        return self.save(PolicyVersion(version=new_id('policy'),parent_version=parent,content=None,policy_hash=None,author='mechanic',raw_proposal_ref=ref,development_episode_ids=[],decision='REJECTED'))


IMPORTED_POLICY_REFUSAL = ('An imported policy keeps only its historical source decision; it is not a local '
    'acceptance. Rerun it through Imported regressions instead.')


def imported_policy(store, policy):
    """True for a local alias created from an imported bundle (see bundle_imports).

    Its saved ``decision`` repeats the source workspace's historical label, so gates
    that require a *local* accepted or baseline policy must refuse it explicitly.
    """
    version = getattr(policy, 'version', policy)
    return bool(version) and import_provenance(store, version) is not None


def import_provenance(store, version):
    """The import marker for a policy version, including older unmarked CLI imports."""
    return store.get_record('policy_imports', version) or legacy_policy_import(store, version)


def legacy_policy_import(store, version):
    """Recognize a foreign policy saved by the older CLI import path.

    Before policy_imports markers existed, that path kept the source's own version
    name and wrote only a ``bundle_imports`` record. Such a policy is foreign when a
    legacy import carried exactly this version and hash and the policy has no locally
    created proposal. Reading never writes, so historical stores stay unchanged.
    """
    import json
    if not version or version == 'policy-v0':
        return None
    saved = store.get_record('policies', version)
    if saved is None or saved.get('policy_hash') is None:
        return None
    ref = saved.get('raw_proposal_ref')
    if ref and store.get_record('proposals', ref) is not None:
        return None  # Proposed in this store; never a foreign label.
    with store.lock:
        rows = store.db.execute(
            "SELECT i.id AS bundle_id, json_extract(f.payload, '$.\"policy.json\"') AS policy "
            "FROM records i JOIN records f ON f.kind='bundle_files' AND f.id=i.id "
            "WHERE i.kind='bundle_imports' ORDER BY i.rowid").fetchall()
    for row in rows:
        try:
            carried = json.loads(row['policy'] or 'null')
        except (TypeError, ValueError):
            continue
        if (isinstance(carried, dict) and carried.get('version') == version
                and carried.get('policy_hash') == saved['policy_hash']):
            return {'imported': True, 'import_id': row['bundle_id'], 'source_policy_version': version,
                    'source_policy_hash': saved['policy_hash'], 'historical_decision': carried.get('decision'),
                    'local_acceptance': False, 'path': 'legacy_cli_import_unmarked'}
    return None


IMPORT_OWNER_REFUSAL = ('Imported regression owners admit only their separately reviewed execution; '
    'create an ordinary campaign for other work.')


def require_ordinary_campaign(store, campaign_id):
    """Refuse every ordinary admission on an imported regression's accounting owner.

    That owner exists only to hold one reviewed fresh execution's budget and evidence;
    its protected study reserves were deliberately released. Call this before any
    record, ledger or file is written.
    """
    from app.lab.storage import StoreConflict
    if store.get_record('import_execution_owners', campaign_id) is not None:
        raise StoreConflict(IMPORT_OWNER_REFUSAL)
