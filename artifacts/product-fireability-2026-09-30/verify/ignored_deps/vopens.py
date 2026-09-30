"""Verifier-only pytest plugin: record every file path opened (read or write) during the run, once each, to
$VOPENS_OUT at exit. Load after vguard (so a protected open is refused before it is recorded as read)."""
import atexit, os, sys
SEEN = set()


def _hook(event, args):
    if event == 'open' and args and isinstance(args[0], (str, bytes, os.PathLike)):
        try:
            SEEN.add(os.path.realpath(os.fsdecode(args[0])))
        except Exception:
            pass


sys.addaudithook(_hook)


def _dump():
    out = os.environ.get('VOPENS_OUT')
    if out:
        with open(out, 'w') as f:
            f.write('\n'.join(sorted(SEEN)) + '\n')


atexit.register(_dump)
