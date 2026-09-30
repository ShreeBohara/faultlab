#!/usr/bin/env python3
"""Misreading check, version 2 (September 30, after live runs v2d and v2e): did a diagnosis Mechanic misread a native
adapter v2 report as citing evidence that was never delivered or never shown?

Version 1 (artifacts/product-native-v2b-2026-09-30/fixer/check_evidence_gap_misreading.py, sha256 70c4eeda...; also
copied unchanged into the v2d and v2e run folders) is kept untouched: it is the pre-registered read-out of runs v2d and
v2e, and it scored both diagnoses NOT_CHECKED because its phrase list matches "not shown" but not "never shown". This
version changes ONLY how a claim is recognised (CLAIM and the denial rule below; CLAIM is a superset of version 1's
phrases) and adds self-tests and output labels. Results of this version on v2d and v2e are POST-HOC: the phrase list was
widened after reading those two hypotheses.

Fixer revision (September 30, before any run used this version; review finding MEDIUM-1). The native_citation_status
block now puts the word "undecoded" (its field name) and "not decoded" (its meaning sentence) into every native v2
Mechanic request. So a Mechanic that reads the block correctly may echo those words, or deny the claim ("no label was
never shown"). The builder's version read 17 of 20 such wordings as claims. Now:
  * bare "undecoded" and bare "not decoded" no longer count; only claim shapes do ("1 undecoded token", "has undecoded
    tokens", "two citations were not decoded");
  * a match does not count when its own clause, before the match, has a denial word (no, none, nothing, neither, nor,
    never, not, n't, zero, 0, without). A clause ends at . ; : ! ? , or a dash, and at and, but, yet, so, because, since,
    while, although, though, whereas, however.
Every counted match is reported with its sentence (claim_matches), and every match the denial rule set aside is
reported too (denied_matches), because a phrase heuristic can still err both ways: a CHECKED verdict counts only after a
person confirms that each claim_matches sentence is a real claim. Known limit: the unchanged v2 memory text itself says
"a token kept as written is one the agent was never shown as a label"; a Mechanic that repeats that rule counts as a
match, and only the human check catches it. Every output states whether it is a pre-registered or a post-hoc read-out
(read_out_status, required on the command line) and this script's own sha256 (review finding LOW-1).

Stdlib only; reads ONE campaign recording export (the JSON the product exports for a campaign, e.g.
artifacts/product-live-2026-09-30/native-v2e-run/export.json). It never imports the app, opens a store, reads .env or
uses the network. $0.

Rule (version 1's rule, with version 2's claim phrases and denial rule):
  A diagnosis is CHECKED when the Mechanic's proposed_kind is CONTRACT_EVIDENCE_GAP and its saved hypothesis claims an
  undelivered, unshown or undecodable citation (case-insensitive match of CLAIM below that the denial rule does not set
  aside). The episodes it read are the counterexample's source episode and the diagnosis's fresh reproduction episodes.
  For each episode read, the data show an undelivered citation when (a) a report evidence ID is not one of that
  episode's recorded observation IDs, or (b) the adapter recorded a cited token it did not decode (v2.1
  `cited_tokens_not_decoded`; the first v2 build's `cited_unshown_labels`). A CHECKED diagnosis is a MISREADING when no
  episode it read shows an undelivered citation, and SUPPORTED otherwise. Diagnoses that do not make that claim are
  NOT_CHECKED (listed, never scored). A CHECKED verdict counts only after a person confirms its claim_matches sentences.

Usage: python3 -B check_evidence_gap_misreading_v2.py EXPORT.json [OUT.json] --read-out {pre-registered,post-hoc}
       python3 -B check_evidence_gap_misreading_v2.py --self-test
"""
import argparse
import hashlib
import json
import re
import sys

CHECKER_VERSION = 'faultlab-misreading-check/v2.1-claim-shapes-and-denials'
# Version 1's phrases, unchanged and in its order.
CLAIM_V1 = (r'undelivered|not\s+(?:been\s+)?delivered|never\s+(?:been\s+)?delivered|not\s+(?:been\s+)?shown|unshown|'
            r'do(?:es)?\s+not\s+contain|outside\s+the\s+delivered')
