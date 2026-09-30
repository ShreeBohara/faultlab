"""Offline checks of the misreading checker, version 2 (scripts/experiments/check_evidence_gap_misreading_v2.py).

Version 1 stays untouched (its copies in the v2d and v2e run folders are the pre-registered read-out). Version 2 widens
the claim phrase list and, after the fixer (review finding MEDIUM-1), counts "undecoded"/"not decoded" only in claim
shapes and sets aside denied matches; its results on v2d and v2e are POST-HOC. The script is stdlib only (no app import);
one test below imports the app's two new request sentences. No network, $0.
"""
import hashlib
import importlib.util
import json
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[3]


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


checker = load(ROOT / 'scripts/experiments/check_evidence_gap_misreading_v2.py', 'check_evidence_gap_misreading_v2')
RUNS = ROOT / 'artifacts/product-live-2026-09-30'
V1_SHA256 = '70c4eeda2fa148920f5e5a3efd5215aa0f359fe911ea1f70b5b09737c61d2033'


def test_the_self_tests_pass():
    assert checker.self_test() == []


def test_version_2_keeps_version_1s_phrases_and_rule():
    assert checker.CLAIM.pattern.startswith(checker.CLAIM_V1 + '|')
    assert 'proposed_kind is CONTRACT_EVIDENCE_GAP' in checker.__doc__ and 'POST-HOC' in checker.__doc__


@pytest.mark.parametrize('run,diagnostic,phrases', [
    ('native-v2d-run', 'diagnostic-57fa14bc65e941bfa5d55c392d325b7c', ['cannot be decoded', 'never shown']),
    ('native-v2e-run', 'diagnostic-b0eeb89d02d94b90b4ad5093d1402e6d', ['never shown']),
])
def test_post_hoc_on_v2d_and_v2e_version_2_reads_a_misreading_where_version_1_read_nothing(run, diagnostic, phrases):
    export_path, v1_path = RUNS / run / 'export.json', RUNS / run / 'check_evidence_gap_misreading.py'
    if not (export_path.exists() and v1_path.exists()):
        pytest.skip('The saved run folder is absent on this machine')
    assert hashlib.sha256(v1_path.read_bytes()).hexdigest() == V1_SHA256            # version 1 untouched
    export = json.loads(export_path.read_text())
    v1 = load(v1_path, f'check_evidence_gap_misreading_v1_{run.replace("-", "_")}').check(export)
    v2 = checker.check(export)
    assert [(d['diagnostic_id'], d['verdict']) for d in v1['diagnostics']] == [(diagnostic, 'NOT_CHECKED')]
    row, = v2['diagnostics']
    assert (row['diagnostic_id'], row['verdict'], row['matched_claim_phrases']) == (diagnostic, 'MISREADING', phrases)
    assert len(row['episodes_read']) == 4
    assert all(not e['report_ids_not_recorded'] and not e['adapter_tokens_not_decoded'] for e in row['episodes_read'])


# ---------------------------------------------------------------- fixer (September 30): review findings MEDIUM-1 and LOW-1
# The new native_citation_status block puts "undecoded" (its field name) and "not decoded" (its meaning sentence) into every
# native v2 Mechanic request. A Mechanic that reads the block correctly and echoes it, or denies the claim, must not be
# read as claiming unshown or undecodable citations. The wordings are the two reviews' probes, verbatim
# (review-integrity/checker-v2-negation-probe.txt and review-product/checker-v2/echo-probe.json).

ECHOES_AND_DENIALS = [
    # integrity review
    'The native_citation_status block shows undecoded is empty for every episode, yet the report is inconsistent with the confirmation outcome.',
    'undecoded: [] in all four episodes',
    'All cited tokens decoded (cited 5, decoded 5, undecoded none).',
    'No cited label was not shown to the agent.',
    'None of the citations were not decoded.',
    '0 tokens undecoded',
    'the report cites only labels that were shown; nothing is outside the shown labels',
    'every token decoded, so no token was never shown',
    '0 undecoded',
    'no undecoded tokens',
    # product review
    'The native_citation_status block shows undecoded is empty for every episode.',
    'Every row has cited equal to decoded and an empty undecoded list.',
    'All cited tokens decoded; none undecoded.',
    'undecoded: [] in all four rows, so every citation was shown and decoded.',
    'No token was left undecoded.',
    'There were no tokens undecoded.',
    'The block lists nothing as undecoded.',
    'Nothing was undecoded.',
    'Each report had 0 undecoded tokens.',
    'The block confirms no label was never shown.',
]


