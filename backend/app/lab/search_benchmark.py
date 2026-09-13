"""Predeclared eight × three selector study with isolated histories and no repair."""
from copy import deepcopy
from app.contracts.models import SearchComparison,FaultSpec,Usage,canonical_json,content_hash,new_id
from app.lab.reproduction import reproduced,valid_trial
from app.lab.challenge import schedule_identity
from app.lab.evaluation import aggregate_usage
from app.agents.explorer import Explorer

class SearchBenchmark:
    def __init__(self,store,runner,ledger,*,evidence_gateway=None): self.store,self.runner,self.ledger,self.evidence_gateway=store,runner,ledger,evidence_gateway
    async def run(self,campaign,baseline,*,stop=lambda:False):
        from app.referee.manifests import load_manifest
        from app.referee.reducer import reducer_hash
        from app.lab.configuration import file_hash,ROOT
        manifest=load_manifest('search-comparison'); development=load_manifest('development')
        if manifest['development_manifest_hash']!=development['manifest_hash']: raise ValueError('Frozen development identity mismatch')
        if baseline.version!='policy-v0' or baseline.content.rules: raise ValueError('Selector comparison requires frozen B0 empty overlay')
        if 'selection_comparison' not in self.ledger.reservations: raise ValueError('Protected comparison reservation unavailable')
        comparison_id=new_id('comparison'); contexts=[new_id('selector-context') for _ in range(2)]
        record=SearchComparison(comparison_id=comparison_id,status='RUNNING',campaign_id=campaign.campaign_id,manifest_hash=manifest['manifest_hash'],registration_id='orders-v1',policy_hash=baseline.policy_hash,generator_hash=development['manifest_hash'],validator_hash=file_hash(ROOT/'backend/app/simulator/faults.py'),deduplication_hash=content_hash(manifest['deduplication']),selector_order=manifest['selector_order'],systematic_digest=content_hash({'order':manifest['systematic_order'],'variants':manifest['systematic_variants']}),context_ids=contexts,trial_ids=[],usage=Usage(),stopping_reason='Study running')
        self.store.put_record('search_comparisons',comparison_id,record)
        trials=[]; outcomes=[]; all_done=True
        def measured(): return {'model_calls':self.ledger.used_calls,'charged_token_upper_bound':self.ledger.used_tokens,'input_tokens':self.ledger.measured_input,'output_tokens':self.ledger.measured_output,'known_cost_dollars':self.ledger.used_cost or 0.0,'unknown_cost_calls':self.ledger.unknown_cost_calls,'unknown_token_calls':self.ledger.unknown_token_calls}
        study_start=measured(); arm_starts={}; arm_ends={}; actor_trials={'explorer':[],'systematic':[]}
        explorer=Explorer(self.runner.provider,self.store,self.ledger)
        try:
            for arm_index,selector in enumerate(manifest['selector_order']):
                arm_starts[selector]=measured()
                history=[]; seen=set(); findings=set()
                for slot in range(8):
                    from app.contracts.models import Provenance
                    planned_episode=new_id('episode')
                    provenance=Provenance(campaign_id=campaign.campaign_id,episode_id=planned_episode,origin='faultlab_evaluation',split='development',arm='B0',source_mode='live',experiment_purpose='selection_comparison',trial_index=0,study_id=comparison_id,evidence_context_id=contexts[arm_index],selector_id=selector,execution_epoch=campaign.execution_epoch)
                    config=self.store.get_record('configurations',campaign.configuration_hash)
                    explorer.trace=getattr(self.runner,'trace',None)
                    explorer.metadata={**provenance.model_dump(mode='json'),'model_id':campaign.model,'policy_hash':baseline.policy_hash,'contract_hash':config['contract_hash'],'scorer_hash':config['scorer_hash']}
                    if stop(): raise InterruptedError()
                    selected=None; selection_ref=None
                    if selector=='explorer':
                        selection_ref,proposal=await explorer.select({'campaign_id':campaign.campaign_id,'study_id':comparison_id,'evidence_context_id':contexts[arm_index],'selector_id':selector,'selection_index':slot,'own_preceding_trials':history},reservation='selection_comparison')
                        if proposal:
                            try: selected=validate_development_selection(proposal.fault_spec,development)
                            except ValueError: selected=None
                    else:
                        case=deepcopy(next(c for c in development['cases'] if c['case_id']==manifest['systematic_order'][slot]))
                        variant=manifest['systematic_variants'][slot]
                        if variant:
                            for primitive in case['fault_spec']['primitives']:
                                if variant['parameter'] in primitive['parameters']: primitive['parameters'][variant['parameter']]=variant['value']; break
                        selected=FaultSpec.model_validate_json(canonical_json(case['fault_spec']))
                    digest=schedule_identity(selected) if selected else None
                    if selected is None or digest in seen:
                        outcomes.append({'selector':selector,'slot':slot,'selection_ref':selection_ref,'status':'INVALID_OR_DUPLICATE','trial_ids':[]})
                        continue
                    seen.add(digest)
                    fixture='history-v1' if any(p.kind=='F3' for p in selected.primitives) else 'standard-v1'
                    current=[]
                    for index in range(3):
                        trial=await self.runner.run(campaign,selected,baseline,episode_id=planned_episode if index==0 else None,purpose='selection_comparison',arm='B0',trial_index=index,study_id=comparison_id,evidence_context_id=contexts[arm_index],selector_id=selector,fixture_id=fixture,ledger=self.ledger,reservation='selection_comparison',stop=stop)
                        current.append(trial); trials.append(trial); actor_trials[selector].append(trial); record.trial_ids.append(trial.episode_id)
                        self.store.put_record('search_comparisons',comparison_id,record)
                    target=sorted(current[0].failed_checks,key=lambda c:int(c[1:]))[0] if current[0].failed_checks else None
                    finding=bool(target and reproduced(current,target))
                    dedup=(target,tuple(sorted(p.kind+':'+p.target_tool+':'+p.target_service for p in selected.primitives)))
                    if finding: findings.add(dedup)
                    summary={'selector':selector,'slot':slot,'selection_ref':selection_ref,'scenario_hash':digest,'trial_ids':[t.episode_id for t in current],'status':'REPRODUCED' if finding else 'NOT_REPRODUCED','valid':sum(valid_trial(t) for t in current),'target_invariant':target,'distinct_findings':len(findings),'outcomes':[t.outcome for t in current]}
                    outcomes.append(summary)
                    # Isolated contexts contain only this selector's already completed trials.
                    if selector=='explorer' and self.evidence_gateway is None: raise ValueError('Verified selector evidence gateway is required before adaptation')
                    if selector=='explorer' and self.evidence_gateway:
                        from app.lab.evidence import EvidenceContext
                        for trial in current:
                            await self.evidence_gateway.get(trial.episode_id,EvidenceContext(campaign.campaign_id,comparison_id,contexts[arm_index],selector))
                    history.append(summary)
                arm_ends[selector]=measured()
        except Exception:
            all_done=False
        finally:
            record.status='COMPLETED' if all_done else 'INCOMPLETE'; record.usage=aggregate_usage(trials)
            end=measured(); delta={k:end[k]-study_start[k] for k in study_start}
            record.usage.model_calls=delta['model_calls']; record.usage.input_tokens=delta['input_tokens']; record.usage.output_tokens=delta['output_tokens']; record.usage.cost_dollars=delta['known_cost_dollars'] if delta['unknown_cost_calls']==0 else None
            per_selector={}
            for selector,start in arm_starts.items():
                finish=arm_ends.get(selector,end)
                per_selector[selector]={'total':{k:finish[k]-start[k] for k in start},'actor_usage':aggregate_usage(actor_trials[selector]).model_dump(mode='json'),'selection_records':[self.store.get_record('selections',row['selection_ref'])['usage'] for row in outcomes if row['selector']==selector and row.get('selection_ref') and self.store.get_record('selections',row['selection_ref']) and 'usage' in self.store.get_record('selections',row['selection_ref'])]}
            record.stopping_reason='All sixteen predeclared selection slots retained; outcomes are empirical' if all_done else 'Stopped, incomplete evidence, or exhausted declared budget'
            self.store.put_record('search_comparisons',comparison_id,record)
            self.store.put_record('search_results',comparison_id,{'comparison_id':comparison_id,'slots':outcomes,'charged_model_calls':delta['model_calls'],'charged_token_upper_bound':delta['charged_token_upper_bound'],'by_selector':per_selector,'usage_metadata_known':delta['unknown_token_calls']==0,'zero_findings_cost_per_finding':None},immutable=True)
            self.ledger.release('selection_comparison')
        return record