# Added in version 2. "undecoded" and "not decoded" count only in a claim shape: a nonzero amount or a verb of having or
# citing right before "undecoded token(s)/label(s)/citation(s)", or a nonzero amount of tokens, labels or citations that
# "was/were not decoded". The block's own words ("undecoded: []", "a token that was not decoded") are not claims.
_AMOUNT = r'(?:[1-9]\d*|one|two|three|four|five|six|seven|eight|nine|ten|some|several|many|an?)'
_ITEMS = r'(?:tokens?|labels?|citations?)'
CLAIM_V2_ADDED = (r'never\s+(?:been\s+)?shown|(?:was|were)\s+not\s+shown|(?:has|have|had)\s+not\s+been\s+shown|'
                  r'(?:cannot|can\s*not|can\'t|could\s+not|couldn\'t)\s+be\s+decoded|not\s+decodable|undecodable|'
                  r'\b' + _AMOUNT + r'\s+(?:cited\s+)?' + _ITEMS + r'\s+(?:was|were)\s+not\s+decoded|'
                  r'\b(?:' + _AMOUNT + r'|has|have|had|includes?|included|contains?|contained|cites?|cited)\s+undecoded\s+' + _ITEMS + r'|'
                  r'outside\s+(?:of\s+)?the\s+shown(?:\s+labels)?|outside\s+(?:of\s+)?the\s+labels\s+(?:it\s+was\s+|that\s+were\s+)?shown')
CLAIM = re.compile(CLAIM_V1 + '|' + CLAIM_V2_ADDED, re.IGNORECASE)
# The denial rule: a match does not count when its clause, before the match, has one of these words.
DENIAL = re.compile(r"\b(?:no|none|nothing|neither|nor|never|not|zero|without)\b|n't\b|(?<![\w.-])0(?![\w.-])", re.IGNORECASE)
CLAUSE_END = re.compile(r'[;:!?,—–]|\.(?=\s|$)|\s-\s|\b(?:and|but|yet|so|because|since|while|although|though|whereas|however)\b',
                        re.IGNORECASE)
SENTENCE_END = re.compile(r'(?<=[.!?])\s+')
READ_OUT = {'pre-registered': ('PRE_REGISTERED', 'Declared before the run it reads; the declaration must name this sha256.'),
            'post-hoc': ('POST_HOC', 'POST-HOC: not a pre-registered read-out. The claim phrases and the denial rule were '
                                     'chosen after reading the v2d and v2e hypotheses.')}


def _hypothesis(raw):
    try:
        return str(json.loads(raw).get('hypothesis') or '')
    except (TypeError, ValueError, AttributeError):
        return str(raw or '')


def _sentence(text, start):
    begin = 0
    for end in SENTENCE_END.finditer(text):
        if end.start() >= start: break
        begin = end.end()
    following = SENTENCE_END.search(text, start)
    return text[begin:following.start() if following else len(text)].strip()


def claim_matches(text):
    """(counted, denied): every CLAIM match in text, split by the denial rule; each with its phrase and sentence."""
    counted, denied = [], []
    for match in CLAIM.finditer(text):
        clause_start = 0
        for end in CLAUSE_END.finditer(text, 0, match.start()):
            clause_start = end.end()
        denial = DENIAL.search(text[clause_start:match.start()])
        row = {'phrase': match.group(0).lower(), 'sentence': _sentence(text, match.start())}
        if denial:
            denied.append({**row, 'denial': denial.group(0).lower()})
        else:
            counted.append(row)
    return counted, denied


