#!/usr/bin/env python3
"""Fixer (v2b): checks for the doc-only and naming parts of the review findings ($0, stdlib only, read-only).

Run against a root (the repo, or fixer/before/ which holds the pre-fix copies of the same files). Each check passes on
the fixed files and fails on the pre-fix copies; mutation_checks.py runs both and logs the result.
Never reads .env, audit/promotion.json, audit/final-audit*, artifacts/heldout2/ or backend/app/referee/checks.py.

Usage: python3 -B doc_checks.py ROOT
"""
import re
import sys
from pathlib import Path


def read(root, rel):
    return (root / rel).read_text(encoding='utf-8')


def checks(root):
    out = []
    def check(finding, name, ok):
        out.append((finding, name, bool(ok)))
    guide = read(root, 'docs/user-guide.md')
    retry = read(root, 'docs/PRODUCT_TRANSPORT_RETRY_2026-09-29.md')
    setup = read(root, 'docs/external-agent-setup.md')
    status = read(root, 'CURRENT_STATUS.md')
    backoff_campaign_ref = read(root, 'backend/tests/lab/test_campaign_transport_retry.py') + read(root, 'backend/tests/lab/test_transport_retry_plans.py')
    adapter_tests = read(root, 'backend/tests/integrations/test_native_adapter_v2.py')
    view_tests = read(root, 'backend/tests/lab/test_native_v2_label_views.py')

    # LOW-5 / P-6: stale names and wording
    check('LOW-5', 'no reference to the nonexistent tests/lab/test_lab_transport_backoff.py',
          'test_lab_transport_backoff' not in backoff_campaign_ref and 'test_lab_backoff_campaign.py' in backoff_campaign_ref)
    check('LOW-5', 'no test named ...labels_are_journal_positions...', 'def test_labels_are_journal_positions' not in adapter_tests)
    check('P-6', 'no test claims "has_no_label_gap" while asserting the o1, o2, o4 gap', 'has_no_label_gap' not in view_tests)
    check('LOW-5', 'user guide gives the same Stop latency as the other docs (about half a second)',
          'within about a second' not in guide and 'within about half a second' in guide)
    # P-6: docs
    check('P-6', 'external-agent-setup heading no longer says v2 was not yet run live',
          not re.search(r'^## Native adapter v2 \(September 29, 2026; built offline, not yet run live\)', setup, re.M)
          and re.search(r'^## Native adapter v2 \(first build run live September 29, 2026; v2\.1 labels not yet run live\)', setup, re.M))
    check('P-6', "'Why this changed' no longer ends 'the agent no longer sees one' and says the Mechanic's view is unchanged",
          'A gap invites a guess; the agent no longer sees one.' not in setup and 'v2.1 does not change what the Mechanic reads' in setup)
    check('P-6', 'user guide no longer says every retry is "listed on its selection"',
          'listed on its selection' not in guide and 'Mechanic request\'s retries appear only in the campaign recording' in guide)
    check('P-6', 'the CURRENT_STATUS results table has no blank line inside it',
          not re.search(r'NATIVE_LEARN_RUN_2026-09-29\.md` \|\n\n\| Native adapter v2, first live run', status))
    check('P-6', 'transport note says the campaign cap of 12 is the real discovery bound under discovery v2',
          'Under discovery v2 the campaign cap of 12 is reached first' in retry)
    check('P-6', 'no link uses the old external-agent-setup anchor',
          'native-adapter-v2-september-29-2026-built-offline-not-yet-run-live' not in status + guide)
    # P-3: where retries are visible
    check('P-3', 'transport note no longer says retries show "on each retried selection in the fault-search panel"',
          'on each retried selection in the fault-search panel' not in retry and '**Where an operator sees the retries.**' in retry
          and 'nothing shows the wait' in retry)
    check('P-3', 'CURRENT_STATUS says challenge and Mechanic retries appear only in the recording and budget',
          'Mechanic retries appear only in the campaign recording and the budget counts' in status)
    # P-5: older checkouts
    check('P-5', 'transport note states the older-checkout limit for new Learn plans',
          '**Older checkouts.** Every new Learn plan now declares rule v2.' in retry)
    check('P-5', 'CURRENT_STATUS states the older-checkout limit', 'an older checkout (`ac7a12d2` or earlier) reports such a plan' in status)
    # LOW-2 / P-4: documented
    check('LOW-2', 'transport note says the budget is checked before the wait', 'checked **before** the wait' in retry)
    check('P-4', 'transport note shows the zero-retry wording', 'A model request failed and no transport retry was sent' in retry)
    # LOW-1 / P-1: honest statements
    check('LOW-1', "setup doc no longer says model readers 'never see the agent's labels' without qualification",
          "never see the\n     agent's labels" not in setup and 'reaches them\n     as written' in setup)
    check('P-1', 'CURRENT_STATUS says the September 29 misdiagnosis is not addressed',
          'Not fixed: the September 29 misdiagnosis' in status and 'v2.1 changes\n  what the agent sees, **not** what the Mechanic reads' in status)
    check('LOW-1', "CURRENT_STATUS no longer says the Mechanic 'never saw the agent's labels'",
          "never saw the agent's\n  labels" not in status)
    # CURRENT_STATUS basics required by the fixer task
    check('status', 'CURRENT_STATUS names the new runtime and the chain, not committed, register v2 again',
          '4553ebe7db2f9e3efda6f8761e987c6f1ea58dce12d3fde2dfbc8812ebb7c057' in status and '→ `18292424` (September 30 builder' in status
          and 'not yet committed' in status and 'Native adapter v2 must be registered again' in status)
    return out


def main(argv):
    root = Path(argv[1]).resolve()
    results = checks(root)
    for finding, name, ok in results:
        print(f'{"PASS" if ok else "FAIL"}  {finding:6} {name}')
    failed = sum(1 for _, _, ok in results if not ok)
    print(f'{len(results) - failed} passed, {failed} failed')
    return 0 if failed == 0 else 1


if __name__ == '__main__':
    sys.exit(main(sys.argv))
