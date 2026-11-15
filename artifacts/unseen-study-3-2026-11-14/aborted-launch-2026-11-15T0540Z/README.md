# Second launch of unseen-case test 3: stopped by a false billing alarm (2026-11-15T05:40Z)

With the owner's new API key the preflight passed (dev-5, COMPLETED, $0.0021), but the launcher's billing guard,
`grep -i -E "402|insufficient credit|billing"`, matched the random trial id `trial-c064e4402417...` in preflight.log, so the
study was not started and no case trial ran. The guard now matches 402 only as a separate number and also matches
"credit balance"; the launcher as it ran is kept here. Earlier launchers had the same latent flaw; it never tripped.
