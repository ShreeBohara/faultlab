"""Run the builder's identity snapshot (copied here) under the backend tests' .env audit hook and a socket guard."""
import os, runpy, socket, sys
from pathlib import Path
REAL_ENV = str(Path(__file__).resolve().parents[3] / '.env')
def refuse(event, args):
    if event == 'open' and args and isinstance(args[0], (str, bytes, os.PathLike)):
        try: path = os.fsdecode(os.fspath(args[0]))
        except TypeError: return
        if os.path.basename(path) == '.env' and os.path.abspath(path) == REAL_ENV:
            raise PermissionError('refused .env')
    if event == 'socket.connect':
        raise PermissionError(f'refused socket connect {args[1:]!r}')
    if event == 'socket.getaddrinfo':
        raise PermissionError(f'refused getaddrinfo {args!r}')
sys.addaudithook(refuse)
os.environ['PYTHON_DOTENV_DISABLED'] = '1'
runpy.run_path(str(Path(__file__).with_name('identity_snapshot_copy.py')), run_name='__main__')
