from app.contracts.models import content_hash

def test_diagnostic_profiles_separate_contract_and_inventory():
    from app.simulator.capabilities import diagnostic_profile,PROFILE_HASHES,PROBES
    profile=diagnostic_profile()
    assert profile.excluded_from_learning and profile.horizon==10 and len(PROBES)==10
    assert PROFILE_HASHES['evidence_gap_v1']['contract_hash']!=PROFILE_HASHES['available_status_v1']['contract_hash']
    assert set(profile.probe_set)=={'original_upgrade_write','upgrade_status','order_projection','identical_upgrade_replay'}

def test_diagnostic_control_is_private_and_cannot_be_regular_fixture(make_world,intent):
    c,w,h=make_world()
    body={'episode_id':'diagnostic-ep','intent':intent.model_dump(mode='json'),'profile_id':'evidence_gap_v1','committed':True}
    assert c.post('/control/diagnostics/worlds',json=body).status_code==403
    r=c.post('/control/diagnostics/worlds',json=body,headers={'X-FaultLab-Control':'test-control'})
    assert r.status_code==201
    standard=c.post('/control/worlds',json={'episode_id':'regular','intent':intent.model_dump(mode='json'),'fault_spec':{'seed':0,'primitives':[]},'fixture_id':'evidence_gap_v1'},headers={'X-FaultLab-Control':'test-control'})
    assert standard.status_code==422
