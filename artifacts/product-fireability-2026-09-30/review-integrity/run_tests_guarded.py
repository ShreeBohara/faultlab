"""Integrity review: run the given backend tests under the network guard ($0). Run from faultlab/backend:
  ../.venv/bin/python -B ../artifacts/product-fireability-2026-09-30/review-integrity/run_tests_guarded.py TESTS...
The guard refuses every non-loopback connection and the real .env (via tests/conftest.py); it prints its counts at exit.
-p no:cacheprovider keeps pytest from writing .pytest_cache into the working tree."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import guard  # noqa: E402,F401
import pytest  # noqa: E402
code = pytest.main(['-q', '-p', 'no:cacheprovider', '-W', 'ignore::DeprecationWarning', *sys.argv[1:]])
import guard as g  # noqa: E402
print(f'[review] pytest exit {code}; refused outbound {len(g.REFUSED)}', file=sys.stderr)
sys.exit(code)
