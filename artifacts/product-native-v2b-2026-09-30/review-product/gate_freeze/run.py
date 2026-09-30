"""Reviewer: run gate_freeze.py's own code (the copy taken from backup/part2-2026-09-22 with git show) on the working tree,
with audit/promotion.json and audit/final-audit.json dropped from FILES so they are never read. checks.py is hashed and
AST-parsed by gate_freeze itself; nothing of it is printed except its hashes."""
import importlib.util, sys
from pathlib import Path
here = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('gate_freeze', here / 'gate_freeze.from-backup.py')
gf = importlib.util.module_from_spec(spec); spec.loader.exec_module(gf)
gf.FILES = [f for f in gf.FILES if f not in ('audit/promotion.json', 'audit/final-audit.json')]
sys.argv = ['gate_freeze.py', '--root', sys.argv[1]]
gf.main()
