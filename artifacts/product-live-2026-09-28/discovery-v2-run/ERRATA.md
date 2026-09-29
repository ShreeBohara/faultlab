# Errata for DECLARATION.json (sha256 2471aa8a…), written 2026-09-29 after the run

The declaration file is never edited after the run starts, so these corrections are recorded here. Neither
changes any result.

1. **Shell expansion damaged a figure.** The `stop_rules` text was written through an unquoted shell here-doc,
   which expanded `$3`, so ">$3.48" reads ">.48" in the file.
   - The intended rule was the one in PLAN.md section 7: a conservative charge above **$3.48** before
     REPRODUCING.
   - The watcher that ran (`monitor.py`) used the correct threshold of 3.48.
   - The run ended at $1.03, so the damaged text had no effect.
2. **Two watcher bugs, both harmless in this run.** An independent review found them in `monitor.py`:
   - It would have marked discovery as over at the first poll of any state other than IDLE or RUNNING
     (for example a transient SELECTING state), which would switch off the discovery accounting guard early.
   - It listed REJECTED among the final states, but a rejected candidate does not end a campaign.

   This campaign went straight from RUNNING to ERROR, so neither bug had any effect. Watchers for later runs
   use the correct final states: NO_CHANGE, COMPLETED, ERROR and STOPPED.
