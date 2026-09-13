# Diagnostic evidence

Integrated diagnostic verification passed against the real localhost simulator (2026-09-12).
The fixture is explicitly `evidence_gap_v1`, separate from the ordinary four-fault catalog.
It compares committed/uncommitted worlds over the fixed finite public probe set and a
separately hashed available-status control. It never supplies a learned-policy gain.

Command: `.venv/bin/python -m pytest backend/tests/integration/test_diagnostic_evidence.py -q --basetemp=artifacts/diagnostic-verification`. Result: 1 passed in 3.97 seconds; 30 actual public HTTP probes, zero model calls. Sanitized result: `docs/diagnostic-evidence.json`. Two fixed witnesses returned CONTRACT_EVIDENCE_GAP; available-status control returned a succeeded receipt; mismatched/incomplete evidence returned INCONCLUSIVE.
Only matching complete witnesses may receive CONTRACT_EVIDENCE_GAP. Missing coverage,
prior delivered receipts, different semantic observations or available distinguishing paths
must yield INCONCLUSIVE. The conclusion is limited to the tested worlds/probes/deadline,
not a universal impossibility claim. The standard API already has operation status;
the recommendation concerns terminal evidence availability within the task deadline.
