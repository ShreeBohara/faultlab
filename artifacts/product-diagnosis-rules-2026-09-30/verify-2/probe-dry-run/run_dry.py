"""Verifier-2 (copied from verify/probe-dry-run/run_dry.py): run scripts/experiments/diagnosis_probe.py in its default dry-run mode under the verifier guard (vguard:
refuses and counts every non-loopback connect / lookup and every .env / protected open). $0. Arguments are passed through."""
import os, runpy, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import vguard  # noqa: F401
import socket
CONNECTS = []
_orig = socket.socket.connect
def _count(sock, address):
    CONNECTS.append(repr(address)); return _orig(sock, address)
socket.socket.connect = _count
script = '/Users/shree/Desktop/Coreweave_AGI_Hackthon/faultlab/scripts/experiments/diagnosis_probe.py'
sys.argv = [script] + sys.argv[1:]
try:
    runpy.run_path(script, run_name='__main__')
except SystemExit as e:
    print(f'[run_dry] exit status {e.code}; socket connect attempts of any kind: {len(CONNECTS)}', file=sys.stderr)
    raise
