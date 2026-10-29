Aborted launch, 2026-10-29T11:42:12Z. The declaration script failed (its check that the amendment text matches the
design note did not strip the note's markdown emphasis around "inert"), so DECLARATION.json and pilot_cap were never
written; the launch command did not stop on that failure, and launch.sh started. Its preflight exited at once with
ConfigurationError FAULTLAB_MONTHLY_DOLLAR_CAP (the empty cap is refused before any provider call), and the launcher
stopped with "STOP preflight failed". No provider call, no ledger row (October still 4,067 rows, $25.6121 committed).
Fixes before the real launch: the text check strips emphasis; launch.sh refuses to start without a declaration whose
sha256 matches and a numeric pilot cap; the launch is chained on the declaration's success.
