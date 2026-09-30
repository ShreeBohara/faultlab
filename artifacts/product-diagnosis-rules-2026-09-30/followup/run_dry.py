"""Follow-up stage: run scripts/experiments/diagnosis_probe.py in its default dry-run mode under the follow-up guard
(fguard: refuses and counts every non-loopback connect or lookup, every .env open and every protected open) and count
socket connect attempts of any kind. $0. Run from faultlab/backend; arguments are passed through to the harness."""
import os, runpy, socket, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fguard  # noqa: F401,E402
CONNECTS = []
_orig = socket.socket.connect
def _count(sock, address):
    CONNECTS.append(repr(address)); return _orig(sock, address)
socket.socket.connect = _count
script = '/Users/shree/Desktop/Coreweave_AGI_Hackthon/faultlab/scripts/experiments/diagnosis_probe.py'
sys.argv = [script] + sys.argv[1:]
code = 0
try:
    runpy.run_path(script, run_name='__main__')
except SystemExit as e:
    code = e.code
print(f'[run_dry] exit status {code}; socket connect attempts of any kind: {len(CONNECTS)}', file=sys.stderr)
sys.exit(code)
