"""Standard-library child for a trusted local callback.

The audit hook prevents common accidental access. It is NOT a security sandbox:
hostile Python/native code must be run under a separate OS isolation boundary.
This module is launched by filename under Python -I -S, never imported by agents.
"""
from __future__ import annotations

import contextlib
from hashlib import sha256
import json
import os
from pathlib import Path
import sys
import sysconfig

PROTOCOL = "faultlab-local-action/v1"
MAX_REQUEST_BYTES = 262_144
MAX_RESPONSE_BYTES = 65_536


def strict_json(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("Duplicate JSON field")
            result[key] = value
        return result
    def invalid(_):
        raise ValueError("Invalid JSON number")
    return json.loads(raw, object_pairs_hook=pairs, parse_constant=invalid)


def install_accident_guards(source: Path, working: Path):
    stdlib = Path(sysconfig.get_path("stdlib")).resolve()
    dynamic = Path(sysconfig.get_config_var("DESTSHARED") or stdlib / "lib-dynload").resolve()
    read_roots = (stdlib, dynamic, working)

    def allowed_path(value, *, writing=False):
        if isinstance(value, int):
            return value in (0, 1, 2)
        path = Path(os.fsdecode(value)).resolve()
        if any(part == ".env" or part.startswith(".env.") for part in path.parts):
            return False
        if any(part in ("site-packages", "dist-packages") for part in path.parts):
            return False
        if writing:
            return path.is_relative_to(working)
        return path == source or any(path.is_relative_to(root) for root in read_roots)

    def require_path(value, *, writing=False):
        if not allowed_path(value, writing=writing):
            raise PermissionError("Local agent accident guard refused filesystem access")

    def guard(event, args):
        if (event.startswith(("socket.", "subprocess.", "ctypes."))
                or event in {"os.system", "os.fork", "os.forkpty", "os.posix_spawn", "os.exec",
                             "os.spawn", "os.kill", "os.killpg", "os.chroot", "os.setuid", "os.setgid"}):
            raise PermissionError("Local agent accident guard refused process or network access")
        if event == "open":
            name, mode, flags = args
            writing = (any(char in (mode or "") for char in "wax+")
                       or bool(flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND)))
            require_path(name, writing=writing)
        elif event in {"os.listdir", "os.scandir"}:
            require_path(args[0] if args[0] is not None else working)
        elif event in {"os.remove", "os.rmdir", "os.mkdir", "os.chmod", "os.chown", "os.truncate", "os.utime"}:
            require_path(args[0], writing=True)
        elif event in {"os.rename", "os.link"}:
            require_path(args[0], writing=True)
            require_path(args[1], writing=True)
        elif event in {"os.symlink", "os.chdir", "os.fchdir"}:
            raise PermissionError("Local agent accident guard refused filesystem alias change")
    sys.addaudithook(guard)


def main():
    if len(sys.argv) != 3:
        return 64
    source = Path(sys.argv[1]).resolve()
    raw = source.read_bytes()
    if len(raw) > 262_144 or sha256(raw).hexdigest() != sys.argv[2]:
        return 65
    working = Path.cwd().resolve()
    # Source is loaded only after guards are active. Agent print() uses stderr;
    # stdout belongs solely to protocol frames.
    sys.dont_write_bytecode = True
    install_accident_guards(source, working)
    # Exceptions during interpreter shutdown otherwise need not change exit status.
    # A report is provisional until the parent observes this clean shutdown.
    def unraisable(_):
        os._exit(71)
    sys.unraisablehook = unraisable
    namespace = {"__name__": "faultlab_user_agent", "__file__": str(source)}
    output = sys.stdout.buffer
    with contextlib.redirect_stdout(sys.stderr):
        exec(compile(raw, str(source), "exec"), namespace)
    callback = namespace.get("decide")
    if not callable(callback):
        return 66
    while True:
        raw_line = sys.stdin.buffer.readline(MAX_REQUEST_BYTES + 1)
        if not raw_line:
            return 0
        if len(raw_line) > MAX_REQUEST_BYTES or not raw_line.endswith(b"\n"):
            return 67
        request = strict_json(raw_line.decode("utf-8", errors="strict"))
        if (not isinstance(request, dict)
                or set(request) != {"protocol", "request_id", "messages", "response_contract"}
                or request["protocol"] != PROTOCOL or not isinstance(request["request_id"], str)):
            return 68
        request_id = request["request_id"]
        with contextlib.redirect_stdout(sys.stderr):
            action = callback(request)
        response = {"protocol": PROTOCOL, "request_id": request_id, "action": action}
        encoded = json.dumps(response, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode("utf-8") + b"\n"
        if len(encoded) > MAX_RESPONSE_BYTES:
            return 69
        output.write(encoded)
        output.flush()


if __name__ == "__main__":
    try:
        code = main()
    except BaseException:
        # Never expose source text, exception messages, paths, or tracebacks.
        code = 70
    raise SystemExit(code)
