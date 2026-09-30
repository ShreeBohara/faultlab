"""Reviewer diagnostic: log the Python stack for every open whose path contains 'heldout2' (no content is read by this hook)."""
import sys, os, traceback
LOG = os.environ['TRACE_LOG']
def hook(event, args):
    if event == 'open' and args and not isinstance(args[0], int):
        try: p = os.fsdecode(args[0])
        except Exception: return
        if 'heldout2' in p:
            with open(LOG, 'a') as fh:
                fh.write('OPEN ' + repr(p) + ' mode=' + repr(args[1:]) + '\n' + ''.join(traceback.format_stack(limit=25)) + '\n----\n')
sys.addaudithook(hook)
import pytest
sys.exit(pytest.main(sys.argv[1:]))
