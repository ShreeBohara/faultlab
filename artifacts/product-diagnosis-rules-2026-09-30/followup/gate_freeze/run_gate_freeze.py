"""Follow-up stage (copied from verify/gate_freeze/run_gate_freeze.py; only the guard import differs). Run the repo's scripts/experiments/gate_freeze.py (loaded from the backup CHECKPOINT copy, byte-identical to the
working copy) on one root. audit/promotion.json and audit/final-audit.json are dropped from FILES, so this run never
opens them (the verifier guard would refuse). checks.py is hashed and AST-parsed by gate_freeze itself; never printed.
Usage: python -B run_gate_freeze.py <gate_freeze.py> <root> > out.json"""
import importlib.util, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # followup/
import fguard  # noqa: F401
script, root = sys.argv[1], sys.argv[2]
spec = importlib.util.spec_from_file_location('gate_freeze', script)
gf = importlib.util.module_from_spec(spec); spec.loader.exec_module(gf)
gf.FILES = [f for f in gf.FILES if f not in ('audit/promotion.json', 'audit/final-audit.json')]
sys.argv = ['gate_freeze.py', '--root', root]
gf.main()
