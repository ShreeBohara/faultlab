#!/usr/bin/env python3
"""Pre-registrable check for review findings LOW-1 / P-1 (September 30): did a diagnosis Mechanic misread a native
adapter v2 report as citing evidence that was never delivered?

Stdlib only; reads ONE campaign recording export (the JSON the product exports for a campaign, e.g.
artifacts/product-live-2026-09-30/native-v2-run/export.json). It never imports the app, opens a store, reads .env or
uses the network. $0.

Declared rule (fixed before any new live run):
  A diagnosis is CHECKED when the Mechanic's proposed_kind is CONTRACT_EVIDENCE_GAP and its saved hypothesis claims an
  undelivered or unshown citation (case-insensitive match of CLAIM below). The episodes it read are the counterexample's
  source episode and the diagnosis's fresh reproduction episodes. For each episode read, the data show an undelivered
  citation when (a) a report evidence ID is not one of that episode's recorded observation IDs, or (b) the adapter
  recorded a cited token it did not decode (v2.1 `cited_tokens_not_decoded`; the first v2 build's `cited_unshown_labels`).
  A CHECKED diagnosis is a MISREADING when no episode it read shows an undelivered citation, and SUPPORTED otherwise.
  Diagnoses that do not make that claim are NOT_CHECKED (listed, never scored).

Usage: python3 -B check_evidence_gap_misreading.py EXPORT.json [OUT.json]
"""
import json
import re
import sys

CLAIM = re.compile(r'undelivered|not\s+(?:been\s+)?delivered|never\s+(?:been\s+)?delivered|not\s+(?:been\s+)?shown|unshown|'
                   r'do(?:es)?\s+not\s+contain|outside\s+the\s+delivered', re.IGNORECASE)


def _hypothesis(raw):
    try:
        return str(json.loads(raw).get('hypothesis') or '')
    except (TypeError, ValueError, AttributeError):
        return str(raw or '')


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
        claims = diagnostic.get('proposed_kind') == 'CONTRACT_EVIDENCE_GAP' and any(CLAIM.search(text) for text in texts)
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
                        'claims_undelivered_citation': claims, 'hypotheses': texts, 'episodes_read': rows, 'verdict': verdict})
    summary = {verdict: sum(1 for r in results if r['verdict'] == verdict) for verdict in ('MISREADING', 'SUPPORTED', 'NOT_CHECKED')}
    return {'rule': __doc__.split('Declared rule (fixed before any new live run):')[1].split('Usage:')[0].strip(),
            'campaign_id': export.get('campaign_id'), 'diagnostics': results, 'summary': summary}


def main(argv):
    with open(argv[1]) as handle:
        result = check(json.load(handle))
    text = json.dumps(result, indent=1, sort_keys=True)
    if len(argv) > 2:
        with open(argv[2], 'w') as handle:
            handle.write(text + '\n')
    print(json.dumps({'campaign_id': result['campaign_id'], 'summary': result['summary'],
                      'verdicts': [(r['diagnostic_id'], r['verdict']) for r in result['diagnostics']]}))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
