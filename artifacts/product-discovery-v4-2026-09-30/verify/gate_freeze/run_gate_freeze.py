"""Independent verifier (discovery v4 review round; copied unchanged from the native v2b verifier): run scripts/experiments/gate_freeze.py's own code (loaded from the CHECKPOINT copy of the
script, so a changed working copy cannot influence it) on the given root. audit/promotion.json and
audit/final-audit.json are dropped from FILES, so this run never reads them (git compares them instead).
checks.py is hashed and AST-parsed by gate_freeze itself; its content is never displayed."""
import importlib.util, sys
script, root = sys.argv[1], sys.argv[2]
spec = importlib.util.spec_from_file_location('gate_freeze', script)
gf = importlib.util.module_from_spec(spec); spec.loader.exec_module(gf)
gf.FILES = [f for f in gf.FILES if f not in ('audit/promotion.json', 'audit/final-audit.json')]
sys.argv = ['gate_freeze.py', '--root', root]
gf.main()
