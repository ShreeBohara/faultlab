"""Public development recordings. Never export private worlds or protected trials."""
import json
from app.contracts.models import canonical_json
from app.telemetry.safety import public_json

V3_HISTORY_CLAIM_RULE=('Results of a discovery v3 campaign are history-informed. A source whose recipe matches a history row '
                       're-tries recorded evidence the Explorer was shown; report it as history-informed, never as independent '
                       'discovery, and name the store and the frozen summary hash.')
V4_HISTORY_CLAIM_RULE=('Results of a discovery v4 campaign are history-informed. A source found in a history replay slot is a '
                       'history replay of that row (discovery_history_replays); any other source whose recipe matches a history '
                       'row re-tries recorded evidence the Explorer was shown. Report each as such, never as independent '
                       'discovery, and name the store and the frozen summary hash.')


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
    fields=('selection_id','raw','model_id','challenge','valid','error','provenance','output','selected_output','search_decision','usage','transport_retries','matches_history_row','history_replay','challenge_reach','fireability')
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
        # Charged Explorer/Mechanic blind retries (Actor retries are actor_transport_retry episode events).
        'transport_retries':[r for r in store.list_records('transport_retries') if r.get('campaign_id')==campaign_id],
        # Telemetry-only evidence retries (manual and declared automatic) and the evidence waits they served.
        'evidence_retries':[r for r in store.list_records('evidence_retries') if r.get('campaign_id')==campaign_id],
        'evidence_waits':[w for w in store.list_records('evidence_waits') if w.get('campaign_id')==campaign_id],
        'sponsor_publication_deferrals':[e for e in store.list_records('sponsor_publication_deferrals') if e.get('campaign_id')==campaign_id],
        'source_validation_results':[e for e in store.list_records('source_validation_results') if e.get('campaign_id')==campaign_id],
        'candidate_qualifications':[e for e in store.list_records('candidate_qualifications') if e.get('campaign_id')==campaign_id],
        'completion_studies':[e for e in store.list_records('completion_studies') if e.get('campaign_id')==campaign_id
            and {row['trial']['episode_id'] for row in e['trial_rows']}<=selected],
        'context_studies':[e for e in store.list_records('context_studies') if e.get('campaign_id')==campaign_id
            and {row['trial']['episode_id'] for row in e['trial_rows']}<=selected],
        'completeness_notes':['Only public development evidence is included; protected evaluation records and private world state are excluded.',
            'Legacy raw outputs without campaign, policy or intervention ownership cannot be attributed and are excluded.']}
    declared=(saved_plan or {}).get('plan') or {}
    if declared.get('mechanic_context') is not None:
        # faultlab-mechanic-context/v2-bounded: every compaction and every search it ended (older recordings keep their exact keys).
        from app.lab.loop_limits import campaign_mechanic_context
        result['mechanic_context_records']=campaign_mechanic_context(store,campaign_id)
    if declared.get('challenge_selection') is not None:
        # faultlab-challenge-selection/v2-candidate-reach: each challenge pick's decision is on its selection (challenge_reach).
        from app.lab.loop_limits import CHALLENGE_REACH_RULE
        result['challenge_selection_rule']={'protocol':declared['challenge_selection']['protocol'],'rule':CHALLENGE_REACH_RULE,
            'refused_selection_ids':[s['selection_id'] for s in selections if (s.get('challenge_reach') or {}).get('status')=='REFUSED_UNREACHED']}
    if declared.get('mechanic_diagnosis') is not None:
        # faultlab-mechanic-diagnosis/v1-repair-and-record: every diagnosis's record (why an intervention did or did not
        # run), with every Mechanic attempt embedded by its id, including a first attempt that shares its request id with
        # a later one (mechanic_outputs above keeps its exact rule; older recordings keep their exact keys).
        from app.lab.diagnosis_protocol import campaign_records
        result['diagnosis_requests']=campaign_records(store,campaign_id)
    if declared.get('explorer_selection') is not None:
        # faultlab-explorer-selection/v3-history-fireability: the frozen table (in run_plan), every pick decision (also on
        # its selection, field fireability) and any discovery slot left without a request (older recordings keep their keys).
        from app.lab.fireability import RULE as FIREABILITY_RULE,campaign_summary
        result['explorer_selection_rule']={'rule':FIREABILITY_RULE,**campaign_summary(store,campaign_id,declared['explorer_selection'])}
    history=(((saved_plan or {}).get('plan') or {}).get('discovery') or {}).get('history')
    if history is not None:
        # Discovery v3: which reproduced sources re-try a recipe row the Explorer was shown (derived from the
        # frozen summary; each v3 selection also carries its own matches_history_row).
        from app.lab.agent_history import MATCH_BASIS,history_row_match
        sources=[]
        for counter in counters:
            recipe=(store.get_record('counterexample_recipes',counter['counterexample_id']) or {}).get('source_recipe')
            sources.append({'counterexample_id':counter['counterexample_id'],'source_episode_id':counter.get('source_episode_id'),
                            'reproduced':counter.get('reproduced'),'source_recipe_recorded':recipe is not None,
                            'matches_history_row':history_row_match(history['summary'],recipe) if recipe is not None else None})
        replay=(((saved_plan or {}).get('plan') or {}).get('discovery') or {}).get('replay')
        result['discovery_history_matches']={'summary_hash':history['summary_hash'],'record_cutoff':history['record_cutoff'],
            'basis':MATCH_BASIS,'sources':sources,
            # A v3 recording keeps its exact text; a v4 recording names v4 (review finding F4, September 30).
            'claim_rule':V3_HISTORY_CLAIM_RULE if replay is None else V4_HISTORY_CLAIM_RULE}
        if replay is not None:
            # Discovery v4 only: the frozen replay list, the replay slots that ran, and which sources they found.
            from app.lab import history_replay
            replayed=history_replay.campaign_replays(store,campaign_id)
            for source in sources:
                source['history_replay']=replayed.get(source['source_episode_id'])
            result['discovery_history_replays']={'label':history_replay.LABEL,'status':replay['status'],
                'statement':replay['statement'],'rule':replay['rule'],'summary_hash':history['summary_hash'],
                'replay_list':replay['rows'],'replay_slots':sorted(replayed.values(),key=lambda block:block['replay']),
                'sources_found_by_replay':[source['counterexample_id'] for source in sources if source['history_replay']],
                'claim_rule':history_replay.CLAIM_RULE}
    imported=store.get_record('import_execution_owners',campaign_id)
    if imported:
        target=imported['target']
        result.update(imported_execution={key:imported[key] for key in
            ('import_id','request_id','execution_id','regression_id','target','role','policy_activation')},
            campaign_role='regression_budget_owner',
            target_configuration=store.get_record('configurations',target['configuration_hash']),
            target_agent_registration=store.get_record('agent_registrations',target['agent_registration_id']),
            policy_import_provenance={p['version']:store.get_record('policy_imports',p['version'])
                for p in policies if store.get_record('policy_imports',p['version'])})
        result['completeness_notes'].append('The campaign is an accounting owner; imported_execution identifies the actual fresh target. Imported policy decisions and source evidence remain historical, without local acceptance or source verification.')
    # Convert nested validated models first, then reject secret/private keys and
    # literal configured credentials. Never redact an original report silently.
    return public_json(json.loads(canonical_json(result)),secrets=secrets,max_bytes=64*1024*1024)
