"""Independent verifier (native v2b, 2026-09-30; copied from the native v2 verifier with only the guard path changed), step 5: which files inside the repository do the new tests open?
Loads the verifier network/.env guard (../../guard/sitecustomize.py, unchanged) and adds a second audit hook that
records every path under the repository opened (open / io.open_code) or listed (os.listdir / os.scandir) by this
process. Paths are only recorded, never read by this hook. One JSON line per process at exit."""
import atexit, json, os, sys
_G = '/Users/shree/Desktop/Coreweave_AGI_Hackthon/faultlab/artifacts/product-native-v2b-2026-09-30/verify/guard/sitecustomize.py'
exec(compile(open(_G).read(), _G, 'exec'))
_R = '/Users/shree/Desktop/Coreweave_AGI_Hackthon/faultlab/'
_OUT = os.environ.get('VERIFY_OPENS_LOG')
_seen = {}
_in = False
def _opens(event, args):
    global _in
    if _in or event not in ('open', 'os.listdir', 'os.scandir'):
        return
    p = args[0] if args else None
    if p is None or isinstance(p, int):
        return
    _in = True
    try:
        try:
            rp = os.path.realpath(os.fsdecode(p))
        except Exception:
            return
        if rp.startswith(_R):
            key = ('L ' if event != 'open' else '') + rp[len(_R):]
            _seen[key] = _seen.get(key, 0) + 1
    finally:
        _in = False
sys.addaudithook(_opens)
def _dump():
    if _OUT:
        with open(_OUT, 'a') as fh:
            fh.write(json.dumps({'pid': os.getpid(), 'argv': ' '.join(sys.argv[:4])[:300], 'paths': sorted(_seen)}) + '\n')
atexit.register(_dump)
