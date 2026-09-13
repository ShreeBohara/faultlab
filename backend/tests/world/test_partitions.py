from pathlib import Path
from app.contracts.models import FaultSpec

def test_frozen_partition_counts_hashes_and_isolation():
    from app.referee.manifests import load_manifest,manifest_hash
    seen=set()
    for split,count in [('development',6),('promotion',6),('final-audit',8)]:
        m=load_manifest(split)
        assert len(m['cases'])==count and m['trials_per_case']==3
        assert manifest_hash(m)==m['manifest_hash']
        for case in m['cases']:
            assert case['case_id'] not in seen;seen.add(case['case_id'])
            assert case['fixture_id'] in ('standard-v1','history-v1')
            spec=FaultSpec.model_validate(case['fault_spec'])
            assert len(spec.primitives)<=2
    audit=load_manifest('final-audit')
    assert audit['access']=='PRIVATE_EVALUATOR'
    assert any(len(c['fault_spec']['primitives'])==2 for c in audit['cases'])
    assert any(p['kind']=='F4' and p['parameters']['failure_count']==18 for c in audit['cases'] for p in c['fault_spec']['primitives'])