async def queue_search(coordinator,campaign_id):
    import asyncio
    from app.lab.budgets import CampaignLedger
    from app.lab.storage import StoreConflict
    campaign=coordinator.get(campaign_id); coordinator.settings.require_live()
    coordinator.validate_core_configuration(campaign)
    if any(r['campaign_id']==campaign_id for r in coordinator.store.list_records('search_comparisons')): raise StoreConflict('This frozen selector study already exists')
    ledger=coordinator.ledgers.setdefault(campaign_id,CampaignLedger(coordinator.store,campaign_id,campaign.caps,dollar_bound=coordinator.settings.model_call_dollar_bound))
    await coordinator.admit_activity(campaign_id)
    campaign=coordinator.get(campaign_id)
    request_id=new_id('search-request')
    async def execute():
        runner=None; owned=False
        try:
            runner,owned=await coordinator._get_runner(True)
            result=await SearchBenchmark(coordinator.store,runner,ledger,evidence_gateway=coordinator.evidence_gateway).run(campaign,coordinator.policies.baseline(),stop=lambda:coordinator.get(campaign_id).stop_requested)
            coordinator.store.put_record('search_requests',request_id,{'request_id':request_id,'comparison_id':result.comparison_id,'status':result.status})
        except Exception:
            coordinator.store.put_record('search_requests',request_id,{'request_id':request_id,'status':'INCOMPLETE'})
        finally:
            if owned and runner:
                await runner.world_client.close(); await runner.provider.close()
                if getattr(runner,'telemetry_worker',None): await runner.telemetry_worker.close()
            coordinator.active_id=None
    coordinator.tasks[request_id]=asyncio.create_task(execute())
    return {'request_id':request_id,'status':'QUEUED'}


def validate_development_selection(recipe,manifest=None):
    """Both selector arms use the same predeclared development family generator."""
    if manifest is None:
        from app.referee.manifests import load_manifest
        manifest=load_manifest('development')
    if len(recipe.primitives)!=1: raise ValueError('Selector must choose one of the fixed fault families')
    def family(p):
        return (p.kind,p.target_tool,p.target_service,getattr(p.parameters,'terminal_status',None),getattr(p.parameters,'failure_code',None))
    allowed={family(FaultSpec.model_validate_json(canonical_json(case['fault_spec'])).primitives[0]) for case in manifest['cases'] if case['fault_spec']['primitives']}
    if family(recipe.primitives[0]) not in allowed: raise ValueError('Schedule falls outside the common selector development definitions')
    return recipe
