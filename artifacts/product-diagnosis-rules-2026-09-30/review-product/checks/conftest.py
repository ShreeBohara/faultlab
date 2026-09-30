"""Product-review harness ($0): loads the backend test suite's own conftest (the .env audit hook, the socket guard and
the scratch simulator import) so these review checks are exactly as network-silent as the product's offline tests.

Run from faultlab/backend:
  ../.venv/bin/python -B -m pytest -p no:cacheprovider -c ../artifacts/product-diagnosis-rules-2026-09-30/review-product/checks/pytest.ini \
      ../artifacts/product-diagnosis-rules-2026-09-30/review-product/checks
"""
import importlib.util
import sys
from pathlib import Path

sys.dont_write_bytecode = True
BACKEND = Path(__file__).resolve().parents[4] / 'backend'
for sub in ('tests/experiments', 'tests/integration', 'tests/lab', 'tests', ''):
    path = str(BACKEND / sub) if sub else str(BACKEND)
    if path not in sys.path:
        sys.path.insert(0, path)

_spec = importlib.util.spec_from_file_location('faultlab_backend_conftest', BACKEND / 'tests' / 'conftest.py')
_backend_conftest = importlib.util.module_from_spec(_spec)
sys.modules['faultlab_backend_conftest'] = _backend_conftest
_spec.loader.exec_module(_backend_conftest)

prohibit_network = _backend_conftest.prohibit_network   # autouse: the same guard every backend test gets
