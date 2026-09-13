def test_external_case_definitions_can_freeze_with_source_pending():
    from app.referee.manifests import load_manifest
    m=load_manifest('portability')
    assert len(m['cases'])==6 and m['trials_per_case']==3 and m['arms']==['B0','L']
    assert m['external_identity']['status']=='PENDING' and not m['execution_authorized']

def test_selector_comparison_is_precommitted_and_equal():
    from app.referee.manifests import load_manifest
    m=load_manifest('search-comparison');development=load_manifest('development')
    assert m['selections_per_arm']==8 and m['trials_per_selection']==3
    assert m['development_manifest_hash']==development['manifest_hash']
    assert len(m['systematic_order'])==8 and set(m['selector_order'])=={'explorer','systematic'}
    assert m['deduplication']=='lowest_failed_invariant+canonical_fault_family'
