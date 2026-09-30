"""Integrity reviewer probe (discovery v4 review, $0, offline): old protocols byte-for-byte across trees.

Copied into <tree>/backend/tests/lab/ of two scratch trees (outside the Desktop):
  checkpoint = git archive of backup/part2-2026-09-22 (4d1c21b, runtime 4553ebe7), no v4;
  current    = checkpoint + the 16 changed and 6 added files of the working tree (runtime 2a181539).
For v1, v2, v3-history and v3-history-reachability it records, normalized (ids and digests replaced by placeholders
numbered by first appearance): every Explorer message, every selection record, the recipes the fake runner ran, the
saved plan's discovery block, the run-options declarations, the search-attempts and experiments API responses and the
recording's selections / discovery_history_matches. Output: JSON at $REVIEW_OUT. The two trees' outputs must be equal.
Scripted Explorer and fake runner of test_discovery_v2_flow (fixture text, not model evidence). No network.
"""
import asyncio
import json
import os
import re

import httpx

import test_discovery_v2_flow as flow
from app.contracts.models import Counterexample, canonical_json, content_hash, new_id
from app.lab.discovery_protocol import DISCOVERY_V1, DISCOVERY_V2, DISCOVERY_V3, DISCOVERY_V3_PRECHECK
from app.lab.exports import development_recording
from app.lab.operator_actions import register_agent
from app.lab.run_plans import build_run_options, read_run_plan
from test_agent_history import Seeder, seed_screen
from test_discovery_v3_flow import Recording, c701, complete_fixture_episodes

owner = flow.owner
anyio_backend = flow.anyio_backend
IDS = re.compile(r'[a-z][a-z_]*-[0-9a-f]{32}|[0-9a-f]{64}|\b[0-9a-f]{12}\b')


def norm(value, mapping):
    text = value if isinstance(value, str) else canonical_json(value)
    return IDS.sub(lambda m: mapping.setdefault(m.group(0), f'<ID{len(mapping)}>'), text)


def sources_hook(owner, monkeypatch):
    async def source(self, current, trial, recipe, incumbent, **kwargs):
        counter = Counterexample(counterexample_id=new_id('counterexample'), campaign_id=current.campaign_id,
                                 agent_registration_id=read_run_plan(owner.store, current.campaign_id)['plan']['agent_registration_id'],
                                 source_episode_id=trial.episode_id, target_invariant='C3', scenario_hash=content_hash(recipe),
                                 configuration_hash=current.configuration_hash, report_ref=trial.episode_id, verdict_ref=trial.episode_id)
        owner.store.put_record('counterexamples', counter.counterexample_id, counter)
        owner.store.put_record('counterexample_recipes', counter.counterexample_id,
                               {'source_recipe': recipe.model_dump(mode='json'), 'fixture_id': 'standard-v1'}, immutable=True)
        from types import SimpleNamespace
        return SimpleNamespace(reproduced=False), []
    monkeypatch.setattr('app.lab.learning.Reproducer.source', source)


def scenario(owner, monkeypatch, protocol, agent, *, seeded, mode):
    if seeded:
        seed_screen(Seeder(owner, register_agent(owner.store, owner.settings, agent)))
    sources_hook(owner, monkeypatch)
    campaign = flow.learn_campaign(owner, protocol, agent)
    monkeypatch.setattr(flow, 'ScriptedExplorer', Recording)
    ledger, runner, selections = flow.run(owner, campaign, c701, mode=mode)
    monkeypatch.undo()
    complete_fixture_episodes(owner)
    from app.main import create_app
    async def read():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=create_app(coordinator=owner)), base_url='http://test') as api:
            return ((await api.get(f'/api/campaigns/{campaign.campaign_id}/search-attempts')).json(),
                    (await api.get(f'/api/campaigns/{campaign.campaign_id}/experiments')).json())
    attempts, experiments = asyncio.run(read())
    recording = development_recording(owner.store, campaign.campaign_id)
    mapping = {}
    ours = [row for row in selections if row['context']['campaign_id'] == campaign.campaign_id]
    plan = read_run_plan(owner.store, campaign)['plan']
    return {
        'messages': [norm(m['content'], mapping) for pair in runner.provider.messages for m in pair],
        'selections': [norm(row, mapping) for row in ours],
        'runner_recipes': [norm(call[1].model_dump(mode='json'), mapping) for call in runner.calls],
        'ledger_used_calls': ledger.used_calls,
        'plan_discovery': norm(plan['discovery'], mapping),
        'plan_keys': sorted(plan),
        'search_attempts': norm(attempts, mapping),
        'experiments_counterexamples': norm(experiments.get('counterexamples'), mapping),
        'recording_selections': norm(recording['selections'], mapping),
        'recording_history_matches': norm(recording.get('discovery_history_matches'), mapping),
        'recording_keys': sorted(recording),
        'state': owner.get(campaign.campaign_id).state,
    }


CASES = [('v1-reference', None, 'reference', False, 'tie'), ('v1-native', DISCOVERY_V1, 'smolagents', False, 'gain'),
         ('v2-reference', DISCOVERY_V2, 'reference', False, 'tie'),
         ('v3-native-seeded', DISCOVERY_V3, 'smolagents', True, 'gain'),
         ('v3-reference-seeded', DISCOVERY_V3, 'reference', True, 'tie'),
         ('v3-native-empty', DISCOVERY_V3, 'smolagents-v2', False, 'gain'),
         ('v3pre-reference-seeded', DISCOVERY_V3_PRECHECK, 'reference', True, 'gain')]


def test_record_old_protocol_bytes(tmp_path, monkeypatch):
    from app.config import Settings
    from app.lab.coordinator import LabCoordinator
    out = {}
    for name, protocol, agent, seeded, mode in CASES:
        coordinator = LabCoordinator(Settings(faultlab_artifact_dir=str(tmp_path / name), wandb_model='deepseek-ai/DeepSeek-V3.1',
                                              wandb_explorer_model=flow.EXPLORER_MODEL))
        try:
            out[name] = scenario(coordinator, monkeypatch, protocol, agent, seeded=seeded, mode=mode)
            if name == 'v1-reference':
                options = build_run_options(coordinator.settings, coordinator.store)['learn']['discovery_protocols']
                mapping = {}
                out['run_options_first_four'] = [norm(row, mapping) for row in options[:4]]
                out['run_options_ids'] = [row['protocol_id'] for row in options]
                out['run_options_default'] = [row['protocol_id'] for row in options if row['default']]
        finally:
            asyncio.run(coordinator.close())
    with open(os.environ['REVIEW_OUT'], 'w') as fh:
        json.dump(out, fh, indent=1, sort_keys=True)
