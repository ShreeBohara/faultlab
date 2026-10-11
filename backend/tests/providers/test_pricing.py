"""The dated price table: the shipped file and scratch tables, never a network price lookup."""
from datetime import date, timedelta
import json
import os

import pytest

from app.providers.catalog import PROVIDER_IDS
from app.providers.pricing import STALE_AFTER, PricingTableError, describe, load_table, table_rates

ENTRY = {'ref': 'openai:gpt-5-mini', 'input_per_million': 0.25, 'output_per_million': 2.0,
         'verified': True, 'verified_on': '2026-10-01', 'source': 'test'}
VERIFIED_ON = date(2026, 10, 1)


def _table(tmp_path, entries, schema='faultlab-pricing-table/v1'):
    path = tmp_path / 'pricing.json'
    path.write_text(json.dumps({'schema': schema, 'entries': entries}))
    return path


def test_shipped_table_parses_and_keeps_the_historical_wandb_rates():
    table = load_table()
    assert (table['wandb:deepseek-ai/DeepSeek-V3.1'].input_per_million,
            table['wandb:deepseek-ai/DeepSeek-V3.1'].output_per_million) == (0.55, 1.65)
    assert (table['wandb:deepseek-ai/DeepSeek-V4-Pro-0813'].input_per_million,
            table['wandb:deepseek-ai/DeepSeek-V4-Pro-0813'].output_per_million) == (1.31, 3.96)
    assert {ref for ref, entry in table.items() if entry.verified} == {
        'wandb:deepseek-ai/DeepSeek-V3.1', 'wandb:deepseek-ai/DeepSeek-V4-Pro-0813', 'wandb:meta-llama/Llama-3.3-70B-Instruct',
        'anthropic:claude-opus-5-5', 'anthropic:claude-sonnet-5-5', 'anthropic:claude-haiku-5-5', 'anthropic:claude-haiku-4-5',
        'anthropic:claude-fable-5-1'}
    # Read from the official Claude pricing page on 2026-10-10.
    assert (table['anthropic:claude-sonnet-5-5'].input_per_million, table['anthropic:claude-sonnet-5-5'].output_per_million) == (2.0, 10.0)
    assert (table['anthropic:claude-haiku-5-5'].input_per_million, table['anthropic:claude-haiku-5-5'].output_per_million) == (0.10, 0.50)
    assert all(not entry.verified for ref, entry in table.items() if ref.startswith('openai:'))
    for entry in table.values():
        assert entry.ref.split(':', 1)[0] in PROVIDER_IDS and entry.source
        # Every entry prices on its verification day and goes stale 90 days later, whatever today is.
        assert entry.usable(today=entry.verified_on, allow_stale=False) is entry.verified
        assert entry.usable(today=entry.verified_on + STALE_AFTER + timedelta(days=1), allow_stale=False) is False


def test_verified_entries_count_only_within_the_staleness_window(tmp_path):
    path = _table(tmp_path, [ENTRY])
    assert table_rates('openai:gpt-5-mini', path=path, today=VERIFIED_ON) == (0.25, 2.0)
    assert table_rates('openai:gpt-5-mini', path=path, today=VERIFIED_ON + STALE_AFTER) == (0.25, 2.0)
    assert table_rates('openai:gpt-5-mini', path=path, today=VERIFIED_ON + STALE_AFTER + timedelta(days=1)) is None
    late = VERIFIED_ON + timedelta(days=400)
    assert table_rates('openai:gpt-5-mini', path=path, today=late, allow_stale=True) == (0.25, 2.0)
    assert describe('openai:gpt-5-mini', path=path, today=late)['status'] == 'stale'
    assert describe('openai:gpt-5-mini', path=path, today=VERIFIED_ON) == {
        'ref': 'openai:gpt-5-mini', 'status': 'priced', 'input_per_million': 0.25, 'output_per_million': 2.0,
        'verified_on': '2026-10-01', 'source': 'test'}


def test_unverified_and_unknown_entries_never_price(tmp_path):
    path = _table(tmp_path, [{**ENTRY, 'verified': False}])
    assert table_rates('openai:gpt-5-mini', path=path, today=VERIFIED_ON) is None
    assert table_rates('openai:gpt-5-mini', path=path, today=VERIFIED_ON, allow_stale=True) is None
    assert describe('openai:gpt-5-mini', path=path, today=VERIFIED_ON)['status'] == 'unverified'
    assert describe('openai:gpt-5', path=path)['status'] == 'unpriced'
    assert table_rates('openai:gpt-5', path=path) is None


@pytest.mark.parametrize('entries,schema', [
    ([{**ENTRY, 'verified': 'yes'}], 'faultlab-pricing-table/v1'),
    ([{**ENTRY, 'input_per_million': -1}], 'faultlab-pricing-table/v1'),
    ([{**ENTRY, 'output_per_million': 'nan'}], 'faultlab-pricing-table/v1'),
    ([{**ENTRY, 'verified_on': 'yesterday'}], 'faultlab-pricing-table/v1'),
    ([{k: v for k, v in ENTRY.items() if k != 'verified_on'}], 'faultlab-pricing-table/v1'),
    ([{**ENTRY, 'ref': 'gpt-5-mini'}], 'faultlab-pricing-table/v1'),
    ([ENTRY, ENTRY], 'faultlab-pricing-table/v1'),
    ([ENTRY], 'something-else'),
])
def test_malformed_tables_are_refused_as_a_whole(tmp_path, entries, schema):
    with pytest.raises(PricingTableError):
        load_table(_table(tmp_path, entries, schema))


def test_missing_or_unreadable_custom_table_is_a_configuration_error(tmp_path):
    with pytest.raises(PricingTableError):
        load_table(tmp_path / 'absent.json')
    broken = tmp_path / 'broken.json'
    broken.write_text('{not json')
    with pytest.raises(PricingTableError):
        load_table(broken)


def test_table_edits_are_seen_without_a_restart(tmp_path):
    path = _table(tmp_path, [ENTRY])
    assert table_rates('openai:gpt-5-mini', path=path, today=VERIFIED_ON) == (0.25, 2.0)
    stamp = path.stat().st_mtime_ns
    _table(tmp_path, [{**ENTRY, 'input_per_million': 0.5}])
    os.utime(path, ns=(stamp + 1_000_000, stamp + 1_000_000))
    assert table_rates('openai:gpt-5-mini', path=path, today=VERIFIED_ON) == (0.5, 2.0)
