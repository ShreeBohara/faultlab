import json
from pathlib import Path
import pytest
from pydantic import TypeAdapter, ValidationError
from app.contracts import models as m


def test_actor_authority_and_exact_report():
    adapter = TypeAdapter(m.ActorAction)
    assert adapter.validate_python({'kind':'tool','tool':'get_order','arguments':{}}).tool == 'get_order'
    for data in [
        {'kind':'tool','tool':'get_order','arguments':{'order_id':'other'}},
        {'kind':'tool','tool':'shell','arguments':{}},
        {'kind':'tool','tool':'update_order','arguments':{'desired_shipping':'standard'}},
        {'kind':'report','report':{'overall':'COMPLETED'}},
    ]:
        with pytest.raises(ValidationError): adapter.validate_python(data)
    assert set(m.TaskReport.model_fields) == {'upgrade_outcome','notification_outcome','overall','evidence_ids','next_action'}


def test_policy_grammar_and_bounds():
    base={'scope':m.SCOPE,'parent_version':'policy-v0','rules':[]}
    m.RecoveryPolicy.model_validate(base)
    with pytest.raises(ValidationError):m.CandidatePolicy.model_validate(base)
    rule={'hook':'before_confirmation','when':'always','steps':[{'op':'retry_original_request','service':'notifications'}]}
    with pytest.raises(ValidationError):m.RecoveryPolicy.model_validate({**base,'rules':[rule]})
    rule['hook']='after_notification_response'
    m.RecoveryPolicy.model_validate({**base,'rules':[rule]})
    for step in [{'op':'shell','command':'anything'},{'op':'wait_ticks','ticks':5},{'op':'read_order','order_id':'hidden'},{'op':'wait_ticks','ticks':True}]:
        with pytest.raises(ValidationError):m.PolicyRule.model_validate({**rule,'steps':[step]})


def test_context_and_export_bounds():
    p=dict(campaign_id='c1',episode_id='e1',origin='prototype',split='development',arm='B0',source_mode='offline_fixture',experiment_purpose='discovery',trial_index=0,study_id='c1',evidence_context_id='c1',execution_epoch=0)
    m.Provenance.model_validate(p)
    with pytest.raises(ValidationError):m.Provenance.model_validate({**p,'split':'final_audit'})
    with pytest.raises(ValidationError):m.Provenance.model_validate({**p,'selector_id':'systematic'})
    for path in ['../x','/x','foo/../../x','https://host/x','a\\b','a//b']:
        with pytest.raises(ValidationError):m.FileEntry(path=path,sha256='0'*64,size_bytes=0)
    with pytest.raises(ValidationError):m.FaultSpec(seed=-1,primitives=[])
    assert m.content_hash({'b':2,'a':1})==m.content_hash({'a':1,'b':2})
    with pytest.raises(ValueError):m.content_hash({'x':float('nan')})


def test_export_parity():
    root=Path(__file__).resolve().parents[3]/'contracts'
    manifest=json.loads((root/'manifest.json').read_text())
    for name,entry in manifest['schemas'].items():
        schema=json.loads((root/entry['file']).read_text())
        model=getattr(m,name)
        assert schema==model.model_json_schema()
        assert m.content_hash(schema)==entry['sha256']


def test_report_next_action_bindings_and_evidence_lists():
    report=dict(upgrade_outcome='UNKNOWN',notification_outcome='NOT_STARTED',overall='SAFE_UNRESOLVED',evidence_ids=[],next_action={'kind':'ESCALATE'})
    for next_action in [{'kind':'NONE','operation_id':'x'},{'kind':'CHECK_EXISTING_UPGRADE'},{'kind':'CHECK_EXISTING_UPGRADE','operation_id':'../../private'}]:
        with pytest.raises(ValidationError):m.TaskReport.model_validate({**report,'next_action':next_action})
    with pytest.raises(ValidationError):m.TaskReport.model_validate({**report,'evidence_ids':['x']*19})
    with pytest.raises(ValidationError):m.TaskReport.model_validate({**report,'overall':'FAILED'})


def test_fault_kind_target_parameters_and_no_unknown_fields():
    spec=dict(schema_version=m.VERSION,scope=m.SCOPE,seed=1,primitives=[])
    primitive=dict(kind='F1',target_tool='update_order',target_service='orders',occurrence=1,parameters={'response_delay_ms':1500})
    m.FaultSpec.model_validate({**spec,'primitives':[primitive]})
    for p in [{**primitive,'target_service':'notifications'},{**primitive,'target_tool':'get_order'},{**primitive,'parameters':{'response_delay_ms':1000}},{**primitive,'occurrence':19},{**primitive,'hidden_recipe':'x'}]:
        with pytest.raises(ValidationError):m.FaultSpec.model_validate({**spec,'primitives':[p]})
    with pytest.raises(ValidationError):m.ExplorerOutput(fault_spec=m.FaultSpec(**spec),hypothesis='empty')
    with pytest.raises(ValidationError):m.F2Parameters(completion_delay_ticks=1,terminal_status='SUCCEEDED',failure_code='UPGRADE_REJECTED')


def test_rule_and_step_maximums():
    step={'op':'read_order'}
    rule=dict(hook='before_final_report',when='always',steps=[step]*8)
    m.PolicyRule.model_validate(rule)
    with pytest.raises(ValidationError):m.PolicyRule.model_validate({**rule,'steps':[step]*9})
    with pytest.raises(ValidationError):m.RecoveryPolicy(parent_version='p0',rules=[m.PolicyRule(**rule)]*9)


def test_utc_timestamps_and_incomplete_challenge_rejection():
    from datetime import datetime,timezone,timedelta
    values=dict(episode_id='e1',seq=1,tick=0,role='coordinator',type='episode_started',visibility='PUBLIC_OBSERVATION')
    with pytest.raises(ValidationError):m.Event(**values,at=datetime(2026,9,12))
    with pytest.raises(ValidationError):m.Event(**values,at=datetime(2026,9,12,tzinfo=timezone(timedelta(hours=2))))
    m.Event(**values,at=datetime(2026,9,12,tzinfo=timezone.utc))
    with pytest.raises(ValidationError):m.ChallengeResult(challenge_id='ch1',candidate_hash='0'*64,incumbent_hash='1'*64,source_validation_ref='s1',schedule_hashes=[],selection_refs=[],novel_schedule_hashes=[],trial_pairs=[],failed_checks=[],status='PASSED_OBSERVED',stopping_reason='missing')


def test_fresh_mode_requires_action_and_playback_is_zero_effect():
    values=dict(execution_id='x1',bundle_id='b1',manifest_hash='0'*64,registration_id='a1',profile_id='offline-v1',mode='VALIDATE_ONLY',explicit_action=False,policy_hash='1'*64,configuration_hash='2'*64,declared_budget=m.EpisodeBudget(),usage=m.Usage(),episode_ids=[],world_ids=[],status='COMPLETED')
    m.RegressionExecution(**values)
    with pytest.raises(ValidationError):m.RegressionExecution(**{**values,'mode':'FRESH_SANDBOX'})
    with pytest.raises(ValidationError):m.RegressionExecution(**{**values,'episode_ids':['e1']})
    with pytest.raises(ValidationError):m.RegressionExecution(**{**values,'usage':m.Usage(http_attempts=1)})