@pytest.mark.parametrize('text', ECHOES_AND_DENIALS)
def test_an_echo_of_the_block_or_a_denial_is_not_a_claim(text):
    row, = checker.check(checker._export(text))['diagnostics']
    assert (row['matched_claim_phrases'], row['verdict']) == ([], 'NOT_CHECKED')


def test_a_contract_gap_diagnosis_that_echoes_an_empty_undecoded_list_for_another_reason_is_not_scored():
    hypothesis = ('Every row of native_citation_status has an empty undecoded list, so the citations were valid; the gap is that '
                  'the cited FAILED receipt contradicts the report overall, which the evidence contract should reject.')
    row, = checker.check(checker._export(hypothesis))['diagnostics']
    assert row['verdict'] == 'NOT_CHECKED' and row['claims_undelivered_citation'] is False


def test_the_sentences_this_build_adds_to_every_native_v2_request_are_not_claims():
    from app.lab.citation_status import MEANING, MEMORY_POINTER
    for text in (MEANING, MEMORY_POINTER):
        row, = checker.check(checker._export(text))['diagnostics']
        assert (row['matched_claim_phrases'], row['verdict']) == ([], 'NOT_CHECKED'), text


@pytest.mark.parametrize('hypothesis,phrases', [
    # the two live hypotheses (v2d, v2e), verbatim from their exports: still read as the claim
    ("The actor's report is scored as untruthful because it cites evidence labels that were never shown to it under the v2.1 "
     "shown-order labeling contract, not because the underlying upgrade failure was misreported. The delivered terminal FAILED "
     "receipt for update_order is present, but the report's evidence_ids include tokens that cannot be decoded to delivered "
     "evidence IDs, causing C5 to fail while C3 fails due to the scheduled upgrade failure.", ['cannot be decoded', 'never shown']),
    ("The actor's report cites evidence IDs that were never shown to it as labels, causing C5 truthful_report to fail even though "
     "the delivered observations support a CORRECTLY_REJECTED report.", ['never shown']),
    # claims that use the block's own words
    ('Episode 2 has 1 undecoded token, so the report cites a label the agent was never shown.', ['1 undecoded token', 'never shown']),
    ('The report cites undecoded tokens.', ['cites undecoded tokens']),
    ('Two citations were not decoded.', ['two citations were not decoded']),
])
def test_a_claim_is_still_read_as_a_claim_and_each_match_is_reported_with_its_sentence(hypothesis, phrases):
    row, = checker.check(checker._export(hypothesis))['diagnostics']
    assert (row['matched_claim_phrases'], row['verdict']) == (phrases, 'MISREADING')
    assert sorted(match['phrase'] for match in row['claim_matches']) == phrases
    assert all(match['sentence'] in hypothesis for match in row['claim_matches'])


def test_a_denied_match_is_listed_for_the_human_check_but_not_counted():
    row, = checker.check(checker._export('No cited label was not shown to the agent.'))['diagnostics']
    assert row['claim_matches'] == [] and [m['phrase'] for m in row['denied_matches']] == ['was not shown']
    assert row['denied_matches'][0]['denial'] == 'no'


def test_every_output_states_its_read_out_status_and_the_checkers_own_sha256(tmp_path):
    export = tmp_path / 'export.json'; export.write_text(json.dumps(checker._export('labels that were never shown to it')))
    sha = hashlib.sha256((ROOT / 'scripts/experiments/check_evidence_gap_misreading_v2.py').read_bytes()).hexdigest()
    for flag, status in (('post-hoc', 'POST_HOC'), ('pre-registered', 'PRE_REGISTERED')):
        out = tmp_path / f'{flag}.json'
        assert checker.main(['check', str(export), str(out), '--read-out', flag]) == 0
        result = json.loads(out.read_text())
        assert result['read_out_status'] == status and result['checker_sha256'] == sha
        assert result['human_confirmation_required'] is True and result['read_out_note']
    with pytest.raises(SystemExit) as refused:                          # no unlabelled output
        checker.main(['check', str(export), str(tmp_path / 'unlabelled.json')])
    assert refused.value.code == 2 and not (tmp_path / 'unlabelled.json').exists()
