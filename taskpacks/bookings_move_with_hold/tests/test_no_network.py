"""The conftest's network guard is active: a socket connect is refused before it happens."""
import socket

import pytest

import conftest


def test_a_socket_connect_is_refused_and_recorded():
    before = len(conftest.SOCKET_ATTEMPTS)
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        with pytest.raises(PermissionError, match='no sockets'):
            sock.connect(('127.0.0.1', 9))
    finally:
        sock.close()
    assert len(conftest.SOCKET_ATTEMPTS) == before + 1
    # This deliberate probe removes its own record; any other attempt fails the run.
    conftest.SOCKET_ATTEMPTS.pop()