def check(export):
    episodes = {row['episode_id']: row for row in export.get('episodes', [])}
    observations = {}
    for row in export.get('observations', []):
        observations.setdefault(row['episode_id'], []).append(row['evidence_id'])
    counterexamples = {row['counterexample_id']: row for row in export.get('counterexamples', [])}
    outputs = [row for row in export.get('mechanic_outputs', []) if row.get('prompt') == 'diagnosis.md']
    results = []
    for diagnostic in export.get('diagnostics', []):
        counter = counterexamples.get(diagnostic.get('counterexample_id')) or {}
        source = counter.get('source_episode_id')
        read = [e for e in dict.fromkeys([source, *(diagnostic.get('reproduction_ids') or [])]) if e]
        texts = [_hypothesis(row.get('raw')) for row in outputs if row.get('episode_id') == source]
        counted, denied = [], []
        for text in texts:
            text_counted, text_denied = claim_matches(text)
            counted += text_counted; denied += text_denied
        matched = sorted({row['phrase'] for row in counted})
        claims = diagnostic.get('proposed_kind') == 'CONTRACT_EVIDENCE_GAP' and bool(matched)
        rows = []
        for episode_id in read:
            report = (episodes.get(episode_id) or {}).get('report') or {}
            recorded = observations.get(episode_id, [])
            undelivered = [token for token in report.get('evidence_ids', []) if token not in recorded]
            submitted = [event['payload'] for event in export.get('events', {}).get(episode_id, [])
                         if event.get('type') == 'report_submitted']
            last = submitted[-1] if submitted else {}
            not_decoded = list(last.get('cited_tokens_not_decoded', last.get('cited_unshown_labels', [])) or [])
            rows.append({'episode_id': episode_id, 'recorded_observations': len(recorded),
                         'report_present': bool(report), 'report_citations': len(report.get('evidence_ids', [])),
                         'citation_protocol': last.get('citation_protocol'),
                         'report_ids_not_recorded': undelivered, 'adapter_tokens_not_decoded': not_decoded})
        shows_gap = any(row['report_ids_not_recorded'] or row['adapter_tokens_not_decoded'] for row in rows)
        verdict = ('NOT_CHECKED' if not claims else 'SUPPORTED' if shows_gap else 'MISREADING')
        results.append({'diagnostic_id': diagnostic.get('diagnostic_id'), 'proposed_kind': diagnostic.get('proposed_kind'),
                        'kind': diagnostic.get('kind'), 'counterexample_id': diagnostic.get('counterexample_id'),
                        'claims_undelivered_citation': claims, 'matched_claim_phrases': matched,
                        'claim_matches': counted, 'denied_matches': denied, 'hypotheses': texts,
                        'episodes_read': rows, 'verdict': verdict})
    summary = {verdict: sum(1 for r in results if r['verdict'] == verdict) for verdict in ('MISREADING', 'SUPPORTED', 'NOT_CHECKED')}
    return {'checker_version': CHECKER_VERSION,
            'rule': __doc__.split('Rule (version 1\'s rule, with version 2\'s claim phrases and denial rule):')[1].split('Usage:')[0].strip(),
            'claim_pattern': CLAIM.pattern, 'denial_pattern': DENIAL.pattern, 'clause_end_pattern': CLAUSE_END.pattern,
            'human_confirmation_required': True,
            'campaign_id': export.get('campaign_id'), 'diagnostics': results, 'summary': summary}


# ------------------------------------------------------------------------------------------------------ self-tests

