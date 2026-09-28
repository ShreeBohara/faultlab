"""Public development recordings. Never export private worlds or protected trials."""
import json
from app.contracts.models import canonical_json
from app.telemetry.safety import public_json


def episode_events(store, episode_id):
    events=[]; after=0
    while True:
        page=store.events(episode_id,after=after,limit=200)
        events.extend(page['events'])
        if not page['has_more']: return events
        if page['next_after']<=after: raise ValueError('Stored event cursor did not advance')
        after=page['next_after']


def development_recording(store,campaign_id,*,episode_ids=None,secrets=()):
    campaign=store.get_record('campaigns',campaign_id)
    from app.lab.run_plans import read_run_plan
    saved_plan=read_run_plan(store,campaign_id) if campaign else None
    binding=store.get_record('campaign_registrations',campaign_id)
    all_episodes=[e for e in store.list_records('episodes') if e.get('campaign_id')==campaign_id and e.get('split')=='development']
    allowed={e['episode_id'] for e in all_episodes}
    selected=allowed if episode_ids is None else allowed.intersection(episode_ids)
    episodes=[e for e in all_episodes if e['episode_id'] in selected]
    owned=[p for p in store.list_records('campaign_proposals') if p.get('campaign_id')==campaign_id]
    versions={e['policy_version'] for e in episodes}
    versions.update(p.get('candidate_version') for p in owned if p.get('candidate_version'))
    if campaign: versions.update((campaign['active_policy_version'],'policy-v0'))
    policies=store.list_records('policies')
    versions.update(p['version'] for p in policies if allowed.intersection(p.get('development_episode_ids',[])))
    # Preserve parents and rejected candidates, without pulling unrelated campaigns.
    while True:
        parents={p.get('parent_version') for p in policies if p['version'] in versions and p.get('parent_version')}
        if parents<=versions: break
        versions.update(parents)
    policies=[p for p in policies if p['version'] in versions]
    proposals=[]
    for policy in policies:
        ref=policy.get('raw_proposal_ref')
        if ref:
            raw=store.get_record('proposals',ref)
            if raw is not None: proposals.append({'proposal_ref':ref,'policy_version':policy['version'],**raw})
    counters=[c for c in store.list_records('counterexamples') if c.get('campaign_id')==campaign_id]
    counter_ids={c['counterexample_id'] for c in counters}
    diagnostics=[d for d in store.list_records('diagnostics') if d.get('counterexample_id') in counter_ids]
    interventions=[i for i in store.list_records('interventions') if i.get('counterexample_id') in counter_ids]
    mechanic_refs={i.get('proposal_ref') for i in interventions}
    mechanic=[]
    for ref in sorted(mechanic_refs-{None}):
        value=store.get_record('mechanic_outputs',ref)
        if value is not None: mechanic.append({'proposal_ref':ref,**value})
    known={p.get('request_id') for p in mechanic}
    mechanic.extend(m for m in store.list_records('mechanic_outputs') if m.get('campaign_id')==campaign_id and (not m.get('request_id') or m['request_id'] not in known))
    selections=[]
    fields=('selection_id','raw','model_id','challenge','valid','error','provenance','output','selected_output','search_decision','usage')
    for selection in store.list_records('selections'):
        if selection.get('context',{}).get('campaign_id')==campaign_id:
            selections.append({k:selection[k] for k in fields if k in selection})
    challenge_ids={c['challenge_id'] for c in store.list_records('challenge_campaigns') if c.get('campaign_id')==campaign_id}
    challenges=[c for c in store.list_records('challenges') if c.get('challenge_id') in challenge_ids]
    result={'recording_version':'faultlab-development-recording/v1','campaign_id':campaign_id,
        'campaign':campaign,
        'configuration':store.get_record('configurations',campaign['configuration_hash']) if campaign else None,
        'run_plan':saved_plan,
        'agent_registration':store.get_record('agent_registrations',binding['registration_id']) if binding else None,
        'episodes':episodes,'events':{e['episode_id']:episode_events(store,e['episode_id']) for e in episodes},
        'observations':[o for o in store.list_records('observations') if o.get('episode_id') in selected],
        'policies':policies,'proposals':proposals,'campaign_proposals':owned,'mechanic_outputs':mechanic,
        'selections':selections,'diagnostics':diagnostics,'interventions':interventions,'challenges':challenges,
        'campaign_provenance':store.get_record('campaign_provenance',campaign_id),
        'execution_errors':[e for e in store.list_records('execution_errors') if e.get('campaign_id')==campaign_id],
        'sponsor_publication_deferrals':[e for e in store.list_records('sponsor_publication_deferrals') if e.get('campaign_id')==campaign_id],
        'source_validation_results':[e for e in store.list_records('source_validation_results') if e.get('campaign_id')==campaign_id],
        'candidate_qualifications':[e for e in store.list_records('candidate_qualifications') if e.get('campaign_id')==campaign_id],
        'completion_studies':[e for e in store.list_records('completion_studies') if e.get('campaign_id')==campaign_id
            and {row['trial']['episode_id'] for row in e['trial_rows']}<=selected],
        'context_studies':[e for e in store.list_records('context_studies') if e.get('campaign_id')==campaign_id
            and {row['trial']['episode_id'] for row in e['trial_rows']}<=selected],
        'completeness_notes':['Only public development evidence is included; protected evaluation records and private world state are excluded.',
            'Legacy raw outputs without campaign, policy or intervention ownership cannot be attributed and are excluded.']}
    # Convert nested validated models first, then reject secret/private keys and
    # literal configured credentials. Never redact an original report silently.
    return public_json(json.loads(canonical_json(result)),secrets=secrets,max_bytes=64*1024*1024)
