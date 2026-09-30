"""Run a script under an audit hook that refuses any open of a file named .env and any socket/DNS use."""
import os, sys, runpy
def guard(event, args):
    if event == 'open' and isinstance(args[0], (str, bytes, os.PathLike)) and os.path.basename(os.fsdecode(args[0])) == '.env':
        raise PermissionError('reviewer guard: .env must not be read')
    if event in ('socket.connect', 'socket.getaddrinfo'):
        raise PermissionError('reviewer guard: network')
sys.addaudithook(guard)
os.environ['PYTHON_DOTENV_DISABLED'] = '1'
script = sys.argv[1]; sys.argv = sys.argv[1:]
runpy.run_path(script, run_name='__main__')
