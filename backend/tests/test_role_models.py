"""Optional separate lab model for Explorer/Mechanic; the actor keeps the frozen campaign model."""
from dataclasses import replace
from types import SimpleNamespace

import pytest

from app.config import Settings, ConfigurationError
from app.contracts.models import CampaignBudget, FaultSpec, canonical_json
from app.lab.budgets import CampaignLedger
from app.lab.storage import LabStore
from app.providers.runtime import RuntimeProvider, RuntimeGeneration, RuntimeProviderError
from pydantic import ValidationError


@pytest.fixture
def anyio_backend(): return 'asyncio'


def priced(**overrides):
    base=Settings(wandb_api_key='fixture',wandb_entity='team',wandb_project='p',wandb_model='deepseek-ai/DeepSeek-V3.1',
        faultlab_live_enabled=True,faultlab_confirmed_entity='team',faultlab_pricing_model='deepseek-ai/DeepSeek-V3.1',
        faultlab_input_dollars_per_million=.55,faultlab_output_dollars_per_million=1.65,faultlab_pricing_verified=True)
    return replace(base,**overrides)


def test_lab_model_routes_roles_and_raises_the_per_call_bound_to_the_dearest_model():
    settings=priced(faultlab_lab_model='deepseek-ai/DeepSeek-V4-Pro-0813',faultlab_lab_pricing_model='deepseek-ai/DeepSeek-V4-Pro-0813',
                    faultlab_lab_input_dollars_per_million=1.31,faultlab_lab_output_dollars_per_million=3.96)
    assert settings.model_for('actor')=='deepseek-ai/DeepSeek-V3.1'
    assert settings.model_for('explorer')==settings.model_for('mechanic')=='deepseek-ai/DeepSeek-V4-Pro-0813'
    assert settings.model_call_dollar_bound==pytest.approx(.04984)
    settings.require_live()
    assert priced().model_for('explorer')=='deepseek-ai/DeepSeek-V3.1' and priced().model_call_dollar_bound==pytest.approx(.0209)
    unpriced=replace(settings,faultlab_lab_pricing_model='other')
    assert unpriced.model_call_dollar_bound is None
    with pytest.raises(ConfigurationError): unpriced.require_live()
    with pytest.raises(ConfigurationError): replace(settings,faultlab_lab_input_dollars_per_million=-1.0).require_live()


def test_campaign_dollar_ceiling_is_500():
    replace(priced(),faultlab_dollar_cap=400.0).require_live()
    with pytest.raises(ConfigurationError): replace(priced(),faultlab_dollar_cap=600.0).require_live()
    assert CampaignBudget(dollars=400.0).dollars==400.0
    with pytest.raises(ValidationError): CampaignBudget(dollars=600.0)


@pytest.mark.anyio
async def test_runtime_provider_sends_each_role_to_its_frozen_model():
    seen=[]
    async def create(**kwargs):
        seen.append(kwargs['model'])
        return SimpleNamespace(usage=SimpleNamespace(prompt_tokens=10,completion_tokens=2),choices=[SimpleNamespace(finish_reason='stop',message=SimpleNamespace(content='{"ok":true}'))])
    settings=priced(faultlab_lab_model='deepseek-ai/DeepSeek-V4-Pro-0813',faultlab_lab_pricing_model='deepseek-ai/DeepSeek-V4-Pro-0813',
                    faultlab_lab_input_dollars_per_million=1.31,faultlab_lab_output_dollars_per_million=3.96)
    provider=RuntimeProvider(settings,live_authorized=True,client_factory=lambda **_: SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create))))
    messages=[{'role':'user','content':'{}'}]
    actor=await provider.complete(messages,role='actor'); explorer=await provider.complete(messages,role='explorer'); mechanic=await provider.complete(messages,role='mechanic')
    assert seen==['deepseek-ai/DeepSeek-V3.1','deepseek-ai/DeepSeek-V4-Pro-0813','deepseek-ai/DeepSeek-V4-Pro-0813']
    assert (actor.model_id,explorer.model_id,mechanic.model_id)==tuple(seen)
    assert provider.role_model('explorer')=='deepseek-ai/DeepSeek-V4-Pro-0813' and provider.role_model('actor')=='deepseek-ai/DeepSeek-V3.1'


class RoleProvider:
    def __init__(self,answers,models): self.answers=list(answers); self.models=models; self.messages=[]
    def role_model(self,role): return self.models.get(role,self.models['actor'])
    async def complete(self,messages,*,role,max_output_tokens=2000,timeout_seconds=20):
        self.messages.append(messages)
        return RuntimeGeneration(content=self.answers.pop(0),model_id=self.role_model(role),input_tokens=5,output_tokens=1)


@pytest.mark.anyio
async def test_explorer_and_mechanic_accept_their_lab_model_and_reject_a_swapped_one(tmp_path):
    from app.agents.explorer import Explorer
    from app.agents.mechanic import Mechanic
    recipe=FaultSpec.model_validate({'seed':1,'primitives':[{'kind':'F2','target_tool':'update_order','target_service':'orders','occurrence':1,'parameters':{'completion_delay_ticks':5,'terminal_status':'SUCCEEDED','failure_code':None}}]})
    selection=canonical_json({'fault_spec':recipe.model_dump(mode='json'),'hypothesis':'Delayed completion may exhaust polling'})
    diagnosis=canonical_json({'proposed_kind':'POLICY_GAP','hypothesis':'h','evidence_ids':['evidence-a'],'requested_intervention_id':'intervention-a'})
    models={'actor':'actor-model','explorer':'lab-model','mechanic':'lab-model'}
    store=LabStore(tmp_path/'lab.db'); ledger=CampaignLedger(store,'c')
    explorer=Explorer(RoleProvider([selection],models),store,ledger); explorer.metadata={'model_id':'actor-model'}
    ref,parsed=await explorer.select({'campaign_id':'c','selection_index':0})
    assert parsed is not None and store.get_record('selections',ref)['model_id']=='lab-model'
    mechanic=Mechanic(RoleProvider([diagnosis],models),store,ledger); mechanic.metadata={'model_id':'actor-model'}
    _,proposal,_=await mechanic.diagnose({'evidence_ids':['evidence-a'],'intervention_ids':['intervention-a']})
    assert proposal is not None and proposal.requested_intervention_id=='intervention-a'
    swapped=Explorer(RoleProvider([selection],{'actor':'actor-model','explorer':'lab-model'}),store,ledger); swapped.metadata={'model_id':'actor-model'}
    swapped.provider.role_model=lambda role: 'lab-model'
    swapped.provider.complete=(lambda p: (lambda messages,*,role,**_: _wrong(p,messages)))(swapped.provider)
    async def _wrong(p,messages): return RuntimeGeneration(content=selection,model_id='actor-model',input_tokens=5,output_tokens=1)
    with pytest.raises(RuntimeProviderError): await swapped.select({'campaign_id':'c','selection_index':1})
