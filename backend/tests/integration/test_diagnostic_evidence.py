"""Separate labeled capability witness, excluded from learned-gain measurements."""
import json
from copy import deepcopy
import httpx
import pytest
from app.adapters.journal import allocate_intent
from app.referee.diagnostics import execute_witness,validate_gap

pytestmark=pytest.mark.localhost_http


def test_real_http_gap_witness_and_available_status_control(tmp_path,simulator_server):
    url,app=simulator_server
    control={'X-FaultLab-Control':'integration-control'}
    witnesses=[]
    with httpx.Client(base_url=url,trust_env=False) as client:
        for profile,committed in [('evidence_gap_v1',True),('evidence_gap_v1',False),('available_status_v1',True)]:
            intent=allocate_intent('order-diagnostic','Resolve the original operation without inventing a result.')
            response=client.post('/control/diagnostics/worlds',headers=control,json={'episode_id':f'diagnostic-{len(witnesses)}','intent':intent.model_dump(mode='json'),'profile_id':profile,'committed':committed})
            assert response.status_code==201,response.text
            witnesses.append(execute_witness(client,response.json(),intent,control_token='integration-control',profile_id=profile))
    result=validate_gap(witnesses[0],witnesses[1])
    assert result.kind=='CONTRACT_EVIDENCE_GAP',result
    assert result.equivalence_refs[0]==result.equivalence_refs[1]
    assert len(witnesses[0]['transcript'])==len(witnesses[1]['transcript'])==10
    assert any(row['result'].get('status')=='SUCCEEDED' for row in witnesses[2]['transcript'])
    assert validate_gap(witnesses[0],witnesses[2]).kind=='INCONCLUSIVE'
    incomplete=deepcopy(witnesses[1]);incomplete['transcript'].pop()
    assert validate_gap(witnesses[0],incomplete).kind=='INCONCLUSIVE'
    serialized=result.model_dump_json()
    assert 'capability' not in json.loads(serialized)
    assert 'world_id' not in serialized and 'private_committed' not in serialized
    summary={'source_mode':'offline_fixture','actual_http_probes':30,'model_calls':0,'witness':result.model_dump(mode='json'),'available_status_control':'distinguishing succeeded receipt observed','learning_or_search_metric':False}
    (tmp_path/'diagnostic-summary.json').write_text(json.dumps(summary,indent=2)+'\n')
