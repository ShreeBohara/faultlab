# Unseen-case test 3: not started (2026-11-14)

Declared (DECLARATION.json, sha256 a3519230...bfb3) and drawn from commit 2072240, leaving out runs 1 and 2. The launcher's
preflight trial failed at 05:31:24Z with ADAPTER_ERROR:RuntimeProviderError, so the study was not started and no case trial
ran. A second preflight (preflight-retry.*) failed the same way. One diagnostic call through RuntimeProvider showed the
cause: HTTP 401, AuthenticationError. The Anthropic API rejects the key configured in `.env`, which worked on 2026-11-09.
The API host was reachable (401 to an unauthenticated request).

No money was billed: each call was refused before any tokens. The spend ledger booked the three reservations
conservatively ($0.0126). The sealed case file is unused. Once the owner replaces the key, the study can run on this draw
under a new declaration that records this incident.
