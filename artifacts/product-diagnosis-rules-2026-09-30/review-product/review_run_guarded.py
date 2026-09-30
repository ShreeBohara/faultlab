"""Run a script under the product-review guard ($0): refuses the real .env, every non-loopback connection and every
non-local DNS lookup; prints the counts at exit. Run from faultlab/backend:
  ../.venv/bin/python -B ../artifacts/product-diagnosis-rules-2026-09-30/review-product/review_run_guarded.py SCRIPT [ARGS...]
"""
import runpy
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import review_guard  # noqa: E402,F401

script, *rest = sys.argv[1:]
sys.argv = [script, *rest]
try:
    runpy.run_path(script, run_name='__main__')
except SystemExit as exit:
    print(f'[review_run_guarded] exit status {exit.code}', file=sys.stderr)
    raise
