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
