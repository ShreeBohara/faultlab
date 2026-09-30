Verifier guards reused unchanged from artifacts/product-native-v2-2026-09-29/verify/guard/ (copied 2026-09-30 by the
v2b verifier): sitecustomize.py (Python audit hook: refuses non-loopback connects/lookups and any read of the real .env
that the backend conftest does not already refuse; counts opens of protected paths), node-guard.cjs (Node require hook:
refuses non-loopback connects/lookups), sampler.sh (lsof sampler over the test.sh process tree), summarize.py.
