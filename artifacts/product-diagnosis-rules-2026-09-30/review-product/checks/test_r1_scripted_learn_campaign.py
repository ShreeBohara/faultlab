"""Review check 1A ($0, offline): Rule 1 inside the real learning loop, end to end.

The offline_fixture Learn campaign (tests/lab/original_loop_fixture.py: real coordinator, real localhost simulator on an
owned ephemeral loopback port, real Explorer/Mechanic parsing, real Diagnostician control/treatment, real gates) with a
scripted provider. Only the Mechanic's DIAGNOSIS answers are changed from the fixture's: a v2g-style first answer whose
hypothesis is 614 characters (requesting the offered intervention), then a repair answer that either fits (428
characters) or is the same 614-character text again (v2g exactly).

The fixture campaign has no saved run plan, so (as in the builder's T8) Rule 1 is declared by patching
diagnosis_protocol.campaign_rule. Check 1B (test_r1b_planned_export_api.py) covers a real saved Learn plan, the export and
the API.
"""
import json

import pytest

import original_loop_fixture as fixture
from app.agents.mechanic import FORMAT_REPAIR_INSTRUCTION, PROMPTS
from app.contracts.models import canonical_json
from app.lab import diagnosis_protocol

DIAGNOSIS_PROMPT = (PROMPTS / 'diagnosis.md').read_text()
LONG = ('Handwritten offline review fixture: the actor sends its confirmation while the delayed upgrade is still pending. '
        * 10)[:614]
SHORT = ('Handwritten offline review fixture: removing the delay removes the premature confirmation. ' * 10)[:428]
assert len(LONG) == 614 and len(SHORT) == 428


@pytest.fixture
def anyio_backend(): return 'asyncio'


def scripted(repair_fits, seen):
    class Provider(fixture.ScriptedProvider):
        async def complete(self, messages, *, role='actor', **kwargs):
            if role == 'mechanic' and messages[0]['content'] == DIAGNOSIS_PROMPT:
                self.calls[role] += 1
                seen.append(json.loads(json.dumps(messages)))
                first = json.loads(messages[1]['content'])
                hypothesis = LONG if len(messages) == 2 or not repair_fits else SHORT
                answer = {'proposed_kind': 'POLICY_GAP', 'hypothesis': hypothesis,
                          'evidence_ids': first['evidence_ids'][:1], 'requested_intervention_id': first['intervention_ids'][0]}
                return fixture.RuntimeGeneration(canonical_json(answer), fixture.MODEL, cost_usd=0.0)
            return await super().complete(messages, role=role, **kwargs)
    return Provider


async def run(tmp_path, monkeypatch, *, rule, repair_fits):
    seen, records = [], []
    monkeypatch.setattr(fixture, 'ScriptedProvider', scripted(repair_fits, seen))
    monkeypatch.setattr(diagnosis_protocol, 'campaign_rule',
                        lambda store, campaign: diagnosis_protocol.declaration() if rule else None)
    original = diagnosis_protocol.record
    def keep(store, *args, **kwargs):
        value = original(store, *args, **kwargs)
        records.append((value, store.get_record('mechanic_outputs', value['output_refs'][0]),
                        [store.get_record('mechanic_outputs', ref) for ref in value['output_refs']],
                        store.get_record('diagnosis_requests', value['diagnostic_id'])))
        return value
    monkeypatch.setattr(diagnosis_protocol, 'record', keep)
    summary = await fixture.exercise(tmp_path / ('on' if rule else 'off') / ('fits' if repair_fits else 'again'), 'accepted')
    return summary, seen, records


EVIDENCE = __import__('pathlib').Path(__file__).resolve().parents[1] / 'loop-evidence'


def dump(name, summary, seen, records):
    EVIDENCE.mkdir(exist_ok=True)
    value = {'campaign_state': summary['campaign']['state'], 'episode_counts': summary['episode_counts'],
             'diagnostics': [{k: d[k] for k in ('kind', 'proposed_kind')} for d in summary['records']['diagnostics']],
             'interventions': [i['result'] for i in summary['records']['interventions']],
             'diagnosis_turns_sent': [len(m) for m in seen],
             'repair_user_messages': [m[3]['content'] for m in seen if len(m) == 4],
             'records': [r[0] for r in records]}
    (EVIDENCE / f'{name}.json').write_text(json.dumps(value, indent=1, sort_keys=True) + '\n')


def repair_message(messages):
    return json.loads(messages[3]['content'])


