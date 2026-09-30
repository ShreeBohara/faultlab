"""Integrity reviewer (v2b): run scripts/experiments/gate_freeze.py's own code, loaded from the CHECKPOINT copy
(git archive of backup/part2-2026-09-22 = 2c178a7), on the given root. audit/promotion.json and audit/final-audit.json
are dropped from FILES so they are never read. checks.py is hashed/AST-parsed by gate_freeze itself; never displayed."""
import importlib.util, sys
script, root = sys.argv[1], sys.argv[2]
spec = importlib.util.spec_from_file_location('gate_freeze', script)
gf = importlib.util.module_from_spec(spec); spec.loader.exec_module(gf)
gf.FILES = [f for f in gf.FILES if f not in ('audit/promotion.json', 'audit/final-audit.json')]
sys.argv = ['gate_freeze.py', '--root', root]
gf.main()
