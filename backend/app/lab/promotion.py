"""Independent fixed empirical promotion predicate and atomic expected-parent update."""
from app.contracts.models import canonical_json,new_id
from app.lab.evaluation import paired_complete
from app.lab.storage import StoreConflict


def promotion_decision(source,challenge,promotion,*,target_invariant,healthy_hashes=()):
    if (source.candidate_hash,source.incumbent_hash)!=(promotion.candidate_hash,promotion.incumbent_hash): return 'INCOMPLETE','Source/promotion identity mismatch'
    if (challenge.candidate_hash,challenge.incumbent_hash)!=(promotion.candidate_hash,promotion.incumbent_hash): return 'INCOMPLETE','Challenge identity mismatch'
    if not paired_complete(source,3) or not paired_complete(promotion,18): return 'INCOMPLETE','Incomplete valid triggered repeated evidence'
    if challenge.status!='PASSED_OBSERVED' or challenge.source_validation_ref!=source.batch_id: return ('REJECTED' if challenge.status=='COUNTEREXAMPLE_FOUND' else 'INCOMPLETE'),'Required matching challenge did not pass'
    def arms(batch):
        lookup={t.episode_id:t for t in batch.trials}
        return [lookup[a] for a,b in batch.trial_pairs],[lookup[b] for a,b in batch.trial_pairs]
    si,sc=arms(source); pi,pc=arms(promotion)
    if not all(target_invariant in t.failed_checks for t in si): return 'INCOMPLETE','Incumbent source no longer reproduces 3/3'
    if any(t.failed_checks or t.outcome=='VIOLATION' for t in sc+pc): return 'REJECTED','Candidate invariant violation'
    if any(t.scenario_hash in healthy_hashes and t.outcome!='COMPLETED' for t in pc): return 'REJECTED','Healthy trial completion not preserved'
    old_completed=sum(t.outcome=='COMPLETED' for t in pi); new_completed=sum(t.outcome=='COMPLETED' for t in pc)
    old_bad=sum(t.outcome=='VIOLATION' for t in pi); new_bad=sum(t.outcome=='VIOLATION' for t in pc)
    if new_completed<old_completed or new_bad>old_bad: return 'REJECTED','Aggregate regression'
    gain=new_bad<old_bad or new_completed>old_completed or (new_completed==old_completed and new_bad==old_bad and sum(t.usage.http_attempts for t in pc)<sum(t.usage.http_attempts for t in pi))
    return ('ACCEPTED','Strict observed promotion gain') if gain else ('NO_CHANGE','No strict observed promotion gain')


def commit_promotion(store,policies,campaign,candidate,decision,reason,*,evaluation_ref):
    decision_id=new_id('decision')
    record={'decision_id':decision_id,'campaign_id':campaign.campaign_id,'candidate_version':candidate.version,'expected_parent':candidate.parent_version,'decision':decision,'reason':reason,'evaluation_ref':evaluation_ref}
    # Policy decision and pointer update are one short transaction.
    with store.transaction() as db:
        row=db.execute('SELECT value FROM pointers WHERE name=?',(f'active-policy:{campaign.campaign_id}',)).fetchone()
        if row is None or row['value']!=candidate.parent_version: raise StoreConflict('Stale expected parent')
        candidate.decision=decision; candidate.decision_ref=decision_id; candidate.evaluation_refs.append(evaluation_ref)
        db.execute('UPDATE records SET payload=? WHERE kind=? AND id=?',(canonical_json(candidate),'policies',candidate.version))
        db.execute('INSERT INTO records(kind,id,payload,immutable) VALUES(?,?,?,1)',('promotion_decisions',decision_id,canonical_json(record)))
        if decision=='ACCEPTED':
            db.execute('UPDATE pointers SET value=? WHERE name=?',(candidate.version,f'active-policy:{campaign.campaign_id}'))
            db.execute('INSERT INTO pointers(name,value) VALUES(?,?) ON CONFLICT(name) DO UPDATE SET value=excluded.value',(f'accepted-policy:{campaign.configuration_hash}',candidate.version))
            campaign.active_policy_version=candidate.version
            db.execute('UPDATE records SET payload=? WHERE kind=? AND id=?',(canonical_json(campaign),'campaigns',campaign.campaign_id))
    return record