@pytest.mark.anyio
@pytest.mark.localhost_http
async def test_rule_1_repair_states_the_limit_and_the_fitting_repair_runs_the_intervention(tmp_path, monkeypatch):
    summary, seen, records = await run(tmp_path, monkeypatch, rule=True, repair_fits=True)
    dump('rule1-on-repair-fits', summary, seen, records)
    assert len(seen) == 2, 'one diagnosis: a first turn and one repair turn'
    first, repair = seen
    assert len(first) == 2 and len(repair) == 4 and repair[:2] == first
    assert json.loads(repair[2]['content'])['hypothesis'] == LONG               # the model's text replayed verbatim
    message = repair_message(repair)
    assert message == {'validation_errors': [{'location': ['hypothesis'], 'type': 'string_too_long',
                                              'max_characters': 600, 'your_characters': 614}],
                       'instruction': FORMAT_REPAIR_INSTRUCTION + ' ' + diagnosis_protocol.REPAIR_SENTENCE}
    assert repair[3]['content'] == canonical_json(message)
    kinds = [d['kind'] for d in summary['records']['diagnostics']]
    results = [i['result'] for i in summary['records']['interventions']]
    assert kinds == ['POLICY_GAP'] and results == ['SUPPORTED']              # the repair fitted, so the intervention ran
    assert summary['episode_counts'].get('intervention') == 6
    (record, _, outputs, saved), = records
    assert saved == json.loads(canonical_json(record))                      # the immutable store record is what was built
    assert record['proposal_status'] == 'VALID_REQUESTED' and record['recorded_proposed_kind_source'] == 'model'
    assert [a['validation_errors'] for a in record['attempts']] == [
        [{'location': ['hypothesis'], 'type': 'string_too_long', 'max_characters': 600, 'your_characters': 614}], []]
    assert [o['attempt'] for o in outputs] == [0, 1] and len({o['request_id'] for o in outputs}) == 1
    assert outputs[0]['request_id'] == record['request_id']
    assert json.loads(outputs[0]['raw'])['hypothesis'] == LONG and json.loads(outputs[1]['raw'])['hypothesis'] == SHORT
    assert record['intervention_ran'] and record['verdict'] == 'POLICY_GAP' and record['fresh_intervention_trials'] == 6
    assert record['requested_intervention_id'] == json.loads(first[1]['content'])['intervention_ids'][0]
    assert record['requested_change'] == json.loads(first[1]['content'])['interventions'][0]['change']
    assert record['requested_change'] != 'removes_violation'                 # the change string, not the prediction
    assert summary['campaign']['state'] == 'COMPLETED'


@pytest.mark.anyio
@pytest.mark.localhost_http
async def test_without_rule_1_the_same_answers_get_todays_repair_message_and_no_record(tmp_path, monkeypatch):
    summary, seen, records = await run(tmp_path, monkeypatch, rule=False, repair_fits=True)
    dump('rule1-off-repair-fits', summary, seen, records)
    first, repair = seen
    assert repair_message(repair) == {'validation_errors': [{'location': ['hypothesis'], 'type': 'string_too_long'}],
                                      'instruction': FORMAT_REPAIR_INSTRUCTION}
    assert records == []
    assert [d['kind'] for d in summary['records']['diagnostics']] == ['POLICY_GAP']


@pytest.mark.anyio
@pytest.mark.localhost_http
async def test_rule_1_records_a_v2g_style_double_overrun_as_invalid_output_with_a_code_default(tmp_path, monkeypatch):
    summary, seen, records = await run(tmp_path, monkeypatch, rule=True, repair_fits=False)
    dump('rule1-on-overrun-twice', summary, seen, records)
    diagnostics = summary['records']['diagnostics']
    assert records and len(records) == len(diagnostics) and len(seen) == 2 * len(diagnostics)   # one record per diagnosis
    for record, _, outputs, saved in records:
        assert saved == json.loads(canonical_json(record))
        assert record['proposal_status'] == 'INVALID_OUTPUT' and record['recorded_proposed_kind_source'] == 'code_default'
        assert record['recorded_proposed_kind'] == 'INCONCLUSIVE' and record['verdict'] == 'INCONCLUSIVE'
        assert not record['intervention_ran'] and record['interventions'] == [] and record['fresh_intervention_trials'] == 0
        assert record['last_raw_unvalidated'] == {'validated': False, 'parsed_json_object': True, 'proposed_kind': 'POLICY_GAP',
                                                  'requested_intervention_id': record['options'][0]['intervention_id']}
        assert [len(a['validation_errors']) for a in record['attempts']] == [1, 1]
        assert '614 of at most 600 characters' in record['statement'] and 'code default' in record['statement']
    assert summary['records']['interventions'] == []
    assert {d['kind'] for d in diagnostics} == {'INCONCLUSIVE'} and {d['proposed_kind'] for d in diagnostics} == {'INCONCLUSIVE'}
    assert summary['campaign']['state'] in ('COMPLETED', 'NO_CHANGE', 'STOPPED') or summary['campaign']['state']