CLAIMS = [  # (text, counts as a claim) -- each added phrase, version 1's phrases, and the two live hypotheses' wording
    ('cites evidence labels that were never shown to it', True),
    ('labels that had never been shown to the agent', True),
    ('the cited label was not shown', True), ('these labels were not shown to the actor', True),
    ('it has not been shown obs-7', True), ('tokens that cannot be decoded to delivered evidence IDs', True),
    ('a token that could not be decoded', True), ("a token that can't be decoded", True), ('the label is not decodable', True),
    ('an undecodable citation', True), ('the report has undecoded tokens', True), ('one citation was not decoded', True),
    ('it cites labels outside the shown labels', True), ('a label outside the labels it was shown', True),
    ('outside of the shown set', True),
    # version 1's phrases still match
    ('an undelivered observation', True), ('evidence not delivered to it', True), ('never been delivered', True),
    ('not shown', True), ('an unshown label', True), ('the journal does not contain it', True), ('outside the delivered set', True),
    # not claims
    ('every cited label was shown and decoded', False), ('all 5 cited tokens decoded; 0 undecoded', False),
    ('no undecoded tokens in any episode', False), ('zero undecoded citations', False), ('without undecoded tokens', False),
    ('the report has 2 undecoded tokens', True),
    ('the report cites delivered evidence', False), ('the agent sent a confirmation after a rejected upgrade', False),
    # fixer (MEDIUM-1): the block's own words, echoed or denied, are not claims (the two reviews' probe wordings)
    ('The native_citation_status block shows undecoded is empty for every episode, yet the report is inconsistent.', False),
    ('undecoded: [] in all four episodes', False), ('All cited tokens decoded (cited 5, decoded 5, undecoded none).', False),
    ('No cited label was not shown to the agent.', False), ('None of the citations were not decoded.', False),
    ('0 tokens undecoded', False), ('the report cites only labels that were shown; nothing is outside the shown labels', False),
    ('every token decoded, so no token was never shown', False), ('Every row has cited equal to decoded and an empty undecoded list.', False),
    ('All cited tokens decoded; none undecoded.', False), ('No token was left undecoded.', False),
    ('There were no tokens undecoded.', False), ('The block lists nothing as undecoded.', False), ('Nothing was undecoded.', False),
    ('Each report had 0 undecoded tokens.', False), ('The block confirms no label was never shown.', False),
    ('undecoded lists every cited token that was not decoded and was kept exactly as written', False),
    # fixer: claims in the block's own words still count
    ('Episode 2 has 1 undecoded token, so the report cites a label the agent was never shown.', True),
    ('The report cites undecoded tokens.', True), ('Two citations were not decoded.', True),
]


def _export(hypothesis, *, proposed_kind='CONTRACT_EVIDENCE_GAP', gap=None):
    events = {'e-src': [{'type': 'report_submitted', 'payload': {'citation_protocol': 'faultlab-native-adapter/v2.1-shown-order-labels',
                                                                'cited_tokens_not_decoded': ['obs-9'] if gap == 'undecoded' else []}}],
              'e-rep': [{'type': 'report_submitted', 'payload': {'citation_protocol': 'faultlab-native-adapter/v2.1-shown-order-labels',
                                                                'cited_tokens_not_decoded': []}}]}
    cited = ['evidence-a', 'evidence-x'] if gap == 'unrecorded' else ['evidence-a']
    return {'campaign_id': 'campaign-self-test',
            'episodes': [{'episode_id': 'e-src', 'report': {'evidence_ids': cited}}, {'episode_id': 'e-rep', 'report': {'evidence_ids': ['evidence-b']}}],
            'observations': [{'episode_id': 'e-src', 'evidence_id': 'evidence-a'}, {'episode_id': 'e-rep', 'evidence_id': 'evidence-b'}],
            'counterexamples': [{'counterexample_id': 'c1', 'source_episode_id': 'e-src'}],
            'mechanic_outputs': [{'prompt': 'diagnosis.md', 'episode_id': 'e-src', 'raw': json.dumps({'hypothesis': hypothesis})},
                                 {'prompt': 'mechanic.md', 'episode_id': 'e-src', 'raw': json.dumps({'hypothesis': 'never shown'})}],
            'diagnostics': [{'diagnostic_id': 'd1', 'counterexample_id': 'c1', 'reproduction_ids': ['e-rep'],
                             'proposed_kind': proposed_kind, 'kind': 'INCONCLUSIVE'}],
            'events': events}


