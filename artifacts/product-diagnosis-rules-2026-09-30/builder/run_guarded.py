"""Run a script under the fixer guard ($0): refuses the real .env and every non-loopback connection; prints the counts.

Run from faultlab/backend:  ../.venv/bin/python -B ../artifacts/product-diagnosis-rules-2026-09-30/builder/run_guarded.py SCRIPT [ARGS...]
"""
import runpy
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import guard  # noqa: E402,F401

script, *rest = sys.argv[1:]
sys.argv = [script, *rest]
try:
    runpy.run_path(script, run_name='__main__')
except SystemExit as exit:
    print(f'[run_guarded] exit status {exit.code}', file=sys.stderr)
    raise
