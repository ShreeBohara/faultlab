"""Runtime/algorithm and component identities with the product's own functions, under the fixer guard ($0, no .env).

Run from faultlab/backend:  ../.venv/bin/python ../artifacts/product-discovery-v4-2026-09-30/fixer/identity.py > out.json
Executes the builder's identity_snapshot.py unchanged, after installing ../fixer/guard.py.
"""
import runpy
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import guard  # noqa: E402,F401

runpy.run_path(str(HERE.parent / 'builder' / 'identity_snapshot.py'), run_name='__main__')