def self_test():
    """Returns a list of failures (empty when every self-test passes)."""
    failures = []
    for text, expected in CLAIMS:
        if bool(claim_matches(text)[0]) != expected:
            failures.append(f'phrase {"missed" if expected else "wrongly counted"}: {text!r}')
    v1 = re.compile(CLAIM_V1, re.IGNORECASE)
    for text, expected in CLAIMS:
        if v1.search(text) and not CLAIM.search(text):
            failures.append(f'version 2 does not match what version 1 matched: {text!r}')
    cases = [
        ('claim, no gap -> MISREADING', _export('labels that were never shown to it'), 'MISREADING'),
        ('claim, undecoded token -> SUPPORTED', _export('a token that cannot be decoded', gap='undecoded'), 'SUPPORTED'),
        ('claim, unrecorded report ID -> SUPPORTED', _export('labels outside the shown labels', gap='unrecorded'), 'SUPPORTED'),
        ('no claim phrase -> NOT_CHECKED', _export('the agent confirmed after a rejected upgrade'), 'NOT_CHECKED'),
        ('another proposed kind -> NOT_CHECKED', _export('never shown', proposed_kind='POLICY_GAP'), 'NOT_CHECKED'),
        ('a negated count is not a claim -> NOT_CHECKED', _export('all cited labels decoded; 0 undecoded'), 'NOT_CHECKED'),
        ('a contract gap for another reason, echoing an empty undecoded list -> NOT_CHECKED',
         _export('Every row of native_citation_status has an empty undecoded list, so the citations were valid; the gap is that '
                 'the cited FAILED receipt contradicts the report overall, which the evidence contract should reject.'), 'NOT_CHECKED'),
        ('a denied claim -> NOT_CHECKED', _export('The block confirms no label was never shown.'), 'NOT_CHECKED'),
    ]
    for name, export, expected in cases:
        result = check(export)
        verdicts = [d['verdict'] for d in result['diagnostics']]
        if verdicts != [expected]:
            failures.append(f'{name}: got {verdicts}')
        if result['checker_version'] != CHECKER_VERSION or 'MISREADING' not in result['summary']:
            failures.append(f'{name}: result shape')
    only_candidate = _export('the agent confirmed after a rejected upgrade')   # "never shown" only in a mechanic.md output
    if check(only_candidate)['diagnostics'][0]['matched_claim_phrases']:
        failures.append('a candidate (mechanic.md) output was read as the diagnosis hypothesis')
    denied = check(_export('No cited label was not shown to the agent.'))['diagnostics'][0]
    if denied['claim_matches'] or [m['phrase'] for m in denied['denied_matches']] != ['was not shown']:
        failures.append('a denied match is not listed as denied')
    return failures


def _own_sha256():
    with open(__file__, 'rb') as handle:
        return hashlib.sha256(handle.read()).hexdigest()


def main(argv):
    if len(argv) > 1 and argv[1] == '--self-test':
        failures = self_test()
        print(json.dumps({'checker_version': CHECKER_VERSION, 'checker_sha256': _own_sha256(),
                          'self_test': 'PASSED' if not failures else 'FAILED', 'phrase_cases': len(CLAIMS), 'failures': failures}))
        return 1 if failures else 0
    parser = argparse.ArgumentParser(prog=argv[0], description='Misreading check, version 2 (see the module docstring).')
    parser.add_argument('export'); parser.add_argument('out', nargs='?')
    parser.add_argument('--read-out', required=True, choices=sorted(READ_OUT),
                        help='Whether this run was declared before the campaign it reads (pre-registered) or not (post-hoc).')
    args = parser.parse_args(argv[1:])
    with open(args.export) as handle:
        result = check(json.load(handle))
    status, note = READ_OUT[args.read_out]
    result.update({'read_out_status': status, 'read_out_note': note, 'checker_sha256': _own_sha256()})
    text = json.dumps(result, indent=1, sort_keys=True)
    if args.out:
        with open(args.out, 'w') as handle:
            handle.write(text + '\n')
    print(json.dumps({'campaign_id': result['campaign_id'], 'read_out_status': status, 'summary': result['summary'],
                      'verdicts': [(r['diagnostic_id'], r['verdict'], r['matched_claim_phrases']) for r in result['diagnostics']]}))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
