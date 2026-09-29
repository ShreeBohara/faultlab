# Appended by the fixer to backend/tests/lab/test_native_adapter_v2_product.py (lines 315-end); nothing else in that file changed.

@pytest.mark.anyio
@pytest.mark.parametrize('agent', ['smolagents', 'smolagents-v2'])
async def test_start_after_a_runtime_change_names_the_next_step_and_keeps_the_plan_readable(tmp_path, monkeypatch, agent):
    """Review finding L4. A runtime change (adapter v2 moved v1's adapter hash by changing registry.py) makes every
    idle plan saved before it unstartable. The refusal says what to do next, and the saved plan still reads."""
    c = await runtime(tmp_path)
    try:
        idle = planned_campaign(c) if agent == 'smolagents' else planned_v2(c)[0]
        real_digest = registry_module.digest
        monkeypatch.setattr(registry_module, 'digest',
                            lambda path: 'f' * 64 if Path(path).name == 'registry.py' else real_digest(path))
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=create_app(coordinator=c)), base_url='http://test') as api:
            started = await api.post(f'/api/campaigns/{idle.campaign_id}/start', json={})
            saved = await api.get(f'/api/campaigns/{idle.campaign_id}/plan')
        assert started.status_code == 409, started.text
        assert started.json()['error']['message'] == ('Current source, model or campaign limits differ from the saved plan. '
                                                      'Register the agent again and create a new campaign; this saved plan stays readable')
        assert saved.status_code == 200 and saved.json()['status'] == 'PLANNED'
        assert c.store.get_model('campaigns', idle.campaign_id, type(idle)).state == 'IDLE'
        assert sum(c.runner.provider.calls.values()) == 0
    finally:
        await c.close()
