"""Local service ports: one environment setting per service, shared by every launcher and the CLI.

FAULTLAB_SIMULATOR_PORT (default 8001), FAULTLAB_BACKEND_PORT (default 8000) and
FAULTLAB_DASHBOARD_PORT (default 5173). Unset or empty means the default, so an unconfigured
machine behaves exactly as before. scripts/lib/ports.sh and frontend/local-ports.ts apply the
same rule. Importing this module performs no I/O.
"""
import os
import re

DEFAULT_PORTS = {
    'FAULTLAB_SIMULATOR_PORT': 8001,
    'FAULTLAB_BACKEND_PORT': 8000,
    'FAULTLAB_DASHBOARD_PORT': 5173,
}
_PORT = re.compile(r'[1-9][0-9]{0,4}')


class PortSettingError(ValueError):
    """A port setting that is not a whole number from 1 to 65535."""


def configured_port(name, environ=None):
    """Return the port named by ``name`` from the environment, or its documented default."""
    if name not in DEFAULT_PORTS:
        raise KeyError(name)
    value = (os.environ if environ is None else environ).get(name, '')
    if value == '':
        return DEFAULT_PORTS[name]
    if not _PORT.fullmatch(value) or int(value) > 65535:
        raise PortSettingError(f'{name} must be a whole port number from 1 to 65535 (got {value!r}).')
    return int(value)


def local_url(name, environ=None):
    """The loopback URL of one local service, for example http://127.0.0.1:8000."""
    return f'http://127.0.0.1:{configured_port(name, environ)}'
