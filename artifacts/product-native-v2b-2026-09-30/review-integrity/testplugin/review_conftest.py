"""Loads backend/tests/conftest.py (the suite's own .env audit hook, socket guard and fixtures) as a plugin, so the
reviewer's probe files outside backend/tests run under exactly the same guards."""
import importlib.util
from pathlib import Path
_PATH = Path(__file__).resolve().parents[4] / 'backend' / 'tests' / 'conftest.py'
_spec = importlib.util.spec_from_file_location('faultlab_backend_tests_conftest', _PATH)
_mod = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(_mod)
globals().update({k: v for k, v in vars(_mod).items() if not k.startswith('__')})
